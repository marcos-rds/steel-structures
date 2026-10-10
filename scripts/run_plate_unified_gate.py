"""Run modest native gates in isolated FreeCAD profiles; stop at first failure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--version", choices=("1.1.4", "1.1.3"), default="1.1.4")
parser.add_argument("--stage", choices=("tracker", "integrated", "geometry", "regression",
                                        "qt_native", "qt_sample"), default="tracker")
parser.add_argument("--processes", type=int, default=2)
parser.add_argument("--cycles", type=int, default=8)
args = parser.parse_args()
assert 1 <= args.processes <= 5 and 1 <= args.cycles <= 20
install = Path("C:/Users/marco/Desktop/FREECAD/FreeCAD_" + args.version + "-Windows-x86_64-py311")
exe = install / "bin/freecad.exe"
batch = ROOT / "test-results/plate_unified_gate" / (str(time.time_ns()) + "_" + args.version + "_" + args.stage)
batch.mkdir(parents=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


preserved = {str(path): sha(path) for path in (
    install / "Mod/Draft/draftguitools/gui_trackers.py",
    install / "bin/Lib/site-packages/pivy/coin.py")}
sources = {str(path.relative_to(ROOT)): sha(path)
           for path in (ROOT / "freecad/SteelStructures").rglob("*.py")}
(batch / "manifest.json").write_text(json.dumps(dict(
    version=args.version, stage=args.stage, cycles=args.cycles, processes=args.processes,
    sources=sources, preserved=preserved,
    harness_sha256=sha(ROOT / "tests/manual_plate_unified_native.py")), indent=2))
profile = ET.parse("C:/Users/marco/AppData/Roaming/FreeCAD/v1-1/user.cfg")
general = profile.getroot().find("./FCParamGroup/FCParamGroup[@Name='BaseApp']/"
                                "FCParamGroup[@Name='Preferences']/FCParamGroup[@Name='General']")
for name, value in (("AutoloadModule", "StartWorkbench"), ("BackgroundAutoloadModules", ""),
                    ("LastModule", "StartWorkbench")):
    element = general.find("FCText[@Name='" + name + "']")
    if element is None:
        element = ET.SubElement(general, "FCText", Name=name)
    element.text = value
dump_dir = Path(os.environ["LOCALAPPDATA"]) / "CrashDumps"


def dumps():
    return {str(path): (path.stat().st_size, path.stat().st_mtime_ns)
            for path in dump_dir.glob("*freecad*.dmp")}


results = []
for index in range(args.processes):
    run = batch / str(index + 1)
    home = run / "home"
    (home / "Mod").mkdir(parents=True)
    profile.write(home / "user.cfg", encoding="UTF-8", xml_declaration=True)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(FREECAD_USER_HOME=str(home), FREECAD_USER_DATA=str(home),
               PLATE_UNIFIED_RUN=str(run), PLATE_UNIFIED_ROOT=str(ROOT),
               PLATE_UNIFIED_STAGE=args.stage, PLATE_UNIFIED_CYCLES=str(args.cycles))
    command = [str(exe), "--write-log", "--log-file", str(run / "FreeCAD.log"),
               str(ROOT / "tests/manual_plate_unified_native.py")]
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    before = dumps()
    with (run / "stdout.txt").open("w") as stdout, (run / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(command, cwd=run, env=env, startupinfo=startup,
                                   stdout=stdout, stderr=stderr)
        record = dict(pid=process.pid, command=command, run=str(run), started=time.time(),
                      profile_sha256=sha(home / "user.cfg"))
        (run / "launch.json").write_text(json.dumps(record, indent=2))
        try:
            record["exit_code"] = process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            record["timeout"] = True
            process.terminate()
            record["exit_code"] = process.wait(timeout=10)
        record["finished"] = time.time()
    result = run / "result.json"
    record["probe"] = json.loads(result.read_text()) if result.exists() else None
    record["new_dumps"] = {key: value for key, value in dumps().items() if before.get(key) != value}
    record["install_preserved"] = all(sha(Path(path)) == value for path, value in preserved.items())
    record["ok"] = bool(record["exit_code"] == 0 and record["probe"]
                        and record["probe"]["ok"] and record["install_preserved"]
                        and not record["new_dumps"] and not record.get("timeout"))
    results.append(record)
    (batch / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(record), flush=True)
    if not record["ok"]:
        raise SystemExit("STOP: native/probe failure; inspect logs before continuing")

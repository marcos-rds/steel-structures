# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run the bilateral miter MVP native gate in an isolated FreeCAD 1.1.4 GUI."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", choices=("Classic", "FreeCAD Dark", "OpenDark"), default="Classic")
    parser.add_argument("--output-root", type=Path, default=root / "test-results/miter",
                        help="Keep this path short for Windows native file APIs")
    parser.add_argument("--install", type=Path, default=Path(
        "C:/Users/marco/Desktop/FREECAD/FreeCAD_1.1.4-Windows-x86_64-py311"))
    parser.add_argument("--opendark", type=Path, default=Path.home() /
                        "AppData/Roaming/FreeCAD/v1-1/Mod/OpenTheme/OpenDark")
    parser.add_argument("--timeout", type=int, default=300,
                        help="Process watchdog only; never a criterion for preview correctness")
    args = parser.parse_args()
    executable = args.install / "bin/freecad.exe"
    if not executable.is_file():
        parser.error("FreeCAD executable unavailable; supply --install")
    folder = args.output_root.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix=str(time.time_ns()) + "_" + args.theme.replace(" ", "_") + "_", dir=folder))
    home = out / "home"
    (home / "Mod").mkdir(parents=True)
    (home / "temp").mkdir()
    config = ET.ElementTree(ET.fromstring('''<FCParameters><FCParamGroup Name="Root"><FCParamGroup Name="BaseApp"><FCParamGroup Name="Preferences"><FCParamGroup Name="General"><FCText Name="AutoloadModule">PartWorkbench</FCText><FCText Name="LastModule">PartWorkbench</FCText></FCParamGroup><FCParamGroup Name="DockWindows"><FCBool Name="ActivateOverlay" Value="0"/></FCParamGroup></FCParamGroup></FCParamGroup></FCParamGroup></FCParameters>'''))
    pack_name = "FreeCAD Classic" if args.theme == "Classic" else args.theme
    pack_path = (args.opendark / "OpenDark.cfg" if args.theme == "OpenDark" else
                 args.install / "data/Gui/PreferencePacks" / pack_name / (pack_name + ".cfg"))
    if not pack_path.is_file():
        parser.error("Preference pack unavailable: " + str(pack_path))
    prefs = config.getroot().find(".//FCParamGroup[@Name='Preferences']")
    for group in ET.parse(pack_path).getroot().find(".//FCParamGroup[@Name='Preferences']"):
        if group.get("Name") == "General":
            continue
        old = prefs.find("FCParamGroup[@Name='" + group.get("Name") + "']")
        if old is not None:
            prefs.remove(old)
        prefs.append(deepcopy(group))
    config.write(home / "user.cfg", encoding="utf-8", xml_declaration=True)
    probe = root / "tests/manual_member_miter_joint.py"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(FREECAD_USER_HOME=str(home), FREECAD_USER_DATA=str(home),
               SS_MITER_ROOT=str(root), SS_MITER_OUT=str(out), SS_MITER_THEME=args.theme)
    if args.theme == "OpenDark":
        qss = args.opendark / "OpenDark.qss"
        if not qss.is_file():
            parser.error("OpenDark QSS unavailable: " + str(qss))
        env["SS_MITER_QSS"] = str(qss)
    command = [str(executable), "--write-log", "--log-file", str(out / "FreeCAD.log"), str(probe)]
    sources = [probe, Path(__file__), *sorted((root / "freecad/SteelStructures").rglob("*.py"))]
    (out / "manifest.json").write_text(json.dumps(dict(command=command, root=str(root),
        theme=args.theme, preference_pack=str(pack_path),
        sources={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}), indent=2), encoding="utf-8")
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    timed_out = False
    with (out / "stdout.txt").open("w") as stdout, (out / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(command, cwd=out, env=env, startupinfo=startup, stdout=stdout, stderr=stderr)
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            code = process.wait(timeout=10)
    path = out / "result.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else dict(ok=False, error="No result")
    pattern = (r"Traceback|Internal C\+\+ object.*already deleted|Access violation|Fatal Python|"
               r"Unhandled Base::Exception|0xC0000005|0xC0000374|heap corruption|ASSERT failure|QThread: Destroyed")
    result["native_log_errors"] = {name: [line for line in (out / name).read_text(errors="replace").splitlines()
        if re.search(pattern, line, re.I)] for name in ("stderr.txt", "FreeCAD.log") if (out / name).is_file()}
    result["exit_code"], result["timeout"] = code, timed_out
    if "checks" not in result and (out / "checks.json").is_file():
        result["checks"] = json.loads((out / "checks.json").read_text(encoding="utf-8"))
    result["ok"] = bool(result.get("ok") and code == 0 and not timed_out
                        and not any(result["native_log_errors"].values()))
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    summary = {key: value for key, value in result.items() if key != "checks"}
    summary["check_count"] = len(result.get("checks", ()))
    print(json.dumps(dict(output=str(out), result=summary), indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Launch an isolated, hidden FreeCAD 1.1.4 gate; preserve user sessions."""
import argparse
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--probe", choices=("alignment", "copy", "delete", "session", "apply", "lifecycle", "undo", "editor", "mass", "editor_actions"), default="alignment")
parser.add_argument("--baseline-lifecycle", action="store_true",
                    help="Reproduce lifecycle using panel/controller from committed 68dc4b4")
parser.add_argument("--editor-qss", type=Path,
                    help="Load a local theme stylesheet in the isolated editor gate only")
parser.add_argument("--editor-theme", choices=("Classic", "FreeCAD Dark"),
                    help="Start the isolated editor gate with a built-in FreeCAD theme")
args = parser.parse_args()
if args.editor_qss and args.probe not in ("editor","editor_actions"):
    parser.error("--editor-qss requires an editor probe")
if args.editor_theme and args.probe not in ("editor","editor_actions"):
    parser.error("--editor-theme requires an editor probe")
if args.baseline_lifecycle and args.probe != "lifecycle":
    parser.error("--baseline-lifecycle requires --probe lifecycle")
probe = {"alignment": "manual_freecad_truss_duopitch.py",
         "copy": "manual_truss_copy.py", "delete": "manual_freecad_truss_delete.py",
         "session": "manual_freecad_truss_session.py",
         "apply": "manual_freecad_truss_apply.py",
         "lifecycle": "manual_freecad_truss_lifecycle.py",
         "undo": "manual_freecad_truss_undo.py",
         "editor": "manual_freecad_truss_editor.py",
         "mass": "manual_freecad_truss_mass.py",
         "editor_actions": "manual_freecad_truss_editor_actions.py"}[args.probe]
output_root = root / "test-results/truss-duopitch"
output_root.mkdir(parents=True, exist_ok=True)
out = Path(tempfile.mkdtemp(prefix=str(time.time_ns()) + "_", dir=output_root))
home = out / "home"
(home / "Mod").mkdir(parents=True)
(home / "user.cfg").write_text('''<?xml version="1.0" encoding="UTF-8"?>
<FCParameters><FCParamGroup Name="Root"><FCParamGroup Name="BaseApp">
<FCParamGroup Name="Preferences"><FCParamGroup Name="General">
<FCText Name="AutoloadModule">PartWorkbench</FCText>
<FCText Name="LastModule">PartWorkbench</FCText>
</FCParamGroup></FCParamGroup></FCParamGroup></FCParamGroup></FCParameters>''', encoding="utf8")
install = Path("C:/Users/marco/Desktop/FREECAD/FreeCAD_1.1.4-Windows-x86_64-py311")
if args.editor_theme:
    config = ET.parse(home / "user.cfg")
    prefs = config.getroot().find(".//FCParamGroup[@Name='Preferences']")
    pack_name = "FreeCAD Classic" if args.editor_theme == "Classic" else args.editor_theme
    pack = ET.parse(install / "data/Gui/PreferencePacks" / pack_name / (pack_name + ".cfg"))
    for group_name in ("MainWindow", "Themes"):
        group = pack.getroot().find(".//FCParamGroup[@Name='Preferences']/FCParamGroup[@Name='" + group_name + "']")
        if group is not None:
            prefs.append(group)
    config.write(home / "user.cfg", encoding="utf8", xml_declaration=True)
env = os.environ.copy()
env.pop("PYTHONPATH", None)
env.update(FREECAD_USER_HOME=str(home), FREECAD_USER_DATA=str(home),
           SS_DUOPITCH_ROOT=str(root), SS_DUOPITCH_OUT=str(out),
           TRUSS_COPY_ROOT=str(root), TRUSS_COPY_RUN=str(out))
if args.editor_qss:
    env["SS_TRUSS_EDITOR_QSS"] = str(args.editor_qss.resolve(strict=True))
if args.baseline_lifecycle:
    baseline = out / "baseline"
    baseline.mkdir()
    for module in ("truss_controller", "truss_task_panel"):
        source = subprocess.check_output(["git", "show",
            "68dc4b4:freecad/SteelStructures/interactive/" + module + ".py"], cwd=root)
        (baseline / (module + ".py")).write_bytes(source)
    env["SS_TRUSS_LIFECYCLE_BASELINE"] = str(baseline)
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0
command = [str(install / "bin/freecad.exe"), "--write-log", "--log-file", str(out / "FreeCAD.log"),
           str(root / "tests" / probe)]
(out / "manifest.json").write_text(json.dumps(dict(command=command,
    theme=args.editor_theme, qss=str(args.editor_qss) if args.editor_qss else None, sources={
    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (root / "freecad/SteelStructures").rglob("*.py")}), indent=2))
with (out / "stdout.txt").open("w") as stdout, (out / "stderr.txt").open("w") as stderr:
    process = subprocess.Popen(command, cwd=out, env=env, startupinfo=startup, stdout=stdout, stderr=stderr)
    try:
        code = process.wait(timeout=300)
    except subprocess.TimeoutExpired:
        process.terminate()
        code = process.wait(timeout=10)
result = json.loads((out / "result.json").read_text()) if (out / "result.json").exists() else None
print(json.dumps(dict(output=str(out), exit_code=code, result=result), indent=2))
raise SystemExit(0 if code == 0 and result and result.get("ok") else 1)

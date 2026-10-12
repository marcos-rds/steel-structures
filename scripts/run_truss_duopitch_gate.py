"""Launch an isolated, hidden FreeCAD 1.1.4 gate; preserve user sessions."""
import argparse
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--probe", choices=("alignment", "copy", "delete"), default="alignment")
args = parser.parse_args()
probe = {"alignment": "manual_freecad_truss_duopitch.py",
         "copy": "manual_truss_copy.py", "delete": "manual_freecad_truss_delete.py"}[args.probe]
out = root / "test-results/truss-duopitch" / str(time.time_ns())
home = out / "home"
(home / "Mod").mkdir(parents=True)
(home / "user.cfg").write_text('''<?xml version="1.0" encoding="UTF-8"?>
<FCParameters><FCParamGroup Name="Root"><FCParamGroup Name="BaseApp">
<FCParamGroup Name="Preferences"><FCParamGroup Name="General">
<FCText Name="AutoloadModule">PartWorkbench</FCText>
<FCText Name="LastModule">PartWorkbench</FCText>
</FCParamGroup></FCParamGroup></FCParamGroup></FCParamGroup></FCParameters>''', encoding="utf8")
install = Path("C:/Users/marco/Desktop/FREECAD/FreeCAD_1.1.4-Windows-x86_64-py311")
env = os.environ.copy()
env.pop("PYTHONPATH", None)
env.update(FREECAD_USER_HOME=str(home), FREECAD_USER_DATA=str(home),
           SS_DUOPITCH_ROOT=str(root), SS_DUOPITCH_OUT=str(out),
           TRUSS_COPY_ROOT=str(root), TRUSS_COPY_RUN=str(out))
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0
command = [str(install / "bin/freecad.exe"), "--write-log", "--log-file", str(out / "FreeCAD.log"),
           str(root / "tests" / probe)]
(out / "manifest.json").write_text(json.dumps(dict(command=command, sources={
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

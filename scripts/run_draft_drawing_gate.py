"""Isolated FreeCAD 1.1.4 gate for the native Draft drawing toolbar."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import re
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--phase',choices=('interface','drawing','lifecycle'),default='drawing')
parser.add_argument('--baseline',action='store_true',help='Compare the same native sequence using init_gui from 27ca585')
parser.add_argument('--theme',choices=('Classic','FreeCAD Dark'),default='Classic')
parser.add_argument('--qss',type=Path)
parser.add_argument('--install',type=Path,default=Path.home()/'Desktop/FREECAD/FreeCAD_1.1.4-Windows-x86_64-py311')
parser.add_argument('--profile',type=Path,default=Path.home()/'AppData/Roaming/FreeCAD/v1-1/user.cfg')
args=parser.parse_args()
out_root=root/'test-results/draft_drawing'
out_root.mkdir(parents=True,exist_ok=True)
out=Path(tempfile.mkdtemp(prefix=args.phase+'_',dir=out_root))
home=out/'home'
(home/'Mod').mkdir(parents=True)
config=ET.fromstring('<FCParameters><FCParamGroup Name="Root"><FCParamGroup Name="BaseApp"><FCParamGroup Name="Preferences"><FCParamGroup Name="General"><FCText Name="AutoloadModule">PartWorkbench</FCText></FCParamGroup></FCParamGroup></FCParamGroup></FCParamGroup></FCParameters>')
if args.profile.is_file(): config=ET.parse(args.profile).getroot()
prefs=config.find('.//FCParamGroup[@Name="Preferences"]')
general=prefs.find('FCParamGroup[@Name="General"]')
for key,text in (('AutoloadModule','PartWorkbench'),('LastModule','PartWorkbench'),('BackgroundAutoloadModules','')):
    value=general.find('FCText[@Name="'+key+'"]')
    if value is None: value=ET.SubElement(general,'FCText',Name=key)
    value.text=text
# Keep the test Task View visible for programmatic numeric entry; FreeCAD's
# default overlay auto-hide deliberately makes hidden fields non-submittable.
dock=prefs.find('FCParamGroup[@Name="DockWindows"]')
if dock is None: dock=ET.SubElement(prefs,'FCParamGroup',Name='DockWindows')
overlay=dock.find('FCBool[@Name="ActivateOverlay"]')
if overlay is None: overlay=ET.SubElement(dock,'FCBool',Name='ActivateOverlay')
overlay.set('Value','0')
pack_name='FreeCAD Classic' if args.theme=='Classic' else args.theme
pack=ET.parse(args.install/'data/Gui/PreferencePacks'/pack_name/(pack_name+'.cfg'))
for group in ('MainWindow','Themes'):
    value=pack.getroot().find('.//FCParamGroup[@Name="Preferences"]/FCParamGroup[@Name="'+group+'"]')
    if value is not None:
        previous=prefs.find('FCParamGroup[@Name="'+group+'"]')
        if previous is not None: prefs.remove(previous)
        prefs.append(value)
ET.ElementTree(config).write(home/'user.cfg',encoding='utf8',xml_declaration=True)
env=os.environ.copy()
env.pop('PYTHONPATH',None)
env.update(FREECAD_USER_HOME=str(home),FREECAD_USER_DATA=str(home),SS_DRAW_ROOT=str(root),
           SS_DRAW_OUT=str(out),SS_DRAW_PHASE=args.phase)
if args.baseline:
    baseline=out/'baseline_init_gui.py'
    baseline.write_bytes(subprocess.check_output(['git','show','27ca585:freecad/SteelStructures/init_gui.py'],cwd=root))
    env['SS_DRAW_BASELINE']=str(baseline)
if args.qss: env['SS_DRAW_QSS']=str(args.qss.resolve(strict=True))
install_files=[args.install/'Mod/Draft'/p for p in ('DraftGui.py','DraftTools.py',
    'draftguitools/gui_lines.py','draftguitools/gui_rectangles.py','draftguitools/gui_snapper.py')]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def fatal_log_lines(text):
    return [line for line in text.splitlines() if re.search(
        r'Traceback|Internal C\+\+ object.*already deleted|Access violation|Fatal Python|Unhandled Base::Exception',line,re.I)]
preserved={str(path):sha(path) for path in install_files}
probe=root/'tests/manual_draft_drawing.py'
(out/'probe_snapshot.py').write_bytes(probe.read_bytes())
(out/'launcher_snapshot.py').write_bytes(Path(__file__).read_bytes())
(out/'manifest.json').write_text(json.dumps(dict(phase=args.phase,theme=args.theme,qss=str(args.qss),
    sources={str(p.relative_to(root)):sha(p) for p in (root/'freecad/SteelStructures').rglob('*.py')},
    baseline=args.baseline,executed_init_gui=str(baseline) if args.baseline else str(root/'freecad/SteelStructures/init_gui.py'),
    executed_init_gui_sha256=sha(baseline) if args.baseline else sha(root/'freecad/SteelStructures/init_gui.py'),
    probe_sha256=sha(probe),runner_sha256=sha(Path(__file__)),profile_sha256=sha(home/'user.cfg'),
    preserved=preserved),indent=2))
dump_root=Path(os.environ['LOCALAPPDATA'])/'CrashDumps'
def dumps(): return {str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in dump_root.glob('*freecad*.dmp')}
before=dumps()
startup=subprocess.STARTUPINFO()
startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow=0
with (out/'stdout.txt').open('w') as stdout,(out/'stderr.txt').open('w') as stderr:
    process=subprocess.Popen([str(args.install/'bin/freecad.exe'),'--write-log','--log-file',str(out/'FreeCAD.log'),
        str(root/'tests/manual_draft_drawing.py')],cwd=out,env=env,startupinfo=startup,stdout=stdout,stderr=stderr)
    try: code=process.wait(timeout=120)
    except subprocess.TimeoutExpired:
        process.terminate()
        code=process.wait(timeout=10)
result=json.loads((out/'result.json').read_text()) if (out/'result.json').exists() else None
new_dumps={p:v for p,v in dumps().items() if before.get(p)!=v}
unchanged=all(sha(Path(p))==value for p,value in preserved.items())
errors={name:fatal_log_lines((out/name).read_text(errors='replace')) for name in ('stdout.txt','stderr.txt','FreeCAD.log')}
record=dict(output=str(out),exit_code=code,result=result,new_dumps=new_dumps,install_preserved=unchanged,log_errors=errors)
(out/'execution.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record,indent=2))
raise SystemExit(0 if code==0 and result and result['ok'] and not new_dumps and unchanged and not any(errors.values()) else 1)

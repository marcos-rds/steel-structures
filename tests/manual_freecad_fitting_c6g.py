"""Focused real-FreeCAD probe for C6-G assembly-to-assembly fitting."""

import os
import sys
import traceback
import types

ROOT = os.getcwd()
OUTPUT = os.path.join(ROOT, "test-results", "fitting-c6g")
os.makedirs(OUTPUT, exist_ok=True)
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests")]
local_tests = types.ModuleType("tests")
local_tests.__path__ = [os.path.join(ROOT, "tests")]
sys.modules["tests"] = local_tests
for module_name in tuple(sys.modules):
    if module_name == "freecad" or module_name.startswith("freecad.SteelStructures"):
        sys.modules.pop(module_name, None)

import FreeCAD as App
import FreeCADGui as Gui
from freecad.SteelStructures import truss
from freecad.SteelStructures.trusses.realization import build_candidate
from test_fitting_c6g_assembly import _candidate

try:
    doc = App.newDocument("FittingC6G")
    value, _pure = _candidate("DoubleAngle", "DoubleAngle", chord_uses_angle=True)
    owner = truss.apply_truss(doc, value)
    doc.recompute()
    candidate = build_candidate(value)
    members = {member.GenerationKey: member for member in owner.GeneratedMembers}
    webs = [item for item in candidate.items
            if item.role == "DIAGONAL" and item.element_kind == "Component"]
    results = []
    for web in webs:
        actions = [action for action in (
            web.physical_fit_plan["start_action"], web.physical_fit_plan["end_action"])
                   if action is not None]
        results.append((web.key, web.component_key,
                        members[web.key].Shape.isValid(),
                        (members[web.key].Shape.BoundBox.ZMin,
                         members[web.key].Shape.BoundBox.ZMax),
                        tuple((action["reference_key"],
                               (members[action["reference_key"]].Shape.BoundBox.ZMin,
                                members[action["reference_key"]].Shape.BoundBox.ZMax),
                               members[web.key].Shape.common(
                                   members[action["reference_key"]].Shape).Volume)
                              for action in actions)))
    with open(os.path.join(OUTPUT, "result.txt"), "w", encoding="utf-8") as stream:
        stream.write(repr(results))
    App.closeDocument(doc.Name)
except Exception:
    with open(os.path.join(OUTPUT, "error.txt"), "w", encoding="utf-8") as stream:
        traceback.print_exc(file=stream)
    raise
finally:
    try:
        Gui.getMainWindow().close()
    except (AttributeError, RuntimeError):
        pass

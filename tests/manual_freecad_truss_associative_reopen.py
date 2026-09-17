"""FreeCAD 1.1.3 gate for manual associative overrides and double-click."""
import importlib
import json
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
import Part


for module in (
        "member_batch", "truss", "interactive.truss_controller",
        "interactive.truss_task_panel", "interactive.member_adjustment_controller"):
    importlib.reload(importlib.import_module("freecad.SteelStructures." + module))

from freecad.SteelStructures import truss
from freecad.SteelStructures.fitting.freecad_adapter import has_manual_adjustment
from freecad.SteelStructures.interactive.member_adjustment_controller import (
    MemberAdjustmentController,
)
from freecad.SteelStructures.interactive import truss_controller
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.serialization import decode_state


checks = []


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def open_by_double_click(owner, expected_warning=False):
    consumed = owner.ViewObject.Proxy.doubleClicked(owner.ViewObject)
    panel = truss_controller._active_panel
    check("double-click consumed", consumed is True)
    check("generator panel opened", panel is not None and Gui.Control.activeDialog())
    if expected_warning:
        check("unresolved override warning", bool(panel.controller.opening_warnings))
    truss_controller.close_truss_panel()
    check("generator panel closed", not Gui.Control.activeDialog())


def unchanged_conflicts(owner, child):
    state = decode_state(owner.AppliedState)
    children = truss.bound_children(owner, state)
    candidate = build_candidate(state["candidate"]["config"])
    return truss.conflicts_for(owner, children, candidate).get(child.GenerationKey)


def same_physical_shape(current, previous):
    current_box, previous_box = current.BoundBox, previous.BoundBox
    values = ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax")
    return (not current.isNull()
            and abs(current.Volume - previous.Volume) < 1e-6
            and all(abs(getattr(current_box, name) - getattr(previous_box, name)) < 1e-7
                    for name in values))


output = Path(
    r"C:\Users\marco\Desktop\FREECAD\MINHA BANCADA\SteelStructures"
    r"\test-results\truss-associative-reopen"
)
output.mkdir(parents=True, exist_ok=True)
for stale_name in (
        "C5BAssociativeReopen", "associative_valid",
        "associative_reference_deleted"):
    if stale_name in App.listDocuments():
        App.closeDocument(stale_name)
doc = App.newDocument("C5BAssociativeReopen")
config = truss.default_config()
config.update(
    span=6000., end=[6000., 0., 0.], height=1600., panel_count=4,
    topology_preset="K",
)
owner = truss.apply_truss(doc, config)
child = next(member for member in owner.GeneratedMembers
             if member.GenerationKey.startswith("DIAGONAL"))
axis = child.EndPoint.sub(child.StartPoint)
axis.normalize()
reference = doc.addObject("Part::Feature", "OverrideReference")
reference.Shape = Part.makePlane(
    2000., 2000., child.StartPoint.add(axis * 250.), axis,
)
doc.recompute()
tool = MemberAdjustmentController(doc, child)

# Official Fixed PlaneCut workflow.
fixed = tool.validate(
    geometry_mode="PlaneCut", end_choice="Start", gap=3.,
    keep_reference=False, reference=(reference, ["Face1"]),
)
tool.apply(fixed)
fixed_shape = child.Shape.copy()
check("Fixed manual recognized", has_manual_adjustment(child))
check("Fixed has no false controlled conflict", unchanged_conflicts(owner, child) is None)
open_by_double_click(owner)
check("Fixed preserved after opening", str(child.StartAdjustmentMode) == "Fixed")

# Official Associative workflow with a valid external reference.
associative = tool.validate(
    geometry_mode="PlaneCut", end_choice="Start", gap=3.,
    keep_reference=True, reference=(reference, ["Face1"]),
)
tool.apply(associative)
valid_shape = child.Shape.copy()
check("Associative manual recognized", has_manual_adjustment(child))
check("Associative mode preserved", str(child.StartAdjustmentMode) == "Associative")
check("Associative reference preserved", child.StartAdjustmentReference[0] is reference)
check("Associative has no false controlled conflict", unchanged_conflicts(owner, child) is None)
open_by_double_click(owner)
check("Manual wins after opening", str(child.StartAdjustmentMode) == "Associative"
      and child.StartAdjustmentReference[0] is reference)

# Save/reopen retains the mode, LinkSub and ability to open the generator.
owner_name, child_name, reference_name = owner.Name, child.Name, reference.Name
path = output / "associative-valid.FCStd"
doc.saveAs(str(path))
App.closeDocument(doc.Name)
doc = App.openDocument(str(path))
owner = doc.getObject(owner_name)
child = doc.getObject(child_name)
reference = doc.getObject(reference_name)
check("save/reopen mode", str(child.StartAdjustmentMode) == "Associative")
check("save/reopen reference", child.StartAdjustmentReference[0] is reference)
open_by_double_click(owner)

# A null reference is an unresolved override, not permission to rewrite it.
before_null = child.Shape.copy()
child.StartAdjustmentReference = None
doc.recompute()
check("null keeps Associative", str(child.StartAdjustmentMode) == "Associative")
check("null preserves last physical shape", same_physical_shape(child.Shape, before_null))
check("null is not a controlled edit", unchanged_conflicts(owner, child) is None)
open_by_double_click(owner, expected_warning=True)
check("null remains untouched by opening", str(child.StartAdjustmentMode) == "Associative"
      and not child.StartAdjustmentReference)

# Restoring then deleting the referenced object must have the same behavior.
reference = doc.addObject("Part::Feature", "DeletedOverrideReference")
reference.Shape = Part.makePlane(
    2000., 2000., child.StartPoint.add(axis * 300.), axis,
)
doc.recompute()
tool = MemberAdjustmentController(doc, child)
tool.apply(tool.validate(
    geometry_mode="LengthLimit", end_choice="Start", gap=2.,
    keep_reference=True, reference=(reference, ["Face1"]),
))
deleted_shape = child.Shape.copy()
doc.removeObject(reference.Name)
doc.recompute()
check("deleted reference keeps Associative", str(child.StartAdjustmentMode) == "Associative")
check("deleted reference becomes null", not child.StartAdjustmentReference)
check("deleted reference preserves last shape", same_physical_shape(child.Shape, deleted_shape))
check("deleted reference is not controlled conflict", unchanged_conflicts(owner, child) is None)
open_by_double_click(owner, expected_warning=True)

path = output / "associative-reference-deleted.FCStd"
doc.saveAs(str(path))
App.closeDocument(doc.Name)
doc = App.openDocument(str(path))
owner = doc.getObject(owner_name)
child = doc.getObject(child_name)
check("deleted reference save/reopen keeps mode",
      str(child.StartAdjustmentMode) == "Associative")
check("deleted reference save/reopen keeps last shape", not child.Shape.isNull())
open_by_double_click(owner, expected_warning=True)

(output / "gate-result.json").write_text(
    json.dumps({"passed": len(checks), "checks": checks}, indent=2),
    encoding="utf-8",
)
print(json.dumps({"passed": len(checks), "checks": checks}))

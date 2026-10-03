"""Focused real FreeCAD 1.1.3 gate for the final C5-B ridge fixes."""
import copy
import importlib
import json
import math
import sys
import traceback
from dataclasses import asdict
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui


ROOT = Path(r"C:\Users\marco\Desktop\FREECAD\MINHA BANCADA\SteelStructures")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for name in (
        "profiles.insertion", "profiles.preview_geometry", "profiles", "profile_catalog",
        "assemblies.transforms", "assemblies.attachment", "connections.models",
        "connections.resolver", "connections", "trusses.connections",
        "trusses.fitting_geometry", "trusses.fitting", "trusses.realization",
        "member_plane_cut", "fitting.freecad_adapter", "member", "member_batch",
        "truss", "interactive.truss_controller"):
    importlib.reload(importlib.import_module("freecad.SteelStructures."+name))

from freecad.SteelStructures import profile_catalog, truss
from freecad.SteelStructures.interactive.truss_controller import TrussController
from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.trusses.models import TopologyEdge, TopologyGraph
from freecad.SteelStructures.trusses.realization import build_candidate


OUTPUT = ROOT / "test-results" / "c5b-final"
OUTPUT.mkdir(parents=True, exist_ok=True)
checks = []


def _record_unhandled(exc_type, exc_value, exc_traceback):
    (OUTPUT/"gate-error.txt").write_text("".join(traceback.format_exception(
        exc_type, exc_value, exc_traceback)), encoding="utf-8")
    traceback.print_exception(exc_type, exc_value, exc_traceback)


sys.excepthook = _record_unhandled


def check(label, condition, value=None):
    if not condition:
        raise AssertionError(label + (" | "+repr(value) if value is not None else ""))
    checks.append(label)


def configured(apex=.5, height=900., inclined=False):
    value = truss.default_config()
    value.update(envelope_type="DuoPitch", span=2400., end=[2400., 0., 0.],
                 apex_position=apex, height=height, panel_count=8,
                 topology_preset="Pratt", top_continuity="Continuous",
                 bottom_continuity="Continuous")
    value["role_specs"]["TOP_CHORD"]["profile_ref"] = asdict(
        profile_catalog.ref_for_designation('U 4" x 8,04'))
    value["role_specs"]["TOP_CHORD"]["rotation"] = -90.
    if inclined:
        value.update(start=[20., 30., 40.], end=[2420., 30., 40.],
                     plane_normal=[0., -.6, .8])
    base = build_candidate(value)
    apex_node = base.graph.node("T_S_APEX")
    bottom = sorted((node for node in base.graph.nodes if node.key.startswith("B_")
                     and abs(node.position_local[0]-apex_node.position_local[0]) > 1e-7),
                    key=lambda node: abs(node.position_local[0]-apex_node.position_local[0]))
    targets = (next(node for node in bottom if node.position_local[0] < apex_node.position_local[0]),
               next(node for node in bottom if node.position_local[0] > apex_node.position_local[0]))
    edges = list(base.graph.edges)
    for index, node in enumerate(targets):
        if not any({edge.start_node_key, edge.end_node_key} == {node.key, apex_node.key}
                   for edge in edges):
            edges.append(TopologyEdge("ridge-diagonal-"+str(index), node.key,
                                      apex_node.key, "DIAGONAL"))
    value.update(topology_mode="Custom", topology_preset="Custom", base_preset="Pratt",
                 custom_topology=materialize(
                     TopologyGraph(base.graph.nodes, tuple(edges)), base.config))
    return value


def members(owner):
    return {member.GenerationKey: member for member in owner.GeneratedMembers}


def valid(owner):
    return all(member.Shape.isValid() and member.Shape.Volume > 0.
               for member in owner.GeneratedMembers)


def distance(a, b):
    return a.Shape.distToShape(b.Shape)[0]


def overlap(a, b):
    return a.Shape.common(b.Shape).Volume


def ridge_measurements(owner):
    candidate = build_candidate(truss.config_from_object(owner))
    by_key = members(owner)
    chords = (by_key["TC_LEFT"], by_key["TC_RIGHT"])
    vertical_item = next(item for item in candidate.items if item.role == "VERTICAL"
                         and "T_S_APEX" in (item.start_node_key, item.end_node_key))
    vertical = by_key[vertical_item.key]
    diagonals = [item for item in candidate.items if item.role == "DIAGONAL"
                 and "T_S_APEX" in (item.start_node_key, item.end_node_key)]
    diagonal_residuals = []
    for item in diagonals:
        other_key = item.end_node_key if item.start_node_key == "T_S_APEX" else item.start_node_key
        other = candidate.graph.node(other_key)
        chord = chords[0] if other.position_local[0] < candidate.config["span"]*candidate.config["apex_position"] else chords[1]
        diagonal_residuals.append(distance(by_key[item.key], chord))
    return dict(candidate=candidate, by_key=by_key, chords=chords, vertical=vertical,
                vertical_residuals=[distance(vertical, chord) for chord in chords],
                vertical_overlaps=[overlap(vertical, chord) for chord in chords],
                diagonal_residuals=diagonal_residuals)


doc = App.newDocument("C5BFinalGate")
doc.UndoMode = 1
value = configured()
owner = truss.apply_truss(doc, value)
doc.recompute()
data = ridge_measurements(owner)
check("symmetric OCC shapes valid", valid(owner))
check("symmetric ridge chords meet without overlap",
      distance(*data["chords"]) < 1e-6 and overlap(*data["chords"]) < 1e-5)
check("symmetric vertical reaches both physical U faces",
      max(data["vertical_residuals"]) < 1e-6, data["vertical_residuals"])
check("symmetric vertical does not penetrate chords",
      max(data["vertical_overlaps"]) < 1e-5, data["vertical_overlaps"])
check("symmetric diagonals reach their physical U faces",
      max(data["diagonal_residuals"]) < 1e-6, data["diagonal_residuals"])
check("left terminal chords meet without overlap",
      distance(data["by_key"]["BC_MAIN"], data["by_key"]["TC_LEFT"]) < 1e-6
      and overlap(data["by_key"]["BC_MAIN"], data["by_key"]["TC_LEFT"]) < 1e-5)
check("right terminal chords meet without overlap",
      distance(data["by_key"]["BC_MAIN"], data["by_key"]["TC_RIGHT"]) < 1e-6
      and overlap(data["by_key"]["BC_MAIN"], data["by_key"]["TC_RIGHT"]) < 1e-5)
check("nominal nodes and axes stay unchanged", all(
    member.StartPoint.distanceToPoint(App.Vector(*item.start_global)) < 1e-7
    and member.EndPoint.distanceToPoint(App.Vector(*item.end_global)) < 1e-7
    for item in data["candidate"].items for member in (data["by_key"][item.key],)))

before_vertical = data["vertical"].Shape.copy()
value = truss.config_from_object(owner)
value.update(apex_position=.37, height=1100.)
owner = truss.apply_truss(doc, value, owner)
doc.recompute()
data = ridge_measurements(owner)
check("asymmetric OCC shapes valid", valid(owner))
check("asymmetric ridge physical contacts close",
      max(data["vertical_residuals"]+data["diagonal_residuals"]) < 1e-6,
      data["vertical_residuals"]+data["diagonal_residuals"])
check("height change regenerates fitted web", before_vertical.distToShape(data["vertical"].Shape)[0] > 1.)
check("asymmetric terminal miters close",
      max(distance(data["by_key"]["BC_MAIN"], data["by_key"][key])
          for key in ("TC_LEFT", "TC_RIGHT")) < 1e-6)

value = truss.config_from_object(owner)
value.update(start=[20., 30., 40.], end=[2420., 30., 40.], plane_normal=[0., -.6, .8])
owner = truss.apply_truss(doc, value, owner)
doc.recompute()
data = ridge_measurements(owner)
check("inclined plane OCC shapes valid", valid(owner))
check("inclined ridge physical contacts close",
      max(data["vertical_residuals"]+data["diagonal_residuals"]) < 1e-6)
check("inclined terminal miters close",
      max(distance(data["by_key"]["BC_MAIN"], data["by_key"][key])
          for key in ("TC_LEFT", "TC_RIGHT")) < 1e-6)

axes = {member.Name: (App.Vector(member.StartPoint), App.Vector(member.EndPoint))
        for member in owner.GeneratedMembers}
vertical_center = data["vertical"].Shape.BoundBox.Center
value = truss.config_from_object(owner)
value["role_specs"]["VERTICAL"]["insertion"] = "envelope_center"
owner = truss.apply_truss(doc, value, owner)
doc.recompute()
data = ridge_measurements(owner)
check("envelope center preserves nominal work lines", all(
    member.StartPoint.distanceToPoint(axes[member.Name][0]) < 1e-7
    and member.EndPoint.distanceToPoint(axes[member.Name][1]) < 1e-7
    for member in owner.GeneratedMembers))
check("envelope center moves physical angle",
      data["vertical"].Shape.BoundBox.Center.distanceToPoint(vertical_center) > 1.)

value = truss.config_from_object(owner)
for role in ("VERTICAL", "DIAGONAL"):
    value["role_specs"][role]["physical_fit_gap"] = 7.
owner = truss.apply_truss(doc, value, owner)
doc.recompute()
data = ridge_measurements(owner)
gap_distances = data["vertical_residuals"] + data["diagonal_residuals"]
check("positive axial gap opens every apex web contact",
      min(gap_distances) > .1, gap_distances)
check("positive axial gap persists as exactly 7 mm", all(
    action["gap"] == 7.
    for item in data["candidate"].items if item.role in ("VERTICAL", "DIAGONAL")
    and "T_S_APEX" in (item.start_node_key, item.end_node_key)
    for plan in (item.physical_fit_plan or {},)
    for action in ([plan.get("start_action"), plan.get("end_action")]
                   + list(plan.get("additional_actions", ()))) if action))

value = truss.config_from_object(owner)
for role in ("VERTICAL", "DIAGONAL"):
    value["role_specs"][role]["physical_fit_gap"] = 0.
value["role_specs"]["TOP_CHORD"]["profile_ref"] = asdict(
    profile_catalog.ref_for_designation("L 40 x 4"))
owner = truss.apply_truss(doc, value, owner)
doc.recompute()
candidate = build_candidate(truss.config_from_object(owner))
different = members(owner)
for node_key in ("N_S_START", "N_S_END"):
    from freecad.SteelStructures.trusses.connections import chord_joints
    joint, = chord_joints(candidate, node_key)
    planes = []
    for run_key, end in joint.run_ends:
        item = next(item for item in candidate.items if item.run_key == run_key)
        plan = item.physical_fit_plan
        action = next(action for action in (
            [plan.get("start_action"), plan.get("end_action")]
            + list(plan.get("additional_actions", ())))
            if action and action["end"] == end and action["reference_key"] == joint.participant_key)
        planes.append((action["plane_origin"], action["plane_normal"]))
    check("different sections share terminal miter plane "+node_key, planes[0] == planes[1])
check("different chord sections remain valid", valid(owner))
check("different sections close without terminal overlap", all(
    distance(different["BC_MAIN"], different[key]) < 1e-6
    and overlap(different["BC_MAIN"], different[key]) < 1e-5
    for key in ("TC_LEFT", "TC_RIGHT")))

view = Gui.activeDocument().activeView()
view.viewAxonometric()
view.fitAll()
orientation_before = tuple(view.getCameraOrientation().Q)
view.getCameraNode().position.setValue(100000., 100000., 100000.)
camera_far = view.getCamera()
objects_before = tuple(obj.Name for obj in doc.Objects)
creation = TrussController(doc)
creation.preview3d(configured(.5, 900.))
camera_framed = view.getCamera()
orientation_after = tuple(view.getCameraOrientation().Q)
check("new preview auto-frames its Coin branch", camera_framed != camera_far)
check("auto-frame preserves view orientation", math.isclose(abs(sum(
    a*b for a,b in zip(orientation_before, orientation_after))), 1., abs_tol=1e-7))
check("preview creates no document object", tuple(obj.Name for obj in doc.Objects) == objects_before)
changed_preview = configured(.5, 1200.)
creation.preview3d(changed_preview)
check("normal preview update does not reframe", view.getCamera() == camera_framed)
creation.remove_preview()
camera_edit = view.getCamera()
editing = TrussController(doc, owner)
editing.preview3d(truss.config_from_object(owner))
check("editing existing truss does not alter camera", view.getCamera() == camera_edit)
editing.remove_preview()

owner_name = owner.Name
path = OUTPUT / "C5BFinal.FCStd"
doc.saveAs(str(path))
App.closeDocument(doc.Name)
doc = App.openDocument(str(path))
owner = doc.getObject(owner_name)
doc.recompute()
check("save reopen keeps valid fitted shapes", valid(owner))
restored = build_candidate(truss.config_from_object(owner))
check("save reopen keeps both terminal joints", all(
    len(__import__("freecad.SteelStructures.trusses.connections", fromlist=["chord_joints"])
        .chord_joints(restored, node_key)) == 1
    for node_key in ("N_S_START", "N_S_END")))
check("save reopen keeps envelope center option",
      truss.config_from_object(owner)["role_specs"]["VERTICAL"]["insertion"] == "envelope_center")

Gui.activeDocument().activeView().viewAxonometric()
Gui.activeDocument().activeView().fitAll()
Gui.activeDocument().activeView().saveImage(str(OUTPUT/"c5b-final.png"), 1400, 900, "Current")
(OUTPUT/"gate-result.json").write_text(json.dumps(dict(
    version=App.Version(), passed=len(checks), checks=checks), indent=2), encoding="utf-8")
print(json.dumps(dict(passed=len(checks), checks=checks)))

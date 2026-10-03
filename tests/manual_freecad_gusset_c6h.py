"""Short FreeCAD 1.1.3 integration gate for the C6-H contact geometry."""

import copy
import json
import os
import sys
import traceback
import types
from dataclasses import asdict

OUTPUT = os.path.join(os.getcwd(), "test-results", "gusset-c6h")
os.makedirs(OUTPUT, exist_ok=True)


def report_exception(kind, value, tb):
    with open(os.path.join(OUTPUT, "gate-error.txt"), "w", encoding="utf-8") as stream:
        traceback.print_exception(kind, value, tb, file=stream)
    traceback.print_exception(kind, value, tb)


sys.excepthook = report_exception
import FreeCAD as App
import FreeCADGui as Gui

ROOT = os.getcwd()
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests")]
local_tests = types.ModuleType("tests")
local_tests.__path__ = [os.path.join(ROOT, "tests")]
sys.modules["tests"] = local_tests
for module_name in tuple(sys.modules):
    if module_name == "freecad" or module_name.startswith("freecad.SteelStructures"):
        sys.modules.pop(module_name, None)

from freecad.SteelStructures import profile_catalog, truss
from freecad.SteelStructures.connections import attachment_warning_messages
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.gusset_freecad import build_gusset_shape
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate
from test_connections_c5b_polish import three_web_config
from test_fitting_c6g_assembly import _candidate as fitting_candidate
from test_gusset_plate_c6a import configured
from test_ridge_fitting import ridge_config

checks = []
doc = App.newDocument("GussetC6H")
doc.UndoMode = 1
PATH = os.path.join(OUTPUT, "GussetC6H.FCStd")


def check(label, condition, detail=None):
    if not condition:
        raise AssertionError(label+(": "+repr(detail) if detail is not None else ""))
    checks.append(label)


def shifted(value, row):
    value = copy.deepcopy(value)
    delta = row*2600.-value["start"][1]
    value["start"][1] += delta
    value["end"][1] += delta
    return value


def case(designation, rotation, row):
    value, node = three_web_config()
    reference = asdict(profile_catalog.ref_for_designation(designation))
    for role in ("TOP_CHORD", "BOTTOM_CHORD"):
        value["role_specs"][role]["profile_ref"] = copy.deepcopy(reference)
        value["role_specs"][role]["rotation"] = rotation
    candidate = build_candidate(configured(
        shifted(value, row), node, plate_thickness=8.,
        chord_contact="TrussInterior"))
    outlines, diagnostics = preliminary_gusset_outlines(candidate)
    if diagnostics:
        raise AssertionError([item.message for item in diagnostics])
    outline = next(item for item in outlines if item.spec.node_key == node)
    owner = truss.apply_truss(doc, candidate.config)
    plate = owner.GeneratedGussetPlates[0]
    return candidate, owner, outline, plate


def plate_slab(shape, outline):
    origin, normal = outline.spec.frame.origin, outline.spec.frame.normal
    values = [sum((vertex.Point[i]-origin[i])*normal[i] for i in range(3))
              for vertex in shape.Vertexes]
    return min(values), max(values)


def chord_penetration(candidate, owner, plate):
    members = {item.GenerationKey: item for item in owner.GeneratedMembers}
    volumes = [plate.Shape.common(members[item.key].Shape).Volume
               for item in candidate.items
               if item.element_kind == "Component"
               and item.role in ("TOP_CHORD", "BOTTOM_CHORD")
               and item.key in members]
    return max(volumes, default=0.)


families = (
    ('U 4" x 8,04', 0.), ('U 4" x 8,04', 90.),
    ('U 4" x 8,04', 180.), ('U 4" x 8,04', 270.),
    ("Ue 150 × 60 × 20 × 3,00", 0.),
    ("W 150 x 13,0", 0.), ('I 3" x 8,48', 0.),
    ("L 40 x 4", 0.), ("SHS 40x40x1,2", 0.),
    ("RHS 60x40x1,2", 0.),
)
results = []
for row, (designation, rotation) in enumerate(families):
    candidate, owner, outline, plate = case(designation, rotation, row)
    label = designation+" @ "+str(rotation)
    check(label+" Shape and slab", plate.Shape.isValid() and
          max(abs(a-b) for a, b in zip(plate_slab(plate.Shape, outline),
               (outline.attachment.plate_low, outline.attachment.plate_high))) < 1e-5)
    penetration = chord_penetration(candidate, owner, plate)
    check(label+" no chord penetration", penetration < 1e-4, penetration)
    results.append((candidate, owner, outline, plate))

check("U rotations retain interior truss contact",
      all(any(edge.kind == "CHORD_BOUNDARY" for edge in result[2].semantic_edges)
          for result in results[:4]))
check("closed tubes never select an enclosed void",
      all(all(value.accessibility.value != "EnclosedVoid"
              for value in result[2].attachment.candidates)
          for result in results[8:10]))
check("preview equals persisted OCC Shape",
      build_gusset_shape(results[0][2]).distToShape(results[0][3].Shape)[0] < 1e-7)

duo = ridge_config(.37, 1100.)
duo["connection_intents"] = {"T_S_LEFT_1_3": dict(form="Gusset",
    gusset=dict(plate_thickness=8., chord_contact="TrussInterior"))}
duo_outline = preliminary_gusset_outlines(build_candidate(duo))[0][0]
check("DuoPitch intermediate direct caps and physical margins",
      tuple(e.kind for e in duo_outline.semantic_edges) == (
          "FREE_MARGIN", "WEB_END_CAP", "WEB_END_CAP", "FREE_MARGIN", "CHORD_BOUNDARY"))
mirror = ridge_config(.63, 1100.)
mirror["connection_intents"] = {"T_S_RIGHT_1_3": dict(form="Gusset",
    gusset=dict(plate_thickness=8., chord_contact="TrussInterior"))}
mirror_outline = preliminary_gusset_outlines(build_candidate(mirror))[0][0]
check("DuoPitch counterpart remains valid", mirror_outline.area > 0.)

terminal = ridge_config(diagonals=False)
terminal["connection_intents"] = {"N_S_START": dict(form="Gusset",
    gusset=dict(plate_thickness=8., edge_margin=500., member_overlap=1000.,
                chord_contact="TrussInterior"))}
terminal_outline = preliminary_gusset_outlines(build_candidate(terminal))[0][0]
check("terminal nominal plane is respected",
      all(point[0] >= -1e-7 for point in terminal_outline.points))

gap_value, gap_node = three_web_config()
role = copy.deepcopy(gap_value["role_specs"]["DIAGONAL"])
role["profile_ref"] = asdict(profile_catalog.ref_for_designation("W 150 x 13,0"))
gap_value["role_specs"]["DIAGONAL"] = configure_assembly(role, "SpacedPair", 120.)
gap = build_candidate(configured(shifted(gap_value, 11), gap_node,
                                 attachment_mode="Center", side="Center",
                                 chord_contact="TrussInterior"))
gap_outline = preliminary_gusset_outlines(gap)[0][0]
check("assembly physical gap remains selectable",
      gap_outline.attachment.kind == "AssemblyMidPlane")

fit_value, _fit_candidate = fitting_candidate(
    "DoubleAngle", "DoubleAngle", chord_uses_angle=True)
fit_owner = truss.apply_truss(doc, shifted(fit_value, 12))
check("assembly fitting member Shapes remain valid",
      all(item.Shape.isValid() for item in fit_owner.GeneratedMembers))

for row, (kind, designation) in enumerate((
        ("DoubleAngle", "L 40 x 4"),
        ("DoubleChannelInward", 'U 4" x 8,04'))):
    value, node = three_web_config()
    role = copy.deepcopy(value["role_specs"]["DIAGONAL"])
    role["profile_ref"] = asdict(profile_catalog.ref_for_designation(designation))
    value["role_specs"]["DIAGONAL"] = configure_assembly(role, kind, 100.)
    value = configured(shifted(value, 13+row), node,
                       attachment_mode="Center", side="Center",
                       chord_contact="TrussInterior")
    owner = truss.apply_truss(doc, value)
    check(kind+" gap materializes in FreeCAD",
          len(owner.GeneratedGussetPlates) == 1
          and owner.GeneratedGussetPlates[0].Shape.isValid())

for row, value in enumerate((duo, mirror, terminal)):
    owner = truss.apply_truss(doc, shifted(value, 15+row))
    check(("DuoPitch intermediate", "DuoPitch mirrored", "terminal")[row]
          +" Shape is valid in FreeCAD",
          len(owner.GeneratedGussetPlates) == 1
          and owner.GeneratedGussetPlates[0].Shape.isValid())
    actual_config = truss.config_from_object(owner)
    actual_candidate = build_candidate(actual_config)
    actual_outlines, diagnostics = preliminary_gusset_outlines(actual_candidate)
    check("DuoPitch/terminal physical outline has no failure diagnostics", not diagnostics)
    actual = actual_outlines[0]
    selected = next(c for c in actual.attachment.candidates
                    if (c.slot_id, c.placement) == (
                        actual.attachment.governing_slot_id, actual.attachment.placement_kind))
    actual_config["connection_intents"][actual.spec.node_key]["gusset"][
        "transverse_placement"] = selected.stable_key
    manual, manual_diagnostics = preliminary_gusset_outlines(build_candidate(actual_config))
    physical = owner.GeneratedGussetPlates[0].Shape
    for label, expected in (("preview", build_gusset_shape(actual)),
                            ("manual same candidate", build_gusset_shape(manual[0]))):
        difference = physical.cut(expected).Volume+expected.cut(physical).Volume
        check("DuoPitch/terminal OCC equals "+label,
              not manual_diagnostics and difference < 1e-5, difference)
    members = {m.GenerationKey: m for m in owner.GeneratedMembers}
    penetration = max(physical.common(members[item.key].Shape).Volume
                      for item in actual_candidate.items if item.element_kind == "Component"
                      and item.role in ("TOP_CHORD", "BOTTOM_CHORD"))
    check("DuoPitch/terminal no chord penetration", penetration < 1e-4, penetration)

# Close views make the real OCC contact inspectable after the numeric gate.
view = Gui.activeDocument().activeView()
for index in (0, 1, 4, 5, 6, 7, 8, 9):
    plate = results[index][3]
    owner = results[index][1]
    for item in doc.Objects:
        if getattr(item, "ViewObject", None) is not None:
            item.ViewObject.Visibility = False
    for item in tuple(owner.GeneratedMembers)+tuple(owner.GeneratedGussetPlates):
        item.ViewObject.Visibility = True
    view.viewAxonometric()
    view.fitAll()
    box = plate.Shape.BoundBox
    centre = App.Vector((box.XMin+box.XMax)/2.,
                        (box.YMin+box.YMax)/2.,
                        (box.ZMin+box.ZMax)/2.)
    camera = view.getCameraNode()
    back = view.getCameraOrientation().multVec(App.Vector(0., 0., 1.))
    camera.position.setValue(*(centre+back*700.))
    camera.height.setValue(420.)
    view.saveImage(os.path.join(OUTPUT, "view-%02d.png" % index),
                   1200, 900, "White")

doc.recompute()
first_owner_name = results[0][1].Name
first_plate_name = results[0][3].Name
doc.saveAs(PATH)
App.closeDocument(doc.Name)
doc = App.openDocument(PATH)
check("save/reopen preserves chord contact and Shape",
      doc.getObject(first_plate_name).ChordContact == "TrussInterior"
      and doc.getObject(first_plate_name).Shape.isValid())
reopened_owner = doc.getObject(first_owner_name)
reopened_outlines, _diagnostics = preliminary_gusset_outlines(
    build_candidate(truss.config_from_object(reopened_owner)))
check("save/reopen recomputes node warnings",
      isinstance(attachment_warning_messages(reopened_outlines), tuple))

with open(os.path.join(OUTPUT, "gate-result.json"), "w", encoding="utf-8") as stream:
    json.dump(dict(freecad=App.Version(), checks=checks, document=PATH),
              stream, ensure_ascii=False, indent=2)
print("C6-H FreeCAD gate OK:", len(checks), "checks")
App.closeDocument(doc.Name)
try:
    Gui.getMainWindow().close()
except (AttributeError, RuntimeError):
    pass

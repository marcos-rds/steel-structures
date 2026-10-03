"""Focused FreeCAD 1.1.3 visual/numeric gate for C6-D gusset placement."""

import copy
import json
import math
import os
import sys
import traceback
import types

OUTPUT = os.path.join(os.getcwd(), "test-results", "gusset-c6d")
os.makedirs(OUTPUT, exist_ok=True)


def _report_exception(kind, value, tb):
    with open(os.path.join(OUTPUT, "gate-error.txt"), "w", encoding="utf-8") as stream:
        traceback.print_exception(kind, value, tb, file=stream)
    traceback.print_exception(kind, value, tb)


sys.excepthook = _report_exception

import FreeCAD as App
import FreeCADGui as Gui

ROOT = os.getcwd()
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
local_tests = types.ModuleType("tests")
local_tests.__path__ = [os.path.join(ROOT, "tests")]
sys.modules["tests"] = local_tests
for module_name in tuple(sys.modules):
    if module_name == "freecad" or module_name.startswith("freecad.SteelStructures"):
        sys.modules.pop(module_name, None)

from freecad.SteelStructures import truss
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.gusset_freecad import build_gusset_shape
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate
from test_connections_c5b_polish import three_web_config
from test_connections_c5b_through import k_config
from test_gusset_plate_c6a import configured
from test_ridge_fitting import ridge_config


checks = []
PATH = os.path.join(OUTPUT, "GussetC6D.FCStd")


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def shifted(value, y):
    value = copy.deepcopy(value)
    start, end = list(value["start"]), list(value["end"])
    delta = y-start[1]
    start[1] += delta
    end[1] += delta
    value.update(start=start, end=end)
    return value


def apply_case(doc, value, node, y, **parameters):
    value = shifted(value, y)
    candidate = build_candidate(configured(value, node, **parameters))
    outlines, diagnostics = preliminary_gusset_outlines(candidate)
    if diagnostics:
        raise AssertionError([item.message for item in diagnostics])
    outline = next(item for item in outlines if item.spec.node_key == node)
    owner = truss.apply_truss(doc, candidate.config)
    plate = owner.GeneratedGussetPlates[0]
    return owner, plate, outline


def projected_limits(shape, outline):
    origin, normal = outline.spec.frame.origin, outline.spec.frame.normal
    values = [sum((vertex.Point[index]-origin[index])*normal[index]
                  for index in range(3)) for vertex in shape.Vertexes]
    return min(values), max(values)


def screenshots(owner, name, axonometric=False):
    for item in doc.Objects:
        if getattr(item, "ViewObject", None) is not None:
            item.ViewObject.Visibility = False
    for item in tuple(owner.GeneratedMembers)+tuple(owner.GeneratedGussetPlates):
        item.ViewObject.Visibility = True
    view = Gui.activeDocument().activeView()
    view.viewAxonometric() if axonometric else view.viewFront()
    view.fitAll()
    path = os.path.join(OUTPUT, name)
    view.saveImage(path, 1600, 900, "White")
    return path


doc = App.newDocument("GussetC6D")

# U chord: physical surface, face-coincident extrusion and persistent results.
value, node = three_web_config()
owner, plate, outline = apply_case(doc, value, node, 0.)
check("U attachment resolves a physical surface",
      outline.attachment.kind == "PhysicalSurface")
check("U web outer surface has expected offset",
      abs(outline.attachment.signed_offset-11.6) < 1e-6)
low, high = projected_limits(plate.Shape, outline)
check("Centered physical solution aligns one wide plate face",
      abs(low-11.6) < 1e-6 and abs(high-19.6) < 1e-6)
check("persistent attachment results mirror authoritative outline",
      abs(plate.AttachmentOffset.Value-outline.attachment.signed_offset) < 1e-7
      and plate.AttachmentStatus == outline.attachment.status
      and plate.AttachmentSurface == outline.attachment.governing_surface_id)
check("plate remains a generated plate, not a member",
      plate not in owner.GeneratedMembers and len(owner.GeneratedGussetPlates) == 1)
u_owner_name = owner.Name

# Side A/B: a plate face, never its mid-plane, is placed on the selected surface.
value, node = three_web_config()
side_a_owner, side_a, side_a_outline = apply_case(doc, value, node, 3500., side="FaceA")
check("Side A extrusion is outside its +normal surface",
      all(abs(a-b) < 1e-6 for a, b in zip(
          projected_limits(side_a.Shape, side_a_outline), (11.6, 19.6))))
value, node = three_web_config()
side_b_owner, side_b, side_b_outline = apply_case(doc, value, node, 7000., side="FaceB")
check("Side B extrusion is outside its -normal surface",
      all(abs(a-b) < 1e-6 for a, b in zip(
          projected_limits(side_b.Shape, side_b_outline), (-1.07, 6.93))))

# Known non-coplanarity remains visible and non-fatal.
value, node = three_web_config()
value["role_specs"]["DIAGONAL"]["rotation"] = 180.
warning_owner, warning_plate, warning_outline = apply_case(doc, value, node, 10500.)
check("non-coplanar participants keep a valid warning plate",
      warning_outline.attachment.status == "Warning"
      and warning_plate.Shape.isValid() and warning_plate.Shape.Volume > 0.)
check("residual diagnostics include numeric gap or interference",
      any(item.residual is not None and abs(item.residual) > .1
          for item in warning_outline.attachment.residuals))

# Assemblies: one plate, physical central gap when semantically clear.
assembly_owners = []
for index, mode in enumerate(("DoubleAngle", "DoubleChannelInward", "SpacedPair")):
    value, node = three_web_config()
    role = value["role_specs"]["DIAGONAL"]
    if mode == "DoubleChannelInward":
        role["profile_ref"] = copy.deepcopy(value["role_specs"]["BOTTOM_CHORD"]["profile_ref"])
    value["role_specs"]["DIAGONAL"] = configure_assembly(role, mode, 100.)
    current_owner, current_plate, current_outline = apply_case(
        doc, value, node, 14000.+index*3500.)
    assembly_owners.append(current_owner)
    check(mode+" creates exactly one Gusset", len(current_owner.GeneratedGussetPlates) == 1)
    if mode != "SpacedPair":
        check(mode+" uses the symmetric physical mid-plane",
              current_outline.attachment.kind == "AssemblyMidPlane"
              and abs(current_outline.attachment.signed_offset) < 1e-7)

# K, ridge, terminal and inclined plane retain their semantic topology.
k_value, k_node = k_config()
k_owner, k_plate, k_outline = apply_case(doc, k_value, k_node, 24500.)
k_candidate = build_candidate(truss.config_from_object(k_owner))
through = [item for item in connection_participants(k_candidate, k_node)
           if item.end == "Through"]
check("K keeps one semantic Through participant",
      len(through) == 1 and k_outline.spec.participant_keys.count(
          through[0].participant_key) == 1)
check("K keeps one valid plate", len(k_owner.GeneratedGussetPlates) == 1
      and k_plate.Shape.isValid())
k_owner_name = k_owner.Name

ridge_value = ridge_config(.5, 1100.)
ridge_owner, ridge_plate, ridge_outline = apply_case(
    doc, ridge_value, "T_S_APEX", 28000.)
check("DuoPitch ridge keeps both chord branches",
      sum("chord-break:TC_LEFT|TC_RIGHT" in key
          for key in ridge_outline.spec.participant_keys) == 1
      and min(x for x, _y in ridge_outline.points) < 0.
      and max(x for x, _y in ridge_outline.points) > 0.)
check("DuoPitch ridge attachment remains physical",
      ridge_outline.attachment.kind in ("PhysicalSurface", "AssemblyMidPlane"))
ridge_owner_name = ridge_owner.Name

asymmetric_value = ridge_config(.37, 900.)
asymmetric_owner, _plate, asymmetric_outline = apply_case(
    doc, asymmetric_value, "T_S_APEX", 31500.)
check("asymmetric DuoPitch produces a valid attachment",
      asymmetric_outline.attachment is not None and asymmetric_outline.area > 0.)

terminal_value = ridge_config(diagonals=False)
terminal_owner, _plate, terminal_outline = apply_case(
    doc, terminal_value, "N_S_START", 35000.)
check("terminal chord closure keeps one regularized plate",
      len(terminal_owner.GeneratedGussetPlates) == 1
      and {item.role for item in connection_participants(
          build_candidate(truss.config_from_object(terminal_owner)), "N_S_START")}
      == {"TOP_CHORD", "BOTTOM_CHORD"})

inclined_value = ridge_config(.37, 900., inclined=True)
inclined_owner, inclined_plate, inclined_outline = apply_case(
    doc, inclined_value, "T_S_APEX", 38500., side="FaceA")
check("inclined attachment normal follows local truss plane",
      all(abs(a-b) < 1e-9 for a, b in zip(
          inclined_outline.attachment.normal, inclined_outline.spec.frame.normal)))
inclined_low, inclined_high = projected_limits(inclined_plate.Shape, inclined_outline)
check("inclined plate uses attachment interval without global-axis assumptions",
      abs(inclined_low-inclined_outline.attachment.plate_low) < 1e-6
      and abs(inclined_high-inclined_outline.attachment.plate_high) < 1e-6)

# Shared geometry, identity update and persistence.
preview_shape = build_gusset_shape(outline)
check("preview and document use identical C6-D geometry",
      preview_shape.distToShape(plate.Shape)[0] < 1e-7
      and abs(preview_shape.Volume-plate.Shape.Volume) < 1e-6)
old_name = plate.Name
changed = truss.config_from_object(owner)
changed["connection_intents"][node]["gusset"]["side"] = "FaceB"
owner = truss.apply_truss(doc, changed, owner)
check("attachment update preserves document identity",
      owner.GeneratedGussetPlates[0].Name == old_name)

doc.recompute()
doc.saveAs(PATH)
saved = {current.Name: tuple(item.Name for item in current.GeneratedGussetPlates)
         for current in (owner, side_a_owner, side_b_owner, warning_owner,
                         k_owner, ridge_owner, asymmetric_owner, terminal_owner,
                         inclined_owner)+tuple(assembly_owners)}
App.closeDocument(doc.Name)
doc = App.openDocument(PATH)
check("save/reopen preserves attachment properties and registries", all(
      tuple(item.Name for item in doc.getObject(name).GeneratedGussetPlates) == names
      and all("AttachmentOffset" in item.PropertiesList and item.Shape.isValid()
              for item in doc.getObject(name).GeneratedGussetPlates)
      for name, names in saved.items()))

screens = (
    screenshots(doc.getObject(u_owner_name), "gusset-c6d-parallel-front.png"),
    screenshots(doc.getObject(k_owner_name), "gusset-c6d-k-front.png"),
    screenshots(doc.getObject(ridge_owner_name), "gusset-c6d-ridge-front.png"),
    screenshots(doc.getObject(u_owner_name), "gusset-c6d-u-attachment-axon.png", True),
)
check("four focused screenshots were generated",
      all(os.path.getsize(path) > 0 for path in screens))

doc.saveAs(PATH)
with open(os.path.join(OUTPUT, "gate-result.json"), "w", encoding="utf-8") as stream:
    json.dump(dict(freecad=App.Version(), checks=checks, document=PATH,
                   screenshots=screens), stream, ensure_ascii=False, indent=2)

print("C6-D manual gate OK:", len(checks), "checks")
App.closeDocument(doc.Name)
Gui.getMainWindow().close()

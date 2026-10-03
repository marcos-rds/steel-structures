"""Focused FreeCAD 1.1.3 visual/numeric gate for C6-E Gusset refinement."""

import copy
import json
import os
import sys
import traceback
import types

OUTPUT = os.path.join(os.getcwd(), "test-results", "gusset-c6e")
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

from freecad.SteelStructures import profile_catalog, truss
from freecad.SteelStructures.connections import attachment_warning_messages
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.connections import (
    connection_participants, gusset_thickness_for_transition,
)
from freecad.SteelStructures.trusses.gusset_freecad import build_gusset_shape
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate
from test_connections_c5b_polish import three_web_config
from test_connections_c5b_through import k_config
from test_gusset_plate_c6a import configured
from test_ridge_fitting import ridge_config


checks = []
PATH = os.path.join(OUTPUT, "GussetC6E.FCStd")


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
    candidate = build_candidate(configured(shifted(value, y), node, **parameters))
    outlines, diagnostics = preliminary_gusset_outlines(candidate)
    if diagnostics:
        raise AssertionError([item.message for item in diagnostics])
    outline = next(item for item in outlines if item.spec.node_key == node)
    owner = truss.apply_truss(doc, candidate.config)
    return owner, owner.GeneratedGussetPlates[0], outline


def projected_limits(shape, outline):
    origin, normal = outline.spec.frame.origin, outline.spec.frame.normal
    values = [sum((vertex.Point[index]-origin[index])*normal[index]
                  for index in range(3)) for vertex in shape.Vertexes]
    return min(values), max(values)


def screenshot(owner, name, axonometric=False):
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


doc = App.newDocument("GussetC6E")

# U: the two semantic surface classes differ by the actual 4.67 mm web wall.
u_value, u_node = three_web_config()
outer_owner, outer_plate, outer = apply_case(
    doc, u_value, u_node, 0., attachment_mode="Outer", side="FaceA",
    plate_thickness=10.)
u_value, _ = three_web_config()
inner_owner, inner_plate, inner = apply_case(
    doc, u_value, u_node, 3500., attachment_mode="Inner", side="Center",
    plate_thickness=10.)
check("U Outer selects the external web surface",
      outer.attachment.governing_surface_class.value == "Outer"
      and abs(outer.attachment.signed_offset-11.6) < 1e-6)
check("U Inner selects the recessed internal web surface",
      inner.attachment.governing_surface_class.value == "Inner"
      and abs(inner.attachment.signed_offset-6.93) < 1e-6)
check("U Outer/Inner offset difference is the geometric wall thickness",
      abs((outer.attachment.signed_offset-inner.attachment.signed_offset)-4.67) < 1e-6)
check("Outer and Inner align a plate wide face without embedding half thickness",
      max(abs(a-b) for a, b in zip(projected_limits(outer_plate.Shape, outer),
                                   (11.6, 21.6))) < 1e-6
      and max(abs(a-b) for a, b in zip(projected_limits(inner_plate.Shape, inner),
                                      (-3.07, 6.93))) < 1e-6)

# Side B remains independent from AttachmentMode.
u_value, _ = three_web_config()
side_b_owner, side_b_plate, side_b = apply_case(
    doc, u_value, u_node, 7000., attachment_mode="Outer", side="FaceB",
    plate_thickness=10.)
check("Outer plus Side B selects the opposite external family",
      side_b.attachment.signed_offset < 0.
      and abs(projected_limits(side_b_plate.Shape, side_b)[1]
              -side_b.attachment.signed_offset) < 1e-6)

# Center is a physical assembly datum, including equal-orientation SpacedPair.
assembly_owners = []
for index, mode in enumerate(("DoubleAngle", "DoubleChannelInward", "SpacedPair")):
    value, node = three_web_config()
    role = value["role_specs"]["DIAGONAL"]
    if mode == "DoubleChannelInward":
        role["profile_ref"] = copy.deepcopy(value["role_specs"]["BOTTOM_CHORD"]["profile_ref"])
    value["role_specs"]["DIAGONAL"] = configure_assembly(role, mode, 100.)
    owner, plate, outline = apply_case(
        doc, value, node, 10500.+index*3500., attachment_mode="Center",
        plate_thickness=10.)
    assembly_owners.append(owner)
    check(mode+" Center uses one physical assembly mid-plane plate",
          len(owner.GeneratedGussetPlates) == 1
          and outline.attachment.kind == "AssemblyMidPlane"
          and abs(outline.attachment.signed_offset) < 1e-7)
double_owner = assembly_owners[0]

# Unique semantic caps in Pratt/K/DuoPitch, without a cap on Through.
value, node = three_web_config()
parallel_owner, parallel_plate, parallel = apply_case(doc, value, node, 21000.)
parallel_caps = [edge for edge in parallel.semantic_edges if edge.kind == "WEB_END_CAP"]
check("parallel chord Pratt node has one exposed cap for each of three webs",
      len(parallel_caps) == 3
      and len({edge.participant_key for edge in parallel_caps}) == 3)

value, node = k_config(False)
k_owner, k_plate, k_outline = apply_case(doc, value, node, 24500.)
k_candidate = build_candidate(truss.config_from_object(k_owner))
through = {item.participant_key for item in connection_participants(k_candidate, node)
           if item.end == "Through"}
k_caps = [edge for edge in k_outline.semantic_edges if edge.kind == "WEB_END_CAP"]
check("K keeps Through continuous and caps only the two terminal diagonals",
      len(k_caps) == 2 and not through.intersection(
          edge.participant_key for edge in k_caps))

ridge_owners = []
for index, apex in enumerate((.5, .37)):
    value = ridge_config(apex, 1100.-index*200., inclined=bool(index))
    owner, plate, outline = apply_case(doc, value, "T_S_APEX", 28000.+index*3500.)
    ridge_owners.append(owner)
    caps = [edge for edge in outline.semantic_edges if edge.kind == "WEB_END_CAP"]
    check(("symmetric" if apex == .5 else "asymmetric")
          +" DuoPitch has one cap per terminal web and two chord boundaries",
          len(caps) == len({edge.participant_key for edge in caps}) == 3
          and sum(edge.kind == "CHORD_BOUNDARY"
                  for edge in outline.semantic_edges) == 2)

# Default, compact UX, shared pipeline and identity update.
check("a genuinely new Gusset starts at 10 mm",
      gusset_thickness_for_transition("new-node") == 10.)
check("an existing 8 mm Gusset value is preserved",
      gusset_thickness_for_transition("node", dict(
          form="Gusset", schema_version=2,
          gusset=dict(plate_thickness=8.))) == 8.)
check("OK attachment produces no editor footer report",
      attachment_warning_messages((outer,)) == ())
preview_shape = build_gusset_shape(outer)
check("preview and persistent Shape use identical C6-E geometry",
      preview_shape.distToShape(outer_plate.Shape)[0] < 1e-7
      and abs(preview_shape.Volume-outer_plate.Shape.Volume) < 1e-6)
old_name = outer_plate.Name
changed = truss.config_from_object(outer_owner)
changed["connection_intents"][u_node]["gusset"]["attachment_mode"] = "Inner"
outer_owner = truss.apply_truss(doc, changed, outer_owner)
check("AttachmentMode update preserves StructuralGussetPlate identity",
      outer_owner.GeneratedGussetPlates[0].Name == old_name
      and outer_owner.GeneratedGussetPlates[0].AttachmentMode == "Inner")

doc.recompute()
doc.saveAs(PATH)
saved = {owner.Name: tuple(item.Name for item in owner.GeneratedGussetPlates)
         for owner in (outer_owner, inner_owner, side_b_owner, parallel_owner,
                       k_owner)+tuple(assembly_owners)+tuple(ridge_owners)}
screen_names = (outer_owner.Name, inner_owner.Name, parallel_owner.Name,
                ridge_owners[0].Name, double_owner.Name)
App.closeDocument(doc.Name)
doc = App.openDocument(PATH)
check("save/reopen preserves mode, valid Shapes and Gusset registries", all(
      tuple(item.Name for item in doc.getObject(name).GeneratedGussetPlates) == names
      and all("AttachmentMode" in item.PropertiesList and item.Shape.isValid()
              for item in doc.getObject(name).GeneratedGussetPlates)
      for name, names in saved.items()))

screens = (
    screenshot(doc.getObject(screen_names[0]), "gusset-c6e-u-outer-axon.png", True),
    screenshot(doc.getObject(screen_names[1]), "gusset-c6e-u-inner-axon.png", True),
    screenshot(doc.getObject(screen_names[2]), "gusset-c6e-parallel-front.png"),
    screenshot(doc.getObject(screen_names[3]), "gusset-c6e-duopitch-front.png"),
    screenshot(doc.getObject(screen_names[4]), "gusset-c6e-double-angle-center.png", True),
)
check("five focused C6-E screenshots were generated",
      all(os.path.getsize(path) > 0 for path in screens))

doc.saveAs(PATH)
with open(os.path.join(OUTPUT, "gate-result.json"), "w", encoding="utf-8") as stream:
    json.dump(dict(freecad=App.Version(), checks=checks, document=PATH,
                   screenshots=screens), stream, ensure_ascii=False, indent=2)

print("C6-E manual gate OK:", len(checks), "checks")
App.closeDocument(doc.Name)
Gui.getMainWindow().close()

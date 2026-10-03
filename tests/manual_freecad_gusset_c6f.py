"""Focused FreeCAD 1.1.3 visual/numeric gate for C6-F Gussets."""

import copy
import json
import os
import sys
import traceback
import types

OUTPUT = os.path.join(os.getcwd(), "test-results", "gusset-c6f")
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
from freecad.SteelStructures.connections import (
    GussetAttachmentMode, GussetSide, attachment_side_options,
    attachment_warning_messages,
)
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.connections import gusset_thickness_for_transition
from freecad.SteelStructures.trusses.gusset_freecad import build_gusset_shape
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate
from test_connections_c5b_polish import three_web_config
from test_connections_c5b_through import k_config
from test_gusset_attachment_c6d import _profile_surfaces
from test_gusset_plate_c6a import configured
from test_ridge_fitting import ridge_config
from test_truss_assemblies import config as warren_config

checks = []
PATH = os.path.join(OUTPUT, "GussetC6F.FCStd")


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def number(value):
    return float(value.Value) if hasattr(value, "Value") else float(value)


def shifted(value, y):
    value = copy.deepcopy(value)
    delta = y-value["start"][1]
    value["start"][1] += delta
    value["end"][1] += delta
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


def screenshot(doc, owner, name, axonometric=False):
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


doc = App.newDocument("GussetC6F")
doc.UndoMode = 1

# Physical U placements: the plate contact face is on the wall and thickness
# grows to free space on both Outer and Inner.
value, node = three_web_config()
u_node = node
outer_owner, outer_plate, outer = apply_case(
    doc, value, node, 0., attachment_mode="Outer", side="FaceA",
    plate_thickness=10.)
value, _ = three_web_config()
inner_owner, inner_plate, inner = apply_case(
    doc, value, node, 3500., attachment_mode="Inner", side="Center",
    plate_thickness=10.)
check("U Outer contact is external and grows outward",
      abs(outer.attachment.signed_offset-11.6) < 1e-6
      and projected_limits(outer_plate.Shape, outer) == (11.6, 21.6))
inner_limits = projected_limits(inner_plate.Shape, inner)
check("U Inner contact is inside the channel and does not enter the web wall",
      abs(inner.attachment.signed_offset-6.93) < 1e-6
      and max(abs(a-b) for a, b in zip(inner_limits, (-3.07, 6.93))) < 1e-6)
check("U wall thickness is derived from the two contact surfaces",
      abs(outer.attachment.signed_offset-inner.attachment.signed_offset-4.67) < 1e-6)
check("Outer UI sides exclude Center while Inner retains a physical Center choice",
      GussetSide.CENTER not in attachment_side_options(
          outer.attachment.candidates, GussetAttachmentMode.OUTER)
      and GussetSide.CENTER in attachment_side_options(
          inner.attachment.candidates, GussetAttachmentMode.INNER))

rhs = _profile_surfaces("RHS 60x40x1,2")
chs = _profile_surfaces("CHS 88,90x3")
check("RHS exposes no closed-void Inner surface",
      rhs and all(value.surface_class.value == "Outer" for value in rhs))
check("CHS invents no planar attachment surface", chs == ())

# Physical assembly gap and one persistent plate.
value, node = three_web_config()
role = copy.deepcopy(value["role_specs"]["DIAGONAL"])
role["profile_ref"] = profile_catalog.ref_for_designation("W 150 x 13,0").__dict__
value["role_specs"]["DIAGONAL"] = configure_assembly(role, "SpacedPair", 120.)
gap_owner, gap_plate, gap = apply_case(
    doc, value, node, 7000., attachment_mode="Center", side="Center",
    plate_thickness=10.)
check("SpacedPair Center uses the real 20 mm physical gap",
      gap.attachment.kind == "AssemblyMidPlane"
      and abs(gap.attachment.plate_low+5.) < 1e-6
      and abs(gap.attachment.plate_high-5.) < 1e-6)
check("assembly gap creates exactly one Gusset plate",
      len(gap_owner.GeneratedGussetPlates) == 1)

# Pair bridge, K/Through and ridge exclusions.
bridge_owner, bridge_plate, bridge = apply_case(
    doc, warren_config(), "B_S_MAIN_1_2", 10500.)
bridges = [edge for edge in bridge.semantic_edges if edge.kind == "WEB_SECTOR_BRIDGE"]
caps = [edge for edge in bridge.semantic_edges if edge.kind == "WEB_END_CAP"]
check("two terminal diagonals create two caps and one straight bridge",
      len(caps) == 2 and len(bridges) == 1)
check("bridge follows the parallel chord", abs(bridges[0].end[1]-bridges[0].start[1]) < 1e-7)
value, node = k_config(False)
k_owner, _k_plate, k_outline = apply_case(doc, value, node, 14000.)
check("K Through receives no artificial bridge",
      not any(edge.kind == "WEB_SECTOR_BRIDGE" for edge in k_outline.semantic_edges))
ridge_owner, _ridge_plate, ridge = apply_case(
    doc, ridge_config(.37, 1100.), "T_S_APEX", 17500.)
check("DuoPitch keeps chord boundaries and no artificial bridge",
      sum(edge.kind == "CHORD_BOUNDARY" for edge in ridge.semantic_edges) == 2
      and not any(edge.kind == "WEB_SECTOR_BRIDGE" for edge in ridge.semantic_edges))

# Terminal clipping is stronger than exaggerated free margin/overlap.
terminal_owners = []
for index, (terminal, predicate) in enumerate((
        ("N_S_START", lambda x: x >= -1e-7),
        ("N_S_END", lambda x: x <= 1e-7))):
    owner, _plate, outline = apply_case(
        doc, ridge_config(diagonals=False), terminal, 21000.+index*3500.,
        edge_margin=500., member_overlap=1000.)
    terminal_owners.append(owner)
    check(terminal+" has one semantic terminal boundary",
          sum(edge.kind == "TERMINAL_BOUNDARY" for edge in outline.semantic_edges) == 1)
    check(terminal+" does not exceed the chord closure",
          all(predicate(point[0]) for point in outline.points))
visual_terminal_owner, _visual_terminal_plate, visual_terminal = apply_case(
    doc, ridge_config(diagonals=False), "N_S_START", 28000.)
check("normal terminal plate remains clipped at the left closure",
      all(point[0] >= -1e-7 for point in visual_terminal.points))

# Shared geometry, compact warnings, persistence and per-truss default.
check("preview and document use the identical placement/outline pipeline",
      build_gusset_shape(outer).distToShape(outer_plate.Shape)[0] < 1e-7)
check("resolved OK placement emits no permanent footer text",
      attachment_warning_messages((outer,)) == ())
inner_warnings = attachment_warning_messages((inner,))
check("warnings are compact and actionable", len(inner_warnings) <= 3)
check("new truss default is 10 mm",
      abs(number(outer_owner.DefaultGussetThickness)-10.) < 1e-7)

changed = truss.config_from_object(outer_owner)
changed["default_gusset_thickness"] = 20.
changed["connection_intents"][u_node]["gusset"]["plate_thickness"] = 20.
outer_name = outer_owner.Name
outer_owner = truss.apply_truss(doc, changed, outer_owner)
check("accepted thickness persists as the per-truss default",
      abs(number(outer_owner.DefaultGussetThickness)-20.) < 1e-7)
doc.undo()
check("Undo restores the previous per-truss default",
      abs(number(doc.getObject(outer_name).DefaultGussetThickness)-10.) < 1e-7)
doc.redo()
outer_owner = doc.getObject(outer_name)
check("Redo reapplies the per-truss default",
      abs(number(outer_owner.DefaultGussetThickness)-20.) < 1e-7)
check("a new Gusset copies the saved 20 mm default",
      gusset_thickness_for_transition("new", None,
                                      number(outer_owner.DefaultGussetThickness)) == 20.)
candidate_only = truss.config_from_object(outer_owner)
candidate_only["default_gusset_thickness"] = 30.
check("candidate-only edit (Cancel) does not mutate the owner default",
      abs(number(outer_owner.DefaultGussetThickness)-20.) < 1e-7)

doc.recompute()
doc.saveAs(PATH)
saved = {owner.Name: tuple(item.Name for item in owner.GeneratedGussetPlates)
         for owner in (outer_owner, inner_owner, gap_owner, bridge_owner, k_owner,
                       ridge_owner, visual_terminal_owner)+tuple(terminal_owners)}
screen_names = (outer_owner.Name, inner_owner.Name, bridge_owner.Name,
                visual_terminal_owner.Name)
App.closeDocument(doc.Name)
doc = App.openDocument(PATH)
check("save/reopen preserves registries, Shapes and DefaultGussetThickness", all(
      tuple(item.Name for item in doc.getObject(name).GeneratedGussetPlates) == names
      and all(item.Shape.isValid() for item in doc.getObject(name).GeneratedGussetPlates)
      for name, names in saved.items())
      and abs(number(doc.getObject(outer_name).DefaultGussetThickness)-20.) < 1e-7)
reopened = doc.getObject(screen_names[1])
reopened_outlines, _ = preliminary_gusset_outlines(
    build_candidate(truss.config_from_object(reopened)))
check("warnings are deterministically rebuilt after reopen",
      attachment_warning_messages(reopened_outlines) == inner_warnings)

screens = (
    screenshot(doc, doc.getObject(screen_names[0]), "gusset-c6f-u-outer-axon.png", True),
    screenshot(doc, doc.getObject(screen_names[1]), "gusset-c6f-u-inner-axon.png", True),
    screenshot(doc, doc.getObject(screen_names[2]), "gusset-c6f-web-bridge-front.png"),
    screenshot(doc, doc.getObject(screen_names[3]), "gusset-c6f-terminal-front.png"),
)
check("four focused C6-F screenshots were generated",
      all(os.path.getsize(path) > 0 for path in screens))

with open(os.path.join(OUTPUT, "gate-result.json"), "w", encoding="utf-8") as stream:
    json.dump(dict(freecad=App.Version(), checks=checks, document=PATH,
                   screenshots=screens), stream, ensure_ascii=False, indent=2)

print("C6-F manual gate OK:", len(checks), "checks")
App.closeDocument(doc.Name)
Gui.getMainWindow().close()

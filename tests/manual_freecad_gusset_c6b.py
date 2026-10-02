"""Focused FreeCAD 1.1.3 gate for persistent C6-B gusset plates."""

import copy
import json
import os
import sys
import traceback

_EARLY_OUTPUT = os.path.join(os.getcwd(), "test-results", "gusset-c6b")
os.makedirs(_EARLY_OUTPUT, exist_ok=True)
def _report_exception(kind, value, tb):
    with open(os.path.join(_EARLY_OUTPUT, "gate-error.txt"), "w", encoding="utf-8") as stream:
        traceback.print_exception(kind, value, tb, file=stream)
    traceback.print_exception(kind, value, tb)
sys.excepthook = _report_exception

import FreeCAD as App
import FreeCADGui as Gui

ROOT = os.getcwd()
sys.path.insert(0, ROOT)
for module_name in tuple(sys.modules):
    if module_name == "freecad" or module_name.startswith("freecad.SteelStructures"):
        sys.modules.pop(module_name, None)

from freecad.SteelStructures import truss
from freecad.SteelStructures.interactive.truss_controller import TrussController
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.trusses.gusset_freecad import build_gusset_shape
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.models import TopologyEdge, TopologyGraph
from freecad.SteelStructures.trusses.realization import build_candidate

OUTPUT = os.path.join(ROOT, "test-results", "gusset-c6b")
os.makedirs(OUTPUT, exist_ok=True)
PATH = os.path.join(OUTPUT, "GussetC6B.FCStd")
checks = []


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def base(preset="Pratt", offset=0.):
    value = truss.default_config()
    value.update(span=2400., height=700., panel_count=4, topology_preset=preset,
                 start=[0., offset, 0.], end=[2400., offset, 0.])
    return value


def useful_node(value):
    candidate = build_candidate(value)
    return next(node.key for node in candidate.graph.nodes
                if sum(p.role in ("DIAGONAL", "VERTICAL", "END_POST")
                       for p in connection_participants(candidate, node.key)) >= 2)


def gusset(value, node, side="Center", margin=25., overlap=150., thickness=8.):
    value["connection_intents"] = {node: dict(form="Gusset", gusset=dict(
        plate_thickness=thickness, normal_clearance=2., axial_clearance=20.,
        edge_margin=margin, member_overlap=overlap, side=side))}
    return value


def direct(value, node):
    value["connection_intents"] = {node: dict(form="Direct", direct_policy="Priority")}
    return value


def only_plate(owner):
    if len(owner.GeneratedGussetPlates) != 1:
        raise AssertionError("expected one persistent plate")
    return owner.GeneratedGussetPlates[0]


doc = App.newDocument("GussetC6B")
doc.UndoMode = 1

value = base()
node = useful_node(value)
owner = truss.apply_truss(doc, value)
owner_name = owner.Name
member_names = tuple(member.Name for member in owner.GeneratedMembers)
edge_count = len(build_candidate(value).graph.edges)
check("truss without Gusset has no plate", not owner.GeneratedGussetPlates)

owner = truss.apply_truss(doc, direct(copy.deepcopy(value), node), owner)

configured = gusset(copy.deepcopy(value), node)
owner = truss.apply_truss(doc, configured, owner)
plate = only_plate(owner)
plate_name = plate.Name
check("StructuralGussetPlate ownership/tree", plate.TypeId == "Part::FeaturePython"
      and plate.ParentTruss == owner and plate in owner.ViewObject.Proxy.claimChildren())
check("stable Node identity", plate.StableKey == node+":gusset-plate" and plate.NodeKey == node)
check("controlled properties and physical results", abs(plate.Thickness.Value-8.) < 1e-9
      and abs(plate.EdgeMargin.Value-25.) < 1e-9 and abs(plate.MemberOverlap.Value-150.) < 1e-9
      and plate.PlateArea.Value > 0 and abs(plate.Volume.Value-plate.Shape.Volume) < 1e-6)
check("member/topology counts unchanged", member_names == tuple(m.Name for m in owner.GeneratedMembers)
      and edge_count == len(build_candidate(configured).graph.edges))

doc.undo(); doc.recompute(); owner = doc.getObject(owner_name)
check("Undo Direct to Gusset removes plate", not owner.GeneratedGussetPlates
      and doc.getObject(plate_name) is None)
doc.redo(); doc.recompute(); owner = doc.getObject(owner_name); plate = only_plate(owner)
check("Redo Direct to Gusset restores same plate", plate.Name == plate_name and plate.Shape.isValid())

plate.Label = "Minha chapa"
before_volume = plate.Shape.Volume
changed = truss.config_from_object(owner)
changed["connection_intents"][node]["gusset"]["edge_margin"] = 45.
owner = truss.apply_truss(doc, changed, owner); plate = only_plate(owner)
check("margin updates same identity and preserves rename", plate.Name == plate_name
      and plate.Label == "Minha chapa" and plate.Shape.Volume > before_volume)

before_volume = plate.Shape.Volume
changed = truss.config_from_object(owner)
changed["connection_intents"][node]["gusset"]["member_overlap"] = 260.
owner = truss.apply_truss(doc, changed, owner); plate = only_plate(owner)
check("overlap updates same identity", plate.Name == plate_name and plate.Shape.Volume > before_volume)

before_area, before_volume = plate.PlateArea.Value, plate.Shape.Volume
changed = truss.config_from_object(owner)
changed["connection_intents"][node]["gusset"]["plate_thickness"] = 12.
owner = truss.apply_truss(doc, changed, owner); plate = only_plate(owner)
check("thickness keeps area and scales volume", plate.Name == plate_name
      and abs(plate.PlateArea.Value-before_area) < 1e-6 and plate.Shape.Volume > before_volume)

for side in ("FaceA", "FaceB"):
    changed = truss.config_from_object(owner)
    changed["connection_intents"][node]["gusset"]["side"] = side
    owner = truss.apply_truss(doc, changed, owner); plate = only_plate(owner)
    check("side "+side+" same identity", plate.Name == plate_name and str(plate.Side) == side)

before_shape = plate.Shape.copy()
before_margin = plate.EdgeMargin.Value
changed = truss.config_from_object(owner)
changed["connection_intents"][node]["gusset"]["edge_margin"] = 60.
owner = truss.apply_truss(doc, changed, owner)
doc.undo(); doc.recompute(); owner = doc.getObject(owner_name); plate = only_plate(owner)
check("Undo parametric edit restores property/Shape", abs(plate.EdgeMargin.Value-before_margin) < 1e-9
      and abs(plate.Shape.Volume-before_shape.Volume) < 1e-6)
doc.redo(); doc.recompute(); owner = doc.getObject(owner_name); plate = only_plate(owner)
check("Redo parametric edit reapplies same identity", plate.Name == plate_name
      and abs(plate.EdgeMargin.Value-60.) < 1e-9)

changed = truss.config_from_object(owner)
changed["height"] = 850.
owner = truss.apply_truss(doc, changed, owner); plate = only_plate(owner)
check("height update preserves NodeKey/object and changes Shape", plate.Name == plate_name
      and plate.NodeKey == node and abs(plate.Shape.Volume-before_shape.Volume) > 1e-3)

changed = truss.config_from_object(owner)
changed["connection_intents"][node] = dict(form="Direct", direct_policy="Priority")
owner = truss.apply_truss(doc, changed, owner)
check("Gusset to Direct removes object", not owner.GeneratedGussetPlates
      and doc.getObject(plate_name) is None)
doc.undo(); doc.recompute(); owner = doc.getObject(owner_name); plate = only_plate(owner)
check("Undo removal restores plate", plate.Name == plate_name and plate.ParentTruss == owner)
doc.redo(); doc.recompute(); owner = doc.getObject(owner_name)
check("Redo removal removes plate", not owner.GeneratedGussetPlates)
doc.undo(); doc.recompute(); owner = doc.getObject(owner_name); plate = only_plate(owner)

state_before = owner.AppliedState
names_before = tuple(obj.Name for obj in doc.Objects)
visibility_before = bool(plate.ViewObject.Visibility)
controller = TrussController(doc, owner)
controller.preview3d(truss.config_from_object(owner), enabled=True)
check("preview hides persistent plate without document objects",
      not plate.ViewObject.Visibility and tuple(obj.Name for obj in doc.Objects) == names_before)
controller.cancel()
check("Cancel restores visibility/state", bool(plate.ViewObject.Visibility) == visibility_before
      and owner.AppliedState == state_before and tuple(obj.Name for obj in doc.Objects) == names_before)

candidate = build_candidate(truss.config_from_object(owner))
outline = preliminary_gusset_outlines(candidate)[0][0]
preview_shape = build_gusset_shape(outline)
check("document Shape equals C6-A pipeline", abs(preview_shape.Volume-plate.Shape.Volume) < 1e-6
      and preview_shape.distToShape(plate.Shape)[0] < 1e-7)

k_value = base("K", 3500.)
k_node = next(n.key for n in build_candidate(k_value).graph.nodes
              if any(p.end == "Through" for p in connection_participants(build_candidate(k_value), n.key)))
k_owner = truss.apply_truss(doc, gusset(k_value, k_node, "Center"))
k_owner_name = k_owner.Name
k_plate = only_plate(k_owner)
through = next(p for p in connection_participants(build_candidate(k_owner.Proxy and
    truss.config_from_object(k_owner)), k_node) if p.end == "Through")
check("K creates one plate and keeps Through semantic", k_plate.NodeKey == k_node
      and through.continuous_through
      and preliminary_gusset_outlines(build_candidate(truss.config_from_object(k_owner)))[0][0]
          .spec.participant_keys.count(through.participant_key) == 1)

ridge_value = base("Pratt", 7000.)
ridge_value.update(envelope_type="DuoPitch", apex_position=.37, height=900., panel_count=8)
ridge_candidate = build_candidate(ridge_value)
apex = ridge_candidate.graph.node("T_S_APEX")
bottom = sorted((n for n in ridge_candidate.graph.nodes if n.key.startswith("B_")
                 and abs(n.position_local[0]-apex.position_local[0]) > 1e-7),
                key=lambda n: abs(n.position_local[0]-apex.position_local[0]))
targets = (next(n for n in bottom if n.position_local[0] < apex.position_local[0]),
           next(n for n in bottom if n.position_local[0] > apex.position_local[0]))
edges = list(ridge_candidate.graph.edges)
for index, target in enumerate(targets):
    if not any({edge.start_node_key, edge.end_node_key} == {target.key, apex.key} for edge in edges):
        edges.append(TopologyEdge("c6b-ridge-"+str(index), target.key, apex.key, "DIAGONAL"))
ridge_value.update(topology_mode="Custom", topology_preset="Custom", base_preset="Pratt",
                   custom_topology=materialize(TopologyGraph(ridge_candidate.graph.nodes, tuple(edges)),
                                               ridge_candidate.config))
ridge_owner = truss.apply_truss(doc, gusset(ridge_value, apex.key, "FaceA"))
ridge_plate = only_plate(ridge_owner)
check("DuoPitch ridge is one FaceA plate", ridge_plate.NodeKey == apex.key
      and str(ridge_plate.Side) == "FaceA")

double_value = base("Pratt", 10500.)
double_node = useful_node(double_value)
double_value["role_specs"]["DIAGONAL"] = configure_assembly(
    double_value["role_specs"]["DIAGONAL"], "DoubleAngle", 60.)
double_owner = truss.apply_truss(doc, gusset(double_value, double_node, "FaceB"))
double_plate = only_plate(double_owner)
check("DoubleAngle creates one FaceB plate", len(double_owner.GeneratedGussetPlates) == 1
      and str(double_plate.Side) == "FaceB")

channel_value = base("Pratt", 14000.)
channel_node = useful_node(channel_value)
channel_value["role_specs"]["DIAGONAL"]["profile_ref"] = copy.deepcopy(
    channel_value["role_specs"]["TOP_CHORD"]["profile_ref"])
channel_value["role_specs"]["DIAGONAL"] = configure_assembly(
    channel_value["role_specs"]["DIAGONAL"], "DoubleChannelInward", 140.)
channel_owner = truss.apply_truss(doc, gusset(channel_value, channel_node))
check("DoubleChannel creates one plate", len(channel_owner.GeneratedGussetPlates) == 1)

spaced_value = base("Pratt", 17500.)
spaced_node = useful_node(spaced_value)
spaced_value["role_specs"]["DIAGONAL"] = configure_assembly(
    spaced_value["role_specs"]["DIAGONAL"], "SpacedPair", 120.)
spaced_owner = truss.apply_truss(doc, gusset(spaced_value, spaced_node))
check("SpacedPair creates one plate", len(spaced_owner.GeneratedGussetPlates) == 1)

terminal_value = base("Pratt", 21000.)
terminal_candidate = build_candidate(terminal_value)
terminal_node = next(n.key for n in terminal_candidate.graph.nodes
                     if abs(n.position_local[0]) < 1e-7
                     and len(connection_participants(terminal_candidate, n.key)) >= 2)
terminal_owner = truss.apply_truss(doc, gusset(terminal_value, terminal_node))
check("terminal NodeKey creates one plate", only_plate(terminal_owner).NodeKey == terminal_node)

inclined_value = base("Pratt", 24500.)
inclined_value.update(start=[20., 24500., 40.], end=[2420., 24500., 40.],
                      plane_normal=[0., -.6, .8])
inclined_node = useful_node(inclined_value)
inclined_owner = truss.apply_truss(doc, gusset(inclined_value, inclined_node))
inclined_outline = preliminary_gusset_outlines(
    build_candidate(truss.config_from_object(inclined_owner)))[0][0]
check("inclined plane persists correct local normal", all(abs(a-b) < 1e-9 for a, b in
      zip(inclined_outline.spec.frame.normal, inclined_value["plane_normal"])))

legacy_value = base("Pratt", 28000.)
legacy_node = useful_node(legacy_value)
legacy_owner = truss.apply_truss(doc, legacy_value)
legacy_gusset = gusset(copy.deepcopy(legacy_value), legacy_node)
truss.set_config(legacy_owner, legacy_gusset)
doc.recompute()
check("ordinary execute does not materialize old Gusset intent",
      not legacy_owner.GeneratedGussetPlates and legacy_owner.NeedsRegeneration)
legacy_owner = truss.apply_truss(doc, legacy_gusset, legacy_owner)
check("explicit regeneration materializes old Gusset intent",
      len(legacy_owner.GeneratedGussetPlates) == 1)

topology_value = base("Pratt", 31500.)
topology_value.update(envelope_type="DuoPitch", apex_position=.37, height=900., panel_count=8)
topology_owner = truss.apply_truss(doc, gusset(topology_value, "T_S_APEX"))
topology_name = topology_owner.Name
topology_plate_name = only_plate(topology_owner).Name
removed_node = truss.config_from_object(topology_owner)
removed_node.update(envelope_type="Parallel", topology_mode="Preset", topology_preset="Pratt")
topology_owner = truss.apply_truss(doc, removed_node, topology_owner)
check("topology removal deletes orphan plate", not topology_owner.GeneratedGussetPlates
      and doc.getObject(topology_plate_name) is None)
doc.undo(); doc.recompute(); topology_owner = doc.getObject(topology_name)
check("Undo topology removal restores same plate", only_plate(topology_owner).Name == topology_plate_name)

doc.recompute()
doc.saveAs(PATH)
saved = {current.Name: (tuple(plate.Name for plate in current.GeneratedGussetPlates), current.AppliedState)
         for current in (owner, k_owner, ridge_owner, double_owner, channel_owner,
                         spaced_owner, terminal_owner, inclined_owner)}
saved[legacy_owner.Name] = (tuple(plate.Name for plate in legacy_owner.GeneratedGussetPlates),
                            legacy_owner.AppliedState)
saved[topology_owner.Name] = (tuple(plate.Name for plate in topology_owner.GeneratedGussetPlates),
                              topology_owner.AppliedState)
App.closeDocument(doc.Name)
doc = App.openDocument(PATH)
check("save/reopen restores all plate registries", all(
    tuple(plate.Name for plate in doc.getObject(name).GeneratedGussetPlates) == data[0]
    for name, data in saved.items()))
check("save/reopen keeps links/keys/Shapes/results", all(
    plate.ParentTruss == current and plate.StableKey == plate.NodeKey+":gusset-plate"
    and plate.Shape.isValid() and plate.Shape.Volume > 0
    and abs(plate.Shape.Volume-plate.Volume.Value) < 1e-6
    for current in (doc.getObject(name) for name in saved)
    for plate in current.GeneratedGussetPlates))

reopened = doc.getObject(k_owner_name)
before = tuple(plate.Name for plate in reopened.GeneratedGussetPlates)
reopened = truss.apply_truss(doc, truss.config_from_object(reopened), reopened)
check("reapply after reopen creates no duplicate", before == tuple(
    plate.Name for plate in reopened.GeneratedGussetPlates))

doc.saveAs(PATH)
with open(os.path.join(OUTPUT, "gate-result.json"), "w", encoding="utf-8") as stream:
    json.dump({"freecad": App.Version(), "checks": checks, "document": PATH}, stream,
              ensure_ascii=False, indent=2)
print("C6-B manual gate OK:", len(checks), "checks")

"""Focused visual/geometric FreeCAD 1.1.3 gate for C6-C gusset outlines."""

import copy
import json
import math
import os
import sys
import traceback

OUTPUT = os.path.join(os.getcwd(), "test-results", "gusset-c6c")
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
for module_name in tuple(sys.modules):
    if module_name == "freecad" or module_name.startswith("freecad.SteelStructures"):
        sys.modules.pop(module_name, None)

from freecad.SteelStructures import truss
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.connections import (
    connection_participants, resolve_truss_connections,
)
from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.trusses.gusset_freecad import build_gusset_shape
from freecad.SteelStructures.trusses.gussets import (
    _chord_support_lines, _corridors, _selected_participants,
    preliminary_gusset_outlines,
)
from freecad.SteelStructures.trusses.models import TopologyEdge, TopologyGraph
from freecad.SteelStructures.trusses.realization import build_candidate, reference_frame

checks = []
PATH = os.path.join(OUTPUT, "GussetC6C.FCStd")


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def base(preset="Pratt", offset=0.):
    value = truss.default_config()
    value.update(span=2400., height=700., panel_count=4, topology_preset=preset,
                 start=[0., offset, 0.], end=[2400., offset, 0.])
    return value


def node_with_chord(value):
    candidate = build_candidate(value)
    return next(node.key for node in candidate.graph.nodes
                if len(connection_participants(candidate, node.key)) >= 3
                and any(p.role in ("TOP_CHORD", "BOTTOM_CHORD")
                        for p in connection_participants(candidate, node.key)))


def gusset(value, node, margin=25., overlap=150., side="Center"):
    value["connection_intents"] = {node: dict(form="Gusset", gusset=dict(
        plate_thickness=8., normal_clearance=2., axial_clearance=20.,
        edge_margin=margin, member_overlap=overlap, side=side))}
    return value


def ridge_config(apex=.5, height=900., inclined=False, diagonals=True):
    value = base("Pratt")
    value.update(envelope_type="DuoPitch", apex_position=apex, height=height,
                 panel_count=8, left_panels=None, right_panels=None,
                 top_continuity="Continuous", bottom_continuity="Continuous")
    if inclined:
        value.update(start=[20., 30., 40.], end=[2420., 30., 40.],
                     plane_normal=[0., -.6, .8])
    if diagonals:
        candidate = build_candidate(value)
        node = candidate.graph.node("T_S_APEX")
        bottom = sorted((item for item in candidate.graph.nodes if item.key.startswith("B_")
                         and abs(item.position_local[0]-node.position_local[0]) > 1e-7),
                        key=lambda item: abs(item.position_local[0]-node.position_local[0]))
        targets = (next(item for item in bottom if item.position_local[0] < node.position_local[0]),
                   next(item for item in bottom if item.position_local[0] > node.position_local[0]))
        edges = list(candidate.graph.edges)
        for index, target in enumerate(targets):
            if not any({edge.start_node_key, edge.end_node_key} == {target.key, node.key}
                       for edge in edges):
                edges.append(TopologyEdge("c6c-ridge-"+str(index), target.key, node.key,
                                          "DIAGONAL"))
        value.update(topology_mode="Custom", topology_preset="Custom", base_preset="Pratt",
                     custom_topology=materialize(
                         TopologyGraph(candidate.graph.nodes, tuple(edges)), candidate.config))
    return value


def _inputs(value, node, **parameters):
    value = copy.deepcopy(value)
    gusset(value, node, margin=parameters.get("edge_margin", 25.),
           overlap=parameters.get("member_overlap", 150.),
           side=parameters.get("side", "Center"))
    candidate = build_candidate(value)
    local_frame = reference_frame(candidate.config)
    resolution = next(item for item in resolve_truss_connections(candidate, local_frame[3])[0]
                      if item.intent.node_key == node)
    participants = _selected_participants(resolution.intent, resolution.participants)
    runs = {run.key: run for run in candidate.runs}
    corridors = tuple(corridor for participant in participants
                      for run_key in participant.physical_run_keys
                      for corridor in _corridors(candidate, participant, runs[run_key], local_frame))
    supports = _chord_support_lines(participants, corridors)
    outlines, diagnostics = preliminary_gusset_outlines(candidate)
    if diagnostics:
        raise AssertionError([item.message for item in diagnostics])
    return candidate, participants, corridors, supports, next(
        item for item in outlines if item.spec.node_key == node)


def supports_active(outline, supports):
    return all(sum(abs(support.normal[0]*point[0]+support.normal[1]*point[1]
                           -support.offset) < 2e-6 for point in outline.points) >= 2
               for support in supports)


def edges_are_semantic(outline, corridors):
    allowed = []
    for corridor in corridors:
        length = math.hypot(*corridor.direction)
        direction = corridor.direction[0]/length, corridor.direction[1]/length
        allowed.extend((direction, (-direction[1], direction[0])))
    for first, second in zip(outline.points, outline.points[1:]+outline.points[:1]):
        edge = second[0]-first[0], second[1]-first[1]
        length = math.hypot(*edge)
        edge = edge[0]/length, edge[1]/length
        if not any(abs(edge[0]*axis[1]-edge[1]*axis[0]) < 2e-6 for axis in allowed):
            return False
    return True


doc = App.newDocument("GussetC6C")

pratt = base("Pratt", 0.)
pratt_node = node_with_chord(pratt)
_candidate, _participants, corridors, supports, outline = _inputs(pratt, pratt_node)
check("Pratt chord support is active", bool(supports) and supports_active(outline, supports))
check("Pratt has only participant-related edges", edges_are_semantic(outline, corridors))
pratt_owner = truss.apply_truss(doc, gusset(pratt, pratt_node))
pratt_plate = pratt_owner.GeneratedGussetPlates[0]
pratt_name = pratt_plate.Name

warren = base("Warren", 3500.)
warren_node = node_with_chord(warren)
_candidate, _participants, corridors, supports, outline = _inputs(warren, warren_node)
check("Warren chord support is active", bool(supports) and supports_active(outline, supports))
check("Warren has only participant-related edges", edges_are_semantic(outline, corridors))
warren_owner = truss.apply_truss(doc, gusset(warren, warren_node))

before = _inputs(base("Pratt"), pratt_node, edge_margin=5.)
after = _inputs(base("Pratt"), pratt_node, edge_margin=45.)
check("EdgeMargin grows free region", after[-1].area > before[-1].area)
check("EdgeMargin preserves governing chord faces",
      [(s.normal, round(s.offset, 7)) for s in before[-2]]
      == [(s.normal, round(s.offset, 7)) for s in after[-2]])
longer = _inputs(base("Pratt"), pratt_node, member_overlap=260.)[-1]
check("MemberOverlap grows required region", longer.area > after[-1].area)

changed = truss.config_from_object(pratt_owner)
changed["connection_intents"][pratt_node]["gusset"]["edge_margin"] = 45.
pratt_owner = truss.apply_truss(doc, changed, pratt_owner)
check("persistent plate keeps identity after C6-C update",
      pratt_owner.GeneratedGussetPlates[0].Name == pratt_name)

k_value = base("K", 7000.)
k_candidate = build_candidate(k_value)
k_node = next(node.key for node in k_candidate.graph.nodes
              if any(p.end == "Through" for p in connection_participants(k_candidate, node.key)))
k_data = _inputs(k_value, k_node)
through = [p for p in k_data[1] if p.end == "Through"]
check("K keeps one semantic Through participant", len(through) == 1
      and k_data[-1].spec.participant_keys.count(through[0].participant_key) == 1)
check("K outline has only participant-related edges", edges_are_semantic(k_data[-1], k_data[2]))
k_owner = truss.apply_truss(doc, gusset(k_value, k_node))

ridge_symmetric = ridge_config(.5, 1100.)
ridge_symmetric.update(start=[0., 10500., 0.], end=[2400., 10500., 0.])
ridge_data = _inputs(ridge_symmetric, "T_S_APEX")
check("symmetric ridge uses two active chord supports",
      len(ridge_data[-2]) == 2 and supports_active(ridge_data[-1], ridge_data[-2]))
check("symmetric ridge spans both physical branches",
      min(point[0] for point in ridge_data[-1].points) < 0.
      and max(point[0] for point in ridge_data[-1].points) > 0.)
ridge_owner = truss.apply_truss(doc, gusset(ridge_symmetric, "T_S_APEX"))

ridge_asymmetric = ridge_config(.37, 900.)
ridge_asymmetric.update(start=[0., 14000., 0.], end=[2400., 14000., 0.])
asymmetric_data = _inputs(ridge_asymmetric, "T_S_APEX")
check("asymmetric ridge uses both physical branches", len(asymmetric_data[-2]) == 2
      and supports_active(asymmetric_data[-1], asymmetric_data[-2]))
asymmetric_owner = truss.apply_truss(doc, gusset(ridge_asymmetric, "T_S_APEX"))

terminal_value = ridge_config(diagonals=False)
terminal_value.update(start=[0., 17500., 0.], end=[2400., 17500., 0.])
terminal_data = _inputs(terminal_value, "N_S_START")
check("terminal closure uses top and bottom chord supports",
      len(terminal_data[-2]) == 2 and supports_active(terminal_data[-1], terminal_data[-2]))
terminal_owner = truss.apply_truss(doc, gusset(terminal_value, "N_S_START"))

for index, mode in enumerate(("DoubleAngle", "DoubleChannelInward", "SpacedPair")):
    value = base("Pratt", 21000.+index*3500.)
    node = node_with_chord(value)
    role = value["role_specs"]["DIAGONAL"]
    if mode == "DoubleChannelInward":
        role["profile_ref"] = copy.deepcopy(value["role_specs"]["TOP_CHORD"]["profile_ref"])
    value["role_specs"]["DIAGONAL"] = configure_assembly(role, mode, 100.)
    data = _inputs(value, node)
    owner = truss.apply_truss(doc, gusset(value, node))
    check(mode+" keeps one regularized plate", len(owner.GeneratedGussetPlates) == 1
          and edges_are_semantic(data[-1], data[2]))

inclined = ridge_config(.37, 900., inclined=True)
inclined.update(start=[20., 31500., 40.], end=[2420., 31500., 40.])
inclined_data = _inputs(inclined, "T_S_APEX")
check("inclined plane keeps local regularized geometry",
      inclined_data[-1].points == _inputs(ridge_config(.37, 900.), "T_S_APEX")[-1].points)
inclined_owner = truss.apply_truss(doc, gusset(inclined, "T_S_APEX", side="FaceA"))

document_plate = pratt_owner.GeneratedGussetPlates[0]
document_outline = preliminary_gusset_outlines(
    build_candidate(truss.config_from_object(pratt_owner)))[0][0]
preview_shape = build_gusset_shape(document_outline)
check("preview and persistent document use identical C6-C geometry",
      preview_shape.distToShape(document_plate.Shape)[0] < 1e-7
      and abs(preview_shape.Volume-document_plate.Shape.Volume) < 1e-6)

doc.recompute()
doc.saveAs(PATH)
pratt_owner_name, ridge_owner_name, inclined_owner_name = (
    pratt_owner.Name, ridge_owner.Name, inclined_owner.Name)
names = {owner.Name: tuple(plate.Name for plate in owner.GeneratedGussetPlates)
         for owner in (pratt_owner, warren_owner, k_owner, ridge_owner,
                       asymmetric_owner, terminal_owner, inclined_owner)}
doc_name = doc.Name
App.closeDocument(doc_name)
doc = App.openDocument(PATH)
check("save/reopen preserves C6-C plates", all(
      tuple(plate.Name for plate in doc.getObject(owner_name).GeneratedGussetPlates) == plate_names
      and all(plate.Shape.isValid() for plate in doc.getObject(owner_name).GeneratedGussetPlates)
      for owner_name, plate_names in names.items()))

view = Gui.activeDocument().activeView()


def screenshot_owner(owner_name, filename, axonometric=False):
    for item in doc.Objects:
        if hasattr(item, "ViewObject") and item.ViewObject is not None:
            item.ViewObject.Visibility = False
    owner = doc.getObject(owner_name)
    for item in tuple(owner.GeneratedMembers)+tuple(owner.GeneratedGussetPlates):
        item.ViewObject.Visibility = True
    view.viewAxonometric() if axonometric else view.viewFront()
    view.fitAll()
    path = os.path.join(OUTPUT, filename)
    view.saveImage(path, 1600, 900, "White")
    return path


screenshots = [screenshot_owner(pratt_owner_name, "gusset-c6c-pratt-front.png"),
               screenshot_owner(ridge_owner_name, "gusset-c6c-ridge-front.png"),
               screenshot_owner(inclined_owner_name, "gusset-c6c-inclined-axon.png", True)]
check("focused visual screenshots generated", all(os.path.getsize(path) > 0
                                                    for path in screenshots))

with open(os.path.join(OUTPUT, "gate-result.json"), "w", encoding="utf-8") as stream:
    json.dump(dict(freecad=App.Version(), checks=checks, document=PATH,
                   screenshots=screenshots),
              stream, ensure_ascii=False, indent=2)

Gui.activeDocument().activeView().fitAll()

"""Short real FreeCAD 1.1.3/OCC gate for preliminary C6-A gusset plates.

Run with the repository root as cwd using FreeCAD.exe.
"""

import copy
import json
import math
import os
import sys
from dataclasses import asdict

import FreeCAD as App
import FreeCADGui as Gui

ROOT = os.getcwd()
sys.path.insert(0, ROOT)
for module_name in tuple(sys.modules):
    if module_name == "freecad" or module_name.startswith("freecad.SteelStructures"):
        sys.modules.pop(module_name, None)

from freecad.SteelStructures import profile_catalog, truss
from freecad.SteelStructures.connections import extrusion_limits
from freecad.SteelStructures.interactive.truss_controller import TrussController
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.trusses.gusset_freecad import build_gusset_shape
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.models import TopologyEdge, TopologyGraph
from freecad.SteelStructures.trusses.realization import build_candidate

OUTPUT = os.path.join(ROOT, "test-results", "gusset-c6a")
os.makedirs(OUTPUT, exist_ok=True)
checks = []


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def base(preset="Pratt"):
    value = truss.default_config()
    value.update(span=2400., height=700., panel_count=4,
                 start=[0., 0., 0.], end=[2400., 0., 0.], topology_preset=preset)
    return value


def useful_node(value, terminal=False):
    candidate = build_candidate(value)
    nodes = sorted(candidate.graph.nodes, key=lambda n: n.position_local[0])
    if terminal:
        return next(node.key for node in nodes
                    if len(connection_participants(candidate, node.key)) >= 2)
    return next(node.key for node in nodes
                if sum(p.role in ("DIAGONAL", "VERTICAL", "END_POST")
                       for p in connection_participants(candidate, node.key)) >= 2)


def configure(value, node, side="Center", margin=25., overlap=150.):
    value["connection_intents"] = {node: dict(form="Gusset", gusset=dict(
        plate_thickness=8., normal_clearance=2., axial_clearance=20.,
        edge_margin=margin, member_overlap=overlap, side=side))}
    return value


def plate(value, label):
    candidate = build_candidate(value)
    outlines, diagnostics = preliminary_gusset_outlines(candidate)
    if len(outlines) != 1:
        raise AssertionError(label+": outline")
    outline = outlines[0]
    shape = build_gusset_shape(outline)
    check(label+": outline/OCC/volume", not diagnostics and shape.isValid()
          and not shape.isNull() and shape.Volume > 0.
          and abs(shape.Volume-outline.area*outline.spec.plate_thickness) < 1e-4)
    return candidate, outline, shape


value = base("Pratt")
node = useful_node(value)
candidate, simple, _shape = plate(configure(value, node), "Pratt")
check("Pratt participant directions", len(simple.spec.participant_keys) >= 2)

value = base("K")
candidate = build_candidate(value)
node = next(node.key for node in candidate.graph.nodes
            if any(p.end == "Through" for p in connection_participants(candidate, node.key)))
candidate, k_plate, _shape = plate(configure(value, node), "K passante")
through = next(p for p in connection_participants(candidate, node) if p.end == "Through")
check("K through remains one semantic participant",
      k_plate.spec.participant_keys.count(through.participant_key) == 1)

value = base("Pratt")
value.update(envelope_type="DuoPitch", apex_position=.37, height=900., panel_count=8)
candidate = build_candidate(value)
apex = candidate.graph.node("T_S_APEX")
bottom = sorted((n for n in candidate.graph.nodes if n.key.startswith("B_")
                 and abs(n.position_local[0]-apex.position_local[0]) > 1e-7),
                key=lambda n: abs(n.position_local[0]-apex.position_local[0]))
targets = (next(n for n in bottom if n.position_local[0] < apex.position_local[0]),
           next(n for n in bottom if n.position_local[0] > apex.position_local[0]))
edges = list(candidate.graph.edges)
for index, target in enumerate(targets):
    if not any({edge.start_node_key, edge.end_node_key} == {target.key, apex.key}
               for edge in edges):
        edges.append(TopologyEdge("c6a-ridge-"+str(index), target.key, apex.key, "DIAGONAL"))
value.update(topology_mode="Custom", topology_preset="Custom", base_preset="Pratt",
             custom_topology=materialize(TopologyGraph(candidate.graph.nodes, tuple(edges)),
                                         candidate.config))
candidate, ridge, _shape = plate(configure(value, apex.key), "Cumeeira DuoPitch")
check("ridge uses ChordBreak stable participant",
      any(p.end == "ChordBreak" for p in connection_participants(candidate, apex.key)))

value = base("Pratt")
node = useful_node(value, terminal=True)
_candidate, terminal, _shape = plate(configure(value, node), "Nó terminal")
check("terminal plate belongs to NodeKey", terminal.spec.node_key == node)

value = base("Pratt")
node = useful_node(value)
value["role_specs"]["DIAGONAL"] = configure_assembly(
    value["role_specs"]["DIAGONAL"], "DoubleAngle", 60.)
_candidate, double_angle, _shape = plate(configure(value, node), "DoubleAngle")
check("DoubleAngle components A B", any(key.endswith(":A") for key in double_angle.spec.component_keys)
      and any(key.endswith(":B") for key in double_angle.spec.component_keys))

side_shapes = {}
for side in ("Center", "FaceA", "FaceB"):
    value = base("Pratt"); node = useful_node(value)
    _candidate, outline, shape = plate(configure(value, node, side=side), "Lado "+side)
    side_shapes[side] = (outline, shape)
check("Centered/A/B signed limits", [extrusion_limits(side_shapes[key][0].spec)
      for key in ("Center", "FaceA", "FaceB")] == [(-4., 4.), (0., 8.), (-8., 0.)])

value = base("Pratt"); node = useful_node(value)
_candidate, small, _shape = plate(configure(value, node, margin=5., overlap=100.), "Margem pequena")
value = base("Pratt"); node = useful_node(value)
_candidate, large, _shape = plate(configure(value, node, margin=40., overlap=250.), "Margem grande")
check("edge margin changes real area", large.area > small.area)
check("member overlap changes real reach", max(math.hypot(x, y) for x, y in large.points) >
      max(math.hypot(x, y) for x, y in small.points))

value = base("Pratt")
value.update(start=[20., 30., 40.], end=[2420., 30., 40.], plane_normal=[0., -.6, .8])
node = useful_node(value)
_candidate, inclined, inclined_shape = plate(configure(value, node), "Plano inclinado")
check("inclined local normal preserved", all(abs(a-b) < 1e-9 for a, b in
      zip(inclined.spec.frame.normal, value["plane_normal"])))

doc = App.newDocument("GussetC6APreview")
Gui.activeDocument().activeView().viewAxonometric()
value = base("Pratt"); node = useful_node(value); configure(value, node)
before = tuple(obj.Name for obj in doc.Objects)
controller = TrussController(doc)
controller.preview3d(value, enabled=True)
check("3D preview includes preliminary plate", controller._preview is not None
      and len(controller._preview.shapes if hasattr(controller._preview, "shapes") else
              controller._preview.colors) > len(controller.last_candidate.items))
check("preview creates no document objects", tuple(obj.Name for obj in doc.Objects) == before)
controller.remove_preview()
check("preview removal creates no document objects", tuple(obj.Name for obj in doc.Objects) == before)
App.closeDocument(doc.Name)

with open(os.path.join(OUTPUT, "gate-result.json"), "w", encoding="utf-8") as stream:
    json.dump({"freecad": App.Version(), "checks": checks}, stream,
              ensure_ascii=False, indent=2)
print("C6-A manual gate OK:", len(checks), "checks")

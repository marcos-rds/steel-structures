"""Surgical FreeCAD 1.1.3 gate for C5-B.

Run in the FreeCAD Python console with the repository root as cwd:
    exec(open(r"tests/manual_freecad_connections_c5b.py", encoding="utf-8").read())
"""

import copy
import json
import os
import sys

import FreeCAD as App

ROOT = os.getcwd()
sys.path.insert(0, ROOT)
for module_name in tuple(sys.modules):
    if module_name == "freecad" or module_name.startswith("freecad.SteelStructures"):
        sys.modules.pop(module_name, None)
from freecad.SteelStructures import truss
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.assemblies import configure_assembly


OUTPUT = os.path.join(ROOT, "test-results", "connections-c5b")
os.makedirs(OUTPUT, exist_ok=True)
PATH = os.path.join(OUTPUT, "ConnectionsC5B.FCStd")
doc = App.newDocument("ConnectionsC5B")
checks = []


def check(label, condition):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def base(offset_y=0., inclined=False):
    value = truss.default_config()
    value.update(span=2400., height=700., panel_count=4,
                 start=[0., offset_y, 0.],
                 end=([2400., offset_y, 500.] if inclined else [2400., offset_y, 0.]))
    if inclined:
        value["span"] = App.Vector(*value["start"]).distanceToPoint(App.Vector(*value["end"]))
    return value


def two_web_node(value):
    candidate = build_candidate(value)
    for node in candidate.graph.nodes:
        incident = [edge for edge in candidate.graph.edges
                    if node.key in (edge.start_node_key, edge.end_node_key)]
        if sum(edge.role == "DIAGONAL" for edge in incident) == 2:
            return node.key
    raise AssertionError("fixture sem nó com duas webs")


def configured(offset_y, form, policy="Independent", gap=0., inclined=False, gusset=None):
    value = base(offset_y, inclined)
    node_key = two_web_node(value)
    value["role_specs"]["DIAGONAL"]["physical_fit_gap"] = gap
    intent = dict(form=form, direct_policy=policy)
    if gusset is not None:
        intent["gusset"] = gusset
    value["connection_intents"] = {node_key: intent}
    return value, node_key


def generated_at(owner, node_key, role):
    result = []
    for member in owner.GeneratedMembers:
        if getattr(member, "AssemblyElementKind", "Component") != "Component":
            continue
        plan_text = getattr(member, "PhysicalFitPlan", "")
        if not plan_text:
            continue
        plan = json.loads(plan_text)
        actions = tuple(action for action in (plan.get("start_action"), plan.get("end_action")) if action)
        if any(action.get("reference_key") == node_key+":connection" for action in actions):
            result.append(member)
    return result


def intent_action(plan, node_key):
    return next(action for action in (plan.get("start_action"), plan.get("end_action"))
                if action and action.get("reference_key") == node_key+":connection")


balanced, balanced_node = configured(0., "Direct", "BalancedMiter")
balanced_owner = truss.apply_truss(doc, balanced)
balanced_owner.Label = "C5B A - BalancedMiter gap 0"
balanced_members = generated_at(balanced_owner, balanced_node, "DIAGONAL")
plans = [json.loads(member.PhysicalFitPlan) for member in balanced_members]
actions = [intent_action(plan, balanced_node) for plan in plans]
check("balanced two physical members", len(actions) == 2)
check("shared PlaneCut", all(action["mode"] == "PlaneCut" for action in actions)
      and actions[0]["plane_origin"] == actions[1]["plane_origin"]
      and actions[0]["plane_normal"] == actions[1]["plane_normal"])
check("balanced shape valid", all(member.Shape.isValid() and member.Shape.Volume > 0
                                   for member in balanced_members))

positive, _ = configured(0., "Direct", "BalancedMiter", gap=20.)
positive_owner = truss.apply_truss(doc, positive)
positive_owner.Label = "C5B B - BalancedMiter gap 20"
positive_actions = [intent_action(json.loads(member.PhysicalFitPlan), balanced_node)
                    for member in generated_at(positive_owner, balanced_node, "DIAGONAL")]
check("gap individual after shared plane", positive_actions and
      all(abs(action["gap"]-20.) < 1e-7 for action in positive_actions))

priority, priority_node = configured(3000., "Direct", "Priority")
priority_owner = truss.apply_truss(doc, priority)
priority_owner.Label = "C5B C - Priority"
check("priority valid", all(member.Shape.isValid() for member in priority_owner.GeneratedMembers))
priority_plans = {}
for member in priority_owner.GeneratedMembers:
    plan_text = getattr(member, "PhysicalFitPlan", "")
    if not plan_text or '"source":"ConnectionIntent"' not in plan_text:
        continue
    plan = json.loads(plan_text)
    priority_plans[member.Name] = next(
        action for action in (plan.get("start_action"), plan.get("end_action"))
        if action and action.get("source") == "ConnectionIntent")
invalid = copy.deepcopy(truss.config_from_object(priority_owner))
invalid["connection_intents"][priority_node]["participant_run_keys"] = ["removed-run"]
priority_owner = truss.apply_truss(doc, invalid, priority_owner)
check("invalid target preserves previous plans", priority_plans and all(
    next(action for action in (
        json.loads(doc.getObject(name).PhysicalFitPlan).get("start_action"),
        json.loads(doc.getObject(name).PhysicalFitPlan).get("end_action"))
         if action and action.get("source") == "ConnectionIntent") == action
    for name, action in priority_plans.items()))
check("invalid intent is not accepted as reproducible state",
      "removed-run" not in priority_owner.C2Configuration)

gusset, gusset_node = configured(6000., "Gusset", gusset=dict(
    plate_thickness=8., normal_clearance=2., axial_clearance=25., side="Center"))
gusset["role_specs"]["DIAGONAL"] = configure_assembly(
    gusset["role_specs"]["DIAGONAL"], "DoubleAngle", 60.)
gusset_owner = truss.apply_truss(doc, gusset)
gusset_owner.Label = "C5B D - Double angle Gusset Center"
gusset_webs = generated_at(gusset_owner, gusset_node, "DIAGONAL")
check("gusset components A B", len(gusset_webs) == 4)
for member in gusset_webs:
    plan = json.loads(member.PhysicalFitPlan)
    action = intent_action(plan, gusset_node)
    contact = max([0.] + [a["reference_offset"] for a in plan.get("additional_actions", ())
                          if a["end"] == action["end"] and a["source"] == "AutoFit"])
    check("gusset preliminary setback after chord contact",
          abs(action["reference_offset"]-contact-25.) < 1e-7)

channel, channel_node = configured(7500., "Gusset", gusset=dict(
    plate_thickness=10., normal_clearance=2., axial_clearance=20., side="Center"))
channel["role_specs"]["DIAGONAL"]["profile_ref"] = copy.deepcopy(
    channel["role_specs"]["TOP_CHORD"]["profile_ref"])
channel["role_specs"]["DIAGONAL"] = configure_assembly(
    channel["role_specs"]["DIAGONAL"], "DoubleChannelInward", 140.)
channel_owner = truss.apply_truss(doc, channel)
channel_owner.Label = "C5B E - Double channel Gusset Center"
check("double channel gusset components", len(generated_at(
    channel_owner, channel_node, "DIAGONAL")) == 4)

inclined, _ = configured(9000., "Direct", "BalancedMiter", inclined=True)
inclined_owner = truss.apply_truss(doc, inclined)
inclined_owner.Label = "C5B F - Inclined plane"
check("inclined valid", all(member.Shape.isValid() and member.Shape.Volume > 0
                            for member in inclined_owner.GeneratedMembers))

many = base(12000.)
many.update(topology_preset="X", x_connection="Connected")
many_candidate = build_candidate(many)
many_node = next(node.key for node in many_candidate.graph.nodes
                 if sum(edge.role == "DIAGONAL" and node.key in
                        (edge.start_node_key, edge.end_node_key)
                        for edge in many_candidate.graph.edges) > 2)
many["connection_intents"] = {many_node: dict(
    form="Direct", direct_policy="BalancedMiter")}
many_owner = truss.apply_truss(doc, many)
check("more than two webs diagnosed", any(
    "exatamente duas barras da alma equivalentes" in getattr(member, "PhysicalFitStatus", "")
    for member in many_owner.GeneratedMembers))

# Manual PlaneCut is deliberately changed outside PhysicalFitAutoState. The
# next connection apply must preserve it and report the block on that end.
manual = balanced_members[0]
prefix = intent_action(json.loads(manual.PhysicalFitPlan), balanced_node)["end"]
setattr(manual, prefix+"AdjustmentMode", "Fixed")
setattr(manual, prefix+"AdjustmentGeometryMode", "PlaneCut")
setattr(manual, prefix+"FixedReferenceOffset", 12.)
setattr(manual, prefix+"FixedPlaneNormal", App.Vector(1., 0., 1.))
manual.Proxy.execute(manual)
balanced_owner = truss.apply_truss(doc, copy.deepcopy(balanced), balanced_owner)
manual = doc.getObject(manual.Name)
check("manual PlaneCut sovereign", abs(getattr(manual, prefix+"FixedReferenceOffset").Value-12.) < 1e-7
      and "manual" in manual.PhysicalFitStatus.lower())

doc.recompute()
doc.saveAs(PATH)
check("fixture saved", os.path.exists(PATH))

# Exercise the document transaction discipline and accepted-snapshot resync.
before = balanced_owner.AppliedState
changed = copy.deepcopy(truss.config_from_object(balanced_owner))
changed["connection_intents"][balanced_node]["direct_policy"] = "Priority"
truss.apply_truss(doc, changed, balanced_owner)
doc.undo()
doc.recompute()
truss.resynchronize_accepted_snapshots(balanced_owner)
check("undo restores applied state", balanced_owner.AppliedState == before)
doc.redo()
doc.recompute()
truss.resynchronize_accepted_snapshots(balanced_owner)
check("redo remains valid", balanced_owner.GenerationState == "Valid")
doc.saveAs(PATH)
App.closeDocument(doc.Name)
doc = App.openDocument(PATH)
check("save reopen keeps valid shapes", all(
    member.Shape.isValid() and member.Shape.Volume > 0
    for owner in doc.Objects if getattr(owner, "AppliedState", "")
    for member in getattr(owner, "GeneratedMembers", ())))
check("save reopen keeps intents", all(
    "connection_intents" in json.loads(owner.C2Configuration)
    for owner in doc.Objects if getattr(owner, "AppliedState", "")))

with open(os.path.join(OUTPUT, "gate-result.json"), "w", encoding="utf-8") as stream:
    json.dump({"freecad": App.Version(), "checks": checks}, stream,
              ensure_ascii=False, indent=2)
print("C5-B manual gate OK:", len(checks), "checks")
print(PATH)

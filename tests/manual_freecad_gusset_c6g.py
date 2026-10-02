"""Real-FreeCAD C6 gate: resolved candidates, solids, fitting and persistence.

Selections use current candidate stable keys. Legacy Inner/Center is retained
only for the deliberate impossible-SHS compatibility test, never as a UI name.
"""
import copy
import json
import os
import sys
import traceback
import types
from collections import defaultdict
from dataclasses import asdict

ROOT = os.getcwd()
OUTPUT = os.path.join(ROOT, "test-results", "gusset-c6g")
os.makedirs(OUTPUT, exist_ok=True)

def report_exception(kind, value, tb):
    with open(os.path.join(OUTPUT, "gate-error.txt"), "w", encoding="utf-8") as stream:
        traceback.print_exception(kind, value, tb, file=stream)
    traceback.print_exception(kind, value, tb)

sys.excepthook = report_exception
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests")]
local_tests = types.ModuleType("tests")
local_tests.__path__ = [os.path.join(ROOT, "tests")]
sys.modules["tests"] = local_tests
for name in tuple(sys.modules):
    if name == "freecad" or name.startswith("freecad.SteelStructures"):
        sys.modules.pop(name, None)

import FreeCAD as App
import FreeCADGui as Gui
from freecad.SteelStructures import profile_catalog, truss
from freecad.SteelStructures.connections import GussetResidualStatus, attachment_warning_messages
from freecad.SteelStructures.connections.gusset_families import requirements, validate_family
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.gusset_freecad import build_gusset_shape
from freecad.SteelStructures.trusses.gussets import preliminary_gusset_outlines
from freecad.SteelStructures.trusses.realization import build_candidate
from tests.test_connections_c5b_polish import three_web_config
from tests.test_fitting_c6g_assembly import _candidate as fitting_candidate
from tests.test_gusset_families_round1 import compute
from tests.test_gusset_plate_c6a import configured
from tests.test_gusset_presentation_c6q import preview_config
from tests.test_gusset_ui_c6m import regions_for
from tests.test_ridge_fitting import ridge_config

checks, records = [], []
PATH = os.path.join(OUTPUT, "GussetC6G.FCStd")
POSITIONS = {"NearA", "Center", "NearB"}

def check(label, condition, detail=None):
    if not condition:
        raise AssertionError(label+(": "+repr(detail) if detail is not None else ""))
    checks.append(label)
    with open(os.path.join(OUTPUT, "progress.txt"), "a", encoding="utf-8") as stream:
        stream.write(label+"\n")

def shifted(value, y):
    value = copy.deepcopy(value)
    delta = y-value["start"][1]
    value["start"][1] += delta
    value["end"][1] += delta
    return value

def resolve(value, node):
    candidate = build_candidate(value)
    views = {}
    outlines, diagnostics = preliminary_gusset_outlines(candidate, transverse_previews=views)
    if diagnostics:
        raise AssertionError([d.message for d in diagnostics])
    return candidate, next(o for o in outlines if o.spec.node_key == node), views[node]

def choice(outline):
    plane = outline.attachment
    return next(c for c in plane.candidates if (c.slot_id, c.placement) ==
                (plane.governing_slot_id, plane.placement_kind))

def selected_config(value, node, selected):
    result = copy.deepcopy(value)
    result["connection_intents"][node]["gusset"]["transverse_placement"] = selected.stable_key
    return result

def difference(first, second):
    return first.cut(second).Volume+second.cut(first).Volume

def projected_limits(shape, outline):
    origin, normal = outline.spec.frame.origin, outline.spec.frame.normal
    values = [sum((v.Point[i]-origin[i])*normal[i] for i in range(3)) for v in shape.Vertexes]
    return min(values), max(values)

def check_physical_requirements(value, node, outline, label):
    _candidate, captured, _outlines, diagnostics = compute(value)
    validate_family(outline.points, requirements(*captured[node]))
    check(label+" coverage, EdgeMargin and MemberOverlap", not diagnostics)

def materialize(value, node, label, owner=None, family_requirements=True):
    candidate, outline, views = resolve(value, node)
    check(label+" valid resolved candidate", outline.attachment.kind != "NominalFallback")
    selected = choice(outline)
    key = value["connection_intents"][node]["gusset"].get("transverse_placement", "")
    check(label+" candidate identity", not key or key == selected.stable_key)
    if family_requirements:
        check_physical_requirements(value, node, outline, label)
    previous = (owner.GeneratedGussetPlates[0].Name if owner is not None else None)
    owner = truss.apply_truss(doc, value, owner)
    doc.recompute()
    check(label+" materializes exactly one plate", len(owner.GeneratedGussetPlates) == 1)
    plate = owner.GeneratedGussetPlates[0]
    check(label+" valid positive solid", plate.Shape.isValid()
          and len(plate.Shape.Solids) == 1 and plate.Shape.Volume > 0.)
    check(label+" volume equals area times thickness",
          abs(plate.Shape.Volume-outline.area*outline.spec.plate_thickness) < 1e-4)
    check(label+" resolved slab", max(abs(a-b) for a,b in zip(
        projected_limits(plate.Shape, outline),
        (selected.plate_low, selected.plate_high))) < 1e-6)
    check(label+" OCC equals shared preview", difference(plate.Shape, build_gusset_shape(outline)) < 1e-5)
    check(label+" identity and hierarchy", (previous is None or plate.Name == previous)
          and plate.StableKey == outline.spec.stable_key and plate.ParentTruss == owner
          and plate in owner.ViewObject.Proxy.claimChildren())
    governing = next(r for r in outline.attachment.residuals
                     if r.participant_key == selected.governing_participant_key)
    check(label+" governing contact", governing.status == GussetResidualStatus.CONTACT
          and abs(governing.residual) < 1e-6)
    members = {m.GenerationKey: m for m in owner.GeneratedMembers}
    chords = [members[i.key].Shape for i in candidate.items
              if i.element_kind == "Component" and i.role in ("TOP_CHORD", "BOTTOM_CHORD")]
    penetration = max(plate.Shape.common(shape).Volume for shape in chords)
    check(label+" no chord penetration", penetration < 1e-4, penetration)
    records.append(dict(label=label, owner=owner.Name, node=node, plate=plate.Name,
                        stable_key=plate.StableKey, placement=selected.stable_key,
                        contact_band=selected.contact_band, outline_band=selected.outline_band,
                        penetration_mm3=penetration))
    return owner, outline, views

def auto_manual(value, node, label):
    owner, automatic, auto_views = materialize(value, node, label+" auto")
    before = owner.GeneratedGussetPlates[0].Shape.copy()
    explicit = selected_config(value, node, choice(automatic))
    owner, manual, manual_views = materialize(explicit, node, label+" manual", owner)
    check(label+" auto/manual identical effective geometry",
          automatic.attachment == manual.attachment and automatic.points == manual.points
          and automatic.semantic_edges == manual.semantic_edges and auto_views == manual_views
          and difference(before, owner.GeneratedGussetPlates[0].Shape) < 1e-5)
    return owner

def exercise_positions(value, node, accessibility, expected, label):
    _candidate, initial, _views = resolve(value, node)
    # The current presentation deduplicates equivalent slots and separates
    # Ue stiffener faces from its main internal region. Do not require every
    # raw solver candidate to appear in that region (or translate old names).
    region_id = "external" if accessibility == "OuterExposed" else "internal"
    positions = next(positions for key,_name,positions in regions_for(initial) if key == region_id)
    visible = {key for key,_name in positions}
    candidates = [c for c in initial.attachment.candidates if c.stable_key in visible]
    check(label+" current controls expose physical candidates", len(candidates) == len(expected)
          and {c.stable_key for c in candidates} == visible
          and all(c.accessibility.value == accessibility for c in candidates))
    check(label+" available physical placements", {c.placement.value for c in candidates} == expected)
    owner, slabs = None, set()
    for selected in candidates:
        explicit = selected_config(value, node, selected)
        owner, outline, _views = materialize(explicit, node,
            label+" "+selected.placement.value, owner)
        slabs.add(projected_limits(owner.GeneratedGussetPlates[0].Shape, outline))
        # SurfaceBand/OpenRecess may start away from zero. The selected
        # material-derived window must survive resolution unchanged.
        check(label+" selected contact window", outline.attachment.contact_window == selected.contact_window
              and selected.contact_window is not None)
    check(label+" distinct physical slabs", len(slabs) == len(expected))
    return owner


doc = App.newDocument("GussetC6G")
doc.UndoMode = 1

# U at 0 degrees: the current internal choices are SurfaceBand supports.
# At 90 degrees an actual accessible OpenRecess provides the three positions.
for rotation in (0., 90.):
    value, node = preview_config('U 4" x 8,04', rotation=rotation)
    value = shifted(value, rotation*100.)
    value["connection_intents"][node]["gusset"]["plate_thickness"] = 10.
    auto_manual(value, node, "U "+str(rotation))
    exercise_positions(value, node, "OuterExposed", {"NearA", "NearB"}, "U external "+str(rotation))
    u_owner = exercise_positions(value, node, "SurfaceBand" if rotation == 0. else "OpenRecess",
                                 POSITIONS, "U internal "+str(rotation))

# SHS: intentional legacy impossible request, not a current menu selection.
value, shs_node = preview_config("SHS 40x40x1,2")
value = shifted(value, 13500.)
value["connection_intents"][shs_node]["gusset"].update(attachment_mode="Inner", side="Center")
_candidate, shs, shs_views = resolve(value, shs_node)
shs_owner = truss.apply_truss(doc, value)
check("SHS closed void absent from available candidates", not any(
    c.accessibility.value in ("OpenRecess", "EnclosedVoid") for c in shs.attachment.candidates))
check("SHS impossible legacy intent warns without plate", shs.attachment.kind == "NominalFallback"
      and attachment_warning_messages((shs,)) and not shs_owner.GeneratedGussetPlates)
before_warnings = attachment_warning_messages((shs,))
shs_name = shs_owner.Name
shs_intents = copy.deepcopy(truss.config_from_object(shs_owner)["connection_intents"])
check("SHS unavailable preview does not invent a plate", shs_views and all(v.message for v in shs_views))

# W/I: both orientations, including 8 mm, use actual transformed sections.
for row, designation in enumerate(("W 150 x 13,0", 'I 3" x 8,48')):
    for rotation in (0., 90.):
        for thickness in (8., 20.):
            value, node = preview_config(designation, rotation=rotation)
            value = shifted(value, 16000.+row*15000.+rotation*50.+thickness*50.)
            value["connection_intents"][node]["gusset"]["plate_thickness"] = thickness
            _candidate, outline, _views = resolve(value, node)
            check(designation+" recess accessibility "+str(rotation),
                  any(c.accessibility.value == "OpenRecess" for c in outline.attachment.candidates)
                  == (rotation == 90.))
            auto_manual(value, node, designation+" "+str((rotation, thickness)))
            exercise_positions(value, node, "SurfaceBand" if rotation == 0. else "OpenRecess",
                               POSITIONS, designation+" "+str((rotation, thickness)))

# Full Ue and angle contours; no assumption that a window contains the axis.
for row, designation in enumerate(("Ue 150 \u00d7 60 \u00d7 20 \u00d7 3,00", "L 40 x 4")):
    value, node = preview_config(designation, rotation=90.)
    value = shifted(value, 50000.+row*3000.)
    exercise_positions(value, node, "OpenRecess", POSITIONS, designation)

# Original spaced-pair diagonal case: inspect complete physical gap slots,
# rather than translating legacy Center/FaceA/FaceB to arbitrary candidates.
value, node = three_web_config()
role = copy.deepcopy(value["role_specs"]["DIAGONAL"])
role["profile_ref"] = asdict(profile_catalog.ref_for_designation("W 150 x 13,0"))
value["role_specs"]["DIAGONAL"] = configure_assembly(role, "SpacedPair", 120.)
value = configured(shifted(value, 58000.), node, plate_thickness=10.)
_candidate, outline, _views = resolve(value, node)
groups = defaultdict(list)
for selected in outline.attachment.candidates:
    if selected.accessibility.value == "AssemblyGap":
        groups[(selected.governing_participant_key, selected.slot_id)].append(selected)
complete = [group for group in groups.values() if {c.placement.value for c in group} == POSITIONS]
check("SpacedPair has complete physical gap slots", bool(complete))
for index, group in enumerate(complete):
    owner, slabs = None, set()
    for selected in group:
        explicit = selected_config(value, node, selected)
        owner, current, _views = materialize(explicit, node, "SpacedPair "+str(index)+" "+selected.placement.value, owner)
        check("SpacedPair gap attachment", current.attachment.kind == "AssemblyMidPlane")
        slabs.add(projected_limits(owner.GeneratedGussetPlates[0].Shape, current))
    check("SpacedPair gap positions remain distinct", len(slabs) == 3)

# Approved DuoPitch sequence; exact topology plus physical requirements.
value = shifted(ridge_config(.37, 1100.), 65000.)
node = "T_S_LEFT_1_3"
value = configured(value, node, plate_thickness=8., edge_margin=25., member_overlap=150.)
owner, duo, _views = materialize(value, node, "DuoPitch direct caps")
check("DuoPitch direct caps and physical margins", tuple(e.kind for e in duo.semantic_edges) == (
    "FREE_MARGIN", "WEB_END_CAP", "WEB_END_CAP", "FREE_MARGIN", "CHORD_BOUNDARY"))
auto_manual(value, node, "DuoPitch")

# A terminal hard support need not become an active polygon edge.
value = configured(shifted(ridge_config(diagonals=False), 68000.), "N_S_START",
                   plate_thickness=8., edge_margin=500., member_overlap=1000.)
_candidate, captured, outlines, diagnostics = compute(value)
terminal = outlines["N_S_START"]
hard = [s for s in captured["N_S_START"][3] if s.kind == "TERMINAL_BOUNDARY"]
check("terminal retains its longitudinal hard support", len(hard) == 1 and not diagnostics)
check("terminal satisfies hard boundary without requiring active edge", all(
    sum(n*x for n,x in zip(s.normal,p)) <= s.offset+1e-7 for s in hard for p in terminal.points))
check("terminal material contact window", terminal.attachment.contact_window is not None)
# This chord-only endpoint has no web corridor to feed the two-web family validator.
materialize(value, "N_S_START", "terminal", family_requirements=False)

# Preserve real component matching and collision checks in assembly fitting.
fit_value, _candidate = fitting_candidate("DoubleAngle", "DoubleAngle", chord_uses_angle=True)
fit_value = shifted(fit_value, 72000.)
fit_owner = truss.apply_truss(doc, fit_value)
doc.recompute()
fit_candidate = build_candidate(fit_value)
members = {m.GenerationKey: m for m in fit_owner.GeneratedMembers}
webs = [i for i in fit_candidate.items if i.role == "DIAGONAL" and i.element_kind == "Component"]
check("DoubleAngle fitting component identities", {i.component_key for i in webs} == {"A", "B"})
check("DoubleAngle fitting valid solids", all(members[i.key].Shape.isValid() for i in webs))
penetrations = [members[web.key].Shape.common(members[action["reference_key"]].Shape).Volume
                for web in webs for action in (web.physical_fit_plan["start_action"], web.physical_fit_plan["end_action"])
                if action is not None]
check("DoubleAngle fitting no component penetration", len(penetrations) == 16 and max(penetrations) < 1e-5,
      penetrations)

# Persistence of all final materialized placements, not only an invalid intent.
identities = {p.Name:(p.ParentTruss.Name, p.NodeKey, p.StableKey, p.Label, p.Shape.copy())
              for owner in doc.Objects for p in getattr(owner, "GeneratedGussetPlates", ())}
doc.recompute()
doc.saveAs(PATH)
App.closeDocument(doc.Name)
doc = App.openDocument(PATH)
doc.recompute()
for name, (parent, node, stable, label, shape) in identities.items():
    plate, owner = doc.getObject(name), doc.getObject(parent)
    check("reopen identity "+name, plate is not None and plate.StableKey == stable and plate.Label == label
          and plate.NodeKey == node and plate.ParentTruss == owner and plate in owner.GeneratedGussetPlates
          and plate in owner.ViewObject.Proxy.claimChildren())
    check("reopen physical solid "+name, plate.Shape.isValid() and difference(shape, plate.Shape) < 1e-5)
    truss.apply_truss(doc, truss.config_from_object(owner), owner)
    check("explicit regeneration retains plate "+name, len(owner.GeneratedGussetPlates) == 1
          and owner.GeneratedGussetPlates[0].Name == name
          and difference(shape, owner.GeneratedGussetPlates[0].Shape) < 1e-5)
reopened = doc.getObject(shs_name)
_, shs_after, _views = resolve(truss.config_from_object(reopened), shs_node)
check("reopen preserves impossible SHS intent", not reopened.GeneratedGussetPlates
      and truss.config_from_object(reopened)["connection_intents"] == shs_intents)
check("reopen recalculates node-local warnings", attachment_warning_messages((shs_after,)) == before_warnings)

with open(os.path.join(OUTPUT, "gate-result.json"), "w", encoding="utf-8") as stream:
    json.dump(dict(freecad=App.Version(), checks=checks, cases=records, document=PATH),
              stream, ensure_ascii=False, indent=2)
print("C6-G manual gate OK:", len(checks), "checks")
App.closeDocument(doc.Name)
Gui.getMainWindow().close()

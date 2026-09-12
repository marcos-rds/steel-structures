"""Surgical FreeCAD 1.1.3 gate and compact C5-A fixture.

Run in the FreeCAD Python console with the repository root as current directory:
    exec(open(r"tests/manual_freecad_fitting_c5a.py", encoding="utf-8").read())
"""

import json
from pathlib import Path
import sys

import FreeCAD as App


ROOT = Path.cwd()
while str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from freecad.SteelStructures import truss
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.interconnector_options import default_connector
from freecad.SteelStructures.interactive.truss_controller import TrussController


OUTPUT = ROOT / "test-results" / "fitting-c5a"
OUTPUT.mkdir(parents=True, exist_ok=True)
FIXTURE = OUTPUT / "FittingC5A.FCStd"
SCREENSHOT = OUTPUT / "FittingC5A.png"
checks = []


def check(name, condition):
    checks.append((name, bool(condition)))
    if not condition:
        raise AssertionError(name)


def base_config(start, end, normal, gap, double=False):
    value = truss.default_config()
    value.update(span=4000., height=1000., panel_count=4, topology_preset="Pratt",
                 top_continuity="Continuous", bottom_continuity="Continuous",
                 start=list(start), end=list(end), plane_normal=list(normal))
    for role in ("DIAGONAL", "VERTICAL"):
        value["role_specs"][role]["physical_fit"] = "ToChord"
        value["role_specs"][role]["physical_fit_gap"] = gap
    if double:
        role = value["role_specs"]["DIAGONAL"]
        value["role_specs"]["DIAGONAL"] = configure_assembly(
            role, "DoubleAngle", 80.,
            interconnectors=(default_connector("Battens"),))
    return value


def primary(obj, role):
    return [child for child in obj.GeneratedMembers
            if getattr(child, "AssemblyElementKind", "Component") == "Component"
            and next((g.TrussRole for g in obj.RoleGroups if child in g.Group), "") == role]


def assert_zero_gap_contacts(owner):
    state = json.loads(owner.AppliedState)
    candidate = truss.build_candidate(state["candidate"]["config"])
    by_key = {member.GenerationKey: member for member in owner.GeneratedMembers}
    for item in candidate.items:
        if item.element_kind != "Component" or not item.physical_fit_plan:
            continue
        for action in (item.physical_fit_plan.get("start_action"),
                       item.physical_fit_plan.get("end_action")):
            if not action:
                continue
            member, target = by_key[item.key], by_key[action["reference_key"]]
            check("gap zero encosta na face física",
                  member.Shape.distToShape(target.Shape)[0] < 1e-6)
            check("contato não invade o banzo",
                  member.Shape.common(target.Shape).Volume < 1e-6)


for name in tuple(document.Name for document in App.listDocuments().values()
                  if document.Name.startswith("FittingC5A")):
    App.closeDocument(name)

doc = App.newDocument("FittingC5A")
doc.UndoMode = 1
flat = truss.apply_truss(doc, base_config(
    (0, 0, 0), (4000, 0, 0), (0, -1, 0), 0.))
inclined = truss.apply_truss(doc, base_config(
    (0, 1800, 300), (4000, 1800, 300), (0, -.6, .8), 5., double=True))
doc.recompute()

flat_diagonals = primary(flat, "DIAGONAL")
flat_verticals = primary(flat, "VERTICAL")
flat_chords = primary(flat, "TOP_CHORD") + primary(flat, "BOTTOM_CHORD")
inclined_diagonals = primary(inclined, "DIAGONAL")

check("diagonal simples válida", bool(flat_diagonals) and all(
    m.Shape.isValid() and m.Shape.Volume > 0 for m in flat_diagonals))
check("montante válido", bool(flat_verticals) and all(
    m.Shape.isValid() and m.Shape.Volume > 0 for m in flat_verticals))
check("diagonal oblíqua usa PlaneCut", any(
    str(m.StartAdjustmentGeometryMode) == "PlaneCut"
    or str(m.EndAdjustmentGeometryMode) == "PlaneCut" for m in flat_diagonals))
check("gap axial zero", any(
    m.StartAdjustmentGap.Value == 0 and m.EndAdjustmentGap.Value == 0
    for m in flat_diagonals))
check("gap axial positivo", any(
    m.StartAdjustmentGap.Value == 5 or m.EndAdjustmentGap.Value == 5
    for m in inclined_diagonals))
check("chord contínuo permanece sem corte", len(flat_chords) == 2 and all(
    str(m.StartAdjustmentMode) == str(m.EndAdjustmentMode) == "None"
    for m in flat_chords))
check("assembly dupla recebe fitting em A/B",
      {m.ComponentKey for m in inclined_diagonals} == {"A", "B"} and all(
          str(m.StartAdjustmentMode) == "Fixed"
          or str(m.EndAdjustmentMode) == "Fixed" for m in inclined_diagonals))
check("plano inclinado mantém sólidos", all(
    m.Shape.isValid() and m.Shape.Volume > 0 for m in inclined.GeneratedMembers))
assert_zero_gap_contacts(flat)

for owner in (flat, inclined):
    state = json.loads(owner.AppliedState)
    candidate = truss.build_candidate(state["candidate"]["config"])
    by_key = {item.key: item for item in candidate.items}
    for child in owner.GeneratedMembers:
        item = by_key[child.GenerationKey]
        check("eixo nominal intacto",
              App.Vector(child.StartPoint).isEqual(App.Vector(*item.start_global), 1e-7)
              and App.Vector(child.EndPoint).isEqual(App.Vector(*item.end_global), 1e-7))
        check("resultados efetivos coerentes",
              child.AdjustedLength.Value > 0 and child.Shape.Volume > 0)

before_names = {m.GenerationKey: m.Name for m in flat.GeneratedMembers}
lengths_at_zero = {m.GenerationKey: m.AdjustedLength.Value for m in flat_diagonals}
updated = truss.config_from_object(flat)
updated["role_specs"]["DIAGONAL"]["physical_fit_gap"] = 50.
flat = truss.apply_truss(doc, updated, flat)
doc.recompute()
check("regeneração preserva objetos",
      before_names == {m.GenerationKey: m.Name for m in flat.GeneratedMembers})
flat_diagonals = primary(flat, "DIAGONAL")
check("gap recua cada ponta ao longo do eixo", all(
    abs(lengths_at_zero[m.GenerationKey] - m.AdjustedLength.Value - 100.) < 1e-6
    for m in flat_diagonals))

connectors = [m for m in inclined.GeneratedMembers
              if getattr(m, "AssemblyElementKind", "") == "Interconnector"]
inclined_chords = primary(inclined, "TOP_CHORD") + primary(inclined, "BOTTOM_CHORD")
check("interconectores existem na assembly dupla", bool(connectors))
check("interconectores ficam fora dos banzos", all(
    connector.Shape.common(chord.Shape).Volume < 1e-6
    for connector in connectors for chord in inclined_chords))

none_config = truss.config_from_object(flat)
none_config["role_specs"]["DIAGONAL"]["physical_fit"] = "None"
flat = truss.apply_truss(doc, none_config, flat)
doc.recompute()
check("None remove integralmente o autofit", all(
    str(m.StartAdjustmentMode) == str(m.EndAdjustmentMode) == "None"
    and abs(m.AdjustedLength.Value - App.Vector(m.StartPoint).distanceToPoint(
        App.Vector(m.EndPoint))) < 1e-7
    for m in primary(flat, "DIAGONAL")))

# Create a real manual adjustment before enabling ToChord. The manual fields
# and their physical result must remain sovereign.
manual_owner = truss.apply_truss(doc, base_config(
    (0, 3600, 0), (4000, 3600, 0), (0, -1, 0), 0.))
manual_none = truss.config_from_object(manual_owner)
manual_none["role_specs"]["DIAGONAL"]["physical_fit"] = "None"
manual_owner = truss.apply_truss(doc, manual_none, manual_owner)
doc.recompute()
manual = primary(manual_owner, "DIAGONAL")[0]
manual.StartAdjustmentMode = "Fixed"
manual.StartAdjustmentGeometryMode = "LengthLimit"
manual.StartFixedReferenceOffset = 20.
manual.StartAdjustmentGap = 3.
doc.recompute()
manual_effective_start = App.Vector(manual.EffectiveStartPoint)
manual_config = truss.config_from_object(manual_owner)
manual_config["role_specs"]["DIAGONAL"]["physical_fit"] = "ToChord"
manual_owner = truss.apply_truss(doc, manual_config, manual_owner)
doc.recompute()
manual = doc.getObject(manual.Name)
check("ajuste manual real bloqueia autofit",
      str(manual.StartAdjustmentGeometryMode) == "LengthLimit"
      and abs(manual.StartFixedReferenceOffset.Value - 20.) < 1e-7
      and abs(manual.StartAdjustmentGap.Value - 3.) < 1e-7
      and App.Vector(manual.EffectiveStartPoint).isEqual(manual_effective_start, 1e-7)
      and "manual" in manual.PhysicalFitStatus.lower())

doc.undo()
doc.recompute()
check("Undo restaura fitting", doc.getObject(flat.Name) is not None)
doc.redo()
doc.recompute()
flat = doc.getObject(flat.Name)
check("Redo restaura fitting", flat is not None and all(
    m.Shape.Volume > 0 for m in flat.GeneratedMembers))

volume_before = sum(m.Shape.Volume for m in inclined.GeneratedMembers)
invalid = truss.config_from_object(inclined)
invalid["plane_normal"] = [0., 0., 0.]
try:
    truss.apply_truss(doc, invalid, inclined)
except ValueError:
    pass
doc.recompute()
check("referência degenerada preserva estado válido",
      abs(sum(m.Shape.Volume for m in inclined.GeneratedMembers) - volume_before) < 1e-6)

# Apply -> Undo/Redo -> reopen/edit. Reopening repairs only a stale accepted
# snapshot whose live controlled inputs still match the restored AppliedState.
undo_owner = truss.apply_truss(doc, base_config(
    (0, 5400, 0), (4000, 5400, 0), (0, -1, 0), 0.))
undo_change = truss.config_from_object(undo_owner)
undo_change["height"] = 1100.
undo_owner = truss.apply_truss(doc, undo_change, undo_owner)
post_apply_snapshots = {member.GenerationKey: member.ControlledState
                        for member in undo_owner.GeneratedMembers}
doc.undo()
doc.recompute()
undo_owner = doc.getObject(undo_owner.Name)
# Reproduce the non-transactional stale Python/accepted snapshot observed in
# the UI while keeping the document properties at their valid undone values.
for member in undo_owner.GeneratedMembers:
    member.ControlledState = post_apply_snapshots[member.GenerationKey]
undo_controller = TrussController(doc, undo_owner)
undo_candidate = undo_controller.candidate(truss.config_from_object(undo_owner))
undo_state = json.loads(undo_owner.AppliedState)
undo_children = truss.bound_children(undo_owner, undo_state)
check("Undo reabre com candidate válido",
      not truss.conflicts_for(undo_owner, undo_children, undo_candidate))
undo_controller.cancel()
doc.redo()
doc.recompute()
undo_owner = doc.getObject(undo_owner.Name)
redo_controller = TrussController(doc, undo_owner)
redo_candidate = redo_controller.candidate(truss.config_from_object(undo_owner))
redo_state = json.loads(undo_owner.AppliedState)
redo_children = truss.bound_children(undo_owner, redo_state)
check("Redo reabre com candidate válido",
      not truss.conflicts_for(undo_owner, redo_children, redo_candidate))
redo_controller.cancel()
doc.undo()
doc.recompute()
undo_owner = doc.getObject(undo_owner.Name)
edit_controller = TrussController(doc, undo_owner)
edit_config = truss.config_from_object(undo_owner)
edit_config["role_specs"]["DIAGONAL"]["physical_fit_gap"] = 2.
edit_candidate = edit_controller.candidate(edit_config)
undo_owner = truss.apply_truss(doc, edit_candidate.config, undo_owner)
check("edição após Undo aplica sem falso conflito",
      undo_owner.GenerationState == "Valid")
edit_controller.cancel()

controlled = primary(undo_owner, "DIAGONAL")[0]
original_start = App.Vector(controlled.StartPoint)
controlled.StartPoint = original_start.add(App.Vector(10., 0., 0.))
doc.recompute()
controlled_state = json.loads(undo_owner.AppliedState)
controlled_children = truss.bound_children(undo_owner, controlled_state)
controlled_candidate = truss.build_candidate(controlled_state["candidate"]["config"])
check("edição externa real continua detectada", any(
    "Propriedade controlada alterada diretamente" in message
    for message in truss.conflicts_for(
        undo_owner, controlled_children, controlled_candidate).values()))
controlled.Proxy._updating = True
controlled.StartPoint = original_start
controlled.Proxy._updating = False
doc.recompute()
truss.resynchronize_accepted_snapshots(undo_owner)

doc.saveAs(str(FIXTURE))
owner_names = (flat.Name, inclined.Name, manual_owner.Name, undo_owner.Name)
App.closeDocument(doc.Name)
doc = App.openDocument(str(FIXTURE))
doc.recompute()
check("save/reopen preserva fitting",
      all(doc.getObject(name) is not None for name in owner_names)
      and all(member.Shape.isValid() and member.Shape.Volume > 0
              for name in owner_names for member in doc.getObject(name).GeneratedMembers))

try:
    import FreeCADGui as Gui
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    Gui.activeDocument().activeView().saveImage(str(SCREENSHOT), 1400, 900, "Current")
except Exception:
    pass

result = {"fixture": str(FIXTURE),
          "screenshot": str(SCREENSHOT) if SCREENSHOT.exists() else "",
          "checks": len(checks), "passed": sum(ok for _name, ok in checks)}
App.Console.PrintMessage("FITTING_C5A_RESULT=" + json.dumps(result, ensure_ascii=False) + "\n")
print("FITTING_C5A_RESULT=" + json.dumps(result, ensure_ascii=False))

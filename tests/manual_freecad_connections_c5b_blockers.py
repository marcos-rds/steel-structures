"""Small OCC/document gate for the C5-B manual blockers; run via FreeCAD MCP."""
import copy
import importlib
import json
from pathlib import Path
import FreeCAD as App

# Refresh changed code without closing or recomputing the user's documents.
for module in (
    'fitting.models','fitting.validation','fitting.serialization','fitting.resolver','fitting',
    'connections.models','connections.validation','connections.serialization','connections.resolver',
    'connections','connections.presentation','trusses.models','trusses.serialization',
    'trusses.connections','trusses.fitting_geometry','trusses.fitting','trusses.realization',
    'member_plane_cut','fitting.freecad_adapter','member','member_batch','truss',
    'interactive.truss_controller','interactive.truss_topology_editor','interactive.truss_task_panel',
):
    importlib.reload(importlib.import_module('freecad.SteelStructures.'+module))

from freecad.SteelStructures import truss
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.connections import connection_participants
from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.interactive.truss_controller import TrussController

ROOT=Path(r'C:\Users\marco\Desktop\FREECAD\MINHA BANCADA\SteelStructures')
OUTPUT=ROOT/'test-results'/'connections-c5b-blockers'
OUTPUT.mkdir(parents=True,exist_ok=True)
doc=App.newDocument('C5BBlockers')
doc.UndoMode=1
checks=[]

def check(label, condition):
    if not condition: raise AssertionError(label)
    checks.append(label)

def config(preset='Warren'):
    value=truss.default_config()
    value.update(span=6000.,height=1600.,panel_count=4,end=[6000.,0.,0.],topology_preset=preset)
    return value

def get_actions(member):
    plan=json.loads(getattr(member,'PhysicalFitPlan','') or '{}')
    return [a for a in (plan.get('start_action'),plan.get('end_action')) if a]+plan.get('additional_actions',[])

def valid(owner):
    return all(m.Shape.isValid() and m.Shape.Volume>0 for m in owner.GeneratedMembers)

value=config()
c=build_candidate(value)
node=next(n for n in c.graph.nodes if len([p for p in connection_participants(c,n.key)
                                        if p.role=='DIAGONAL'])==2)
value['connection_intents']={node.key:dict(form='Direct',direct_policy='BalancedMiter')}
owner=truss.apply_truss(doc,value)
check('composed OCC shapes valid',valid(owner))
for m in owner.GeneratedMembers:
    actions=get_actions(m)
    if not any(a['source']=='ConnectionIntent' for a in actions): continue
    check('ToChord and miter both persisted',len(actions)>=3)
    shape=m.Shape.copy()
    shape.Placement=m.Placement
    direction=m.EndPoint.sub(m.StartPoint); direction.normalize()
    for a in actions:
        inward=direction if a['end']=='Start' else direction*-1.
        endpoint=m.StartPoint if a['end']=='Start' else m.EndPoint
        point=endpoint.add(inward*(a['reference_offset']+a['gap']))
        normal=App.Vector(*(a['plane_normal'] or tuple(direction)))
        sign=1. if normal.dot(inward)>0 else -1.
        check('Shape respects each clipping half-space',all(
            sign*normal.dot(v.Point.sub(point))>=-1e-5 for v in shape.Vertexes))
    original=next(i for i in c.items if i.key==m.GenerationKey)
    check('nominal points intact',m.StartPoint.isEqual(App.Vector(*original.start_global),1e-7)
          and m.EndPoint.isEqual(App.Vector(*original.end_global),1e-7))

volumes={m.GenerationKey:m.Shape.Volume for m in owner.GeneratedMembers}
value['role_specs']['DIAGONAL']['physical_fit_gap']=15.
owner=truss.apply_truss(doc,value,owner)
check('positive axial gap reduces fitted web volumes',all(
    m.Shape.Volume<volumes[m.GenerationKey] for m in owner.GeneratedMembers
    if any(a['source']=='ConnectionIntent' for a in get_actions(m))))
preview=truss.prepare_batch(build_candidate(value),truss.bound_children(
    owner,json.loads(owner.AppliedState)))
check('preview and applied composed shapes agree',all(
    abs(preview[m.GenerationKey].Shape.Volume-m.Shape.Volume)<1e-5 for m in owner.GeneratedMembers))

pv=config('Pratt')
pc=build_candidate(pv)
pn=next(n for n in pc.graph.nodes if {p.role for p in connection_participants(pc,n.key)
           if p.role in ('DIAGONAL','VERTICAL')}=={'DIAGONAL','VERTICAL'})
webs=[p for p in connection_participants(pc,pn.key) if p.role in ('DIAGONAL','VERTICAL')]
priority=None
for choice in ('ParticipantA','ParticipantB','Automatic'):
    pv['connection_intents']={pn.key:dict(form='Direct',direct_policy='Priority',
        priority_member=choice,participant_run_keys=[p.run_key for p in webs])}
    priority=truss.apply_truss(doc,pv,priority)
    check('Pratt '+choice+' OCC valid',valid(priority))

gv=copy.deepcopy(value)
gv['connection_intents']={node.key:dict(form='Gusset',gusset=dict(
    plate_thickness=8.,normal_clearance=200.,axial_clearance=200.,side='Center'))}
gusset=truss.apply_truss(doc,gv)
single_keys={m.GenerationKey:m.Name for m in gusset.GeneratedMembers}
for mode in ('DoubleAngle','DoubleChannelInward','SpacedPair'):
    role=copy.deepcopy(gv['role_specs']['DIAGONAL'])
    if mode=='DoubleChannelInward': role['profile_ref']=copy.deepcopy(gv['role_specs']['TOP_CHORD']['profile_ref'])
    gv['role_specs']['DIAGONAL']=configure_assembly(role,mode,100. if mode=='DoubleAngle' else 600.)
    gusset=truss.apply_truss(doc,gv,gusset)
    targets=[m for m in gusset.GeneratedMembers if any(a['source']=='ConnectionIntent' for a in get_actions(m))]
    check(mode+' has both components fitted',len(targets)==4 and {m.ComponentKey for m in targets}=={'A','B'})
    check(mode+' shapes valid',valid(gusset))
    actual=truss.config_from_object(gusset)['connection_intents'][node.key]['gusset']
    check('8/200/200 persists',actual==dict(plate_thickness=8.,normal_clearance=200.,axial_clearance=200.,side='Center'))
    if mode=='DoubleAngle':
        check('insufficient normal space is explicit without discarding A/B',all(
            'espaço central' in m.PhysicalFitStatus for m in targets))
        b=next(m for m in targets if m.ComponentKey=='B')
        old_offset=b.StartFixedReferenceOffset.Value
        b.StartFixedReferenceOffset=old_offset+3.
        doc.recompute()
        forbidden=copy.deepcopy(gv)
        forbidden['role_specs']['DIAGONAL']=configure_assembly(forbidden['role_specs']['DIAGONAL'],'Single')
        before_state=gusset.AppliedState
        try:
            truss.apply_truss(doc,forbidden,gusset)
        except ValueError as exc:
            check('manual B removal remains protected','ajustes manuais' in str(exc))
        else:
            raise AssertionError('manual B removal was allowed')
        check('failed removal leaves document intact',gusset.AppliedState==before_state and doc.getObject(b.Name) is not None)
        b.StartFixedReferenceOffset=old_offset
        doc.recompute()
    gv['role_specs']['DIAGONAL']=configure_assembly(gv['role_specs']['DIAGONAL'],'Single')
    gusset=truss.apply_truss(doc,gv,gusset)
    check('Double to Single retains A',all(m.Name==single_keys[m.GenerationKey] for m in gusset.GeneratedMembers))
    check('A transform cleared',all(not getattr(m,'AssemblySectionTransform','') for m in gusset.GeneratedMembers))

for preset in ('Pratt','Howe','Warren'):
    switched=truss.config_from_object(owner); switched['topology_preset']=preset
    owner=truss.apply_truss(doc,switched,owner)
    check('preset '+preset+' removal accepts autofit',valid(owner))

manual=next(m for m in priority.GeneratedMembers if any(a['source']=='ConnectionIntent' for a in get_actions(m)))
manual.StartAdjustmentMode='Fixed'; manual.StartAdjustmentGeometryMode='PlaneCut'
manual.StartFixedReferenceOffset=45.; manual.StartFixedPlaneNormal=App.Vector(0.2,0.,1.)
doc.recompute()
priority=truss.apply_truss(doc,truss.config_from_object(priority),priority)
check('true manual PlaneCut protected',abs(manual.StartFixedReferenceOffset.Value-45.)<1e-7)
check('manual diagnostic', 'manual' in manual.PhysicalFitStatus.lower())

before=gusset.AppliedState
changed=truss.config_from_object(gusset)
changed['connection_intents'][node.key]['gusset']['axial_clearance']=210.
truss.apply_truss(doc,changed,gusset)
doc.undo(); doc.recompute()
controller=TrussController(doc,gusset)
controller.candidate(truss.config_from_object(gusset))
check('undo reopen candidate valid',gusset.AppliedState==before)
doc.redo(); doc.recompute()
controller=TrussController(doc,gusset)
controller.candidate(truss.config_from_object(gusset))
check('redo reopen candidate valid',valid(gusset))
changed['connection_intents'][node.key]['gusset']['axial_clearance']=200.
truss.apply_truss(doc,changed,gusset)
filename=str(OUTPUT/'C5BBlockers.FCStd')
names=[o.Name for o in (owner,priority,gusset)]
doc.recompute(); doc.saveAs(filename)
App.closeDocument(doc.Name)
doc=App.openDocument(filename)
check('FCStd roundtrip valid',all(valid(doc.getObject(name)) for name in names))
check('FCStd 8/200/200',truss.config_from_object(doc.getObject(names[-1]))['connection_intents'][node.key]['gusset']==
      dict(plate_thickness=8.,normal_clearance=200.,axial_clearance=200.,side='Center'))
from freecad.SteelStructures.interactive.truss_task_panel import TrussTaskPanel
from freecad.SteelStructures.interactive.truss_topology_editor import TopologyEditor
target=doc.getObject(names[-1])
controller=TrussController(doc,target)
panel=TrussTaskPanel(doc,controller,truss.config_from_object(target))
panel._refresh()
dialog=TopologyEditor(panel)
dialog.select_node(node.key)
check('real Qt editor reopens 8/200/200',
      (dialog.gusset_plate.value(),dialog.gusset_normal.value(),dialog.gusset_axial.value())==(8.,200.,200.))
check('Qt spin boxes commit complete input',not dialog.gusset_axial.keyboardTracking())
check('human priority names',all(dialog.priority_member.itemText(i) not in ('Participante A','Participante B')
                                for i in range(dialog.priority_member.count())))
panel._set_preset_value('WarrenVerticals')
panel._refresh()
current=controller.last_candidate
three=next(n for n in current.graph.nodes if len([p for p in connection_participants(current,n.key)
                   if p.role in ('DIAGONAL','VERTICAL','END_POST')])==3)
dialog.select_node(three.key)
check('Qt omits miter with three webs',dialog.direct_policy.findData('BalancedMiter') == -1)
try:
    panel.set_connection_intent(three.key,dict(form='Direct',direct_policy='BalancedMiter'))
except ValueError as exc:
    check('candidate refuses invalid miter immediately',str(exc)==
          'Meia-esquadria equilibrada requer exatamente duas barras da alma equivalentes.')
else:
    raise AssertionError('invalid miter accepted')
dialog.close(); dialog.deleteLater()
panel._preview_timer.stop(); panel._closed=True
controller.remove_preview(); panel.form.deleteLater()
(OUTPUT/'result.json').write_text(json.dumps(dict(version=App.Version(),checks=checks),indent=2),encoding='utf-8')
print('C5-B blockers:',len(checks),'checks OK')

"""Short real OCC/Qt gate for ridge fitting and angle envelope insertion."""
import importlib
import json
import sys
from pathlib import Path
from dataclasses import asdict
import FreeCAD as App
import FreeCADGui as Gui

ROOT=Path(r'C:\Users\marco\Desktop\FREECAD\MINHA BANCADA\SteelStructures')
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
for name in ('profiles.insertion','profiles.preview_geometry','profiles','profile_catalog','assemblies.transforms',
             'assemblies.attachment','connections.models','connections.resolver','connections',
             'trusses.connections','trusses.fitting_geometry','trusses.fitting','trusses.realization',
             'member','member_batch','truss','interactive.truss_controller',
             'interactive.section_orientation_preview'):
    importlib.reload(importlib.import_module('freecad.SteelStructures.'+name))
from freecad.SteelStructures import truss, member, profile_catalog
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.profiles.geometry import build_section_geometry
from freecad.SteelStructures.profiles.insertion import insertion_reference
from freecad.SteelStructures.interactive.truss_controller import TrussController
from freecad.SteelStructures.interactive.section_orientation_preview import SectionOrientationPreview
from freecad.SteelStructures.trusses.editing import materialize
from freecad.SteelStructures.trusses.models import TopologyEdge, TopologyGraph


def ridge_config(apex,height):
    value=truss.default_config()
    value.update(envelope_type='DuoPitch',span=2400.,end=[2400.,0.,0.],
                 apex_position=apex,height=height,panel_count=8,topology_preset='Pratt')
    value['role_specs']['TOP_CHORD']['profile_ref']=asdict(profile_catalog.ref_for_designation('U 4" x 8,04'))
    base=build_candidate(value)
    node=base.graph.node('T_S_APEX')
    bottom=sorted((n for n in base.graph.nodes if n.key.startswith('B_')
                   and abs(n.position_local[0]-node.position_local[0])>1e-7),
                  key=lambda n:abs(n.position_local[0]-node.position_local[0]))
    targets=[next(n for n in bottom if n.position_local[0]<node.position_local[0]),
             next(n for n in bottom if n.position_local[0]>node.position_local[0])]
    edges=list(base.graph.edges)
    for index,n in enumerate(targets):
        if not any({e.start_node_key,e.end_node_key}=={n.key,node.key} for e in edges):
            edges.append(TopologyEdge('ridge-diagonal-'+str(index),n.key,node.key,'DIAGONAL'))
    value.update(topology_mode='Custom',topology_preset='Custom',base_preset='Pratt',
                 custom_topology=materialize(TopologyGraph(base.graph.nodes,tuple(edges)),base.config))
    return value


def actions(item,end):
    p=item.physical_fit_plan or {}
    return [a for a in [p.get('start_action'),p.get('end_action')]+list(p.get('additional_actions',()))
            if a and a['end']==end]

checks=[]
def check(label,condition):
    if not condition: raise AssertionError(label)
    checks.append(label)

def check_owner(owner):
    c=build_candidate(truss.config_from_object(owner))
    members={m.GenerationKey:m for m in owner.GeneratedMembers}
    chords=[members['TC_LEFT'],members['TC_RIGHT']]
    check('valid OCC solids',all(m.Shape.isValid() and m.Shape.Volume>0 for m in members.values()))
    check('chords have no overlap',chords[0].Shape.common(chords[1].Shape).Volume<1e-5)
    check('chords meet with no gap',chords[0].Shape.distToShape(chords[1].Shape)[0]<1e-6)
    for item in c.items:
        m=members[item.key]
        check('nominal start/end unchanged',m.StartPoint.distanceToPoint(App.Vector(*item.start_global))<1e-6
              and m.EndPoint.distanceToPoint(App.Vector(*item.end_global))<1e-6)
        if item.role not in ('VERTICAL','DIAGONAL') or 'T_S_APEX' not in (item.start_node_key,item.end_node_key): continue
        end='Start' if item.start_node_key=='T_S_APEX' else 'End'
        cuts=actions(item,end)
        if item.role=='VERTICAL': check('apex vertical has both constraints',len(cuts)==2)
        else: check('apex diagonal has branch and optional clearance constraint',len(cuts) in (1,2))
        check('apex web clears BOTH chords',all(m.Shape.common(chord.Shape).Volume<1e-5 for chord in chords))
    return c,members

out=ROOT/'test-results'/'ridge-insertion'
out.mkdir(parents=True,exist_ok=True)
doc=App.newDocument('C5BRidgeInsertion')
value=ridge_config(.5,900.)
value['role_specs']['TOP_CHORD']['rotation']=-90.
owner=truss.apply_truss(doc,value)
c,members=check_owner(owner)
for apex,height in ((.37,1100.),(.63,750.)):
    value=truss.config_from_object(owner)
    value.update(apex_position=apex,height=height)
    owner=truss.apply_truss(doc,value,owner)
    doc.recompute()
    c,members=check_owner(owner)

value=truss.config_from_object(owner)
value.update(start=[20.,30.,40.],end=[2420.,30.,40.],plane_normal=[0.,-.6,.8])
owner=truss.apply_truss(doc,value,owner)
c,members=check_owner(owner)
controller=TrussController(doc,owner)
controller.preview3d(truss.config_from_object(owner))
check('preview uses same candidate',controller.last_candidate==c)
controller.remove_preview()

axes={m.Name:(tuple(m.StartPoint),tuple(m.EndPoint)) for m in owner.GeneratedMembers}
before_graph=c.graph
vertical=next(m for m in owner.GeneratedMembers if m.RunKey.startswith('VERTICAL'))
before_center=vertical.Shape.BoundBox.Center
value=truss.config_from_object(owner)
value['role_specs']['VERTICAL']['insertion']='envelope_center'
owner=truss.apply_truss(doc,value,owner)
c,members=check_owner(owner)
check('insertion preserves topology',c.graph==before_graph)
check('insertion preserves work lines',all(
    m.StartPoint.distanceToPoint(App.Vector(*axes[m.Name][0]))<1e-6
    and m.EndPoint.distanceToPoint(App.Vector(*axes[m.Name][1]))<1e-6
    for m in owner.GeneratedMembers))
check('only physical section shifts',vertical.Shape.BoundBox.Center.distanceToPoint(before_center)>1.)

# Standalone angle: roll rotates the insertion offset exactly once.
angle=member.create_member(doc,App.Vector(),App.Vector(0,0,1000),'L 40 x 4',rotation=35.)
center=angle.Shape.CenterOfMass
geometry=build_section_geometry(profile_catalog.get('L 40 x 4').definition)
point=insertion_reference(geometry,'envelope_center').point
mini=SectionOrientationPreview()
mini.resize(360,300)
mini.set_geometry(geometry,'envelope_center',35.)
check('Qt preview selects envelope center',mini._selected_reference().id=='envelope_center')
mini.grab().save(str(out/'envelope-center-preview.png'))
angle.Insertion='Centro do envelope'; doc.recompute()
expected=angle.Placement.Rotation.multVec(App.Vector(-point.x,-point.y,0.))
check('roll applies physical insertion once',angle.Shape.CenterOfMass.sub(center).distanceToPoint(expected)<1e-6)
angle.Insertion='Centroide';doc.recompute()
check('insertion switch restores physical position',angle.Shape.CenterOfMass.distanceToPoint(center)<1e-6)
angle.Insertion='Centro do envelope'
angle.addProperty('App::PropertyString','AssemblySectionTransform')
angle.AssemblySectionTransform=json.dumps(dict(rotation_degrees=37.,reflect_x=True))
doc.recompute()
shape=angle.Shape.copy();shape.Placement=App.Placement()
check('transformed envelope has no doubled offset',abs(shape.BoundBox.XMin+shape.BoundBox.XMax)<1e-6
      and abs(shape.BoundBox.YMin+shape.BoundBox.YMax)<1e-6)

owner_name,angle_name=owner.Name,angle.Name
path=out/'RidgeInsertion.FCStd'
doc.saveAs(str(path))
App.closeDocument(doc.Name)
doc=App.openDocument(str(path))
owner,angle=doc.getObject(owner_name),doc.getObject(angle_name)
doc.recompute()
check_owner(owner)
check('save/reopen insertion',str(angle.Insertion)=='Centro do envelope')
check('save/reopen truss insertion',truss.config_from_object(owner)['role_specs']['VERTICAL']['insertion']=='envelope_center')
Gui.activeDocument().activeView().viewAxonometric()
Gui.activeDocument().activeView().fitAll()
Gui.activeDocument().activeView().saveImage(str(out/'ridge.png'),1400,900,'Current')
(out/'gate-result.json').write_text(json.dumps(dict(passed=len(checks),checks=checks),indent=2),encoding='utf-8')
print(json.dumps(dict(passed=len(checks),checks=checks)))

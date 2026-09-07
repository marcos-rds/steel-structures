"""Focused C2 acceptance contracts; no broad document/GUI QA."""
import copy
import math
import unittest
from dataclasses import asdict
from types import SimpleNamespace
from tests.test_truss_qa import config
from tests.test_truss_manual_fixes import definition
from tests.test_truss_c2_editor import EditorGestureTests
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.editing import edit_candidate
from freecad.SteelStructures.trusses.editor_snapping import snap_target
from freecad.SteelStructures.trusses.validation import human_diagnostics
from freecad.SteelStructures.trusses.preset_contracts import compatible_presets


def web(candidate):
    return [e for e in candidate.graph.edges if e.role not in ("TOP_CHORD","BOTTOM_CHORD")]


class RoofContracts(unittest.TestCase):
    def test_exact_envelope_options(self):
        common=("Warren","WarrenVerticals","Pratt","Howe","X")
        self.assertEqual(compatible_presets("Parallel"),common+("K","Custom"))
        self.assertEqual(compatible_presets("DuoPitch"),common+("Fink","Fan","KingPost","QueenPost","Custom"))

    def test_roof_webs(self):
        for preset in ("Fink","Fan","KingPost","QueenPost"):
            c=build_candidate(config(envelope_type="DuoPitch",topology_preset=preset))
            edges=web(c)
            segments={frozenset((c.graph.node(e.start_node_key).position_local,c.graph.node(e.end_node_key).position_local)) for e in edges}
            self.assertEqual(segments,{frozenset((6000-x,y,z) for x,y,z in segment) for segment in segments})
            self.assertFalse(c.warnings)
            if preset=="KingPost":
                self.assertEqual(len(edges),3)
                self.assertEqual(sum(e.role=="VERTICAL" for e in edges),1)
                bottom=next(n for n in c.graph.nodes if n.position_local==(3000.,0.,0.))
                self.assertTrue(all(bottom.key in (e.start_node_key,e.end_node_key) for e in edges))
            elif preset=="QueenPost":
                self.assertEqual(len(edges),3)
                self.assertEqual(sum(e.role=="VERTICAL" for e in edges),2)
                beam=next(e for e in edges if e.role!="VERTICAL")
                self.assertEqual(c.graph.node(beam.start_node_key).position_local[1],c.graph.node(beam.end_node_key).position_local[1])
            elif preset=="Fan":
                bottom=next(n for n in c.graph.nodes if n.position_local==(3000.,0.,0.))
                self.assertGreaterEqual(len(edges),5)
                self.assertTrue(all(bottom.key in (e.start_node_key,e.end_node_key) for e in edges))
            else:
                self.assertEqual(len(edges),4)
                # Ordered web is a W, with lower nodes on the tie.
                ordered=sorted(edges,key=lambda e:c.graph.node(e.start_node_key).position_local[0])
                self.assertEqual([c.graph.node(e.start_node_key).position_local[1]>0 for e in ordered],[True,False,True,False])

    def test_x_declared_crossings_and_custom_summary(self):
        c=build_candidate(config(topology_preset="X"))
        self.assertFalse(c.warnings)
        custom=build_candidate(edit_candidate(c,"add_node",point=(50.,100.,0.)))
        messages=human_diagnostics(custom.warnings)
        self.assertIn("2 componentes desconectados",messages)
        self.assertIn("6 cruzamentos sem conexão",messages)
        self.assertFalse(any("DIAGONAL:" in m or "N_MANUAL" in m for m in messages))


class EditorContracts(unittest.TestCase):
    def test_snap_priority_and_tolerance(self):
        c=build_candidate(config())
        self.assertEqual(snap_target(c.graph,(1,1,0),10)["kind"],"node")
        middle=snap_target(c.graph,(503,2,0),10)
        self.assertEqual(middle["kind"],"midpoint")
        self.assertEqual(middle["point"],(500,0,0))
        self.assertEqual(snap_target(c.graph,(350,2,0),10)["kind"],"edge")
        self.assertIsNone(snap_target(c.graph,(350,400,0),1))

    def test_split_chord_keeps_run_and_affiliation(self):
        c=build_candidate(config())
        edge=next(e for e in c.graph.edges if e.role=="TOP_CHORD")
        a,b=(c.graph.node(k).position_local for k in (edge.start_node_key,edge.end_node_key))
        point=tuple((x+y)/2 for x,y in zip(a,b))
        edited=build_candidate(edit_candidate(c,"add_node",point=point,edge_key=edge.key))
        node=next(n for n in edited.graph.nodes if n.position_local==point)
        self.assertEqual(node.affiliations,("TOP_CHORD",))
        self.assertEqual(len(edited.graph.incidence[node.key]),2)
        self.assertEqual(len(c.runs),len(edited.runs))
        self.assertEqual(edited.config["topology_mode"],"Custom")

    def test_copy_preserves_origin_deduplicates_and_both_directions(self):
        for direction in ("LeftToRight","RightToLeft"):
            c=build_candidate(config(panel_count=5))
            edited=build_candidate(edit_candidate(c,"copy_mirrored",direction=direction))
            pairs=lambda c:{frozenset((e.start_node_key,e.end_node_key)) for e in c.graph.edges}
            self.assertTrue(pairs(c)<=pairs(edited))
            self.assertEqual(len(edited.graph.edges),len(pairs(edited)))
            again=build_candidate(edit_candidate(edited,"copy_mirrored",direction=direction))
            self.assertEqual(edited.graph,again.graph)
            self.assertEqual(edited.config["topology_mode"],"Custom")

    def test_move_rejects_node_merge_atomically(self):
        c=build_candidate(edit_candidate(build_candidate(config()),"add_node",point=(500.,300.,0.)))
        n=next(n for n in c.graph.nodes if n.classification=="INTERNAL_NODE")
        with self.assertRaises(ValueError): edit_candidate(c,"move_node",key=n.key,point=(0.,0.,0.))
        self.assertEqual(c.graph.node(n.key).position_local,(500.,300.,0.))

    def test_profile_rotation_keeps_preset(self):
        cfg=config(); cfg["role_specs"]["DIAGONAL"]["rotation"]=90
        self.assertEqual(build_candidate(cfg).config["topology_mode"],"Preset")


class PanelContracts(unittest.TestCase):
    def panel_class(self):
        return definition("interactive/truss_task_panel.py","TrussTaskPanel",
                          dict(math=math,__package__="freecad.SteelStructures.interactive"))

    def test_main_panel_materializes_custom_after_edit(self):
        panel=object.__new__(self.panel_class())
        panel._initial=config()
        panel.get_config=lambda:copy.deepcopy(panel._initial)
        panel.controller=SimpleNamespace(candidate=build_candidate)
        panel.driver=SimpleNamespace(blockSignals=lambda _:False,findData=lambda x:x,setCurrentIndex=lambda _:None)
        panel.preset=SimpleNamespace(blockSignals=lambda _:False,findData=lambda x:x,setCurrentIndex=lambda value:setattr(panel,"shown_preset",value))
        panel._refresh=lambda:None
        c=build_candidate(panel.get_config())
        edge=next(e for e in web(c) if e.role=="DIAGONAL")
        panel.apply_topology_edit("remove_edge",key=edge.key)
        self.assertEqual(panel.get_config()["topology_mode"],"Custom")
        self.assertEqual(panel.shown_preset,"Custom")
        self.assertNotIn(edge.key,[e.key for e in build_candidate(panel.get_config()).graph.edges])

    def test_envelope_fallback_and_custom_protection(self):
        class Combo:
            def __init__(self,keys,current): self.keys=list(keys); self.current=current
            def currentData(self): return self.current
            def count(self): return len(self.keys)
            def itemData(self,i): return self.keys[i]
            def findData(self,key): return self.keys.index(key)
            def setCurrentIndex(self,i): self.current=self.keys[i]
            def blockSignals(self,_): return False
            def clear(self): self.keys=[]
            def addItem(self,label,key): self.keys.append(key)
        panel=object.__new__(self.panel_class())
        panel._initial=config()
        panel.envelope_type=Combo(("Parallel","DuoPitch"),"Parallel")
        panel.preset=Combo(compatible_presets("DuoPitch"),"Fink")
        panel._sync_presets()
        self.assertEqual(panel.preset.currentData(),"Warren")
        self.assertIn("Warren",panel._preset_notice)
        panel._initial=edit_candidate(build_candidate(config()),"add_node",point=(700.,300.,0.))
        before=copy.deepcopy(panel._initial)
        panel.envelope_type.current="DuoPitch"
        panel._sync_presets()
        self.assertEqual(panel.envelope_type.currentData(),"Parallel")
        self.assertEqual(panel._initial,before)

    def test_complete_span_is_explicit_and_overflow_unchanged(self):
        cls=definition("interactive/truss_task_panel.py","TrussTaskPanel",dict(math=math))
        panel=object.__new__(cls)
        values=[1000.]*5
        panel.spacing_editor=SimpleNamespace(values=lambda:values[:],set_values=lambda v:values.__setitem__(slice(None),v))
        panel.get_config=lambda:dict(span=6000.)
        panel._complete_span()
        self.assertEqual(values,[1000.]*6)
        values.append(500.)
        panel._complete_span()
        self.assertEqual(values,[1000.]*6+[500.])

    def test_defaults_resolve_actual_catalog(self):
        from freecad.SteelStructures import profile_catalog
        from freecad.SteelStructures.trusses.models import ROLES
        default=definition("truss.py","default_config",dict(profile_catalog=profile_catalog,ROLES=ROLES,asdict=asdict))
        cfg=default()
        from freecad.SteelStructures.profiles import ProfileRef
        for role,spec in cfg["role_specs"].items():
            name=profile_catalog.selection_for_ref(ProfileRef(**spec["profile_ref"]))[2]
            self.assertEqual(name,'U 4" x 8,04' if role in ("TOP_CHORD","BOTTOM_CHORD") else 'L 40 x 4')
        self.assertEqual(cfg["role_specs"]["TOP_CHORD"]["rotation"],-90)
        self.assertEqual(cfg["role_specs"]["BOTTOM_CHORD"]["rotation"],90)
        self.assertEqual(cfg["role_specs"]["END_POST_LEFT"]["rotation"],180)
        self.assertEqual(cfg["role_specs"]["END_POST_RIGHT"]["rotation"],0)
        self.assertEqual(cfg["role_specs"]["VERTICAL"]["rotation"],0)
        self.assertEqual(cfg["role_specs"]["DIAGONAL"]["rotation"],0)


class NewGestureContracts(EditorGestureTests):
    def test_free_node_requires_opt_in(self):
        self.canvas.editor.allow_free.isChecked=lambda:False
        self.mode="add_node"
        self.click(750,-400)
        self.assertFalse(self.actions)
        self.assertIn("Permitir nó livre",self.messages[-1])

    def test_snap_click_splits_edge(self):
        edge=next(e for e in self.controller.last_candidate.graph.edges if e.role=="BOTTOM_CHORD")
        graph=self.controller.last_candidate.graph
        a,b=(graph.node(k).position_local for k in (edge.start_node_key,edge.end_node_key))
        point=tuple((x+y)/2 for x,y in zip(a,b))
        self.mode="add_node"
        self.canvas.snap_at=lambda pos:dict(kind="midpoint",key=edge.key,point=point)
        self.click(503,2)
        self.assertEqual(self.controller.last_candidate.config["topology_mode"],"Custom")
        self.assertEqual(self.actions[-1][1]["point"],point)

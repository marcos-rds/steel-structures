"""Focused follow-up: Custom UX, geometric mirrors, safe removal and incidence."""
import copy
import math
import unittest
from dataclasses import asdict, replace
from types import SimpleNamespace
from tests.test_truss_qa import config
from tests.test_truss_manual_fixes import definition
from tests.test_truss_c2_references import rectangle
from freecad.SteelStructures.trusses.editing import edit_candidate, restore_preset, materialize
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.serialization import dumps, loads
from freecad.SteelStructures.trusses.models import TopologyGraph, TopologyNode, TopologyEdge
from freecad.SteelStructures.trusses.validation import connected_components
from freecad.SteelStructures.truss_reference import selection_reference


def manual_half():
    c=build_candidate(config(topology_preset="Custom",panelization_mode="CustomSpacingList",
                             custom_spacings=[700.,1000.,1300.,900.,1100.,1000.]))
    top=next(n for n in c.graph.nodes if n.position_local==(700.,1200.,0.))
    bottom=next(n for n in c.graph.nodes if n.position_local==(1700.,0.,0.))
    return build_candidate(edit_candidate(c,"add_edge",start=top.key,end=bottom.key))


def web_segments(c):
    return {frozenset((c.graph.node(e.start_node_key).position_local,c.graph.node(e.end_node_key).position_local))
            for e in c.graph.edges if e.role not in ("TOP_CHORD","BOTTOM_CHORD")}


class CustomGraphReview(unittest.TestCase):
    def test_inversion_non_symmetric_stations_preserves_web_and_connectivity(self):
        c=manual_half()
        inverted=build_candidate(edit_candidate(c,"mirror"))
        expected={frozenset((6000-x,y,z) for x,y,z in segment) for segment in web_segments(c)}
        self.assertEqual(web_segments(inverted),expected)
        self.assertEqual(len(connected_components(inverted.graph)),1)
        self.assertEqual(inverted.config["panelization_mode"],"CustomSpacingList")
        self.assertEqual(web_segments(build_candidate(edit_candidate(inverted,"mirror"))),web_segments(c))

    def test_copy_splits_destination_chords_preserves_source_and_is_idempotent(self):
        c=manual_half()
        copied=build_candidate(edit_candidate(c,"copy_mirrored",direction="LeftToRight"))
        self.assertTrue(web_segments(c)<web_segments(copied))
        self.assertEqual(len(web_segments(copied)),2)
        self.assertEqual(len(connected_components(copied.graph)),1)
        self.assertEqual(copied.graph,build_candidate(edit_candidate(c,"copy_mirrored",direction="LeftToRight")).graph)
        self.assertEqual(copied.graph,build_candidate(edit_candidate(copied,"copy_mirrored",direction="LeftToRight")).graph)
        for point in ((5300.,1200.,0.),(4300.,0.,0.)):
            nodes=[n for n in copied.graph.nodes if n.position_local==point]
            self.assertEqual(len(nodes),1)
            self.assertEqual(len(copied.graph.incidence[nodes[0].key]),3)

    def test_mirror_internal_nodes_and_roles(self):
        c=manual_half()
        c=build_candidate(edit_candidate(c,"add_node",point=(1100.,450.,0.)))
        node=next(n for n in c.graph.nodes if n.position_local==(1100.,450.,0.))
        end=next(n for n in c.graph.nodes if n.position_local==(700.,1200.,0.))
        c=build_candidate(edit_candidate(c,"add_edge",start=node.key,end=end.key))
        inv=build_candidate(edit_candidate(c,"mirror"))
        self.assertTrue(any(n.position_local==(4900.,450.,0.) and n.classification=="INTERNAL_NODE" for n in inv.graph.nodes))
        self.assertEqual(sorted(e.role for e in c.graph.edges if e.role not in ("TOP_CHORD","BOTTOM_CHORD")),
                         sorted(e.role for e in inv.graph.edges if e.role not in ("TOP_CHORD","BOTTOM_CHORD")))
        self.assertEqual(len(connected_components(inv.graph)),1)

    def split(self,c,role):
        edge=next(e for e in c.graph.edges if e.role==role)
        a,b=(c.graph.node(k).position_local for k in (edge.start_node_key,edge.end_node_key))
        point=tuple((x+y)/2 for x,y in zip(a,b))
        split=build_candidate(edit_candidate(c,"add_node",point=point,edge_key=edge.key))
        node=next(n for n in split.graph.nodes if n.position_local==point)
        return split,node,edge

    def test_remove_split_node_restores_original_identity_after_roundtrip(self):
        for role in ("TOP_CHORD","BOTTOM_CHORD","DIAGONAL"):
            c=build_candidate(config())
            split,node,edge=self.split(c,role)
            restored=build_candidate(loads(dumps(split.config)))
            merged=build_candidate(edit_candidate(restored,"remove_node",key=node.key))
            self.assertEqual(c.graph,merged.graph)
            self.assertEqual(c.runs,merged.runs)
            self.assertEqual(merged.config["topology_preset"],"Custom")

    def test_nested_split_removal_and_restored_recompute(self):
        c=build_candidate(config())
        split,first,edge=self.split(c,"TOP_CHORD")
        part=next(e for e in split.graph.edges if e.role=="TOP_CHORD" and first.key==e.end_node_key)
        a=split.graph.node(part.start_node_key).position_local
        point=tuple((x+y)/2 for x,y in zip(a,first.position_local))
        nested=build_candidate(edit_candidate(split,"add_node",point=point,edge_key=part.key))
        second=next(n for n in nested.graph.nodes if n.position_local==point)
        removed=build_candidate(edit_candidate(nested,"remove_node",key=first.key))
        merged=build_candidate(edit_candidate(removed,"remove_node",key=second.key))
        self.assertEqual(c.graph,merged.graph)
        self.assertEqual(merged.graph,build_candidate(loads(dumps(merged.config))).graph)

    def test_reflected_split_web_can_be_rejoined(self):
        c=manual_half()
        split,node,_=self.split(c,"DIAGONAL")
        inv=build_candidate(edit_candidate(split,"mirror"))
        point=(6000-node.position_local[0],node.position_local[1],0.)
        mirrored=next(n for n in inv.graph.nodes if n.position_local==point)
        joined=build_candidate(edit_candidate(inv,"remove_node",key=mirrored.key))
        self.assertEqual(len(web_segments(joined)),1)

    def test_remove_node_rejects_extra_incidence_and_original_station(self):
        c=build_candidate(config())
        split,node,edge=self.split(c,"TOP_CHORD")
        other=next(n for n in split.graph.nodes if n.position_local[1]==0.)
        joined=build_candidate(edit_candidate(split,"add_edge",start=node.key,end=other.key))
        before=dumps(joined)
        with self.assertRaisesRegex(ValueError,"O nó possui barras conectadas"):
            edit_candidate(joined,"remove_node",key=node.key)
        self.assertEqual(dumps(joined),before)
        station=next(n for n in c.graph.nodes if len(c.graph.incidence[n.key])>=2)
        with self.assertRaises(ValueError): edit_candidate(c,"remove_node",key=station.key)

    def test_remove_legacy_c2_split_and_free_node(self):
        c=build_candidate(config())
        split,node,_=self.split(c,"TOP_CHORD")
        cfg=copy.deepcopy(split.config); cfg["custom_topology"].pop("edge_origins")
        old=build_candidate(cfg)
        self.assertEqual(c.graph,build_candidate(edit_candidate(old,"remove_node",key=node.key)).graph)
        free=build_candidate(edit_candidate(c,"add_node",point=(250.,350.,0.)))
        n=next(n for n in free.graph.nodes if n.position_local==(250.,350.,0.))
        self.assertEqual(c.graph,build_candidate(edit_candidate(free,"remove_node",key=n.key)).graph)

    def test_move_isolated_node_onto_edge_propagates_incidence(self):
        c=build_candidate(config())
        free=build_candidate(edit_candidate(c,"add_node",point=(250.,350.,0.)))
        n=next(n for n in free.graph.nodes if n.position_local==(250.,350.,0.))
        edge=next(e for e in c.graph.edges if e.role=="DIAGONAL")
        a,b=(c.graph.node(k).position_local for k in (edge.start_node_key,edge.end_node_key))
        point=tuple((x+y)/2 for x,y in zip(a,b))
        moved=build_candidate(edit_candidate(free,"move_node",key=n.key,point=point))
        self.assertEqual(len(connected_components(moved.graph)),1)
        self.assertEqual(len(moved.graph.incidence[n.key]),2)

    def test_legacy_coincident_ids_and_unsplit_endpoint_repaired(self):
        c=build_candidate(config())
        support=next(n for n in c.graph.nodes if n.position_local==(0.,0.,0.))
        duplicate=replace(support,key="OLD_DUPLICATE",optional_station_key=None)
        end=TopologyNode("OLD_END",(500.,1200.,0.),(),"INTERNAL_NODE")
        edge=TopologyEdge("OLD_WEB",duplicate.key,end.key,"DIAGONAL")
        graph=TopologyGraph(c.graph.nodes+(duplicate,end),c.graph.edges+(edge,))
        cfg=copy.deepcopy(c.config); cfg.update(topology_mode="Custom",custom_topology=materialize(graph,cfg))
        fixed=build_candidate(cfg)
        self.assertEqual(len(connected_components(fixed.graph)),1)
        self.assertEqual(sum(n.position_local==(0.,0.,0.) for n in fixed.graph.nodes),1)
        self.assertEqual(len(fixed.graph.incidence[end.key]),3)
        self.assertEqual(fixed.graph.node(end.key).affiliations,("TOP_CHORD",))
        inverse=build_candidate(edit_candidate(fixed,"mirror"))
        self.assertEqual(len(connected_components(inverse.graph)),1)

    def test_crossings_without_explicit_nodes_stay_disconnected(self):
        c=build_candidate(config(topology_preset="X"))
        edited=build_candidate(edit_candidate(c,"mirror"))
        self.assertEqual(len(edited.graph.nodes),len(c.graph.nodes))
        self.assertEqual(len(connected_components(edited.graph)),1)
        self.assertEqual(sum(w.startswith("Cruzamento") for w in edited.warnings),6)


class CustomStateReview(unittest.TestCase):
    def test_copy_menu_executes_direction_and_main_button_repeats_it(self):
        cls=definition("interactive/truss_topology_editor.py","TopologyEditor",
                       dict(QtWidgets=SimpleNamespace(QDialog=object)))
        editor=object.__new__(cls)
        calls=[]; checked={}; tooltips=[]
        editor.copy_direction="LeftToRight"
        editor.copy_actions={key:SimpleNamespace(text=lambda label=label:label,
            setChecked=lambda value,key=key:checked.__setitem__(key,value))
            for key,label in (("LeftToRight","Esquerda → Direita"),("RightToLeft","Direita → Esquerda"))}
        editor.copy_button=SimpleNamespace(setToolTip=tooltips.append)
        editor.canvas=SimpleNamespace(cancel_gesture=lambda:None,refresh_candidate=lambda:None)
        editor.panel=SimpleNamespace(apply_topology_edit=lambda action,**args:calls.append((action,args)))
        editor.message=SimpleNamespace(setText=lambda _:None)
        editor.transform_web("copy_mirrored")
        editor.copy_in_direction("RightToLeft")
        editor.transform_web("copy_mirrored")
        self.assertEqual([args["direction"] for _,args in calls],["LeftToRight","RightToLeft","RightToLeft"])
        self.assertEqual(checked,{"LeftToRight":False,"RightToLeft":True})
        self.assertIn("Direita → Esquerda",tooltips[-1])
        editor.transform_web("mirror")
        self.assertEqual(calls[-1],("mirror",{}))

    def test_main_combo_stays_custom_and_restore_uses_separate_base(self):
        cls=definition("interactive/truss_task_panel.py","TrussTaskPanel",
                       dict(__package__="freecad.SteelStructures.interactive"))
        panel=object.__new__(cls)
        c=build_candidate(config())
        edge=next(e for e in c.graph.edges if e.role=="DIAGONAL")
        panel._initial=edit_candidate(c,"remove_edge",key=edge.key)
        panel._updating=False
        panel.shown="K"
        panel.preset=SimpleNamespace(currentData=lambda:panel.shown,blockSignals=lambda _:False,
            findData=lambda v:v,setCurrentIndex=lambda v:setattr(panel,"shown",v))
        panel._refresh=lambda:None
        panel.get_config=lambda:dict(copy.deepcopy(panel._initial),topology_preset=panel.shown)
        panel.controller=SimpleNamespace(candidate=build_candidate)
        panel._preset_changed()
        self.assertEqual(panel.shown,"Custom")
        self.assertEqual(panel.get_config()["base_preset"],"K")
        panel._restore_topology()
        self.assertEqual(panel.shown,"K")
        self.assertEqual(panel._initial["topology_mode"],"Preset")
        self.assertIsNone(panel._initial["custom_topology"])
        self.assertNotIn("base_preset",panel._initial)

    def test_base_seed_persists_separately_and_restore_returns_preset(self):
        c=build_candidate(config(topology_preset="K"))
        edge=next(e for e in c.graph.edges if e.role=="DIAGONAL")
        edited=build_candidate(edit_candidate(c,"remove_edge",key=edge.key))
        self.assertEqual(edited.config["topology_preset"],"Custom")
        self.assertEqual(edited.config["base_preset"],"K")
        loaded=build_candidate(loads(dumps(edited.config)))
        restored=build_candidate(restore_preset(loaded.config))
        self.assertEqual(restored.config["topology_mode"],"Preset")
        self.assertEqual(restored.config["topology_preset"],"K")
        self.assertEqual(restored.graph,c.graph)

    def test_legacy_seed_and_style_changes(self):
        c=manual_half(); cfg=copy.deepcopy(c.config)
        cfg.pop("base_preset",None); cfg["topology_preset"]="Pratt"
        restored=build_candidate(cfg)
        self.assertEqual(restored.config["base_preset"],"Pratt")
        self.assertEqual(restored.config["topology_preset"],"Custom")
        normal=config(); normal["role_specs"]["DIAGONAL"].update(rotation=30,color=[1,0,0])
        self.assertEqual(build_candidate(normal).config["topology_mode"],"Preset")

    def test_midpoint_triangle_node_circle_edge_square(self):
        calls=[]
        scene=SimpleNamespace(**{name:(lambda *args,kind=name:calls.append((kind,args)))
                                for name in ("addPolygon","addEllipse","addRect")})
        cls=definition("interactive/truss_topology_editor.py","TopologyCanvas",dict(
            TrussPreview2D=object,QtCore=SimpleNamespace(QPointF=lambda x,y:(x,y)),QtGui=SimpleNamespace(QPolygonF=lambda p:p)))
        canvas=object.__new__(cls); canvas.scene=lambda:scene; canvas._pen=lambda *args:None
        for kind in ("midpoint","node","edge"): canvas.add_snap_marker(kind)
        self.assertEqual([c[0] for c in calls],["addPolygon","addEllipse","addRect"])
        self.assertEqual(len(calls[0][1][0]),3)


class RectangleBaseReview(unittest.TestCase):
    def test_real_long_edges_square_and_preselected_override(self):
        for length,height,expected in ((6000.,1200.,"Edge1"),(1200.,6000.,"Edge2"),(2000.,2000.,""),(2000.,2000.0000001,"")):
            source=rectangle(length,height)
            item=SimpleNamespace(Object=source,SubElementNames=[])
            self.assertEqual(selection_reference([item])[2],expected)
            for edge in ("Edge1","Edge2","Edge3","Edge4"):
                item.SubElementNames=[edge]
                self.assertEqual(selection_reference([item])[2],edge)

    def test_longest_uses_real_edge_order(self):
        source=rectangle(6000,1200)
        source.Shape.Edges[:]=source.Shape.Edges[1:]+source.Shape.Edges[:1]
        item=SimpleNamespace(Object=source,SubElementNames=[])
        self.assertEqual(selection_reference([item])[2],"Edge2")

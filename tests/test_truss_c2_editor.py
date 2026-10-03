"""Gesture dispatch and shared candidate state; Qt is replaced at its boundary."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests.test_truss_manual_fixes import definition
from tests.test_truss_qa import config
from tests.test_member_placement import Vector
from freecad.SteelStructures.trusses.editing import edit_candidate
from freecad.SteelStructures.trusses.realization import build_candidate


class Point:
    def __init__(self,x=0,y=0): self._x,self._y=x,y
    def x(self): return self._x
    def y(self): return self._y
    def __sub__(self,other): return Point(self._x-other._x,self._y-other._y)


class CanvasBase:
    def mousePressEvent(self,event): pass


class EditorGestureTests(unittest.TestCase):
    def setUp(self):
        qt=SimpleNamespace(Qt=SimpleNamespace(LeftButton=1,IntersectsItemShape=2),
            QPoint=Point,QSize=lambda *args:args,QRect=lambda *args:args)
        cls=definition("interactive/truss_topology_editor.py","TopologyCanvas",dict(TrussPreview2D=CanvasBase,QtCore=qt))
        self.canvas=object.__new__(cls)
        self.canvas.pending=self.canvas.rubber=None
        self.messages=[]; self.actions=[]; self.items=[]
        self.controller=SimpleNamespace(last_candidate=build_candidate(config()))
        def apply(action,**args):
            self.actions.append((action,args))
            self.controller.last_candidate=build_candidate(edit_candidate(self.controller.last_candidate,action,**args))
        self.mode="create"
        self.canvas.editor=SimpleNamespace(current_mode=lambda:self.mode,
            allow_free=SimpleNamespace(isChecked=lambda:True),
            message=SimpleNamespace(setText=self.messages.append),
            panel=SimpleNamespace(controller=self.controller,apply_topology_edit=apply))
        self.canvas.items=lambda *args:self.items
        self.canvas.mapToScene=lambda point:point
        self.canvas.refresh_candidate=lambda:None
        self.canvas.snap_at=lambda pos:None

    def hit(self,kind,key):
        self.items=[SimpleNamespace(data=lambda index:kind if index==0 else key)]

    def click(self,x=0,y=0):
        self.canvas.mousePressEvent(SimpleNamespace(button=lambda:1,pos=lambda:Point(x,y)))

    def test_create_two_clicks_and_duplicate_error_preserve_shared_state(self):
        candidate=self.controller.last_candidate
        edge=next(e for e in candidate.graph.edges if e.role=="DIAGONAL")
        self.hit("node",edge.start_node_key); self.click()
        self.assertEqual(self.canvas.pending,edge.start_node_key)
        self.hit("node",edge.end_node_key); self.click()
        self.assertEqual(self.controller.last_candidate,candidate)
        self.assertIn("já existe",self.messages[-1])
        self.assertTrue(self.canvas.cancel_gesture())
        self.assertFalse(self.canvas.cancel_gesture())

    def test_remove_changes_shared_candidate_to_custom(self):
        edge=next(e for e in self.controller.last_candidate.graph.edges if e.role=="DIAGONAL")
        self.mode="remove"; self.hit("edge",edge.key); self.click()
        self.assertEqual(self.controller.last_candidate.config["topology_mode"],"Custom")
        self.assertFalse(any(e.key==edge.key for e in self.controller.last_candidate.graph.edges))

    def test_add_and_move_only_internal_node(self):
        self.mode="add_node"; self.click(750,-400)
        node=next(n for n in self.controller.last_candidate.graph.nodes if n.classification=="INTERNAL_NODE")
        self.mode="move_node"; self.hit("node",node.key); self.click()
        self.items=[]; self.click(800,-450)
        self.assertEqual(self.controller.last_candidate.graph.node(node.key).position_local,(800,450,0))
        chord=next(n for n in self.controller.last_candidate.graph.nodes if n.classification=="CHORD_NODE")
        self.hit("node",chord.key); self.click()
        self.assertIsNone(self.canvas.pending)
        self.assertIn("controlados",self.messages[-1])

    def test_escape_consumes_gesture_before_closing_dialog(self):
        events=[]
        class Dialog:
            def keyPressEvent(self,event): events.append("close")
        cls=definition("interactive/truss_topology_editor.py","TopologyEditor",dict(
            QtWidgets=SimpleNamespace(QDialog=Dialog),QtCore=SimpleNamespace(Qt=SimpleNamespace(Key_Escape=27))))
        editor=object.__new__(cls); editor.canvas=self.canvas
        self.canvas.pending="gesture"
        event=SimpleNamespace(key=lambda:27,accept=lambda:events.append("accepted"))
        editor.keyPressEvent(event); editor.keyPressEvent(event)
        self.assertEqual(events,["accepted","close"])

    def test_three_point_capture_uses_same_snapper_and_removes_callbacks(self):
        callbacks={}; snaps=[]; received=[]
        view=SimpleNamespace(addEventCallback=lambda kind,fn:callbacks.setdefault(kind,fn),
            removeEventCallback=lambda kind,token:callbacks.pop(kind))
        snapper=SimpleNamespace(show=lambda:None,off=lambda:snaps.append("off"),
            snap=lambda pos,**kw:snaps.append((pos,kw)) or Vector(pos[0],pos[1],0))
        cls=definition("interactive/truss_controller.py","TrussController",dict(
            Gui=SimpleNamespace(activeDocument=lambda:SimpleNamespace(activeView=lambda:view),Snapper=snapper),
            App=SimpleNamespace(Vector=Vector)))
        controller=cls(None)
        with patch.dict("sys.modules",WorkingPlane=SimpleNamespace(get_working_plane=lambda:SimpleNamespace(axis=(0,0,1)))):
            controller.pick_points(received.append,count=3)
            for pos in ((0,0),(6000,0),(3000,1200)):
                callbacks["SoLocation2Event"]({"Position":pos})
                callbacks["SoMouseButtonEvent"](dict(State="DOWN",Button="BUTTON1",Position=pos))
        self.assertEqual(len(received[0]),3)
        self.assertEqual(len([s for s in snaps if s!="off"]),6)
        self.assertFalse(callbacks)
        self.assertEqual(snaps[-1],"off")

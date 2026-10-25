"""Presentation ownership, material copies and failure rollback without FreeCAD."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

PATH=Path(__file__).resolve().parents[1]/"freecad/SteelStructures/interactive/structural_reference_modes.py"


class Field:
    def __init__(self,values): self.values=list(values)
    def getNum(self): return len(self.values)
    def __getitem__(self,index): return self.values[index]
    def setValues(self,start,count,values): self.values[start:start+count]=values


class Node:
    INVISIBLE, UNPICKABLE = 1,2
    def __init__(self,name="",**fields):
        self.name,self.fields,self.children,self.refs,self.revision=name,fields,[],0,1
    def ref(self): self.refs+=1
    def unref(self):
        self.refs-=1
        if self.refs<0: raise AssertionError("unbalanced native pin")
    def getName(self): return self.name
    def getField(self,name): return self.fields.get(name)
    def addChild(self,node): self.children.append(node)
    def getChild(self,index): return self.children[index]
    def getNumChildren(self): return len(self.children)
    def findChild(self,node): return self.children.index(node) if node in self.children else -1
    def replaceChild(self,old,new): self.children[self.children.index(old)]=new
    def removeChild(self,node): self.children.remove(node)
    def removeAllChildren(self): self.children.clear()
    def setOverride(self,value): self.override=value
    def getNodeId(self): return self.revision
    def copy(self):
        result=deepcopy(self)
        result.refs=0
        return result


class PresentationTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location("_reference_modes_test",PATH)
        self.module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=self.module
        spec.loader.exec_module(self.module)
        coin=types.SimpleNamespace(SoSeparator=Node,SoSwitch=Node,SoDrawStyle=Node,SoPickStyle=Node,SoMaterial=Node,SO_SWITCH_NONE=-1)
        self.patch=patch.dict(sys.modules,{"pivy":types.SimpleNamespace(coin=coin)})
        self.patch.start()
        self.material=Node(transparency=Field([0.,.95]),diffuseColor=Field([(.2,.5,.9)]),rgba=Field([0x55C8D0FF,0xFFEEDD10]))
        self.source=Node("ObjectGroup")
        self.source.addChild(self.material)
        self.front=Node("GroupOnTop")
        self.scene=Node()
        self.scene.addChild(Node("Environment"))
        self.scene.addChild(self.source)
        self.scene.addChild(self.front)
        self.original=list(self.scene.children)
        self.presentation=self.module.ViewportPresentation(types.SimpleNamespace(getSceneGraph=lambda:self.scene))

    def tearDown(self):
        self.presentation.close()
        self.patch.stop()
        sys.modules.pop("_reference_modes_test",None)

    def test_structural_is_local_and_restores_exact_native_branches(self):
        second=Node()
        second.children=list(self.original)
        self.presentation.update("structural")
        self.assertEqual(len(self.presentation.wrappers),2)
        self.assertEqual(second.children,self.original)
        self.assertIs(self.presentation.source,self.source)
        self.assertEqual(self.presentation.wrappers[0].wrapper.whichChild,-1)
        self.assertEqual(self.source.children,[self.material])
        self.presentation.update("physical")
        self.assertEqual(self.scene.children,self.original)
        self.assertEqual(self.source.refs,0)

    def test_xray_clamps_only_copied_alpha_and_rebuilds_only_changed_source(self):
        original=deepcopy(self.material.fields)
        self.presentation.update("xray")
        clone=self.presentation.clone
        material=clone.children[0]
        self.assertEqual(material.fields["transparency"].values,[.78,.95])
        self.assertEqual(material.fields["rgba"].values,[0x55C8D038,0xFFEEDD10])
        self.assertEqual(material.fields["diffuseColor"].values,[(.2,.5,.9)])
        self.assertEqual(self.material.fields["transparency"].values,original["transparency"].values)
        self.presentation.update("xray")
        self.assertIs(self.presentation.clone,clone)
        self.assertEqual(self.presentation.copy_updates,1)
        self.material.fields["transparency"].values=[.9]
        self.source.revision+=1
        self.presentation.update("xray")
        self.assertEqual(clone.refs,0)
        self.assertEqual(self.presentation.clone.children[0].fields["transparency"].values,[.9])
        self.presentation.update("physical")
        self.assertEqual(self.material.fields["transparency"].values,[.9])
        self.assertEqual(self.scene.children,self.original)

    def test_copy_failure_restores_physical_and_balances_native_pins(self):
        with patch.object(self.source,"copy",side_effect=RuntimeError("unavailable native copy")):
            with self.assertRaisesRegex(RuntimeError,"unavailable native copy"):
                self.presentation.update("xray")
        self.assertEqual(self.presentation.mode,"physical")
        self.assertEqual(self.scene.children,self.original)
        self.assertEqual(self.source.refs,0)

    def test_repeated_modes_and_close_leave_no_owned_graphics(self):
        for _ in range(10):
            for mode in ("structural","xray","physical"):
                self.presentation.update(mode)
        self.presentation.close()
        self.presentation.close()
        self.assertEqual(self.scene.children,self.original)
        self.assertEqual(self.scene.refs,0)
        self.assertFalse(self.presentation.wrappers)

    def test_missing_native_seam_does_not_modify_other_graphics(self):
        self.source.name="UnexpectedNativeGroup"
        with self.assertRaisesRegex(RuntimeError,"ObjectGroup"):
            self.presentation.update("structural")
        self.assertEqual(self.scene.children,self.original)
        self.assertEqual(self.presentation.mode,"physical")

    def test_service_revision_ignores_native_preselection_notifications(self):
        self.presentation.update("xray",revision=7)
        clone=self.presentation.clone
        self.source.revision+=1
        self.presentation.update("xray",revision=7)
        self.assertIs(self.presentation.clone,clone)
        self.presentation.update("xray",revision=8)
        self.assertIsNot(self.presentation.clone,clone)

    def test_foreign_reparenting_is_neutralized_without_rewriting_foreign_tree(self):
        self.presentation.update("xray")
        wrapper=self.presentation.wrappers[0].wrapper
        foreign=Node("ExternalOwner")
        foreign.addChild(wrapper)
        self.scene.replaceChild(wrapper,foreign)
        with self.assertRaisesRegex(RuntimeError,"Outro recurso"):
            self.presentation.update("xray")
        self.assertEqual(self.scene.children[1],foreign)
        self.assertEqual(foreign.children,[wrapper])
        self.assertEqual(wrapper.children,[self.source])
        self.assertEqual(self.presentation.mode,"physical")


if __name__=="__main__": unittest.main()

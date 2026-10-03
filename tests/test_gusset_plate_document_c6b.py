"""Focused non-FreeCAD contracts for C6-B document integration."""

import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from freecad.SteelStructures.connections import (
    GussetCorridor, GussetPlateFrame, GussetPlateSpec, build_gusset_outline,
)
from tests.test_truss_manual_fixes import definition


ROOT = Path(__file__).parents[1]


class FakeObject:
    def __init__(self, name="StructuralGussetPlate"):
        self.Name = name
        self.Label = name
        self.PropertiesList = []
        self.editor_modes = {}
        self.Proxy = SimpleNamespace(_updating=False)

    def addProperty(self, _kind, name, _group):
        self.PropertiesList.append(name)

    def setEditorMode(self, name, mode):
        self.editor_modes[name] = mode


def outline(node="N", **changes):
    values = dict(stable_key=node+":gusset-plate", node_key=node,
                  plate_thickness=8., edge_margin=25., member_overlap=150.,
                  participant_keys=("P1", "P2"), component_keys=("R1:A", "R2:A"),
                  frame=GussetPlateFrame((10., 20., 30.), (1., 0., 0.),
                                         (0., 1., 0.), (0., 0., 1.)))
    values.update(changes)
    spec = GussetPlateSpec(**values)
    corridors = (GussetCorridor("P1", "R1:A", (1., 0.), -10., 10.),
                 GussetCorridor("P2", "R2:A", (0., 1.), -12., 12.))
    return build_gusset_outline(spec, corridors)


class GussetDocumentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT/"freecad"/"SteelStructures"/"gusset_plate.py").read_text(encoding="utf-8")
        cls.truss_source = (ROOT/"freecad"/"SteelStructures"/"truss.py").read_text(encoding="utf-8")

    def test_document_type_is_not_a_member_or_analytical_bar(self):
        self.assertIn('addObject("Part::FeaturePython", "StructuralGussetPlate")', self.source)
        for forbidden in ("create_member", "StructuralMemberProxy", "PhysicalRun", "AnalyticalBar",
                          "Interconnector"):
            self.assertNotIn(forbidden, self.source)
        self.assertIn("GeneratedGussetPlates", self.truss_source)
        self.assertNotIn('obj.GeneratedMembers = [children[key] for key in sorted(children)] +',
                         self.truss_source)

    def test_properties_are_controlled_and_apply_exact_outline_results(self):
        ensure = definition("gusset_plate.py", "ensure_gusset_properties", {})
        signature = definition("gusset_plate.py", "outline_signature", dict(json=json))
        apply = definition("gusset_plate.py", "apply_gusset_result", dict(
            ensure_gusset_properties=ensure, outline_signature=signature,
            build_gusset_shape=lambda _outline: None, GUSSET_OBJECT_SCHEMA_VERSION=1))
        obj = FakeObject()
        parent = object()
        value = outline()
        shape = SimpleNamespace(Volume=value.area*value.spec.plate_thickness)
        apply(obj, parent, value, shape)
        self.assertEqual((obj.StableKey, obj.NodeKey), ("N:gusset-plate", "N"))
        self.assertIs(obj.ParentTruss, parent)
        self.assertEqual((obj.Thickness, obj.EdgeMargin, obj.MemberOverlap), (8., 25., 150.))
        self.assertEqual(obj.AttachmentMode, "Auto")
        self.assertEqual(obj.ChordContact, "Auto")
        self.assertEqual(obj.TransversePlacement, "")
        self.assertAlmostEqual(obj.PlateArea, value.area)
        self.assertAlmostEqual(obj.Volume, shape.Volume)
        self.assertIs(obj.Shape, shape)
        self.assertEqual(obj.GenerationStatus, "Valid")
        for name in ("StableKey", "NodeKey", "Thickness", "EdgeMargin", "MemberOverlap",
                     "Side", "AttachmentMode", "ChordContact", "TransversePlacement",
                     "PlateArea", "Volume", "ParentTruss"):
            self.assertEqual(obj.editor_modes[name], 1)
        self.assertEqual(obj.editor_modes["SourceSignature"], 2)

    def test_signature_tracks_shape_inputs_but_not_label(self):
        signature = definition("gusset_plate.py", "outline_signature", dict(json=json))
        first = outline()
        second = build_gusset_outline(replace(first.spec, edge_margin=30.), (
            GussetCorridor("P1", "R1:A", (1., 0.), -10., 10.),
            GussetCorridor("P2", "R2:A", (0., 1.), -12., 12.)))
        self.assertNotEqual(signature(first), signature(second))
        self.assertEqual(signature(first), signature(outline()))

    def test_registry_is_separate_unique_and_node_stable(self):
        bound = definition("truss.py", "bound_gusset_plates", {})
        owner = SimpleNamespace(PropertiesList=["GeneratedGussetPlates"])
        plate = SimpleNamespace(Name="Plate001", NodeKey="NODE", StableKey="NODE:gusset-plate",
                                ParentTruss=owner)
        owner.GeneratedGussetPlates = [plate]
        self.assertEqual(bound(owner), {"NODE": plate})
        owner.GeneratedGussetPlates = [plate, plate]
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            bound(owner)
        owner.GeneratedGussetPlates = [SimpleNamespace(
            Name="Plate001", NodeKey="NODE", StableKey="unstable", ParentTruss=owner)]
        with self.assertRaisesRegex(ValueError, "inconsistente"):
            bound(owner)

    def test_registry_recovers_owned_plate_for_next_explicit_apply(self):
        bound = definition("truss.py", "bound_gusset_plates", {})
        owner = SimpleNamespace(PropertiesList=["GeneratedGussetPlates"],
                                GeneratedGussetPlates=[])
        plate = SimpleNamespace(Name="Plate001", NodeKey="NODE",
                                StableKey="NODE:gusset-plate", ParentTruss=owner,
                                GeneratedByTruss=True,
                                PropertiesList=["NodeKey"])
        owner.Document = SimpleNamespace(Objects=[plate])
        self.assertEqual(bound(owner), {"NODE": plate})

    def test_accept_state_keeps_member_and_plate_registries_separate(self):
        encoded = []
        accept = definition("truss.py", "accept_state", dict(
            ensure_gusset_registry=lambda obj: None,
            encode_state=lambda candidate, bindings: encoded.append(bindings) or "STATE",
            decode_state=lambda _text: {"schema_version": 5}))
        owner = SimpleNamespace()
        candidate = SimpleNamespace(stations=SimpleNamespace(left_panels=2, right_panels=3),
                                    warnings=())
        members = {"M": SimpleNamespace(Name="Member")}
        plates = {"N": SimpleNamespace(Name="Plate")}
        accept(owner, candidate, members, plates)
        self.assertEqual(owner.GeneratedMembers, [members["M"]])
        self.assertEqual(owner.GeneratedGussetPlates, [plates["N"]])
        self.assertEqual(encoded, [{"M": "Member"}])

    def test_preview_visibility_is_restored_individually(self):
        controller = definition("interactive/truss_controller.py", "TrussController", dict(
            App=SimpleNamespace(Console=SimpleNamespace(PrintWarning=lambda _text: None)),
            Gui=SimpleNamespace(), resynchronize_accepted_snapshots=lambda _obj: None))
        visible = SimpleNamespace(Name="A", ViewObject=SimpleNamespace(Visibility=True))
        hidden = SimpleNamespace(Name="B", ViewObject=SimpleNamespace(Visibility=False))
        owner = SimpleNamespace(AppliedState="state", GeneratedGussetPlates=[visible, hidden])
        document = SimpleNamespace(getObject=lambda name: {"A": visible, "B": hidden}.get(name))
        value = controller(document, owner)
        value._hide_persistent_gussets()
        self.assertEqual([visible.ViewObject.Visibility, hidden.ViewObject.Visibility], [False, False])
        value._restore_persistent_gussets()
        self.assertEqual([visible.ViewObject.Visibility, hidden.ViewObject.Visibility], [True, False])

    def test_normal_ui_consolidates_contact_into_plate_position(self):
        source = (ROOT/"freecad"/"SteelStructures"/"interactive"/
                  "truss_topology_editor.py").read_text(encoding="utf-8")
        preview = (ROOT/"freecad"/"SteelStructures"/"interactive"/
                   "gusset_section_preview.py").read_text(encoding="utf-8")
        self.assertNotIn("Contato no banzo:", source+preview)
        self.assertIn("Região da chapa:", preview)
        self.assertIn("Posição:", preview)
        self.assertIn("self.transverse_preview.add_position_controls(", source)
        self.assertIn("TrussInterior", source)
        self.assertNotIn("TrussExterior", source)
        self.assertNotIn("Apoio da chapa:", source+preview)


if __name__ == "__main__":
    unittest.main()

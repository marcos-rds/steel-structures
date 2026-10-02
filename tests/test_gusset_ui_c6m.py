"""Focused C6-M contextual transverse-placement presentation tests."""

from pathlib import Path
from types import SimpleNamespace
import unittest

from freecad.SteelStructures.connections import dumps, loads
from freecad.SteelStructures.trusses.connections import intent_from_data
from tests.test_gusset_c6j import _production
from tests.test_truss_manual_fixes import definition


class Combo:
    def __init__(self):
        self.items = []
        self.index = 0
        self.enabled = True

    def blockSignals(self, _value): return False
    def clear(self): self.items = []; self.index = 0
    def addItem(self, label, data): self.items.append((label, data))
    def findData(self, data):
        return next((index for index, item in enumerate(self.items)
                     if item[1] == data), -1)
    def setCurrentIndex(self, index): self.index = index
    def currentData(self): return self.items[self.index][1]
    def setEnabled(self, value): self.enabled = value


def presentation_functions():
    center = definition("interactive/truss_controller.py", "_candidate_center", {})
    deduplicate = definition(
        "interactive/truss_controller.py",
        "_deduplicated_transverse_candidates", {})
    regions = definition(
        "interactive/truss_controller.py", "_transverse_placement_regions",
        dict(_candidate_center=center,
             _deduplicated_transverse_candidates=deduplicate))
    return center, deduplicate, regions


def regions_for(outline):
    return presentation_functions()[2](outline.attachment.candidates)


def region_map(outline):
    return {region_id: (label, positions)
            for region_id, label, positions in regions_for(outline)}


def editor_for(regions, placement=""):
    cls = definition("interactive/truss_topology_editor.py", "TopologyEditor", dict(
        QtWidgets=SimpleNamespace(QDialog=object),
        __package__="freecad.SteelStructures.interactive"))
    editor = object.__new__(cls)
    editor._connection_node = "N"
    editor.gusset_region = Combo()
    editor.gusset_position = Combo()
    editor.canvas = SimpleNamespace(_last_model={"gussets": [{
        "node_key": "N", "transverse_regions": regions}]})
    invalid = editor._populate_gusset_options(placement)
    return editor, invalid


class ContextualRegionTests(unittest.TestCase):
    def test_laminated_u_has_external_then_internal_regions(self):
        outline = _production('U 4" x 8,04')
        regions = regions_for(outline)
        self.assertEqual(tuple(value[1] for value in regions),
                         ("Externa", "Interna"))
        self.assertEqual(tuple(label for _key, label in regions[0][2]),
                         ("Lado A", "Lado B"))
        self.assertEqual(tuple(label for _key, label in regions[1][2]),
                         ("Lado A", "Central", "Lado B"))

    def test_rotated_ue_separates_internal_and_both_stiffeners(self):
        outline = _production("Ue 150 × 60 × 20 × 3,00", rotation=90.)
        regions = regions_for(outline)
        self.assertEqual(tuple(value[1] for value in regions),
                         ("Externa", "Interna", "Enrijecedor A", "Enrijecedor B"))
        self.assertEqual(tuple(label for _key, label in regions[1][2]),
                         ("Lado A", "Central", "Lado B"))
        for region in regions[2:]:
            labels = tuple(label for _key, label in region[2])
            self.assertEqual(labels, (
                "Apoio — lado interno", "Apoio central",
                "Apoio — lado externo", "Face externa"))
            self.assertEqual(len(labels), len(set(labels)))

    def test_double_angle_prioritizes_external_and_between_components(self):
        regions = regions_for(_production("L 40 x 4", assembly="DoubleAngle"))
        self.assertEqual(tuple(value[1] for value in regions),
                         ("Externa", "Entre componentes",
                          "Cantoneira A", "Cantoneira B"))
        self.assertEqual(tuple(label for _key, label in regions[1][2]),
                         ("Junto ao componente A", "Central",
                          "Junto ao componente B"))
        self.assertFalse(any("faixa" in label.lower() or "região" in label.lower()
                             for _region, _name, positions in regions
                             for _key, label in positions))

    def test_closed_tubes_offer_only_physical_external_and_supported_regions(self):
        for designation in ("SHS 40x40x1,2", "RHS 60x40x1,2"):
            with self.subTest(designation=designation):
                regions = regions_for(_production(designation))
                self.assertEqual(tuple(value[1] for value in regions),
                                 ("Externa", "Apoiada no banzo"))
                self.assertNotIn("Interna", tuple(value[1] for value in regions))

    def test_local_ab_order_is_independent_of_candidate_enumeration(self):
        outline = _production("Ue 150 × 60 × 20 × 3,00", rotation=90.)
        function = presentation_functions()[2]
        self.assertEqual(function(outline.attachment.candidates),
                         function(tuple(reversed(outline.attachment.candidates))))


class DeduplicationTests(unittest.TestCase):
    @staticmethod
    def candidate(key, outline_band):
        return SimpleNamespace(
            stable_key=key,
            accessibility=SimpleNamespace(value="OuterExposed"),
            placement=SimpleNamespace(value="NearA"), diagnostics=(),
            slot_id="outer", plate_low=10., plate_high=18.,
            governing_participant_key="chord", contact_direction=1,
            contact_band=30., outline_band=outline_band,
            contact_window=SimpleNamespace(intervals=((None, None),)))

    def test_equivalent_candidates_collapse_but_different_outline_remains(self):
        _center, deduplicate, regions = presentation_functions()
        first = self.candidate("a-first", -10.)
        equivalent = self.candidate("z-equivalent", -10.)
        different_outline = self.candidate("different", -12.)
        values = deduplicate((first, equivalent, different_outline))
        self.assertEqual(tuple(value.stable_key for value in values),
                         ("a-first", "different"))
        visible = regions((first, equivalent, different_outline))
        self.assertEqual(tuple(key for key, _label in visible[0][2]),
                         ("a-first", "different"))


class DependentComboTests(unittest.TestCase):
    def setUp(self):
        self.outline = _production("L 40 x 4", assembly="DoubleAngle")
        self.regions = regions_for(self.outline)

    def test_persisted_stable_key_restores_both_fields_without_remapping(self):
        between = next(value for value in self.regions if value[0] == "between")
        saved_key = between[2][1][0]
        editor, invalid = editor_for(self.regions, saved_key)
        self.assertFalse(invalid)
        self.assertEqual(editor.gusset_region.currentData(), "between")
        self.assertEqual(editor.gusset_position.currentData(), saved_key)

        intent = intent_from_data("N", dict(
            form="Gusset", gusset=dict(transverse_placement=saved_key)))
        reopened = loads(dumps(intent))
        self.assertEqual(reopened.gusset.transverse_placement, saved_key)

    def test_automatic_disables_position_and_invalid_key_falls_back(self):
        automatic, invalid = editor_for(self.regions)
        self.assertFalse(invalid)
        self.assertEqual(automatic.gusset_region.currentData(), "")
        self.assertFalse(automatic.gusset_position.enabled)
        self.assertEqual(automatic.gusset_position.items,
                         [("Resolvida automaticamente", "")])

        fallback, invalid = editor_for(self.regions, "removed-profile-slot")
        self.assertTrue(invalid)
        self.assertEqual(fallback.gusset_region.currentData(), "")
        self.assertFalse(fallback.gusset_position.enabled)

    def test_region_change_uses_existing_candidates_and_selects_first_position(self):
        editor, _invalid = editor_for(self.regions)
        calls = []
        editor._connection_changed = lambda *_args: calls.append(
            editor.gusset_position.currentData())
        editor.gusset_region.setCurrentIndex(
            editor.gusset_region.findData("external"))
        editor._gusset_region_changed()
        external = next(value for value in self.regions if value[0] == "external")
        self.assertTrue(editor.gusset_position.enabled)
        self.assertEqual(editor.gusset_position.currentData(), external[2][0][0])
        self.assertEqual(calls, [external[2][0][0]])

    def test_presentation_never_changes_candidate_geometry(self):
        before = self.outline.points
        visible_keys = {key for _region, _label, positions in self.regions
                        for key, _position in positions}
        selected = next(candidate for candidate in self.outline.attachment.candidates
                        if candidate.stable_key in visible_keys)
        rebuilt = _production("L 40 x 4", assembly="DoubleAngle",
                              placement=selected.stable_key)
        self.assertEqual(self.outline.attachment.candidates,
                         rebuilt.attachment.candidates)
        self.assertEqual(before, self.outline.points)

    def test_region_and_position_are_not_document_schema_fields(self):
        for path in ("freecad/SteelStructures/connections/models.py",
                     "freecad/SteelStructures/connections/serialization.py"):
            source = Path(path).read_text(encoding="utf-8")
            self.assertNotIn("gusset_region", source)
            self.assertNotIn("gusset_position", source)


if __name__ == "__main__":
    unittest.main()

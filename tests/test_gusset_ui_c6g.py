"""Focused C6-G node-local diagnostics and dynamic placement UI tests."""

from pathlib import Path
from types import SimpleNamespace
import unittest

from freecad.SteelStructures.connections import compact_connection_messages
from tests.test_truss_manual_fixes import definition


class Combo:
    def __init__(self):
        self.items = []
        self.index = 0

    def blockSignals(self, _value): return False
    def clear(self): self.items = []; self.index = 0
    def addItem(self, label, data): self.items.append((label, data))
    def findData(self, data):
        return next((index for index, item in enumerate(self.items)
                     if item[1] == data), -1)
    def setCurrentIndex(self, index): self.index = index
    def currentData(self): return self.items[self.index][1]
    def setEnabled(self, value): self.enabled = value


class GussetUiTests(unittest.TestCase):
    def test_all_node_warnings_remain_accessible_without_dead_counter(self):
        values = compact_connection_messages(("quatro", "dois", "um", "três", "um"))
        self.assertEqual(len(values), 4)
        self.assertFalse(any("avisos adicionais" in value for value in values))

    def test_no_selected_node_clears_stale_gusset_warning(self):
        cls = definition("interactive/truss_topology_editor.py", "TopologyEditor", dict(
            QtWidgets=SimpleNamespace(QDialog=object),
            __package__="freecad.SteelStructures.interactive"))
        editor = object.__new__(cls)
        editor._connection_node = "old"
        editor.connection_box = SimpleNamespace(setEnabled=lambda _value: None)
        editor.participants = SimpleNamespace(setText=lambda value: setattr(
            editor.participants, "text", value))
        editor.message = SimpleNamespace(text="warning", setText=lambda value: setattr(
            editor.message, "text", value))
        editor.select_node(None)
        self.assertEqual(editor.message.text, "")

    def test_placement_labels_come_from_physical_candidates(self):
        cls = definition("interactive/truss_topology_editor.py", "TopologyEditor", dict(
            QtWidgets=SimpleNamespace(QDialog=object),
            __package__="freecad.SteelStructures.interactive"))
        editor = object.__new__(cls)
        editor._connection_node = "N"
        editor.gusset_region = Combo()
        editor.gusset_position = Combo()
        editor.canvas = SimpleNamespace(_last_model={"gussets": [{
            "node_key": "N",
            "transverse_regions": (("between", "Entre componentes", (
                ("gap:NearA", "Junto ao componente A"),
                ("gap:Center", "Central"),
                ("gap:NearB", "Junto ao componente B"))),),
        }]})
        editor._populate_gusset_options("gap:Center", False)
        self.assertEqual([label for label, _value in editor.gusset_region.items],
                         ["Automática", "Entre componentes"])
        self.assertEqual([label for label, _value in editor.gusset_position.items],
                         ["Junto ao componente A", "Central",
                          "Junto ao componente B"])
        self.assertEqual(editor.gusset_position.currentData(), "gap:Center")

    def test_invalid_old_placement_falls_back_to_automatic(self):
        cls = definition("interactive/truss_topology_editor.py", "TopologyEditor", dict(
            QtWidgets=SimpleNamespace(QDialog=object),
            __package__="freecad.SteelStructures.interactive"))
        editor = object.__new__(cls)
        editor._connection_node = "N"
        editor.gusset_region = Combo()
        editor.gusset_position = Combo()
        editor.canvas = SimpleNamespace(_last_model={"gussets": [{
            "node_key": "N", "transverse_regions": ()}]})
        invalid = editor._populate_gusset_options("old-slot", True)
        self.assertTrue(invalid)
        self.assertEqual(editor.gusset_region.currentData(), "")
        self.assertEqual(editor.gusset_position.currentData(), "")
        self.assertFalse(editor.gusset_position.enabled)

    def test_candidate_options_exclude_closed_void_and_unsupported_slab(self):
        center = definition("interactive/truss_controller.py", "_candidate_center", {})
        deduplicate = definition("interactive/truss_controller.py",
                                 "_deduplicated_transverse_candidates", {})
        labels = definition("interactive/truss_controller.py",
                            "_transverse_placement_regions", dict(
                                _candidate_center=center,
                                _deduplicated_transverse_candidates=deduplicate))
        def candidate(key, accessibility, placement):
            return SimpleNamespace(stable_key=key,
                                   accessibility=SimpleNamespace(value=accessibility),
                                   placement=SimpleNamespace(value=placement),
                                   diagnostics=(("Faixa de superfície de seção fechada.",)
                                                if accessibility == "SurfaceBand" else ()))
        options = labels((candidate("a:NearA", "OuterExposed", "NearA"),
                          candidate("b:Center", "AssemblyGap", "Center"),
                          candidate("s:Center", "SurfaceBand", "Center"),
                          candidate("c:Center", "EnclosedVoid", "Center"),
                          candidate("d:Center", "Unsupported", "Center")))
        self.assertEqual(options, (
            ("external", "Externa", (("a:NearA", "Lado A"),)),
            ("between", "Entre componentes", (("b:Center", "Central"),)),
            ("supported", "Apoiada no banzo", (("s:Center", "Central"),))))

    def test_generator_model_does_not_merge_gusset_diagnostics_globally(self):
        source = Path("freecad/SteelStructures/interactive/truss_controller.py").read_text(
            encoding="utf-8")
        global_block = source[source.index("connection_diagnostics=list"):
                              source.index("connection_diagnostics_by_node")]
        self.assertNotIn("gusset_diagnostics", global_block)
        self.assertNotIn("attachment_diagnostics", global_block)
        self.assertIn("value.intent.form.value != \"Gusset\"", global_block)

    def test_normal_ui_exposes_region_and_contextual_position(self):
        source = Path("freecad/SteelStructures/interactive/truss_topology_editor.py").read_text(
            encoding="utf-8")
        self.assertIn('self.transverse_preview.add_position_controls(', source)
        preview_source = Path("freecad/SteelStructures/interactive/gusset_section_preview.py").read_text(
            encoding="utf-8")
        self.assertIn('form.addRow("Região da chapa:", region)', preview_source)
        self.assertIn('form.addRow("Posição:", position)', preview_source)
        self.assertNotIn("self.gusset_transverse", source)
        self.assertNotIn("self.gusset_contact", source)
        self.assertNotIn("OPEN_RECESS", source)
        self.assertNotIn("StableKey", source)


if __name__ == "__main__":
    unittest.main()

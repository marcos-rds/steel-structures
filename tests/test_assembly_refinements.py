"""Focused final C3-B label and composition selection regressions."""
import types
import unittest
from unittest.mock import Mock

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.profiles.selection_filter import ProfileChoices
from freecad.SteelStructures.trusses.assemblies import compatible_modes, configure_assembly, component_label
from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration
from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
from tests.test_truss_assemblies import config
from tests.test_truss_manual_fixes import definition
from tests.test_profile_options_browser_integration import _load_options_runtime_module, _Combo


class AssemblyRefinementTests(unittest.TestCase):
    def test_all_catalog_levels_use_validation_compatibility(self):
        for mode in ('Single', 'DoubleAngle', 'DoubleChannelInward', 'DoubleChannelOutward', 'SpacedPair'):
            choices = ProfileChoices(lambda p: mode in compatible_modes(p))
            expected = {p.designation for p in profile_catalog.profiles().values()
                        if mode in compatible_modes(p.definition)}
            actual = set()
            for category in choices.categories():
                series = choices.series_for_category(category)
                self.assertTrue(series)
                for name in series:
                    items = choices.designations(category, name)
                    self.assertTrue(items)
                    actual.update(items)
            self.assertEqual(actual, expected)

    def test_filter_switch_preserves_compatible_and_restores_previous_choice(self):
        module = _load_options_runtime_module()
        # This isolated options loader normally stubs sibling modules.
        module.ProfileOptionsWidget.set_profile_filter.__globals__['__spec__'] = None
        module.ProfileOptionsWidget.set_profile_filter.__globals__['__package__'] = 'freecad.SteelStructures.interactive'
        widget = object.__new__(module.ProfileOptionsWidget)
        widget.category = _Combo(profile_catalog.categories())
        widget.series, widget.profile = _Combo(), _Combo()
        widget.refresh_automatic_name = lambda: None
        angle, channel = 'L 40 x 4', 'U 4" x 8,04'
        widget.set_profile_ref(profile_catalog.ref_for_designation(channel))
        for mode in ('DoubleChannelInward', 'DoubleChannelOutward', 'SpacedPair', 'Single'):
            widget.set_profile_filter(lambda p: mode in compatible_modes(p))
            self.assertEqual(widget.profile_designation, channel)
        widget.set_profile_filter(lambda p: 'DoubleAngle' in compatible_modes(p), angle)
        self.assertEqual(widget.profile_designation, angle)
        before = (widget.category.items[:], widget.series.items[:], widget.profile.items[:])
        with self.assertRaises(ValueError):
            widget.set_profile_ref(profile_catalog.ref_for_designation(channel))
        self.assertEqual(before, (widget.category.items, widget.series.items, widget.profile.items))
        widget.set_profile_filter(lambda p: 'DoubleChannelInward' in compatible_modes(p), channel)
        self.assertEqual(widget.profile_designation, channel)
        self.assertTrue(widget.profile.currentIndexChanged.values)

        editor_type = definition('interactive/assembly_editor.py', 'AssemblyEditor',
            dict(_RoleProfileDialog=object, compatible_modes=compatible_modes))
        editor = object.__new__(editor_type)
        editor.options = widget
        editor.mode = _Combo(['DoubleAngle'])
        editor._last_mode = 'DoubleChannelInward'
        editor._profile_choices = {}
        editor.angle_arrangement = _Combo(['outward', 'inward'])
        editor._queue_refresh = Mock()
        editor._mode_changed()
        self.assertIn('DoubleAngle', compatible_modes(profile_catalog.get(widget.profile_designation).definition))
        self.assertEqual(editor._profile_choices['DoubleChannelInward'], channel)
        editor.mode = _Combo(['DoubleChannelInward'])
        editor._mode_changed()
        self.assertEqual(widget.profile_designation, channel)
        self.assertEqual(editor._queue_refresh.call_count, 2)

    def test_catalog_browser_filters_tree_and_table_with_same_predicate(self):
        from freecad.SteelStructures.profiles import ProfileLibrary
        from freecad.SteelStructures.paths import CATALOGS_DIR
        class Item:
            def __init__(self, text):
                self.children = []
            def setData(self, *args):
                self.data = args[-1]
            def addChild(self, item):
                self.children.append(item)
            def setExpanded(self, value):
                pass
        qt = types.SimpleNamespace(QDialog=object, QTreeWidgetItem=Item, QTableWidgetItem=Item)
        browser_type = definition('interactive/profile_browser.py', 'ProfileBrowserDialog',
            dict(QtWidgets=qt, _user_role=lambda: 32))
        browser = object.__new__(browser_type)
        browser.library = ProfileLibrary(CATALOGS_DIR)
        browser._profile_filter = lambda p: 'DoubleChannelInward' in compatible_modes(p)
        browser._filter_catalog = True
        roots = []
        browser.tree = types.SimpleNamespace(addTopLevelItem=roots.append)
        browser._populate_tree()
        expected = [p for p in browser.library.list_profiles() if browser._profile_filter(p)]
        self.assertEqual({r.data[0] for r in roots}, {p.category_id for p in expected})
        self.assertEqual({c.data for r in roots for c in r.children},
                         {(p.category_id, p.series_id) for p in expected})
        browser.table = Mock()
        browser.model = types.SimpleNamespace(profiles=browser.library.list_profiles())
        browser._show_profile = Mock()
        browser._populate_table()
        self.assertEqual(browser.table.insertRow.call_count, len(expected))
        self.assertEqual({call.args[2].data for call in browser.table.setItem.call_args_list},
                         {p.ref for p in expected})

    def test_double_to_single_preserves_a_removes_b_and_normalizes_label(self):
        value = config()
        value['role_specs']['DIAGONAL'] = configure_assembly(value['role_specs']['DIAGONAL'], 'DoubleAngle', 80)
        before = build_candidate(value)
        children = {}
        for item in before.items:
            child = types.SimpleNamespace(
                Name='Member'+str(len(children)), GenerationKey=item.key, ComponentKey=item.component_key,
                PropertiesList=['RunKey', 'AssemblyKey', 'ComponentKey'], setEditorMode=lambda *args: None,
                AssemblySectionTransform='transform' if item.spec.assembly != 'Single' else '',
                Label=component_label(item, before.runs), DisplayName=component_label(item, before.runs),
                StartExtension=12, Adjustments=['kept'], State=[], GenerationStatus='Valid',
                Shape=types.SimpleNamespace(isNull=lambda: False, isValid=lambda: True, Volume=1))
            children[item.key] = child
        original = {k: vars(c).copy() for k, c in children.items()}
        obj = types.SimpleNamespace(AppliedState=encode_state(before, {k: c.Name for k, c in children.items()}),
            Proxy=types.SimpleNamespace(), RoleGroups=[], ViewObject=types.SimpleNamespace(Visibility=True))
        document = Mock()
        value['role_specs']['DIAGONAL'] = configure_assembly(value['role_specs']['DIAGONAL'], 'Single')
        namespace = dict(__package__='freecad.SteelStructures', resolve_linked_reference=lambda d,c,o:c,
            decode_state=decode_state, build_candidate=build_candidate, bound_children=lambda *args:children,
            conflicts_for=lambda *args:{}, plan_regeneration=plan_regeneration,
            prepare_batch=lambda c,ch:{i.key:None for i in c.items}, set_config=lambda *args:None,
            apply_result=lambda *args:None, controlled_state=lambda c:'state', ROLES=(),
            accept_state=lambda o,c,result:setattr(o,'GeneratedMembers',list(result.values())))
        apply = definition('truss.py', 'apply_truss', namespace)
        apply(document, value, obj)
        after = build_candidate(value)
        for item in after.items:
            child = children[item.key]
            self.assertIn(child, obj.GeneratedMembers)
            self.assertEqual(child.GenerationKey, original[item.key]['GenerationKey'])
            self.assertEqual(child.ComponentKey, 'A')
            self.assertEqual(child.StartExtension, 12)
            self.assertEqual(child.Adjustments, ['kept'])
            self.assertEqual(child.Label, component_label(item, after.runs))
            self.assertNotIn(' / ', child.Label)
        removed = {call.args[0] for call in document.removeObject.call_args_list}
        self.assertEqual(removed, {c.Name for c in children.values() if c.ComponentKey == 'B'})
        document.addObject.assert_not_called()


if __name__ == '__main__':
    unittest.main()

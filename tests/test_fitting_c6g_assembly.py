"""Focused C6-G regressions for component-to-component chord fitting."""

import copy
import unittest

from freecad.SteelStructures.trusses.assemblies import configure_assembly
from freecad.SteelStructures.trusses.realization import build_candidate, plan_regeneration
from tests.test_truss_assemblies import config


def _actions(item):
    plan = item.physical_fit_plan
    return tuple(action for action in (plan["start_action"], plan["end_action"])
                 if action is not None)


def _candidate(web_mode="Single", chord_mode="Single", spacing=60.,
               chord_uses_angle=False, web_uses_channel=False):
    value = config()
    if chord_uses_angle:
        for role in ("TOP_CHORD", "BOTTOM_CHORD"):
            value["role_specs"][role]["profile_ref"] = copy.deepcopy(
                value["role_specs"]["DIAGONAL"]["profile_ref"])
    if web_uses_channel:
        value["role_specs"]["DIAGONAL"]["profile_ref"] = copy.deepcopy(
            value["role_specs"]["TOP_CHORD"]["profile_ref"])
    for role in ("TOP_CHORD", "BOTTOM_CHORD"):
        value["role_specs"][role] = configure_assembly(
            value["role_specs"][role], chord_mode, spacing)
    value["role_specs"]["DIAGONAL"] = configure_assembly(
        value["role_specs"]["DIAGONAL"], web_mode, spacing)
    value["role_specs"]["DIAGONAL"]["physical_fit"] = "ToChord"
    return value, build_candidate(value)


class AssemblyChordFittingTests(unittest.TestCase):
    def _assert_all_web_ends_fitted(self, candidate):
        webs = [item for item in candidate.items
                if item.role == "DIAGONAL" and item.element_kind == "Component"]
        self.assertTrue(webs)
        for item in webs:
            self.assertEqual(len(_actions(item)), 2)
            self.assertFalse(any(diagnostic["code"] == "INVALID_CHORD_GEOMETRY"
                                 for diagnostic in item.physical_fit_plan["diagnostics"]))
        return webs

    def test_double_angle_web_matches_double_angle_chord_components(self):
        value, candidate = _candidate("DoubleAngle", "DoubleAngle",
                                      chord_uses_angle=True)
        webs = self._assert_all_web_ends_fitted(candidate)
        targets = {item.key: item for item in candidate.items
                   if item.role in ("TOP_CHORD", "BOTTOM_CHORD")
                   and item.element_kind == "Component"}
        for web in webs:
            self.assertTrue(all(targets[action["reference_key"]].component_key
                                == web.component_key for action in _actions(web)))

        # Fitting changes plans, never nominal component axes or identities.
        nominal_value = copy.deepcopy(value)
        nominal_value["role_specs"]["DIAGONAL"]["physical_fit"] = "None"
        nominal = build_candidate(nominal_value)
        axes = {item.key: (item.start_global, item.end_global)
                for item in nominal.items if item.role == "DIAGONAL"}
        self.assertEqual(axes, {item.key: (item.start_global, item.end_global)
                               for item in candidate.items if item.role == "DIAGONAL"})
        rebuilt = build_candidate(value, candidate)
        self.assertTrue(all(action.action == "UNCHANGED"
                            for action in plan_regeneration(rebuilt, candidate).actions))

    def test_double_angle_web_to_single_channel_is_preserved(self):
        _value, candidate = _candidate("DoubleAngle", "Single")
        webs = self._assert_all_web_ends_fitted(candidate)
        self.assertTrue(all(len({action["reference_key"] for action in _actions(web)}) <= 2
                            for web in webs))

    def test_single_web_fits_to_nearest_double_angle_component(self):
        _value, candidate = _candidate("Single", "DoubleAngle",
                                       chord_uses_angle=True)
        webs = self._assert_all_web_ends_fitted(candidate)
        target_keys = {item.key for item in candidate.items
                       if item.role in ("TOP_CHORD", "BOTTOM_CHORD")
                       and item.element_kind == "Component"}
        self.assertTrue(all(action["reference_key"] in target_keys
                            for web in webs for action in _actions(web)))

    def test_double_channel_and_spaced_pair_use_shared_matching(self):
        _value, double_channel = _candidate(
            "DoubleChannelInward", "DoubleChannelInward", 100.,
            web_uses_channel=True)
        channel_webs = self._assert_all_web_ends_fitted(double_channel)
        channel_targets = {item.key: item for item in double_channel.items
                           if item.role in ("TOP_CHORD", "BOTTOM_CHORD")
                           and item.element_kind == "Component"}
        for web in channel_webs:
            self.assertTrue(all(channel_targets[action["reference_key"]].component_key
                                == web.component_key for action in _actions(web)))

        _value, spaced_pair = _candidate("Single", "SpacedPair", 100.)
        self._assert_all_web_ends_fitted(spaced_pair)


if __name__ == "__main__":
    unittest.main()

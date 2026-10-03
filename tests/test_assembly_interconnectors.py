"""C4-A focused pure contract, geometry and regeneration tests."""
from dataclasses import asdict, replace
import json
import math
import unittest

from freecad.SteelStructures.assemblies import (
    MemberFrame, InterconnectorSpec, DistributionSpec, SectionTransform,
    resolve_member_assembly, resolve_stations, plan_regeneration)
from freecad.SteelStructures.assemblies.interconnectors import validate_pair
from freecad.SteelStructures.assemblies.serialization import dumps, loads
from tests.assemblies_c4a_fixtures import proof_specs

AXIS = ((0., 0., 0.), (0., 0., 1000.))
FRAME = MemberFrame.from_axis(AXIS, (1., 0., 0.))


class DistributionTests(unittest.TestCase):
    def test_count_means_stations_with_offsets_and_both_boundaries(self):
        result = resolve_stations(1000., DistributionSpec(station_count=4), 100., 150.)
        self.assertEqual([s.position for s in result.stations], [100., 350., 600., 850.])
        self.assertEqual((result.effective_count, result.effective_spacing, result.effective_length), (4, 250., 750.))

    def test_target_spacing_ceil_and_effective_spacing(self):
        for spacing, count, effective in ((300., 4, 250.), (250., 4, 250.), (1000., 2, 750.)):
            result = resolve_stations(1000., DistributionSpec("ByTargetSpacing", None, spacing), 100, 150)
            self.assertEqual(result.effective_count, count)
            self.assertEqual(result.effective_spacing, effective)
            self.assertLessEqual(effective, spacing)

    def test_single_batten_station_is_midpoint(self):
        result = resolve_stations(1000., DistributionSpec(station_count=1), 100, 150)
        self.assertEqual(result.stations[0].position, 475.)
        self.assertEqual(result.effective_spacing, 0.)
        self.assertTrue(result.messages)

    def test_slots_are_stable_and_can_be_persisted(self):
        spec = DistributionSpec(station_count=3, station_keys=("left", "middle", "right"))
        a = resolve_stations(1000, spec)
        b = resolve_stations(1700, spec, 100, 200)
        self.assertEqual([s.key for s in a.stations], [s.key for s in b.stations])
        self.assertNotEqual(a.stations, b.stations)
        with self.assertRaisesRegex(ValueError, "chaves"):
            resolve_stations(1000, replace(spec, station_count=4))

    def test_invalid_distribution_inputs(self):
        for count in (0, -1, True, 2.5, 10001):
            with self.subTest(count=count), self.assertRaises(ValueError):
                DistributionSpec(station_count=count)
        for spacing in (0, -1, float("nan"), True):
            with self.subTest(spacing=spacing), self.assertRaises(ValueError):
                DistributionSpec("ByTargetSpacing", None, spacing)
        for kwargs in (dict(mode="Other"), dict(target_spacing=2),
                       dict(station_keys=("same", "same")), dict(station_keys=("",))):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                DistributionSpec(**kwargs)

    def test_invalid_nominal_length_and_offsets(self):
        for length, start, end in ((0, 0, 0), (100, 60, 40), (100, 60, 50),
                                   (100, -1, 0), (math.inf, 0, 0), (100, 0, math.nan)):
            with self.subTest(values=(length, start, end)), self.assertRaises(ValueError):
                resolve_stations(length, DistributionSpec(), start, end)

    def test_resource_limit_is_explicit(self):
        with self.assertRaisesRegex(ValueError, "demais"):
            resolve_stations(1000, DistributionSpec("ByTargetSpacing", None, 1e-300))


class InterconnectorTests(unittest.TestCase):
    def setUp(self):
        self.specs = proof_specs()

    def realize(self, spec, axis=AXIS, frame=FRAME):
        return resolve_member_assembly(axis, frame, spec)

    def test_all_proof_presets_roundtrip_without_schema_bump(self):
        for spec, count in zip(self.specs, (0, 4, 3, 6, 4, 3, 3)):
            with self.subTest(spec=spec):
                self.assertEqual(loads(dumps(spec)), spec)
                self.assertEqual(json.loads(dumps(spec))["schema_version"], 1)
                result = self.realize(spec)
                self.assertEqual(len(result.components), 2)
                self.assertEqual(len(result.interconnectors), count)
                self.assertEqual(len(result.elements), count+2)

    def test_c3_missing_reserved_field_loads_empty(self):
        payload = json.loads(dumps(self.specs[0]))
        del payload["spec"]["interconnectors"]
        self.assertEqual(loads(json.dumps(payload)), self.specs[0])
        self.assertEqual(self.realize(loads(json.dumps(payload))).interconnectors, ())

    def test_none_is_empty_realization(self):
        spec = self.specs[1]
        result = self.realize(replace(spec, interconnectors=(replace(spec.interconnectors[0], kind="None"),)))
        self.assertEqual(result.interconnectors, ())
        self.assertEqual(result.components, self.realize(self.specs[0]).components)

    def test_invalid_contracts(self):
        connector = self.specs[1].interconnectors[0]
        for changes in (dict(component_pair=("A", "A")), dict(component_pair=("A",)),
                        dict(kind="StayPlate"), dict(interconnector_key=""), dict(profile_ref=None),
                        dict(color=(1, -1, 0)), dict(start_offset=-1), dict(section_transform=None),
                        dict(start_side="B"), dict(distribution=None), dict(insertion_reference="")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(connector, **changes)

    def test_component_pair_uses_keys_and_validates_membership(self):
        spec = self.specs[1]
        self.assertEqual(self.realize(spec).interconnectors,
                         self.realize(replace(spec, components=spec.components[::-1])).interconnectors)
        with self.assertRaisesRegex(ValueError, "não existe"):
            replace(spec, interconnectors=(replace(spec.interconnectors[0], component_pair=("A", "missing")),))
        with self.assertRaisesRegex(ValueError, "únicas"):
            replace(spec, interconnectors=spec.interconnectors*2)

    def test_cardinality_and_coincident_axes_rejected(self):
        spec = self.specs[1]
        with self.assertRaisesRegex(ValueError, "dois"):
            replace(spec, components=spec.components+(replace(spec.components[0], component_key="C"),),
                    component_spacing=None, assembly_insertion="Center")
        with self.assertRaisesRegex(ValueError, "coincidentes"):
            self.realize(replace(spec, component_spacing=0,
                components=tuple(replace(c, transverse_translation=(0, 0)) for c in spec.components)))

    def test_resolved_pair_checks_parallel_length_and_nominal_origin(self):
        components = self.realize(self.specs[1]).components
        for changes, message in ((dict(end_global=(150, 0, 1000)), "paralelos"),
                                 (dict(end_global=(120, 0, 900)), "Comprimentos"),
                                 (dict(start_global=(120, 0, 100), end_global=(120, 0, 1100)), "estação"),
                                 (dict(end_global=(120, 0, 0)), "degenerado")):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                validate_pair((components[0], replace(components[1], **changes)), ("A", "B"), AXIS)

    def test_battens_are_axis_to_axis_at_stations(self):
        result = self.realize(self.specs[1])
        self.assertEqual([c.start_global for c in result.interconnectors],
                         [(-120., 0., s) for s in (100., 350., 600., 850.)])
        self.assertEqual([c.end_global for c in result.interconnectors],
                         [(120., 0., s) for s in (100., 350., 600., 850.)])
        self.assertEqual([c.label for c in result.interconnectors], [f"Presilha {i:02d}" for i in range(1, 5)])

    def test_single_lacing_alternates_and_start_side_updates_identity(self):
        spec = self.specs[2]
        a = self.realize(spec)
        b = self.realize(replace(spec, interconnectors=(replace(spec.interconnectors[0], start_side="B"),)))
        self.assertEqual([c.start_global[0] for c in a.interconnectors], [-120, 120, -120])
        self.assertEqual([c.end_global[0] for c in a.interconnectors], [120, -120, 120])
        self.assertEqual([c.start_global[2] for c in a.interconnectors], [100, 350, 600])
        self.assertEqual([c.end_global[2] for c in a.interconnectors], [350, 600, 850])
        self.assertEqual([c.start_global[0] for c in b.interconnectors], [120, -120, 120])
        self.assertFalse(plan_regeneration(b, a).structural)
        self.assertEqual([c.stable_identity for c in a.elements], [c.stable_identity for c in b.elements])

    def test_double_lacing_has_two_independent_unsplit_diagonals_per_bay(self):
        result = self.realize(self.specs[3])
        for a, b in zip(result.interconnectors[::2], result.interconnectors[1::2]):
            mid_a = tuple((x+y)/2 for x, y in zip(a.start_global, a.end_global))
            mid_b = tuple((x+y)/2 for x, y in zip(b.start_global, b.end_global))
            self.assertEqual(mid_a, mid_b)
            self.assertNotEqual(a.stable_identity, b.stable_identity)
            self.assertEqual(a.slot_key, b.slot_key)
            self.assertEqual(a.start_global[2]+250, a.end_global[2])

    def test_lacing_requires_two_stations(self):
        spec = self.specs[2]
        with self.assertRaisesRegex(ValueError, "duas estações"):
            self.realize(replace(spec, interconnectors=(replace(spec.interconnectors[0],
                distribution=DistributionSpec(station_count=1)),)))

    def test_same_cardinality_keeps_bindings_across_geometry_and_profile_changes(self):
        spec = self.specs[1]
        before = self.realize(spec)
        changed = replace(spec.interconnectors[0], start_offset=80, end_offset=200,
                          profile_ref=self.specs[2].interconnectors[0].profile_ref, color=(1, 0, 0),
                          section_transform=SectionTransform(37, True))
        after = self.realize(replace(spec, interconnectors=(changed,)))
        bindings = {c.stable_identity: "member"+str(i) for i, c in enumerate(before.elements)}
        plan = plan_regeneration(after, before, bindings)
        self.assertFalse(plan.structural)
        self.assertEqual({a.existing_binding for a in plan.actions}, set(bindings.values()))
        self.assertEqual(sum(a.action == "UPDATE_EXISTING" for a in plan.actions), 4)

    def test_transverse_spacing_updates_components_and_connectors_in_place(self):
        spec = self.specs[1]
        changed = replace(spec, component_spacing=400., components=tuple(replace(c,
            transverse_translation=(-200. if c.component_key == "A" else 200., 0.)) for c in spec.components))
        plan = plan_regeneration(self.realize(changed), self.realize(spec))
        self.assertFalse(plan.structural)
        self.assertTrue(all(a.action == "UPDATE_EXISTING" for a in plan.actions))

    def test_target_spacing_changes_same_count_preserve_slots(self):
        spec = self.specs[1]
        connector = replace(spec.interconnectors[0], distribution=DistributionSpec("ByTargetSpacing", None, 300))
        a = self.realize(replace(spec, interconnectors=(connector,)))
        b = self.realize(replace(spec, interconnectors=(replace(connector, end_offset=200),)))
        self.assertFalse(plan_regeneration(b, a).structural)
        self.assertEqual(a.distributions[0][1].effective_count, b.distributions[0][1].effective_count)

    def test_pattern_and_count_transitions_are_structural(self):
        for first, second in ((0, 1), (1, 2), (2, 3)):
            plan = plan_regeneration(self.realize(self.specs[second]), self.realize(self.specs[first]))
            self.assertTrue(plan.structural)
            self.assertEqual(sum(a.action == "UNCHANGED" for a in plan.actions), 2)
        spec = self.specs[1]
        changed = replace(spec, interconnectors=(replace(spec.interconnectors[0],
            distribution=DistributionSpec(station_count=5)),))
        self.assertTrue(plan_regeneration(self.realize(changed), self.realize(spec)).structural)

    def test_frame_and_transform_follow_inclined_assembly_plane(self):
        axis = ((10, 20, 30), (610, 620, 630))
        frame = MemberFrame.from_axis(axis, (1, -1, 0))
        spec = self.specs[3]
        transform = SectionTransform(37, True)
        spec = replace(spec, interconnectors=(replace(spec.interconnectors[0], section_transform=transform),))
        result = self.realize(spec, axis, frame)
        for c in result.interconnectors:
            self.assertEqual(c.section_transform, transform)
            self.assertAlmostEqual(abs(sum(x*y for x, y in zip(c.orientation.v, frame.v))), 1.)
            self.assertAlmostEqual(sum(x*y for x, y in zip(c.orientation.u, c.orientation.w)), 0.)
            self.assertGreater(math.dist(c.start_global, c.end_global), 240.)

    def test_truss_topology_is_untouched_and_role_preserves_interconnectors(self):
        from tests.test_truss_assemblies import config
        from freecad.SteelStructures.trusses.realization import build_candidate
        from freecad.SteelStructures.trusses.assemblies import configure_assembly, role_assembly_spec
        from freecad.SteelStructures.assemblies.resolver import resolve_logical_member
        value = config()
        candidate = build_candidate(value)
        before = asdict(candidate)
        item = candidate.items[0]
        resolved = resolve_logical_member(item, self.specs[3])
        self.assertEqual(len(resolved.interconnectors), 6)
        self.assertEqual(asdict(candidate), before)
        role = configure_assembly(value["role_specs"]["TOP_CHORD"], "SpacedPair", 240)
        payload = json.loads(dumps(self.specs[3]))
        payload["spec"]["assembly_key"] = "ASSEMBLY"
        role["assembly_spec"] = payload
        self.assertEqual(role_assembly_spec(role).interconnectors, self.specs[3].interconnectors)
        value["role_specs"]["TOP_CHORD"] = role
        integrated = build_candidate(value)
        self.assertEqual(integrated.graph, candidate.graph)
        self.assertEqual(integrated.runs, candidate.runs)
        self.assertTrue(any(i.element_kind == "Interconnector" for i in integrated.items))

    def test_catalog_profiles_in_proof_are_real(self):
        from freecad.SteelStructures import profile_catalog
        from freecad.SteelStructures.profiles.geometry import build_section_geometry
        for spec in self.specs[1:]:
            for connector in spec.interconnectors:
                designation = profile_catalog.selection_for_ref(connector.profile_ref)[2]
                self.assertGreater(build_section_geometry(profile_catalog.get(designation).definition).area, 0)

    def test_multiple_specs_and_component_order_do_not_change_identities(self):
        spec = self.specs[1]
        second = replace(self.specs[2].interconnectors[0], interconnector_key="SECOND")
        spec = replace(spec, interconnectors=spec.interconnectors+(second,))
        a = self.realize(spec)
        b = self.realize(replace(spec, components=spec.components[::-1], interconnectors=spec.interconnectors[::-1]))
        self.assertEqual(a.interconnectors, b.interconnectors)
        self.assertEqual(len({e.stable_identity for e in a.elements}), len(a.elements))


class AdapterContractTests(unittest.TestCase):
    """Small boundary checks; actual OCC/transactions live in the manual gate."""
    def load_definition(self, name, namespace):
        from tests.test_truss_manual_fixes import definition
        namespace.update(__package__="freecad.SteelStructures", json=json)
        return definition("assembly.py", name, namespace)

    def test_metadata_distinguishes_elements_without_labels_or_links(self):
        metadata = self.load_definition("element_metadata", {"_identity": json.dumps})
        spec = proof_specs()[1]
        result = resolve_member_assembly(AXIS, FRAME, spec)
        a, b = metadata(result.components[0]), metadata(result.interconnectors[0])
        self.assertEqual(a["AssemblyElementKind"], "Component")
        self.assertEqual(a["ComponentKey"], "A")
        self.assertEqual(a["InterconnectorKey"], "")
        self.assertEqual(b["AssemblyElementKind"], "Interconnector")
        self.assertEqual(b["ComponentKey"], "")
        self.assertEqual(b["InterconnectorKey"], "WEB")
        self.assertEqual(json.loads(b["InterconnectorSlotKey"]), ["S0000"])
        self.assertTrue(all(isinstance(v, str) for v in b.values()))

    def test_unknown_profile_is_human_value_error_before_mutation(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from freecad.SteelStructures.profiles.validation import ProfileNotFoundError
        resolver = Mock(side_effect=ProfileNotFoundError("internal ref"))
        values = self.load_definition("component_values", dict(SimpleNamespace=SimpleNamespace,
            asdict=asdict, item_values=resolver))
        item = resolve_member_assembly(AXIS, FRAME, proof_specs()[1]).interconnectors[0]
        with self.assertRaisesRegex(ValueError, "não está disponível no catálogo"):
            values(item)

    def test_pure_core_does_not_import_freecad_or_gui(self):
        import subprocess
        import sys
        code = ("import sys; import freecad.SteelStructures.assemblies; "
                "assert not {'FreeCAD', 'Part', 'PySide', 'PySide2', 'pivy'}.intersection(sys.modules)")
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()

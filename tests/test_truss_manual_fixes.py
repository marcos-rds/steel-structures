"""Focused regressions for the C1 manual feedback (no FreeCAD/Qt runtime)."""
import ast
import copy
from dataclasses import asdict
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from freecad.SteelStructures import profile_catalog, profiles
from freecad.SteelStructures.profiles.preview_geometry import transform_preview_point
from freecad.SteelStructures.profiles.geometry import Point2D
from freecad.SteelStructures.trusses.realization import build_candidate
from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
from tests.test_truss_task_panel import config_fixture, make_panel, Number
from tests.test_member_placement import Vector, Rotation, mat_vec, load_member

ROOT = Path(__file__).resolve().parents[1] / "freecad/SteelStructures"


def definition(filename, name, namespace):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf8"))
    node = next(n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), namespace)
    return namespace[name]


class ManualFixTests(unittest.TestCase):
    def candidate(self):
        config = config_fixture()
        config["role_specs"]["END_POST"] = copy.deepcopy(config["role_specs"]["END_POST_LEFT"])
        return config

    def test_new_truss_defaults_fit_web_roles_only(self):
        from freecad.SteelStructures.trusses.models import ROLES
        factory = definition("truss.py", "default_config", dict(
            profile_catalog=profile_catalog, asdict=asdict, ROLES=ROLES))
        roles = factory()["role_specs"]
        self.assertEqual(roles["TOP_CHORD"]["physical_fit"], "None")
        self.assertEqual(roles["BOTTOM_CHORD"]["physical_fit"], "None")
        for role in ("DIAGONAL", "VERTICAL", "END_POST",
                     "END_POST_LEFT", "END_POST_RIGHT"):
            self.assertEqual(roles[role]["physical_fit"], "ToChord")
            self.assertEqual(roles[role]["physical_fit_gap"], 0.)

    def test_undo_redo_snapshot_resync_keeps_real_external_edit_detection(self):
        item = SimpleNamespace(key="WEB", spec=SimpleNamespace(color=(1., .5, 0.)))
        candidate = SimpleNamespace(items=(item,))
        child = SimpleNamespace(
            current="accepted-before-undo", ControlledState="accepted-after-apply",
            ViewObject=SimpleNamespace(ShapeColor=(1., .5, 0., 1.)),
            Proxy=SimpleNamespace(_last_generated_result="stale",
                                  _generated_prepared_signature="stale"))
        prepared = SimpleNamespace(current="accepted-before-undo")
        owner = SimpleNamespace(AppliedState="restored")
        locked = []
        namespace = dict(
            decode_state=lambda _text: {"candidate": {"config": {}}},
            build_candidate=lambda _config: candidate,
            bound_children=lambda _obj, _state: {"WEB": child},
            prepare_batch=lambda _candidate, _children: {"WEB": prepared},
            controlled_state=lambda source, color=None: source.current,
            lock_controlled=lambda current: locked.append(current),
        )
        resync = definition("truss.py", "resynchronize_accepted_snapshots", namespace)

        # apply -> undo -> reopen: current inputs match restored AppliedState,
        # therefore the stale post-apply snapshot is repaired.
        self.assertEqual(resync(owner), 1)
        self.assertEqual(child.ControlledState, "accepted-before-undo")
        self.assertIs(child.Proxy._last_generated_result, prepared)
        self.assertIsNone(child.Proxy._generated_prepared_signature)
        self.assertEqual(locked, [child])

        # A direct external edit does not match the accepted realization and
        # must remain visible to the existing conflict guard.
        child.current = "manual-external-edit"
        child.ControlledState = "accepted-before-undo"
        self.assertEqual(resync(owner), 0)
        self.assertNotEqual(child.current, child.ControlledState)

        # Redo has the same rule: once current inputs match the redone state,
        # reopening can safely rebuild its accepted snapshot.
        child.current = prepared.current = "accepted-after-apply"
        self.assertEqual(resync(owner), 1)
        self.assertEqual(child.current, child.ControlledState)

    def test_independent_end_specs_roundtrip_without_topology_changes(self):
        config = self.candidate()
        before = build_candidate(config)
        right = config["role_specs"]["END_POST_RIGHT"]
        right.update(rotation=180, insertion="top_left", color=[1, 0, 0], section_geometry_mode="Simplified")
        after = build_candidate(config)
        self.assertEqual(before.graph, after.graph)
        self.assertEqual(before.runs, after.runs)
        posts = sorted((i for i in after.items if i.role == "END_POST"), key=lambda i: i.start_local[0])
        self.assertEqual(posts[0].spec.rotation, 0)
        self.assertEqual(posts[1].spec.rotation, 180)
        self.assertEqual(posts[1].spec.insertion, "top_left")
        self.assertEqual(posts[1].spec.color, (1, 0, 0))
        self.assertEqual(posts[1].spec.section_geometry_mode, "Simplified")
        rebuilt = build_candidate(decode_state(encode_state(after))["candidate"]["config"])
        self.assertEqual(encode_state(rebuilt), encode_state(after))

    def test_legacy_end_spec_supplies_two_detached_sides(self):
        config = self.candidate()
        del config["role_specs"]["END_POST_LEFT"]
        del config["role_specs"]["END_POST_RIGHT"]
        config["role_specs"]["END_POST"]["rotation"] = 90
        candidate = build_candidate(config)
        self.assertTrue(all(i.spec.rotation == 90 for i in candidate.items if i.role == "END_POST"))
        candidate.config["role_specs"]["END_POST_LEFT"]["rotation"] = 0
        self.assertEqual(candidate.config["role_specs"]["END_POST_RIGHT"]["rotation"], 90)
        self.assertNotIn("END_POST_LEFT", config["role_specs"])

    def test_physical_section_matches_editor_for_u_l_rhs_and_all_directions(self):
        member = load_member()
        namespace = dict(math=math, App=SimpleNamespace(Vector=Vector), member=member,
                         ProfileRef=profiles.ProfileRef, profile_catalog=profile_catalog,
                         section_insertion_references=profiles.section_insertion_references)
        values = definition("member_batch.py", "item_values", namespace)
        library = profiles.ProfileLibrary(profile_catalog.CATALOGS_DIR)
        selected = [library.search(query)[0] for query in ("U3x6.10", "L", "RHS")]
        self.assertEqual([profile_catalog.get(p.designation).definition.geometry_type for p in selected],
                         ["channel_section", "equal_angle", "hollow_section"])
        with patch.object(Rotation, "multVec", lambda self, v: mat_vec(self.matrix, v), create=True), patch.object(
                member, "_section_geometry", lambda p, mode: profiles.build_section_geometry(p.definition, mode)):
            for profile in selected:
                ref = profile_catalog.ref_for_designation(profile.designation)
                for end in ((10,0,0), (0,0,10), (10,0,7), (10,0,-7), (-10,0,0), (0,0,-10)):
                    for angle in (0, 90, -90, 180):
                        with self.subTest(profile=profile.designation, end=end, angle=angle):
                            spec = SimpleNamespace(profile_ref=dict(catalog_id=ref.catalog_id, profile_id=ref.profile_id),
                                section_geometry_mode="Simplified", insertion="centroid", rotation=angle)
                            item = SimpleNamespace(spec=spec, start_global=(0,0,0), end_global=end,
                                                   section_u_global=build_candidate(self.candidate()).items[0].section_u_global)
                            result = values(item)
                            w = Vector(end); w.normalize()
                            rotation = member._member_frame_rotation(w).multiply(Rotation(Vector(0,0,1), result["Rotation"]))
                            u, v = Vector(0,1,0), Vector(-w.z,0,w.x)
                            # Compare asymmetric section points through the same editor transform.
                            geometry = profiles.build_section_geometry(profile_catalog.get(profile.designation).definition, "Simplified")
                            points = [segment.start for segment in geometry.outer_path.segments]
                            for point in points:
                                preview = transform_preview_point(point, Point2D(0,0), angle)
                                expected = (u * preview.x).add(v * preview.y)
                                actual = rotation.multVec(Vector(point.x, point.y, 0))
                                for axis in ("x", "y", "z"):
                                    self.assertAlmostEqual(getattr(actual, axis), getattr(expected, axis), places=6)
                            x = rotation.multVec(Vector(1,0,0)); y = rotation.multVec(Vector(0,1,0))
                            self.assertAlmostEqual(x.cross(y).dot(w), 1)

    @patch.dict("sys.modules", pivy=SimpleNamespace(coin=SimpleNamespace(SoGroup=object)))
    def test_parent_visibility_restores_individually_hidden_child(self):
        provider = definition("truss.py", "StructuralTrussViewProvider", {})
        children = [SimpleNamespace(Name=str(i), ViewObject=SimpleNamespace(Visibility=v)) for i,v in enumerate((True, False, True))]
        modes = []
        view = SimpleNamespace(Object=SimpleNamespace(GeneratedMembers=children), Visibility=True,
                               SwitchNode=SimpleNamespace(getNumChildren=lambda: len(modes)),
                               listDisplayModes=lambda: modes,
                               addDisplayMode=lambda node, name: modes.append(name))
        proxy = provider(view)
        self.assertEqual(modes, ["Group"])
        self.assertEqual(proxy.getDefaultDisplayMode(), "Group")
        self.assertEqual(proxy.getDisplayModes(view), ["Group"])
        view.Visibility = False; proxy.onChanged(view, "Visibility")
        self.assertEqual([c.ViewObject.Visibility for c in children], [False]*3)
        proxy.onChanged(view, "Visibility")
        saved = proxy.dumps()
        proxy = provider(view)
        proxy.loads(saved)
        proxy.attach(view)
        self.assertEqual(modes, ["Group"])
        view.Visibility = True; proxy.onChanged(view, "Visibility")
        self.assertEqual([c.ViewObject.Visibility for c in children], [True, False, True])

    def test_role_controls_follow_candidate_edges(self):
        panel = make_panel()
        panel.role_buttons = {key: Number(0) for key in panel._role_specs}
        panel.role_labels = {key: Number(0) for key in panel._role_specs}
        panel._refresh()
        self.assertTrue(panel.role_buttons["TOP_CHORD"].visible)
        self.assertFalse(panel.role_buttons["VERTICAL"].visible)
        self.assertFalse(panel.role_buttons["END_POST_RIGHT"].visible)

    def test_snapper_motion_click_escape_and_cleanup(self):
        callbacks = {}; calls = []; received = []
        view = SimpleNamespace(addEventCallback=lambda kind, fn: callbacks.setdefault(kind, fn),
                               removeEventCallback=lambda kind, token: callbacks.pop(kind))
        snapper = SimpleNamespace(show=lambda: None, off=lambda: calls.append("off"),
            snap=lambda pos, **kw: calls.append((pos, kw)) or Vector(pos[0], pos[1], 0))
        gui = SimpleNamespace(activeDocument=lambda: SimpleNamespace(activeView=lambda: view), Snapper=snapper)
        controller_type = definition("interactive/truss_controller.py", "TrussController", dict(Gui=gui, App=SimpleNamespace(Vector=Vector)))
        controller = controller_type(None)
        plane = SimpleNamespace(get_working_plane=lambda: SimpleNamespace(axis=(0,0,1)))
        with patch.dict("sys.modules", WorkingPlane=plane):
            controller.pick_points(lambda *args: received.append(args))
            callbacks["SoLocation2Event"]({"Position": (2,3)})
            self.assertEqual(calls[-1][0], (2,3))
            click = callbacks["SoMouseButtonEvent"]
            click(dict(State="DOWN", Button="BUTTON1", Position=(2,3)))
            callbacks["SoLocation2Event"]({"Position": (4,5)})
            self.assertIsInstance(calls[-1][1]["lastpoint"], Vector)
            click(dict(State="DOWN", Button="BUTTON1", Position=(4,5)))
            self.assertFalse(callbacks)
            self.assertEqual(received[0][2], [0,0,1])
            controller.pick_points(lambda *args: received.append(args))
            callbacks["SoKeyboardEvent"](dict(Key="ESCAPE", State="DOWN"))
            self.assertFalse(callbacks)
            self.assertEqual(received[-1][:2], (None, None))

    def test_structural_properties_readonly_on_creation_and_restore(self):
        from freecad.SteelStructures.trusses.models import SCHEMA_VERSION, CONTINUITIES
        from freecad.SteelStructures.trusses.preset_contracts import PRESETS
        from freecad.SteelStructures.trusses.drivers import DRIVERS
        namespace = dict(SCHEMA_VERSION=SCHEMA_VERSION, CONTINUITIES=CONTINUITIES,
                         PRESETS=PRESETS, DRIVERS=DRIVERS)
        definition("truss.py", "ensure_c2_properties", namespace)
        proxy_type = definition("truss.py", "StructuralTrussProxy", namespace)
        modes = {}
        properties = []
        obj = SimpleNamespace(PropertiesList=properties, addProperty=lambda kind,name,*args: properties.append(name),
                              setEditorMode=lambda name, mode: modes.update({name: mode}))
        proxy = proxy_type(obj)
        structural = ("TopologyPreset", "EnvelopeType", "PanelCount", "TopChordContinuity",
                      "BottomChordContinuity", "PanelizationMode", "LeftPanels", "RightPanels")
        self.assertTrue(all(modes[name] == 1 for name in structural))
        self.assertTrue(all(name not in modes for name in ("Span", "Height", "ApexPosition", "DisplayName")))
        modes.clear()
        obj.SchemaVersion = 3
        proxy.onDocumentRestored(obj)
        self.assertTrue(all(modes[name] == 1 for name in structural))
        self.assertNotEqual(obj.GenerationState, "UnsupportedSchema")

    def test_object_schema_matches_the_encoded_applied_state(self):
        from freecad.SteelStructures.trusses.serialization import encode_state, decode_state
        from freecad.SteelStructures.trusses.assemblies import configure_assembly
        from tests.test_truss_assemblies import config
        accept = definition("truss.py", "accept_state", dict(
            encode_state=encode_state, decode_state=decode_state))

        configs = []
        plain = config()
        configs.append(plain)
        assembled = copy.deepcopy(plain)
        role = assembled["role_specs"]["DIAGONAL"]
        assembled["role_specs"]["DIAGONAL"] = configure_assembly(
            role, "DoubleAngle", 60.)
        configs.append(assembled)
        fitted = copy.deepcopy(plain)
        fitted["role_specs"]["DIAGONAL"]["physical_fit"] = "ToChord"
        fitted["role_specs"]["DIAGONAL"]["physical_fit_gap"] = 0.
        configs.append(fitted)

        self.assertEqual([decode_state(encode_state(build_candidate(value)))["schema_version"]
                          for value in configs], [2, 3, 4])
        for value in configs:
            candidate = build_candidate(value)
            children = {item.key: SimpleNamespace(Name="Member"+str(index))
                        for index, item in enumerate(candidate.items)}
            owner = SimpleNamespace()
            accept(owner, candidate, children)
            self.assertEqual(owner.SchemaVersion,
                             decode_state(owner.AppliedState)["schema_version"])

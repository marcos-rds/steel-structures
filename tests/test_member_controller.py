"""Behavioral tests for the controller shared by the native Draft tool."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "freecad" / "SteelStructures"
CONTROLLER = PACKAGE / "interactive" / "member_controller.py"


class Vector:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z

    def sub(self, other):
        return Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    @property
    def Length(self):
        return (self.x**2 + self.y**2 + self.z**2) ** 0.5


class FakeSelection:
    def __init__(self):
        self.clear_count = 0
        self.selected = []

    def clearSelection(self):
        self.clear_count += 1

    def addSelection(self, member):
        self.selected.append(member)


class FakeDocument:
    def __init__(self):
        self.Objects = []
        self.opened = []
        self.commits = 0
        self.aborts = 0
        self.fail_commit = False

    def openTransaction(self, name):
        self.opened.append(name)

    def commitTransaction(self):
        if self.fail_commit:
            raise RuntimeError("commit failure")
        self.commits += 1

    def abortTransaction(self):
        self.aborts += 1


def load_controller():
    package_name = "_metal_controller_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(PACKAGE)]
    interactive_name = f"{package_name}.interactive"
    interactive = types.ModuleType(interactive_name)
    interactive.__path__ = [str(PACKAGE / "interactive")]
    selection = FakeSelection()
    freecad = types.ModuleType("FreeCAD")
    freecad.Gui = types.SimpleNamespace(Selection=selection)
    member = types.ModuleType(f"{package_name}.member")
    member.create_member = lambda **_kwargs: None
    axis_source = types.ModuleType(f"{package_name}.member_axis_source")
    axis_source.resolve_axis_source = lambda link: getattr(
        link[0], "resolved_axis", None
    ) if link else None
    injected = {
        package_name: package,
        interactive_name: interactive,
        f"{package_name}.member": member,
        f"{package_name}.member_axis_source": axis_source,
        "FreeCAD": freecad,
    }
    previous = {name: sys.modules.get(name) for name in injected}
    sys.modules.update(injected)
    spec = importlib.util.spec_from_file_location(
        f"{interactive_name}.member_controller", CONTROLLER
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    def cleanup():
        for name in list(sys.modules):
            if name == package_name or name.startswith(f"{package_name}."):
                sys.modules.pop(name, None)
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old

    return module, selection, cleanup


class MemberControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module, cls.selection, cls.cleanup = load_controller()

    @classmethod
    def tearDownClass(cls):
        cls.cleanup()

    def setUp(self):
        self.document = FakeDocument()
        self.selection.clear_count = 0
        self.selection.selected.clear()
        self.calls = []

        def factory(**kwargs):
            self.calls.append(kwargs)
            member = types.SimpleNamespace(
                Label=kwargs["display_name"],
                DisplayName=kwargs["display_name"],
                PropertiesList=["DisplayName"],
                Profile=kwargs["designation"],
            )
            self.document.Objects.append(member)
            return member

        self.controller = self.module.MemberController(
            self.document, member_factory=factory, selection=self.selection
        )

    def options(self, **overrides):
        values = {
            "start": Vector(0, 0, 0),
            "end": Vector(1000, 2000, 3000),
            "designation": "W 150 x 13,0",
            "element_type": "Membro",
            "insertion": "Centroide",
            "rotation": 15.0,
            "color": (0.7, 0.8, 0.9),
            "display_name": "Membro 001 - W150x13,0",
        }
        values.update(overrides)
        return self.module.MemberCreationOptions(**values)

    def test_state_lifecycle(self):
        state = self.module.ControllerState
        self.assertEqual(
            [item.name for item in state],
            ["INACTIVE", "READY_NUMERIC", "CREATING", "STOPPING"],
        )
        self.controller.start()
        self.assertIs(self.controller.state, state.READY_NUMERIC)
        self.controller.stop()
        self.assertIs(self.controller.state, state.INACTIVE)

    def test_factory_runs_while_controller_is_creating(self):
        observed = []

        def factory(**kwargs):
            observed.append(self.controller.state)
            member = types.SimpleNamespace(Label=kwargs["display_name"])
            self.document.Objects.append(member)
            return member

        self.controller._member_factory = factory
        self.controller.start()
        self.controller.create(self.options())
        self.assertEqual(observed, [self.module.ControllerState.CREATING])

    def test_creation_commits_one_transaction_and_selects_member(self):
        self.controller.start()
        result = self.controller.create(self.options())
        self.assertEqual(self.document.opened, ["Criar elemento estrutural"])
        self.assertEqual((self.document.commits, self.document.aborts), (1, 0))
        self.assertEqual(self.selection.clear_count, 1)
        self.assertIs(self.selection.selected[-1], result.member)

    def test_coincident_points_are_rejected_before_transaction(self):
        self.controller.start()
        point = Vector(10, 20, 30)
        with self.assertRaisesRegex(ValueError, "devem ser diferentes"):
            self.controller.create(self.options(start=point, end=point))
        self.assertEqual(self.document.opened, [])
        self.assertEqual(self.calls, [])

    def test_failure_aborts_and_restores_ready_state(self):
        def failing_factory(**_kwargs):
            raise RuntimeError("falha controlada")

        controller = self.module.MemberController(
            self.document, member_factory=failing_factory, selection=self.selection
        )
        controller.start()
        with self.assertRaisesRegex(RuntimeError, "falha controlada"):
            controller.create(self.options())
        self.assertEqual((self.document.commits, self.document.aborts), (0, 1))
        self.assertIs(controller.state, self.module.ControllerState.READY_NUMERIC)

    def test_options_are_forwarded_without_conversion(self):
        self.controller.start()
        self.controller.create(self.options(display_name="Pilar principal"))
        call = self.calls[0]
        self.assertEqual(call["designation"], "W 150 x 13,0")
        self.assertEqual(call["insertion"], "Centroide")
        self.assertEqual(call["rotation"], 15.0)
        self.assertEqual(call["color"], (0.7, 0.8, 0.9))
        self.assertEqual(call["display_name"], "Pilar principal")

    def test_linked_creation_hides_source_only_after_factory_success(self):
        source = types.SimpleNamespace(
            ViewObject=types.SimpleNamespace(Visibility=True)
        )
        self.controller.start()
        self.controller.create(self.options(axis_source=(source, ["Edge1"]), link_axis=True))
        self.assertFalse(source.ViewObject.Visibility)
        self.assertTrue(self.calls[0]["link_axis"])
        self.assertIs(self.calls[0]["axis_source"][0], source)

    def test_independent_creation_hides_source_after_success(self):
        source = types.SimpleNamespace(
            ViewObject=types.SimpleNamespace(Visibility=True)
        )
        self.controller.start()
        self.controller.create(self.options(axis_source=(source, ["Edge1"]), link_axis=False))
        self.assertFalse(source.ViewObject.Visibility)

    def test_source_axis_overrides_both_interactive_points_even_when_independent(self):
        source = types.SimpleNamespace(
            ViewObject=types.SimpleNamespace(Visibility=True),
            resolved_axis=types.SimpleNamespace(
                start=Vector(11, 22, 33), end=Vector(4011, 5022, 6033)
            ),
        )
        self.controller.start()
        self.controller.create(self.options(
            start=Vector(-1, -1, -1), end=Vector(1, 1, 1),
            axis_source=(source, ["Edge1"]), link_axis=False,
            geometry_mode=self.module.CreationGeometryMode.SOURCE_AXIS,
        ))
        call = self.calls[0]
        self.assertEqual((call["start"].x, call["start"].y, call["start"].z),
                         (11, 22, 33))
        self.assertEqual((call["end"].x, call["end"].y, call["end"].z),
                         (4011, 5022, 6033))
        self.assertFalse(source.ViewObject.Visibility)

    def test_initially_hidden_source_remains_hidden(self):
        source = types.SimpleNamespace(
            ViewObject=types.SimpleNamespace(Visibility=False)
        )
        self.controller.start()
        self.controller.create(self.options(
            axis_source=(source, ["Edge1"]), link_axis=False
        ))
        self.assertFalse(source.ViewObject.Visibility)

    def test_failed_independent_commit_restores_source_visibility(self):
        source = types.SimpleNamespace(
            ViewObject=types.SimpleNamespace(Visibility=True)
        )
        self.document.fail_commit = True
        self.controller.start()
        with self.assertRaisesRegex(RuntimeError, "commit failure"):
            self.controller.create(self.options(
                axis_source=(source, ["Edge1"]), link_axis=False
            ))
        self.assertTrue(source.ViewObject.Visibility)

    def test_source_axis_rejects_invalid_source_before_transaction(self):
        source = types.SimpleNamespace(
            ViewObject=types.SimpleNamespace(Visibility=True), resolved_axis=None
        )
        self.controller.start()
        with self.assertRaisesRegex(ValueError, "linha de origem"):
            self.controller.create(self.options(
                axis_source=(source, ["Edge1"]),
                geometry_mode=self.module.CreationGeometryMode.SOURCE_AXIS,
            ))
        self.assertEqual(self.document.opened, [])

    def test_failed_linked_commit_restores_source_visibility(self):
        source = types.SimpleNamespace(
            ViewObject=types.SimpleNamespace(Visibility=True)
        )
        self.document.fail_commit = True
        self.controller.start()
        with self.assertRaisesRegex(RuntimeError, "commit failure"):
            self.controller.create(self.options(axis_source=(source, ["Edge1"]), link_axis=True))
        self.assertTrue(source.ViewObject.Visibility)

    def test_repeated_creation_advances_automatic_name(self):
        self.controller.start()
        first = self.controller.create(self.options())
        second = self.controller.create(
            self.options(display_name=first.next_default_name)
        )
        self.assertEqual(first.next_default_name, "Membro 002 - W150x13,0")
        self.assertEqual(second.next_default_name, "Membro 003 - W150x13,0")
        self.assertEqual(self.document.commits, 2)

    def test_automatic_sequences_are_independent_by_element_type(self):
        self.document.Objects.extend(
            [
                types.SimpleNamespace(Label="Pilar 004 - W150x13,0", PropertiesList=[]),
                types.SimpleNamespace(Label="Viga 009 - W150x13,0", PropertiesList=[]),
            ]
        )
        self.assertEqual(
            self.module.next_default_label(self.document, "Pilar", "W 150 x 13,0"),
            "Pilar 005 - W150x13,0",
        )
        self.assertEqual(
            self.module.next_default_label(self.document, "Viga", "W 150 x 13,0"),
            "Viga 010 - W150x13,0",
        )

    def test_inactive_or_stopped_controller_cannot_create(self):
        with self.assertRaisesRegex(RuntimeError, "não está ativa"):
            self.controller.create(self.options())
        self.controller.start()
        self.controller.stop()
        with self.assertRaisesRegex(RuntimeError, "não está ativa"):
            self.controller.create(self.options())

    def test_stop_is_idempotent_and_releases_document_and_selection(self):
        self.controller.start()
        self.controller.stop()
        self.controller.stop()
        self.assertIs(self.controller.state, self.module.ControllerState.INACTIVE)
        self.assertIsNone(self.controller.document)
        self.assertIsNone(self.controller._selection)


if __name__ == "__main__":
    unittest.main()

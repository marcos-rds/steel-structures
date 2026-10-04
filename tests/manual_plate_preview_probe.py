"""Coin smoke test; run inside a graphical FreeCAD session with freecad/ on sys.path."""

import importlib.util
import sys
import types
from pathlib import Path

import FreeCAD as App
from pivy import coin

from SteelStructures.plate_geometry import PlateContour2D


# Load this view-only module in isolation from native Draft command setup.
root = Path(__file__).resolve().parents[1] / "freecad" / "SteelStructures"
interactive = types.ModuleType("SteelStructures.interactive")
interactive.__path__ = [str(root / "interactive")]
sys.modules[interactive.__name__] = interactive
spec = importlib.util.spec_from_file_location(
    "SteelStructures.interactive.plate_preview", root / "interactive" / "plate_preview.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

scene = coin.SoSeparator()
view = types.SimpleNamespace(getSceneGraph=lambda: scene)
preview = module.PlatePreview(view)
preview.outline((App.Vector(0, 0, 0), App.Vector(100, 0, 0)),
                App.Vector(100, 50, 0))
assert scene.getNumChildren() == 1
contour = PlateContour2D.from_points(((0, 0), (100, 0), (60, 80)))
preview.solid(contour, App.Placement(), 10.0, 2.0)
assert preview._root.getNumChildren() == 2
clockwise = PlateContour2D.from_points(((0, 0), (60, 80), (100, 0)))
preview.solid(clockwise, App.Placement(App.Vector(25, 30, 40), App.Rotation()),
              8.0, -3.0)
assert preview._root.getNumChildren() == 2
preview.remove()
preview.remove()
assert scene.getNumChildren() == 0
for _ in range(20):
    preview = module.PlatePreview(view)
    preview.outline((App.Vector(0, 0, 0), App.Vector(20, 10, 0)))
    preview.remove()
    preview.remove()
    assert scene.getNumChildren() == 0
print("PlatePreview Coin smoke test: OK")

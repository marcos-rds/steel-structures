"""Native FreeCAD 1.1.3 check for StructuralPlate source/FCStd lifecycle.

Run with FreeCAD's bundled Python and ``freecad/`` on ``PYTHONPATH``.  This is
excluded from ``unittest discover`` because it requires Draft and native BRep.
"""

import os
import tempfile

import Draft
import FreeCAD as App

from SteelStructures.plate import create_plate
from SteelStructures.plate_sources import resolve_plate_source


def _near(value, expected, tolerance=1e-6):
    assert abs(value - expected) <= tolerance, (value, expected)


def run():
    handle, path = tempfile.mkstemp(prefix="steel_structures_plate_", suffix=".FCStd")
    os.close(handle)
    doc = None
    reopened = None
    try:
        doc = App.newDocument("PlatePersistence")
        rectangle = Draft.make_rectangle(100, 50)
        wire = Draft.make_wire([App.Vector(0, 0, 0), App.Vector(120, 0, 0),
                                App.Vector(90, 55, 0), App.Vector(0, 45, 0)], closed=True)
        group = doc.addObject("App::Part", "SourceContainer")
        group.addObject(rectangle)
        doc.recompute()
        linked = create_plate(doc, None, source_mode="DraftRectangle", source_object=rectangle,
                              keep_source_link=True, thickness=8, offset=3)
        snapshot = create_plate(doc, None, source_mode="DraftWire", source_object=wire,
                                keep_source_link=False, thickness=6)
        linked_wire = create_plate(doc, None, source_mode="DraftWire", source_object=wire,
                                   keep_source_link=True, thickness=5)
        _near(linked.Shape.Volume, 100 * 50 * 8)
        _near(linked.Shape.BoundBox.ZMin, 3)
        assert snapshot.SourceObject is None
        assert linked.SourceObject is rectangle
        assert len(resolve_plate_source(wire, "DraftWire").contour.vertices) == 4
        previous_snapshot_volume = snapshot.Shape.Volume
        wire.Points = [App.Vector(0, 0, 0), App.Vector(160, 0, 0),
                       App.Vector(90, 55, 0), App.Vector(0, 45, 0)]
        rectangle.Length = 130
        doc.recompute()
        _near(linked.Shape.Volume, 130 * 50 * 8)
        _near(snapshot.Shape.Volume, previous_snapshot_volume)
        assert linked_wire.Shape.Volume != previous_snapshot_volume
        group.Placement.Base = App.Vector(200, 300, 400)
        doc.recompute()
        _near(linked.Placement.Base.x, 200)
        _near(linked.Placement.Base.y, 300)
        _near(linked.Placement.Base.z, 400)
        _near(linked.Shape.BoundBox.ZMin, 403)
        assert group in linked.SourceContainers
        linked_wire_volume = linked_wire.Shape.Volume
        linked_wire_box = linked_wire.Shape.BoundBox
        linked_wire_contour = linked_wire.ContourData
        wire.Closed = False
        doc.recompute()
        assert linked_wire.GenerationStatus.startswith("Erro:"), linked_wire.GenerationStatus
        _near(linked_wire.Shape.Volume, linked_wire_volume)
        _near(linked_wire.Shape.BoundBox.XMin, linked_wire_box.XMin)
        _near(linked_wire.Shape.BoundBox.XMax, linked_wire_box.XMax)
        assert linked_wire.ContourData == linked_wire_contour
        wire.Closed = True
        doc.recompute()
        assert linked_wire.GenerationStatus == "Valid"
        frozen_contour = linked_wire.ContourData
        frozen_placement = App.Placement(linked_wire.Placement)
        linked_wire.KeepSourceLink = False
        doc.recompute()
        assert linked_wire.SourceObject is None
        assert len(linked_wire.SourceContainers) == 0
        wire.Points = [App.Vector(0, 0, 0), App.Vector(200, 0, 0),
                       App.Vector(90, 55, 0), App.Vector(0, 45, 0)]
        doc.recompute()
        assert linked_wire.ContourData == frozen_contour
        assert linked_wire.Placement == frozen_placement
        linked_name = linked.Name
        rectangle_name = rectangle.Name
        doc.saveAs(path)
        App.closeDocument(doc.Name)
        doc = None
        reopened = App.openDocument(path)
        reopened.recompute()
        restored = reopened.getObject(linked_name)
        assert restored.Proxy.__class__.__name__ == "StructuralPlateProxy"
        assert restored.SourceObject is reopened.getObject(rectangle_name)
        _near(restored.Placement.Base.x, 200)
        _near(restored.Placement.Base.y, 300)
        _near(restored.Placement.Base.z, 400)
        _near(restored.Shape.BoundBox.ZMin, 403)
        _near(restored.Shape.Volume, 130 * 50 * 8)
        _near(restored.GrossArea.Value, 130 * 50)
        _near(restored.EnvelopeVolume.Value, 130 * 50 * 8)
        assert restored.GenerationStatus == "Valid", restored.GenerationStatus
        retained_volume = restored.Shape.Volume
        retained_contour = restored.ContourData
        reopened.removeObject(rectangle_name)
        reopened.recompute()
        assert restored.GenerationStatus.startswith("Erro:"), restored.GenerationStatus
        _near(restored.Shape.Volume, retained_volume)
        assert restored.ContourData == retained_contour
        assert restored.KeepSourceLink
        print("OK: StructuralPlate Draft links, snapshot, container, Placement and FCStd persistence", flush=True)
    finally:
        for candidate in (reopened, doc):
            if candidate is not None:
                App.closeDocument(candidate.Name)
        os.remove(path)


if __name__ == "__main__":
    run()

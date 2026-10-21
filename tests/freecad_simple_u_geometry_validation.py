"""Native kernel validation: run with FreeCAD 1.1.4 bin/python.exe.

Checks faces/extrusions for all 125 sizes and both representations, plus
Placement/insertion/roll and FCStd shape persistence. No GUI or creation tool
integration; no existing document is opened or changed.
"""

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(output):
    import FreeCAD as App
    from freecad.SteelStructures.paths import CATALOGS_DIR
    from freecad.SteelStructures.profiles import (
        ProfileLibrary, build_section_geometry, section_insertion_references,
    )
    from freecad.SteelStructures.profiles.freecad_geometry import section_geometry_to_face

    profiles = ProfileLibrary(CATALOGS_DIR).list_profiles(series_id="u-simple-nbr-6355")
    if len(profiles) != 125:
        raise AssertionError("Expected 125 simple U profiles")
    output.mkdir(parents=True, exist_ok=True)
    report = {"freecad_version": App.Version(), "profiles": 125, "faces": 0,
              "solids": 0, "placements": 0, "max_area_error_mm2": 0,
              "max_volume_error_mm3": 0, "fractional_radius_mm": None}

    def near(actual, expected, absolute=1e-7):
        if not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=absolute):
            raise AssertionError((actual, expected))

    for p in profiles:
        for mode in ("Detailed", "Simplified"):
            geometry = build_section_geometry(p, mode)
            face = section_geometry_to_face(geometry)
            if face.isNull() or not face.isValid() or len(face.Wires) != 1 or not face.Wires[0].isClosed():
                raise AssertionError((p.designation, mode, "invalid face"))
            near(face.Area, geometry.area)
            near(face.BoundBox.XLength, p.geometry["bf"])
            near(face.BoundBox.YLength, p.geometry["bw"])
            solid = face.extrude(App.Vector(0, 0, 1000))
            if solid.isNull() or not solid.isValid() or len(solid.Solids) != 1:
                raise AssertionError((p.designation, mode, "invalid solid"))
            near(solid.Volume, geometry.area * 1000, 1e-5)
            report["faces"] += 1
            report["solids"] += 1
            report["max_area_error_mm2"] = max(report["max_area_error_mm2"], abs(face.Area - geometry.area))
            report["max_volume_error_mm3"] = max(report["max_volume_error_mm3"], abs(solid.Volume - geometry.area * 1000))
            if p.geometry["ri"] == 9.525 and mode == "Detailed":
                radii = sorted(edge.Curve.Radius for edge in face.Edges if hasattr(edge.Curve, "Radius"))
                for actual, expected in zip(radii, (9.525, 9.525, 15.875, 15.875)):
                    near(actual, expected, 1e-10)
                if len(radii) != 4:
                    raise AssertionError(radii)
                report["fractional_radius_mm"] = radii[0]

    if report["fractional_radius_mm"] is None:
        raise AssertionError("Fractional radius control was not executed")
    chosen = [profiles[0], profiles[-1], next(p for p in profiles if p.geometry["tn"] == 6.35)]
    directions = (App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1), App.Vector(2, -3, 4))
    for p in chosen:
        geometry = build_section_geometry(p)
        face = section_geometry_to_face(geometry)
        for ref in section_insertion_references(geometry):
            for direction in directions:
                for angle in (0, 37, 90, 180, 270):
                    local = face.copy()
                    local.translate(App.Vector(-ref.point.x, -ref.point.y, 0))
                    solid = local.extrude(App.Vector(0, 0, 1000))
                    rotation = App.Rotation(App.Vector(0, 0, 1), direction).multiply(
                        App.Rotation(App.Vector(0, 0, 1), angle))
                    placement = App.Placement(App.Vector(15, 25, 35), rotation)
                    solid.Placement = placement
                    expected_center = placement.multVec(App.Vector(-ref.point.x, -ref.point.y, 500))
                    near((solid.CenterOfMass - expected_center).Length, 0, 1e-7)
                    near(solid.Volume, geometry.area * 1000, 1e-5)
                    if not solid.isValid():
                        raise AssertionError("Invalid placed solid")
                    report["placements"] += 1

    # Persistence here covers kernel shapes and their Placement only, not the
    # future StructuralMember/trellis integration or FeaturePython callbacks.
    document = App.newDocument("SimpleUStageAKernelValidation")
    reopened = None
    try:
        expected = {}
        for index, p in enumerate(chosen):
            for mode in ("Detailed", "Simplified"):
                geometry = build_section_geometry(p, mode)
                obj = document.addObject("Part::Feature", f"U{index}{mode}")
                obj.Shape = section_geometry_to_face(geometry).extrude(App.Vector(0, 0, 1000))
                obj.Placement = App.Placement(App.Vector(index * 500, 70, 90),
                                              App.Rotation(App.Vector(1, 2, 3), 37))
                expected[obj.Name] = (obj.Shape.Volume, obj.Placement.toMatrix().A)
        document.recompute()
        path = output.resolve() / "simple_u_kernel.FCStd"
        document.saveAs(str(path))
        App.closeDocument(document.Name)
        document = None
        reopened = App.openDocument(str(path))
        reopened.recompute()
        for name, (volume, matrix) in expected.items():
            obj = reopened.getObject(name)
            if not obj.Shape.isValid() or len(obj.Shape.Solids) != 1:
                raise AssertionError((name, "invalid restored shape"))
            near(obj.Shape.Volume, volume, 1e-5)
            for actual, value in zip(obj.Placement.toMatrix().A, matrix):
                near(actual, value, 1e-10)
        report["fcstd_restored_shapes"] = len(expected)
    finally:
        if document is not None:
            App.closeDocument(document.Name)
        if reopened is not None:
            App.closeDocument(reopened.Name)
    report["status"] = "PASS"
    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "test-results/simple_u_stage_a_native")
    run(parser.parse_args().output)

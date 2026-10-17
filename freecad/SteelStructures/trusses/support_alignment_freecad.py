"""OCC verification of the final physical upper chord at both support planes."""
import FreeCAD as App
import Part

from .realization import reference_frame


def support_sections(candidate, prepared):
    """Return exact section bounds in the nominal truss frame after all cuts.

    The reference is the longitudinal projection of the upper physical
    envelope across the chord width, including separated assembly components.
    """
    origin, x, y, z = reference_frame(candidate.config)
    placement = App.Placement(App.Vector(*origin), App.Rotation(
        App.Vector(*x), App.Vector(*y), App.Vector(*z), "ZXY"))
    inverse = placement.inverse()
    result = []
    upper = candidate.config.get("reference_alignment") == "TopChordSupports"
    role = "TOP_CHORD" if upper else "BOTTOM_CHORD"
    for point in candidate.config["support_reference_local"]:
        sections = []
        for item in candidate.items:
            if item.role != role or item.element_kind != "Component":
                continue
            if min(abs(item.start_local[0]-point[0]), abs(item.end_local[0]-point[0])) > 1e-6:
                continue
            value = prepared[item.key]
            shape = value.Shape.copy()
            if shape.isNull():
                continue
            shape.Placement = inverse.multiply(value.Placement)
            box = shape.BoundBox
            radius = max(box.YLength, box.ZLength, abs(box.YMin), abs(box.YMax),
                         abs(box.ZMin), abs(box.ZMax), 1.)*3.
            face = Part.makePlane(2*radius, 2*radius, App.Vector(point[0], -radius, -radius),
                                  App.Vector(1, 0, 0), App.Vector(0, 1, 0))
            section = shape.section(face)
            if not section.isNull() and section.Edges:
                sections.append(section.BoundBox)
        if not sections:
            raise ValueError("O banzo escolhido não alcança o plano físico de uma extremidade após os cortes.")
        result.append(max(box.YMax for box in sections) if upper else min(box.YMin for box in sections))
    return tuple(result)


def validate_support_alignment(candidate, prepared):
    if (candidate.config.get("reference_alignment") != "TopChordSupports"
            and candidate.config.get("reference_surface") != "OuterFace"):
        return
    actual = support_sections(candidate, prepared)
    expected = [p[1] for p in candidate.config["support_reference_local"]]
    if any(abs(a-b) > 1e-5 for a, b in zip(actual, expected)):
        raise ValueError("Cortes ou inserção impedem o alinhamento físico da face externa do banzo nas extremidades.")

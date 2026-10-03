"""Thin OCC adapter for the shared pure preliminary gusset outline."""

from ..connections import outline_extrusion_limits


def build_gusset_shape(outline):
    import FreeCAD as App
    import Part

    frame = outline.spec.frame
    low, high = outline_extrusion_limits(outline)
    def point(value, normal_offset=0.):
        x, y = value
        return App.Vector(*(frame.origin[index]+x*frame.x_axis[index]+y*frame.y_axis[index]
                            +normal_offset*frame.normal[index] for index in range(3)))
    vertices = [point(value, low) for value in outline.points]
    wire = Part.makePolygon(vertices+[vertices[0]])
    face = Part.Face(wire)
    shape = face.extrude(App.Vector(*(component*(high-low) for component in frame.normal)))
    if shape.isNull() or not shape.isValid():
        raise ValueError("Não foi possível gerar o sólido preliminar da chapa.")
    return shape

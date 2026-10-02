"""Disposable transverse views of already resolved gussets; no placement rules."""

from dataclasses import dataclass
import math

from ..connections.presentation import participant_names


@dataclass(frozen=True)
class TransverseComponent:
    key: str
    outer: tuple
    holes: tuple = ()


@dataclass(frozen=True)
class GussetTransverseView:
    participant_key: str
    label: str
    components: tuple = ()
    plate: tuple = ()
    message: str = ""

    @property
    def bounds(self):
        points = self.plate + tuple(point for component in self.components
                                    for point in component.outer)
        if not points:
            return None
        return (min(p[0] for p in points), min(p[1] for p in points),
                max(p[0] for p in points), max(p[1] for p in points))


def transverse_views(outline, participants, materials):
    """Project each chord independently using the resolver's material frame.

    X is the plate normal; Y is the chord's in-plane transverse axis. Plate
    height is the orthographic projection of the *final* approved outline,
    not an invented contact depth or a new solution of its contact bands.
    Section material is nominal (pre-fitting), just as in attachment solving.
    """
    result = []
    names = participant_names(participants)
    for participant in participants:
        if participant.role not in ("TOP_CHORD", "BOTTOM_CHORD"):
            continue
        key = participant.participant_key
        label = names[participant.run_key]
        values = tuple(m for m in materials if m.participant_key == key)
        attachment = outline.attachment
        if not values or attachment is None or attachment.kind == "NominalFallback":
            result.append(GussetTransverseView(
                key, label, message="Prévia indisponível: sem posição física confiável."))
            continue
        groups = []
        for material in values:
            group = next((group for group in groups if abs(sum(
                a*b for a, b in zip(group[0].local_axis, material.local_axis)))
                >= 1.-1e-6), None)
            if group is None:
                groups.append([material])
            else:
                group.append(material)
        for index, group in enumerate(groups):
            section_label = (label if len(groups) == 1 else
                             label+" / seção %d" % (index+1))
            result.append(_transverse_view(outline, key, section_label, group))
    return tuple(result)


def _transverse_view(outline, key, label, values):
    attachment = outline.attachment
    axis = values[0].local_axis
    if (all(math.isfinite(v) for v in axis)
            and abs(sum(v*v for v in axis)-1.) <= 1e-6
            and abs(sum(a*b for a, b in zip(axis, attachment.normal))) <= 1e-6):
        components = []
        for material in values:
            alignment = sum(a*b for a, b in zip(axis, material.local_axis))
            if abs(abs(alignment)-1.) > 1e-6:
                break
            sign = 1. if alignment >= 0. else -1.
            transform = lambda path: tuple((x, sign*y) for x, y in path)
            component = TransverseComponent(
                material.component_key, transform(material.outer),
                tuple(transform(path) for path in material.holes))
            # Continuous chord runs can expose the same section twice.
            if component not in components:
                components.append(component)
        else:
            frame = outline.spec.frame
            u = sum(a*b for a, b in zip(axis, frame.x_axis))
            v = sum(a*b for a, b in zip(axis, frame.y_axis))
            heights = tuple(x*u+y*v for x, y in outline.points)
            if heights and max(heights)-min(heights) > 1e-7:
                low, high = attachment.plate_low, attachment.plate_high
                plate = ((low, min(heights)), (high, min(heights)),
                         (high, max(heights)), (low, max(heights)))
                return GussetTransverseView(key, label, tuple(components), plate)
    return GussetTransverseView(
        key, label, message="Prévia indisponível: seções incompatíveis.")


@dataclass(frozen=True)
class TransverseViewport:
    scale: float
    offset_x: float
    offset_y: float

    def point(self, point):
        return (self.offset_x+self.scale*point[0],
                self.offset_y-self.scale*point[1])


def fit_transverse_bounds(bounds, width, height, padding=12.):
    """Uniform fit, including Y inversion for screen coordinates, in pixels."""
    if bounds is None or not all(math.isfinite(v) for v in (*bounds, width, height)):
        return None
    left, bottom, right, top = bounds
    if right <= left or top <= bottom or min(width, height) <= 2.*padding:
        return None
    scale = min((width-2.*padding)/(right-left),
                (height-2.*padding)/(top-bottom))
    return TransverseViewport(scale, width/2.-scale*(left+right)/2.,
                              height/2.+scale*(bottom+top)/2.)

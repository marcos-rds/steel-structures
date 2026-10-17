"""Exact upper support envelope and rigid alignment of supported truss forms.

``span`` is the supplied support-line length.  The nominal lower-chord span
is derived for DuoPitch in upper mode; Parallel keeps it equal to ``span``.
Heights remain perpendicular to that nominal chord.
At a support station x=0/S, an extruded section's upper tangent plane meets
the station at h + c/cos(pitch), not at h + c*cos(pitch).  ``c`` includes
insertion, roll, component transforms and the complete assembly arrangement.
"""
import copy
import math


def chord_section_extreme(config, role_name, upper):
    """Highest physical chord section relative to its nominal insertion axis.

    A horizontal probe is sufficient: roll and component layout rotate with
    the chord frame, so the offset in the ascending chord normal is invariant
    under pitch and the final rigid placement.  Connectors do not define the
    chord's upper support surface and are omitted from this section query.
    """
    from .models import MemberSpec, RealizationItem
    from .assemblies import expand_run
    from .fitting_geometry import _section_interval

    role = copy.deepcopy(config["role_specs"][role_name])
    if role.get("assembly_spec"):
        role["assembly_spec"]["spec"]["interconnectors"] = []
    item = RealizationItem("SUPPORT_PROBE", role_name, "L", "R",
                           (0., 0., 0.), (1., 0., 0.),
                           (0., 0., 0.), (1., 0., 0.), (0., 0., -1.),
                           MemberSpec(**role))
    offsets = [_section_interval(component, (0., 1., 0.))[1 if upper else 0]
               for component in expand_run(item)
               if component.element_kind == "Component"]
    if not offsets or not all(math.isfinite(value) for value in offsets):
        raise ValueError("Não foi possível determinar a face externa física do banzo.")
    return max(offsets) if upper else min(offsets)


def upper_section_offset(config):
    return chord_section_extreme(config, "TOP_CHORD", True)


def _support_heights(span, height, left, right, apex, offset):
    left_rise = (height-left)/apex
    right_rise = (height-right)/(1.-apex)
    return (left+offset*math.hypot(1., left_rise/span),
            right+offset*math.hypot(1., right_rise/span))


def _solve_nominal_span(length, height, left, right, apex, offset):
    """Largest positive root; locate the minimum before rejecting a bracket.

    With one role/assembly, both pitches have the same section offset. The
    squared support distance is unimodal: while its derivative can be
    negative, its second derivative is positive. This avoids missing two
    closely spaced roots near the minimum by sampling span values alone.
    """
    left_rise = (height-left)/apex
    right_rise = (height-right)/(1.-apex)
    tolerance = max(1e-9, length*1e-13)
    if offset == 0. or left_rise == right_rise:
        difference = abs(right-left)
        if length <= difference:
            raise ValueError("Não existe vão nominal positivo compatível com a linha de apoio.")
        return math.sqrt((length-difference)*(length+difference))

    def residual(span):
        ql, qr = _support_heights(span, height, left, right, apex, offset)
        return math.hypot(span, qr-ql)-length

    def derivative(span):
        ql, qr = _support_heights(span, height, left, right, apex, offset)
        slope = offset*(left_rise**2/math.hypot(span, left_rise)
                        - right_rise**2/math.hypot(span, right_rise))/span**2
        return span+(qr-ql)*slope

    upper = length
    if abs(residual(upper)) <= tolerance:
        return upper
    if derivative(upper) <= 0.:
        raise ValueError("A linha de apoio é curta demais para as alturas e o perfil selecionados.")
    lower = upper
    for _ in range(100):
        trial = lower/2.
        if residual(trial) <= 0.:
            lower = trial
            break
        if derivative(trial) <= 0.:
            lo, hi = trial, lower
            for _ in range(100):
                middle = (lo+hi)/2.
                if derivative(middle) <= 0.:
                    lo = middle
                else:
                    hi = middle
            lower = (lo+hi)/2.
            if residual(lower) > tolerance:
                raise ValueError("Não existe vão nominal compatível com a linha de apoio, alturas e perfil.")
            break
        lower = trial
    else:
        raise ValueError("Não existe vão nominal positivo compatível com a linha de apoio.")
    for _ in range(100):
        middle = (lower+upper)/2.
        value = residual(middle)
        if abs(value) <= tolerance:
            return middle
        if value > 0.:
            upper = middle
        else:
            lower = middle
    return (lower+upper)/2.


def resolve_support_alignment(config):
    """Return derived geometry without changing supplied reference or inputs."""
    mode = config.get("reference_alignment", "BottomChord")
    if mode not in ("BottomChord", "TopChordSupports"):
        raise ValueError("Alinhamento da linha de referência inválido.")
    length = float(config["span"])
    if mode == "BottomChord":
        if config.get("reference_surface") != "OuterFace":
            return {"nominal_span": length}
        offset = chord_section_extreme(config, "BOTTOM_CHORD", False)
        return {"nominal_span": length,
                "support_reference_local": ((0., offset, 0.), (length, offset, 0.)),
                "support_section_offset": offset}
    kind = config["envelope_type"]
    if kind not in ("Parallel", "DuoPitch"):
        raise ValueError("Alinhamento superior indisponível para esta forma de treliça.")
    height = float(config["height"])
    if not all(math.isfinite(v) and v > 0. for v in (length, height)):
        raise ValueError("Vão e altura devem ser positivos e finitos.")
    if kind == "Parallel":
        # Both chords are parallel to the supplied reference. End-height
        # fields belong to DuoPitch and may retain latent values after a switch.
        offset = upper_section_offset(config)
        return {"nominal_span": length,
                "support_reference_local": ((0., height+offset, 0.),
                                            (length, height+offset, 0.)),
                "support_section_offset": offset}
    left = float(config.get("left_end_height", 0.))
    right = left if config.get("link_end_heights", True) else float(config.get("right_end_height", 0.))
    apex = float(config.get("apex_position", .5))
    if (not all(math.isfinite(value) for value in (length, height, left, right, apex))
            or length <= 0. or height <= 0. or not 0. < apex < 1.
            or min(left, right) < 0. or max(left, right) >= height):
        raise ValueError("Vão, alturas ou inclinações inválidos para o alinhamento superior.")
    offset = upper_section_offset(config)
    if offset < -1e-7:
        raise ValueError("O topo físico do perfil fica abaixo da inserção; não alcança as seções de apoio nas extremidades.")
    offset = max(0., offset)
    span = _solve_nominal_span(length, height, left, right, apex, offset)
    for run, rise in ((apex*span, height-left), ((1.-apex)*span, height-right)):
        # At the station plane, the tangent point is offset*tan(pitch)
        # inside the branch. A huge section/steep roof can exceed its length.
        if offset*rise/run > math.hypot(run, rise)+1e-7:
            raise ValueError("A seção do banzo ultrapassa a cumeeira antes de alcançar o topo físico no apoio.")
    ql, qr = _support_heights(span, height, left, right, apex, offset)
    return {"nominal_span": span,
            "support_reference_local": ((0., ql, 0.), (span, qr, 0.)),
            "support_section_offset": offset}


def aligned_frame(config, raw_frame):
    """Nominal geometry frame; owner Placement stays in ``raw_frame``."""
    if (config.get("reference_alignment", "BottomChord") == "BottomChord"
            and config.get("reference_surface") != "OuterFace"):
        return raw_frame
    resolved = (config if config.get("support_reference_local")
                else resolve_support_alignment(config))
    left, right = resolved["support_reference_local"]
    angle = -math.atan2(right[1]-left[1], right[0]-left[0])
    c, s = math.cos(angle), math.sin(angle)
    origin, x, y, z = raw_frame
    physical_x = tuple(c*u+s*v for u, v in zip(x, y))
    physical_y = tuple(-s*u+c*v for u, v in zip(x, y))
    physical_origin = tuple(o-left[0]*u-left[1]*v-left[2]*w
                            for o, u, v, w in zip(origin, physical_x, physical_y, z))
    return physical_origin, physical_x, physical_y, z

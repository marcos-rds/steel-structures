"""Manual OCC diagnostic for an associative PlaneCut in FreeCAD 1.1.3.

Run from the FreeCAD Python console with:
    exec(open(r"C:\\path\\to\\tests\\manual_plane_cut_diagnostic.py", encoding="utf-8").read())

Select the structural member first.  Alternatively set TARGET_OBJECT_NAME to
its internal document Name (never its translated Label) before executing.
This script creates only transient in-memory Shapes and does not alter the
member, its reference, or the document.
"""

from math import acos, asin, degrees, sqrt

import FreeCAD as App
import FreeCADGui as Gui
import Part

from freecad.SteelStructures import profile_catalog
from freecad.SteelStructures.member import _insertion_translation, _section_face
from freecad.SteelStructures.member_adjustment_geometry import (
    normalized_vector,
    plane_axial_span,
)
from freecad.SteelStructures.member_adjustment_reference import (
    plane_reference_from_link,
    unpack_link_sub,
)
from freecad.SteelStructures.member_plane_cut import (
    clip_prism_by_plane_finite,
    global_plane_to_member_local,
    plane_point_at_axis_station,
)


TARGET_OBJECT_NAME = None
TARGET_END = "End"
TOLERANCE = 1e-7


def emit(message=""):
    text = "[PlaneCut diagnostic] " + str(message)
    try:
        App.Console.PrintMessage(text + "\n")
    except Exception:
        print(text)


def value_of(value):
    return float(getattr(value, "Value", value))


def vector_text(value):
    return "({:.12g}, {:.12g}, {:.12g})".format(value.x, value.y, value.z)


def tuple_text(value):
    return "({:.12g}, {:.12g}, {:.12g})".format(*value)


def bbox_text(shape):
    bounds = shape.BoundBox
    return ("X=[{:.12g}, {:.12g}] Y=[{:.12g}, {:.12g}] "
            "Z=[{:.12g}, {:.12g}]").format(
        bounds.XMin, bounds.XMax, bounds.YMin, bounds.YMax,
        bounds.ZMin, bounds.ZMax,
    )


def shape_report(label, shape):
    if shape is None:
        emit(label + ": None")
        return
    try:
        emit("{}: isNull={} isValid={} Volume={:.12g} Solids={} BoundBox={}".format(
            label,
            shape.isNull() if hasattr(shape, "isNull") else "n/a",
            shape.isValid() if hasattr(shape, "isValid") else "n/a",
            float(shape.Volume) if hasattr(shape, "Volume") else float("nan"),
            len(shape.Solids) if hasattr(shape, "Solids") else "n/a",
            bbox_text(shape),
        ))
    except Exception as error:
        emit("{}: report exception {}: {}".format(label, type(error).__name__, error))


def selected_member():
    document = App.ActiveDocument
    if document is None:
        raise RuntimeError("Nenhum documento ativo.")
    if TARGET_OBJECT_NAME:
        target = document.getObject(TARGET_OBJECT_NAME)
        if target is None:
            raise RuntimeError("Objeto {!r} não encontrado.".format(TARGET_OBJECT_NAME))
        return target
    candidates = [obj for obj in Gui.Selection.getSelection()
                  if hasattr(obj, "StartAdjustmentGeometryMode")]
    if len(candidates) != 1:
        raise RuntimeError("Selecione exatamente um membro Steel Structures.")
    return candidates[0]


def run():
    member = selected_member()
    if TARGET_END not in ("Start", "End"):
        raise RuntimeError("TARGET_END deve ser Start ou End.")
    mode = str(getattr(member, TARGET_END + "AdjustmentMode"))
    geometry_mode = str(getattr(member, TARGET_END + "AdjustmentGeometryMode"))
    reference = getattr(member, TARGET_END + "AdjustmentReference")
    gap = getattr(member, TARGET_END + "AdjustmentGap")
    if mode != "Associative":
        raise RuntimeError(TARGET_END + "AdjustmentMode deve ser Associative.")
    if geometry_mode != "PlaneCut":
        raise RuntimeError(TARGET_END + "AdjustmentGeometryMode deve ser PlaneCut.")
    unpacked = unpack_link_sub(reference)
    if unpacked is None or not unpacked[1].startswith("Face"):
        raise RuntimeError("AdjustmentReference deve conter exatamente uma FaceN.")
    reference_object, subelement = unpacked
    reference_plane = plane_reference_from_link(reference)
    if reference_plane is None:
        raise RuntimeError("Não foi possível resolver a Face plana global.")

    emit("=" * 72)
    emit("MEMBRO")
    emit("Name={} Label={!r}".format(member.Name, member.Label))
    emit("StartPoint={} EndPoint={}".format(
        vector_text(member.StartPoint), vector_text(member.EndPoint)))
    emit("Length={:.12g} AdjustedLength={:.12g} AdjustedEnd={} Gap={:.12g}".format(
        value_of(member.Length), value_of(member.AdjustedLength),
        TARGET_END, value_of(gap)))
    emit("Placement atual={}".format(member.Placement))

    # For an established member execute() preserves the complete current
    # rotation and updates only Base to EffectiveStartPoint before assigning
    # the local Shape.  Reproduce that exact branch without changing the object.
    shape_placement = App.Placement(member.Placement)
    shape_placement.Base = App.Vector(member.EffectiveStartPoint)
    emit("shape_placement usado para Shape local={}".format(shape_placement))

    emit("REFERÊNCIA")
    emit("Object={} Label={!r} Subelement={}".format(
        reference_object.Name, reference_object.Label, subelement))
    emit("ponto global={} normal global={}".format(
        tuple_text(reference_plane.point_global), tuple_text(reference_plane.normal_global)))

    local_plane = global_plane_to_member_local(
        shape_placement, App.Vector,
        reference_plane.point_global, reference_plane.normal_global, TOLERANCE,
    )
    if local_plane is None:
        raise RuntimeError("Conversão global→local retornou None.")
    local_point, local_normal = local_plane
    magnitude = sqrt(sum(value * value for value in local_normal))
    axial_dot = local_normal[2]
    axis_normal_angle = degrees(acos(min(1.0, max(-1.0, abs(axial_dot)))))
    plane_axis_angle = degrees(asin(min(1.0, max(0.0, abs(axial_dot)))))
    cut_station = 0.0 if TARGET_END == "Start" else value_of(member.AdjustedLength)
    cutting_point = plane_point_at_axis_station(
        local_point, local_normal, cut_station, TOLERANCE)
    if cutting_point is None:
        raise RuntimeError("Plano paralelo/quase paralelo ao eixo local.")
    raw_axis_station = (local_point[2]
                        + (local_normal[0] * local_point[0]
                           + local_normal[1] * local_point[1]) / local_normal[2])

    emit("CONVERSÃO")
    emit("ponto local={} normal local={}".format(
        tuple_text(local_point), tuple_text(local_normal)))
    emit("|normal local|={:.12g} normal·Z={:.12g}".format(magnitude, axial_dot))
    emit("estação axial referência={:.12g} estação de corte com Gap={:.12g}".format(
        raw_axis_station, cut_station))
    emit("ângulo eixo↔normal={:.12g}° ângulo plano↔eixo={:.12g}°".format(
        axis_normal_angle, plane_axis_angle))
    emit("ponto local do plano de corte={}".format(tuple_text(cutting_point)))

    profile = profile_catalog.get(str(member.Profile))
    section_face = _section_face(profile)
    tx, ty = _insertion_translation(profile, str(member.Insertion))
    section_face.translate(App.Vector(
        tx + value_of(member.OffsetX), ty + value_of(member.OffsetY), 0.0))
    bounds = section_face.BoundBox
    span = plane_axial_span(
        cut_station, local_normal,
        (bounds.XMin, bounds.XMax), (bounds.YMin, bounds.YMax), TOLERANCE)
    if span is None:
        raise RuntimeError("plane_axial_span retornou None.")
    section_scale = max(float(bounds.XLength), float(bounds.YLength), 1.0)
    overbuild = max(TOLERANCE * 100.0, section_scale * 1e-6)
    pre_start = min(0.0, span[0] - overbuild) if TARGET_END == "Start" else 0.0
    pre_end = (max(value_of(member.AdjustedLength), span[1] + overbuild)
               if TARGET_END == "End" else value_of(member.AdjustedLength))
    precursor_face = section_face.copy()
    if abs(pre_start) > TOLERANCE:
        precursor_face.translate(App.Vector(0, 0, pre_start))
    prism = precursor_face.extrude(App.Vector(0, 0, pre_end - pre_start))

    emit("PRISMA PRECURSOR")
    emit("span=[{:.12g}, {:.12g}] overbuild={:.12g} pre_start={:.12g} pre_end={:.12g}".format(
        span[0], span[1], overbuild, pre_start, pre_end))
    shape_report("prism", prism)

    diagonal = sqrt(bounds.XLength ** 2 + bounds.YLength ** 2 + (pre_end - pre_start) ** 2)
    plane_size = max(2.0 * diagonal, 1.0)
    point_vector = App.Vector(*cutting_point)
    normal_vector = App.Vector(*local_normal)
    keep_z = value_of(member.AdjustedLength) if TARGET_END == "Start" else 0.0
    keep_point = App.Vector(0, 0, keep_z)

    emit("HALF-SPACE LEGADO (DISPONIBILIDADE/COMPARAÇÃO)")
    emit("plane_size={:.12g} keep_point={}".format(plane_size, vector_text(keep_point)))
    plane_face = half_space = current_result = None
    try:
        if not hasattr(Part, "makeHalfSpace"):
            emit("Part.makeHalfSpace indisponível neste FreeCAD")
        else:
            plane_face = Part.makePlane(plane_size, plane_size, point_vector, normal_vector)
            center = plane_face.CenterOfMass
            plane_face.translate(point_vector.sub(center))
            shape_report("plane_face", plane_face)
            half_space = Part.makeHalfSpace(plane_face, keep_point)
            shape_report("half_space", half_space)
            current_result = prism.common(half_space)
            shape_report("prism.common(half_space)", current_result)
    except Exception as error:
        emit("EXCEÇÃO OCC half-space/common: {}: {}".format(type(error).__name__, error))

    emit("CLIPPING FINITO DE PRODUÇÃO")
    try:
        finite = clip_prism_by_plane_finite(
            Part, App.Vector, prism, cutting_point, local_normal,
            (keep_point.x, keep_point.y, keep_point.z), TOLERANCE)
        if finite is None:
            emit("clip_prism_by_plane_finite retornou None")
        else:
            emit("normal orientada={} e1={} e2={}".format(
                tuple_text(finite.plan.normal), tuple_text(finite.plan.e1),
                tuple_text(finite.plan.e2)))
            emit("e1=[{:.12g}, {:.12g}] e2=[{:.12g}, {:.12g}] depth={:.12g} margin={:.12g}".format(
                finite.plan.e1_min, finite.plan.e1_max,
                finite.plan.e2_min, finite.plan.e2_max,
                finite.plan.depth, finite.plan.margin))
            shape_report("finite clipping face", finite.clipping_face)
            shape_report("finite keep_solid", finite.keep_solid)
            shape_report("prism.common(keep_solid)", finite.shape)
    except Exception as error:
        emit("EXCEÇÃO OCC clipping finito/common: {}: {}".format(type(error).__name__, error))
    emit("=" * 72)


try:
    run()
except Exception as diagnostic_error:
    emit("ERRO {}: {}".format(type(diagnostic_error).__name__, diagnostic_error))

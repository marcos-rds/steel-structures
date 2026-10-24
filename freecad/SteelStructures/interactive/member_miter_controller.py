# SPDX-License-Identifier: LGPL-2.1-or-later
"""Two detached candidates, one common-plane validation, one transaction."""
from dataclasses import dataclass
import math

import FreeCAD as App
import Part

from .. import member as member_module, profile_catalog
from ..member_adjustment_reference import would_create_adjustment_cycle, unpack_link_sub, plane_reference_from_link, linear_reference_from_link
from ..member_miter_geometry import MiterValidationError, dot, resolve_miter
from ..member_plane_cut import global_plane_to_member_local, orthonormal_plane_basis, plane_axial_span
from ..member_batch import signature
from .member_adjustment_controller import (
    MemberAdjustmentController, is_structural_member, verify_adjustment_candidate,
)


SUPPORTED_SECTIONS = frozenset((
    ("i_section", "parallel_flange"), ("cold_formed_channel", "simple_u"),
    ("cold_formed_channel", "stiffened_u"), ("hollow_section", "rectangular"),
    ("hollow_section", "square"),
))


@dataclass(frozen=True)
class MiterCandidate:
    members: tuple
    plan: object
    candidates: tuple
    global_shapes: tuple
    section_scale: float


def parent_placement(member):
    """Rigid parent-local -> world transform; never mutate the member frame."""
    global_placement = member.getGlobalPlacement() if hasattr(member, "getGlobalPlacement") else member.Placement
    return global_placement.multiply(member.Placement.inverse())


def _global_shape(result, parent):
    shape = result.Shape.copy()
    shape.Placement = parent.multiply(result.Placement)
    return shape


def global_member_shape(member):
    shape = member.Shape.copy()
    shape.Placement = member.getGlobalPlacement() if hasattr(member, "getGlobalPlacement") else App.Placement(member.Placement)
    return shape


def _finite(value, message):
    value = float(value)
    if not math.isfinite(value):
        raise MiterValidationError(message)
    return value


def validate_pair_shapes(shapes, plan):
    """Measure material on a plane, not a second cutting algorithm."""
    if dot(plan.normal, plan.inward[0])*dot(plan.normal, plan.inward[1]) >= 0:
        raise MiterValidationError("Os membros não preservam semiespaços opostos.")
    for shape in shapes:
        if (shape is None or shape.isNull() or not shape.isValid() or len(shape.Solids) != 1
                or _finite(shape.Volume, "Volume inválido.") <= 1e-7):
            raise MiterValidationError("Cada resultado deve conter exatamente um sólido válido.")
    e1, e2, _ = orthonormal_plane_basis(plan.normal)
    points = []
    for shape in shapes:
        box = shape.BoundBox
        points.extend((x, y, z) for x in (box.XMin, box.XMax)
                      for y in (box.YMin, box.YMax) for z in (box.ZMin, box.ZMax))
    coordinates = [[dot(tuple(v-p for v, p in zip(point, plan.point)), axis) for point in points]
                   for axis in (e1, e2)]
    margin = max(plan.length_tolerance*10., 1.)
    bounds = [(min(values)-margin, max(values)+margin) for values in coordinates]
    def vertex(x, y):
        return App.Vector(*(p+x*a+y*b for p, a, b in zip(plan.point, e1, e2)))
    x, y = bounds
    corners = [vertex(x[0], y[0]), vertex(x[1], y[0]), vertex(x[1], y[1]), vertex(x[0], y[1])]
    plane = Part.Face(Part.makePolygon(corners+[corners[0]]))
    caps = tuple(shape.common(plane).removeSplitter() for shape in shapes)
    areas = tuple(_finite(cap.Area, "Área de contato inválida.") for cap in caps)
    if any(a <= plan.length_tolerance**2 for a in areas) or any(not cap.Faces for cap in caps):
        raise MiterValidationError("Não existe superfície útil de contato no plano do encontro.")
    perimeter = sum(edge.Length for cap in caps for edge in cap.Edges)
    area_tolerance = max(1e-6, plan.length_tolerance*perimeter)
    common = _finite(caps[0].common(caps[1]).Area, "Contato inválido.")
    residuals = tuple(_finite(a.cut(b).Area, "Comparação de contato inválida.")
                      for a, b in (caps, caps[::-1]))
    if common <= area_tolerance or max(residuals) > area_tolerance:
        raise MiterValidationError("As seções não fecham no plano comum; revise orientação e inserção.")
    # Exact curve correspondence is an extra conservative gate. A minimum
    # distToShape()==0 would say nothing about the rest of the boundaries.
    boundaries = tuple(Part.makeCompound(cap.Edges) for cap in caps)
    for a, b in (boundaries, boundaries[::-1]):
        length = _finite(a.cut(b).Length, "Comparação de contornos inválida.")
        if length > plan.length_tolerance*max(1, len(a.Edges)+len(b.Edges)):
            raise MiterValidationError("Os contornos das superfícies de corte não coincidem.")
    overlap = _finite(shapes[0].common(shapes[1]).Volume, "Interpenetração inválida.")
    volume_tolerance = max(1e-5, plan.length_tolerance*sum(areas))
    if overlap > volume_tolerance:
        raise MiterValidationError("Os resultados apresentam interpenetração volumétrica.")


class MemberMiterController:
    def __init__(self, document, members=()):
        self.document = document
        if len(members) > 2:
            raise MiterValidationError("Selecione somente dois membros para a meia-esquadria.")
        self.members = list(members)+[None]*max(0, 2-len(members))

    def set_member(self, index, member):
        if index not in (0, 1) or not is_structural_member(member):
            raise MiterValidationError("Selecione um membro estrutural.")
        if member is self.members[1-index]:
            raise MiterValidationError("Selecione dois membros diferentes.")
        if member.Document is not self.document:
            raise MiterValidationError("Os dois membros devem pertencer ao documento da tarefa.")
        self.members[index] = member

    @staticmethod
    def _sources(obj):
        queue, seen = list(obj.OutList), set()
        while queue:
            source = queue.pop()
            if id(source) in seen:
                continue
            seen.add(id(source))
            yield source
            queue.extend(source.OutList)

    def _source_states(self, obj):
        return tuple(sorted((source.Name, tuple(source.State)) for source in self._sources(obj)))

    def _eligible(self):
        if len(self.members) != 2 or any(not is_structural_member(obj) for obj in self.members):
            raise MiterValidationError("Selecione dois membros estruturais.")
        a, b = self.members
        if a is b:
            raise MiterValidationError("Selecione dois membros diferentes.")
        for obj in self.members:
            if obj.Document is not self.document or self.document.getObject(obj.Name) is not obj:
                raise MiterValidationError("Um membro está indisponível ou pertence a outro documento.")
            if getattr(obj, "GenerationOwner", None) is not None:
                raise MiterValidationError("Filhos de treliças não são suportados nesta meia-esquadria.")
            if str(obj.AxisDefinitionMode) != "Independent":
                raise MiterValidationError("Este MVP exige eixos independentes, sem AxisSource vinculado.")
            if (getattr(obj, "AssemblySectionTransform", "") or getattr(obj, "PhysicalFitPlan", "")
                    or getattr(obj, "PhysicalFitAutoState", "")):
                raise MiterValidationError("Composições ou planos automáticos existentes não são suportados.")
            if str(obj.SectionGeometryMode) != "Detailed":
                raise MiterValidationError("Este MVP exige geometria de seção Detalhada nos dois membros.")
            if "Invalid" in obj.State:
                raise MiterValidationError("Um membro está inválido; revise suas propriedades.")
            definition = profile_catalog.get(str(obj.Profile)).definition
            if (definition.geometry_type, definition.geometry_variant) not in SUPPORTED_SECTIONS:
                raise MiterValidationError("Família de seção fora do escopo inicial da meia-esquadria.")
            # Detached evaluation does not execute document expressions.
            if obj.ExpressionEngine:
                raise MiterValidationError("Membros com expressões exigem revisão e não são suportados neste MVP.")
            if any(str(getattr(obj, end+"AdjustmentMode")) == "Associative" for end in ("Start", "End")):
                parent = parent_placement(obj)
                if any(abs(a-b) > 1e-9 for a, b in zip(parent.toMatrix().A, App.Placement().toMatrix().A)):
                    raise MiterValidationError("Ajustes associativos em contêiner transformado exigem revisão fora deste MVP.")
            for source in self._sources(obj):
                if any(s in source.State for s in ("Touched", "Invalid", "Recompute")):
                    raise MiterValidationError("Recompute as referências dos membros antes do encontro.")
        if str(a.Profile) != str(b.Profile):
            raise MiterValidationError("Perfis diferentes não são suportados nesta operação equilibrada.")
        if would_create_adjustment_cycle(a, b) or would_create_adjustment_cycle(b, a):
            raise MiterValidationError("Os membros já dependem um do outro; o par não pode ser avaliado isoladamente.")

    def prepare_inputs(self):
        """Resolve replay's pending outputs locally, without a preview transaction.

        FreeCAD Undo/Redo restores the inputs and outputs but marks the features
        Touched. Partial document recompute clears that state; object.recompute()
        does not. Check ALL eligibility/dependencies first: partial recompute can
        otherwise execute dirty upstream sources as well as the selected pair.
        """
        self._eligible()
        pending = [obj for obj in self.members if any(s in obj.State for s in ("Touched", "Recompute"))]
        if not pending:
            return
        before = tuple(signature(obj) for obj in self.members)
        self.document.recompute(pending)
        if before != tuple(signature(obj) for obj in self.members):
            raise MiterValidationError("A atualização dos membros alterou entradas paramétricas; revise o modelo.")
        if any(s in obj.State for obj in self.members for s in ("Touched", "Invalid", "Recompute")):
            raise MiterValidationError("Não foi possível atualizar os membros para o encontro.")

    def evaluate(self):
        try:
            self.prepare_inputs()
            members = tuple(self.members)
            parents = tuple(parent_placement(obj) for obj in members)
            plan = resolve_miter(*(tuple(parent.multVec(p)) for obj, parent in zip(members, parents)
                                   for p in (obj.StartPoint, obj.EndPoint)))
            candidates, sizes = [], []
            for obj, parent, prefix, station in zip(members, parents, plan.ends, plan.stations):
                if str(getattr(obj, prefix+"AdjustmentMode")) != "None":
                    raise MiterValidationError("A ponta %s de %s já possui ajuste; remova-o antes da meia-esquadria."
                                               % ("inicial" if prefix == "Start" else "final", obj.Label))
                axis = obj.EndPoint.sub(obj.StartPoint)
                length = axis.Length
                axis.normalize()
                local_axis = obj.Placement.Rotation.multVec(App.Vector(0, 0, 1))
                if local_axis.sub(axis).Length > 1e-7:
                    raise MiterValidationError("Placement e eixo nominal não estão coerentes.")
                local = global_plane_to_member_local(parent.multiply(obj.Placement), App.Vector, plan.point, plan.normal)
                values = {prefix+"AdjustmentMode": "Fixed", prefix+"AdjustmentGeometryMode": "PlaneCut",
                          prefix+"AdjustmentReference": None, prefix+"AdjustmentGap": 0.,
                          prefix+"FixedReferenceOffset": station if prefix == "Start" else length-station,
                          prefix+"FixedPlaneNormal": App.Vector(*local[1])}
                geometry = member_module._section_geometry(profile_catalog.get(str(obj.Profile)), "Detailed")
                tx, ty = member_module._geometry_insertion_translation(geometry, str(obj.Insertion))
                bounds = geometry.bounds
                xb = (bounds.min_x+tx+float(obj.OffsetX.Value), bounds.max_x+tx+float(obj.OffsetX.Value))
                yb = (bounds.min_y+ty+float(obj.OffsetY.Value), bounds.max_y+ty+float(obj.OffsetY.Value))
                sizes.append(max(xb[1]-xb[0], yb[1]-yb[0]))
                span = plane_axial_span(station, local[1], xb, yb)
                opposite = "End" if prefix == "Start" else "Start"
                opposite_station = getattr(obj, "Effective"+opposite+"Point").sub(obj.StartPoint).dot(axis)
                opposite_normal = (0., 0., 1.)
                if (str(getattr(obj, opposite+"AdjustmentMode")) != "None"
                        and str(getattr(obj, opposite+"AdjustmentGeometryMode")) == "PlaneCut"):
                    if str(getattr(obj, opposite+"AdjustmentMode")) == "Fixed":
                        normal = getattr(obj, opposite+"FixedPlaneNormal")
                        if normal.Length > 1e-7:
                            opposite_normal = tuple(normal)
                    else:
                        reference = plane_reference_from_link(getattr(obj, opposite+"AdjustmentReference"))
                        if reference is None:
                            raise MiterValidationError("A referência da ponta oposta não está válida.")
                        opposite_normal = global_plane_to_member_local(
                            obj.Placement, App.Vector, reference.point_global, reference.normal_global)[1]
                opposite_span = plane_axial_span(opposite_station, opposite_normal, xb, yb)
                if span is None or opposite_span is None:
                    raise MiterValidationError("Plano de corte quase paralelo ao eixo.")
                if ((prefix == "Start" and span[1] >= opposite_span[0]-plan.length_tolerance)
                        or (prefix == "End" and span[0] <= opposite_span[1]+plan.length_tolerance)):
                    raise MiterValidationError("A seção no encontro alcança a extremidade oposta.")
                candidate = MemberAdjustmentController(self.document, obj).evaluate_values(values)
                candidates.append(candidate)
            shapes = tuple(_global_shape(c.result, parent) for c, parent in zip(candidates, parents))
            validate_pair_shapes(shapes, plan)
            return MiterCandidate(members, plan, tuple(candidates), shapes, max(sizes))
        except MiterValidationError:
            raise
        except Exception as exc:
            raise MiterValidationError("Não foi possível validar os dois cortes. " + str(exc)) from exc

    def _preserved(self, obj, prefix):
        opposite = "End" if prefix == "Start" else "Start"
        fields = ("StartPoint", "EndPoint", "Length", "MemberLength", "Profile", "ProfileCategory",
                  "ProfileSeries", "Rotation", "Insertion", "OffsetX", "OffsetY", "StartExtension", "EndExtension")
        fields += tuple(opposite+s for s in ("AdjustmentMode", "AdjustmentGeometryMode", "AdjustmentReference",
                                            "AdjustmentGap", "FixedReferenceOffset", "FixedPlaneNormal"))
        def plain(value):
            if isinstance(value, App.Vector):
                return tuple(value)
            if hasattr(value, "Value"):
                return float(value.Value)
            return value
        return tuple(plain(getattr(obj, name)) for name in fields)

    def apply(self):
        candidate = self.evaluate()  # Includes fresh eligibility and geometric pair checks.
        preserved = tuple(self._preserved(obj, end) for obj, end in zip(candidate.members, candidate.plan.ends))
        self.document.openTransaction("Meia-esquadria")
        try:
            for obj, prepared in zip(candidate.members, candidate.candidates):
                for name, value in prepared.values.items():
                    setattr(obj, name, value)
            self.document.recompute(list(candidate.members))
            for obj, prepared, end, old in zip(candidate.members, candidate.candidates, candidate.plan.ends, preserved):
                verify_adjustment_candidate(obj, prepared)
                if self._preserved(obj, end) != old:
                    raise MiterValidationError("O recompute alterou propriedades fora das pontas escolhidas.")
            validate_pair_shapes(tuple(global_member_shape(obj) for obj in candidate.members), candidate.plan)
            self.document.commitTransaction()
        except Exception:
            self.document.abortTransaction()
            raise
        return candidate

    def input_signature(self):
        result = []
        for obj in self.members:
            if obj is None:
                result.append(None)
                continue
            links = []
            for prefix in ("Start", "End"):
                link = getattr(obj, prefix+"AdjustmentReference", None)
                unpacked = unpack_link_sub(link)
                if unpacked:
                    links.append((unpacked[0].Name, unpacked[1],
                                  plane_reference_from_link(link) if unpacked[1].startswith("Face")
                                  else linear_reference_from_link(link)))
            global_placement = obj.getGlobalPlacement() if hasattr(obj, "getGlobalPlacement") else obj.Placement
            result.append((obj.Name, signature(obj), tuple(obj.Placement.toMatrix().A), tuple(global_placement.toMatrix().A),
                           tuple(obj.State), self._source_states(obj), repr(obj.ExpressionEngine), tuple(links),
                           str(getattr(obj, "GenerationOwner", None)),
                           str(getattr(obj, "PhysicalFitPlan", "")), str(getattr(obj, "PhysicalFitAutoState", ""))))
        return tuple(result)

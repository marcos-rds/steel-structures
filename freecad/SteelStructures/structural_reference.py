# SPDX-License-Identifier: LGPL-2.1-or-later
"""Read-only nominal member references, without GUI, OCC or recompute.

StartPoint/EndPoint live in the parent's coordinate system. Shape Placement
starts at the effective cut station and must not be applied to those points.
Descriptors are detached session values, not persistent identities or nodes.
"""

from dataclasses import dataclass
import hashlib
import json
import math


LENGTH_TOLERANCE = 1e-7
FRAME_TOLERANCE = 1e-7
_READ_ERRORS = (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError,
                KeyError, IndexError, OverflowError)

# Inputs and persisted scalar/vector outputs relevant to replay of this member.
# Deliberately exclude Shape and presentation; this reader cannot evaluate OCC.
_SIGNATURE_FIELDS = (
    "StartPoint", "EndPoint", "Length", "MemberLength", "EffectiveStartPoint",
    "EffectiveEndPoint", "AdjustedLength", "Profile", "ProfileCategory",
    "ProfileSeries", "Insertion", "Rotation", "SectionGeometryMode", "Material",
    "OffsetX", "OffsetY", "StartExtension", "EndExtension", "AxisDefinitionMode",
    "AxisSource", "ExpressionEngine", "AssemblySectionTransform", "PhysicalFitPlan",
    "PhysicalFitAutoState", "Manufacturer", "ProfileFamily", "MassPerMeter",
    "TotalMass", "CatalogArea", "CatalogSource",
    "GenerationKey", "GenerationStatus", "ControlledState", "SourceSignature",
) + tuple(prefix+suffix for prefix in ("Start", "End") for suffix in (
    "AdjustmentMode", "AdjustmentGeometryMode", "AdjustmentReference",
    "AdjustmentGap", "FixedReferenceOffset", "FixedPlaneNormal"))

# The owner's declared configuration inputs (truss.PROPERTY_CONFIG plus the
# C2/reference controls), accepted state and registry identity. No graph is
# rebuilt. This is a replay fingerprint, not another configuration resolver.
_OWNER_SIGNATURE_FIELDS = (
    "SchemaVersion", "EnvelopeType", "Span", "Height", "ApexPosition",
    "PanelCount", "TopologyPreset", "TopChordContinuity", "BottomChordContinuity",
    "LeftEndHeight", "RightEndHeight", "LinkEndHeights", "ReferenceAlignment",
    "DefaultGussetThickness", "NominalSpan", "PanelizationMode", "LeftPanels",
    "RightPanels", "TopologyMode", "ReferenceMode", "ReferenceLinked",
    "RoleSpecs", "C2Configuration", "AppliedState", "GenerationState",
    "NeedsRegeneration", "ExpressionEngine",
)


@dataclass(frozen=True)
class AxisReference:
    key: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    frame: tuple[tuple[float, float, float], ...]
    parents: tuple[str, ...]
    category: str


@dataclass(frozen=True)
class AxisResolution:
    axis: AxisReference | None
    reason: str = ""


class AxisReadContext:
    """Disposable accepted-owner cache for ONE synchronous read batch.

    Create at the beginning of a GUI flush and discard before returning to the
    event loop. Never retain across document writes, recompute, Undo/Redo or an
    event-loop yield. This deliberately has no observer or persistent cache:
    a new batch revalidates every owner. Per-child geometry is still read on
    each resolution. Owner validation/decoding/indexing is linear once per batch.

    ``trusted_replay`` is optional session evidence supplied only after an
    observed Undo/Redo: member Name -> fingerprints of previously clean reads.
    The caller owns evidence lifetime and revokes permission on material edits.
    Merely constructing a context does not permit reading pending members.
    """

    def __init__(self, *, trusted_replay=None):
        self._owners = {}
        self._owner_fingerprints = {}
        self._trusted_replay = {name: frozenset(signatures)
                                for name, signatures in (trusted_replay or {}).items()}

    def _allows_replay(self, member):
        signature = axis_state_signature(member, context=self)
        return (signature is not None
                and signature in self._trusted_replay.get(member.Name, ()))

    def _owner_fingerprint(self, owner, document, vector_type):
        key = (id(document), id(owner))
        if key not in self._owner_fingerprints:
            try:
                fingerprint = _owner_replay_fingerprint(owner, document, vector_type)
            except _READ_ERRORS:
                fingerprint = None
            self._owner_fingerprints[key] = (owner, document, fingerprint)
        return self._owner_fingerprints[key][2]

    def _owner(self, owner, document, *, allow_replay_touched=False):
        # A strict failure cannot poison a trusted read, and a trusted read must
        # never authorize a different child without its own matching fingerprint.
        key = (id(document), id(owner), allow_replay_touched)
        if key not in self._owners:
            try:
                snapshot, error = _read_owner(
                    owner, document, allow_replay_touched=allow_replay_touched), ""
            except _READ_ERRORS as exc:
                snapshot, error = None, str(exc) or "Treliça indisponível."
            # Keep wrappers alive for the batch so transient Python ids cannot
            # be reused. These are session handles, not persistent identities.
            self._owners[key] = (owner, document, snapshot, error)
        _owner, _document, snapshot, error = self._owners[key]
        if error:
            raise ValueError(error)
        return snapshot


def _xyz(value):
    values = (float(value.x), float(value.y), float(value.z))
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Coordenadas não finitas.")
    return values


def _vector(values):
    result = tuple(float(v) for v in values)
    if len(result) != 3 or not all(math.isfinite(v) for v in result):
        raise ValueError("Vetor inválido.")
    return result


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def _close(a, b, tolerance=LENGTH_TOLERANCE):
    return math.dist(a, b) <= tolerance


def _proxy_is(obj, name, module):
    proxy = getattr(obj, "Proxy", None)
    return (proxy is not None and type(proxy).__name__ == name
            and type(proxy).__module__ in ("freecad.SteelStructures"+module,
                                          "SteelStructures"+module))


def _pending(obj):
    return any(state in getattr(obj, "State", ())
               for state in ("Touched", "Invalid", "Recompute"))


def _frame(placement, vector_type):
    _xyz(placement.Base)
    axes = tuple(_xyz(placement.Rotation.multVec(vector_type(*unit)))
                 for unit in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
    if (any(abs(_dot(axis, axis)-1) > FRAME_TOLERANCE for axis in axes)
            or any(abs(_dot(axes[i], axes[j])) > FRAME_TOLERANCE
                   for i, j in ((0, 1), (0, 2), (1, 2)))
            or not _close(_cross(axes[0], axes[1]), axes[2], FRAME_TOLERANCE)):
        raise ValueError("Referencial não rígido ou inválido.")
    return axes


def _parents(member):
    result = []
    current = member
    while hasattr(current, "getParentGeoFeatureGroup"):
        current = current.getParentGeoFeatureGroup()
        if current is None:
            break
        if current == member or current in result:
            raise ValueError("Ciclo de contêineres.")
        if (current.TypeId != "App::Part" or current.Document != member.Document
                or "Invalid" in current.State):
            raise ValueError("Contêiner fora do domínio de hierarquia rígida.")
        result.append(current)
    return result


def _signature_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if hasattr(value, "x"):
        return _xyz(value)
    if isinstance(value, float) or hasattr(value, "Value"):
        number = float(getattr(value, "Value", value))
        if not math.isfinite(number):
            raise ValueError("Assinatura não finita.")
        return number
    if isinstance(value, (tuple, list)):
        return tuple(_signature_value(item) for item in value)
    raise ValueError("Propriedade fora do contrato de assinatura.")


def _signature_fields(obj, names):
    return tuple((name, _signature_value(getattr(obj, name))
                  if hasattr(obj, name) else ("absent",)) for name in names)


def _placement_signature(placement, vector_type):
    return _xyz(placement.Base), _frame(placement, vector_type)


def _owner_replay_fingerprint(owner, document, vector_type):
    """Hash all accepted-owner inputs once per batch, with no Shape access."""
    from .trusses.serialization import decode_state, loads

    if (owner.Document != document or document.getObject(owner.Name) != owner
            or not _proxy_is(owner, "StructuralTrussProxy", ".truss")
            or "Invalid" in owner.State or owner.GenerationState != "Valid"
            or owner.NeedsRegeneration or getattr(owner, "ExpressionEngine", ())
            or getattr(owner, "ReferenceLinked", False)
            or getattr(owner, "ReferenceSource", None)
            or getattr(owner, "ReferenceContainers", ())
            or owner.getParentGeoFeatureGroup() is not None):
        raise ValueError("Treliça fora do contrato de replay conhecido.")
    config = loads(owner.C2Configuration or "{}")
    state = decode_state(owner.AppliedState)
    if (config.get("reference_linked", False)
            or state["candidate"]["config"].get("reference_linked", False)):
        raise ValueError("Fonte de treliça vinculada fora do replay conhecido.")
    registries = []
    for name in ("GeneratedMembers", "RoleGroups", "GeneratedGussetPlates"):
        values = tuple(sorted((obj.Name, _signature_value(getattr(obj, "ID", None)))
                              for obj in getattr(owner, name, ())))
        registries.append((name, values))
    payload = (str(owner.Name), _signature_value(getattr(owner, "ID", None)),
               _signature_fields(owner, _OWNER_SIGNATURE_FIELDS),
               _placement_signature(owner.Placement, vector_type), tuple(registries))
    # Keeping a digest in each child fingerprint avoids rehashing/copying a full
    # AppliedState/registry for every member (which would restore quadratic cost).
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def axis_state_signature(member, *, context=None):
    """Return an immutable session fingerprint, or None outside replay support.

    Touched/Recompute are deliberately omitted so restored inputs can be
    compared. A fingerprint is NOT a validity certificate: callers may only
    remember it after a successful clean read. They may offer remembered values
    to AxisReadContext only after an observed Undo/Redo, revoking that permission
    on subsequent material edits. Invalid/transacting members never qualify.

    Expressions and live source/adjustment dependencies stay strict. Root truss
    children additionally fingerprint their accepted, unlinked owner and registry.
    Use the same batch context while recording clean fingerprints to keep owner
    decoding/hashing linear in the number of children.
    Shape and all presentation properties are neither read nor fingerprinted.
    """
    try:
        document = member.Document
        if (member.TypeId != "Part::FeaturePython"
                or not _proxy_is(member, "StructuralMemberProxy", ".member")
                or document is None or document.getObject(member.Name) != member
                or getattr(document, "Transacting", False)
                or "Invalid" in member.State
                or member.AxisDefinitionMode != "Independent"
                or getattr(member, "ExpressionEngine", ())
                or getattr(member, "AxisSource", None)):
            return None
        for prefix in ("Start", "End"):
            if (getattr(member, prefix+"AdjustmentMode", "None") == "Associative"
                    or getattr(member, prefix+"AdjustmentReference", None)):
                return None
        parents = _parents(member)
        vector_type = type(member.StartPoint)
        owner = getattr(member, "GenerationOwner", None)
        owner_fingerprint = None
        if owner is not None:
            if parents or member.GenerationStatus != "Valid":
                return None
            owner_fingerprint = (context._owner_fingerprint(owner, document, vector_type)
                                 if context is not None else
                                 _owner_replay_fingerprint(owner, document, vector_type))
            if owner_fingerprint is None:
                return None
        fields = _signature_fields(member, _SIGNATURE_FIELDS)
        return (id(document), str(document.Name), str(member.Name),
                _signature_value(getattr(member, "ID", None)), fields,
                _placement_signature(member.Placement, vector_type),
                _placement_signature(member.getGlobalPlacement(), vector_type),
                tuple((parent.Name, _placement_signature(parent.Placement, vector_type))
                      for parent in parents), owner_fingerprint)
    except _READ_ERRORS:
        return None


def _matches_saved_value(current, saved):
    if isinstance(saved, list):
        values = _xyz(current) if hasattr(current, "x") else tuple(current)
        return (len(values) == len(saved)
                and all(math.isfinite(float(v)) for v in values)
                and _close(values, tuple(float(v) for v in saved)))
    if isinstance(saved, (int, float)):
        value = float(getattr(current, "Value", current))
        return math.isfinite(value) and abs(value-float(saved)) <= LENGTH_TOLERANCE
    return str(current) == saved


def _read_owner(owner, document, *, allow_replay_touched=False):
    """Read and index accepted metadata once, without realizing a truss graph."""
    from .trusses.serialization import decode_state

    if (owner.Document != document or document.getObject(owner.Name) != owner
            or not _proxy_is(owner, "StructuralTrussProxy", ".truss")
            or owner.GenerationState != "Valid" or owner.NeedsRegeneration
            or "Invalid" in owner.State
            or (_pending(owner) and not allow_replay_touched)):
        raise ValueError("Filho sem estado de treliça aceito e válido.")
    state = decode_state(owner.AppliedState)
    bindings = state["bindings"]
    children = tuple(owner.GeneratedMembers)
    children_by_name = {child.Name: child for child in children}
    if (len(children_by_name) != len(children)
            or set(bindings.values()) != set(children_by_name)
            or len(set(bindings.values())) != len(bindings)):
        raise ValueError("Binding de membro gerado inconsistente.")
    children_by_key = {}
    for key, name in bindings.items():
        child = document.getObject(name)
        if (child != children_by_name[name] or child.GenerationOwner != owner
                or child.GenerationKey != key):
            raise ValueError("Registro de filhos inconsistente.")
        children_by_key[key] = child
    items = state["candidate"]["items"]
    items_by_key = {item["key"]: item for item in items}
    if len(items_by_key) != len(items) or set(items_by_key) != set(bindings):
        raise ValueError("Realização aceita ausente ou ambígua.")
    return children_by_key, items_by_key


def _validate_generated(member, parent, local_frame, vector_type, context):
    """Validate physical child inputs against accepted, indexed owner metadata."""
    from .trusses.serialization import loads

    owner = member.GenerationOwner
    if member.GenerationStatus != "Valid" or member.ExpressionEngine:
        raise ValueError("Filho sem estado de treliça aceito e válido.")
    # Applied realizations store world coordinates. Arbitrary transformed child
    # containers are not part of the first-stage generated-member contract.
    if (not _close(_xyz(parent.Base), (0., 0., 0.))
            or any(not _close(axis, unit, FRAME_TOLERANCE)
                   for axis, unit in zip(_frame(parent, vector_type),
                                         ((1, 0, 0), (0, 1, 0), (0, 0, 1))))):
        raise ValueError("Filho gerado em contêiner transformado não suportado.")
    allow_replay_touched = bool(context is not None and _pending(owner)
                               and context._allows_replay(member))
    children, items = (context._owner(owner, member.Document,
                                     allow_replay_touched=allow_replay_touched)
                       if context is not None else _read_owner(owner, member.Document))
    if children.get(member.GenerationKey) != member:
        raise ValueError("Binding de membro gerado inconsistente.")
    item = items[member.GenerationKey]
    if (not _close(_xyz(member.StartPoint), _vector(item["start_global"]))
            or not _close(_xyz(member.EndPoint), _vector(item["end_global"]))):
        raise ValueError("Eixo do filho diverge da realização aceita.")
    u = _vector(item["section_u_global"])
    v = _cross(local_frame[2], u)
    angle = math.radians(float(item["spec"]["rotation"]))
    expected_u = tuple(math.cos(angle)*x + math.sin(angle)*y for x, y in zip(u, v))
    if not _close(local_frame[0], expected_u, FRAME_TOLERANCE):
        raise ValueError("Orientação do filho diverge da realização aceita.")
    saved = loads(member.ControlledState)
    required = {"StartPoint", "EndPoint", "Profile", "Insertion", "Rotation",
                "SectionGeometryMode", "AxisDefinitionMode", "AxisSource", "Placement"}
    if not required.issubset(saved):
        raise ValueError("Snapshot controlado incompleto.")
    # The producer owns ControlledState's serialization. Compare its persisted
    # fields as values; color is presentation and cannot invalidate an axis.
    for name, value in saved.items():
        if name == "Color":
            continue
        current = (list(_xyz(member.Placement.Base)) + list(member.Placement.Rotation.Q)
                   if name == "Placement" else getattr(member, name))
        if not _matches_saved_value(current, value):
            raise ValueError("Entradas do filho divergem do estado controlado.")


def resolve_member_axis(member, *, context=None):
    """Return an immutable world reference or an explicit conservative refusal.

No document mutation, Shape access, dependency execution or visual-property
access occurs. ``key`` is the member Name within the caller's live document;
it is not a cross-document/persistent UUID. Frame order is global X, Y, Z.
An optional AxisReadContext shares owner reads only within one synchronous
batch with no mutations or event-loop yields. Without it each call revalidates.
"""
    try:
        if (member is None or member.TypeId != "Part::FeaturePython"
                or not _proxy_is(member, "StructuralMemberProxy", ".member")):
            raise ValueError("Objeto não é um membro estrutural suportado.")
        document = member.Document
        if document is None or document.getObject(member.Name) != member:
            raise ValueError("Membro não está disponível no documento.")
        if getattr(document, "Transacting", False):
            raise ValueError("Documento em restauração transacional.")
        if "Invalid" in member.State:
            raise ValueError("Membro inválido.")
        if _pending(member) and (context is None or not context._allows_replay(member)):
            raise ValueError("Membro pendente de recompute ou inválido.")
        if str(member.AxisDefinitionMode) != "Independent":
            raise ValueError("Eixo vinculado fora do escopo inicial.")
        parents = _parents(member)
        start, end = _xyz(member.StartPoint), _xyz(member.EndPoint)
        length = math.dist(start, end)
        if length <= LENGTH_TOLERANCE or not math.isfinite(length):
            raise ValueError("Eixo nominal nulo ou inválido.")
        vector_type = type(member.StartPoint)
        placement = member.getGlobalPlacement()
        frame = _frame(placement, vector_type)
        local_frame = _frame(member.Placement, vector_type)
        direction = tuple((b-a)/length for a, b in zip(start, end))
        if not _close(local_frame[2], direction, FRAME_TOLERANCE):
            raise ValueError("Placement diverge do eixo nominal.")
        parent = placement.multiply(member.Placement.inverse())
        _frame(parent, vector_type)
        category = "member"
        if getattr(member, "GenerationOwner", None) is not None:
            _validate_generated(member, parent, local_frame, vector_type, context)
            category = "generated_member"
        return AxisResolution(AxisReference(
            str(member.Name), _xyz(parent.multVec(member.StartPoint)),
            _xyz(parent.multVec(member.EndPoint)), frame,
            tuple(str(obj.Name) for obj in parents), category))
    except _READ_ERRORS as exc:
        return AxisResolution(None, str(exc) or "Referência indisponível.")


__all__ = ["AxisReference", "AxisResolution", "AxisReadContext",
           "axis_state_signature", "resolve_member_axis"]

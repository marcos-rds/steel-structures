"""Read-only quantities of the final fabricated pieces, never a fused envelope."""
from dataclasses import dataclass
import math

from .serialization import decode_state


STEEL_DENSITY_KG_M3 = 7850.


@dataclass(frozen=True)
class PhysicalPiece:
    name: str
    kind: str
    volume_mm3: float


@dataclass(frozen=True)
class PhysicalMass:
    pieces: tuple = ()
    diagnostics: tuple = ()
    support_distance_mm: float | None = None
    nominal_span_mm: float | None = None
    density_kg_m3: float = STEEL_DENSITY_KG_M3

    @property
    def available(self):
        return bool(self.pieces) and not self.diagnostics and self.support_distance_mm is not None

    @property
    def volume_mm3(self):
        return math.fsum(piece.volume_mm3 for piece in self.pieces) if self.available else None

    @property
    def mass_kg(self):
        return self.volume_mm3 * self.density_kg_m3 * 1e-9 if self.available else None

    @property
    def linear_mass_kg_m(self):
        return self.mass_kg / (self.support_distance_mm * .001) if self.available else None


def _solid_only(shape):
    if shape.ShapeType == "Solid":
        return True
    if shape.ShapeType not in ("Compound", "CompSolid"):
        return False
    children = shape.childShapes()
    return bool(children) and all(_solid_only(child) for child in children)


def read_physical_mass(owner, density_kg_m3=STEEL_DENSITY_KG_M3):
    """Inspect registries, ownership, applied bindings and final solids without writes.

    Missing Gussets requested in the applied definition are conservatively treated
    as incomplete coverage: older NominalFallback plates may never materialize.
    No resolver or geometry builder is called to infer their intended shape.
    """
    pieces, diagnostics = [], []
    distance = nominal = None
    try:
        if not math.isfinite(density_kg_m3) or density_kg_m3 <= 0:
            raise ValueError("Densidade inválida.")
        document = owner.Document
        if document.getObject(owner.Name) is not owner:
            raise ValueError("Treliça ausente do documento.")
        if (owner.NeedsRegeneration or owner.GenerationState != "Valid"
                or {"Invalid", "Touched", "Recompute"}.intersection(owner.State)):
            raise ValueError("Geometria física pendente ou inválida; aplique a configuração.")
        state = decode_state(owner.AppliedState)
        config = state["candidate"]["config"]
        start, end = config["start"], config["end"]
        if len(start) != 3 or len(end) != 3:
            raise ValueError("Apoios inválidos no estado aplicado.")
        distance = math.dist(start, end)
        nominal = float(config.get("nominal_span", config["span"]))
        if not math.isfinite(distance) or distance <= 0 or not math.isfinite(nominal) or nominal <= 0:
            raise ValueError("Distância entre apoios inválida.")
        items = state["candidate"]["items"]
        keys = [item["key"] for item in items]
        bindings = state["bindings"]
        if not keys or len(set(keys)) != len(keys) or set(keys) != set(bindings):
            raise ValueError("Peças aplicadas e bindings discordam.")
        members = list(owner.GeneratedMembers)
        plates = list(getattr(owner, "GeneratedGussetPlates", ()))
        for child in members + plates:
            if document.getObject(child.Name) is not child:
                raise ValueError("Registro aponta para peça ausente ou de outro documento: " + child.Name)
        member_names = {child.Name for child in members}
        plate_names = {child.Name for child in plates}
        if member_names != set(bindings.values()) or len(set(bindings.values())) != len(bindings):
            raise ValueError("Registro de membros incompleto ou bindings repetidos.")
        for key, name in bindings.items():
            child = document.getObject(name)
            if (child is None or child not in members or child.GenerationOwner != owner
                    or child.GenerationKey != key):
                raise ValueError("Ownership/binding inconsistente: " + name)
        for child in document.Objects:
            if getattr(child, "GenerationOwner", None) == owner and child.Name not in member_names:
                diagnostics.append("Membro físico fora do registro: " + child.Name)
            if (getattr(child, "ParentTruss", None) == owner
                    and getattr(child, "GeneratedByTruss", False) and child.Name not in plate_names):
                diagnostics.append("Chapa Gusset fora do registro: " + child.Name)
        node_keys = set()
        node_names = {}
        for plate in plates:
            node = getattr(plate, "NodeKey", "")
            if (plate.ParentTruss != owner or not plate.GeneratedByTruss or not node
                    or plate.StableKey != node + ":gusset-plate"):
                raise ValueError("Ownership/binding de Gusset inconsistente: " + plate.Name)
            if node in node_names and node_names[node] != plate.Name:
                raise ValueError("Mais de uma peça Gusset para o mesmo nó: " + node)
            node_names[node] = plate.Name
            node_keys.add(node)
        intended = {value.get("node_key", key) for key, value in config.get("connection_intents", {}).items()
                    if value.get("form") == "Gusset"}
        if intended - node_keys:
            diagnostics.append("Gusset solicitado sem peça física contabilizável (inclusive fallback nominal): "
                               + ", ".join(sorted(intended - node_keys)))
        if node_keys - intended:
            diagnostics.append("Chapa Gusset sem intenção correspondente no estado aplicado.")
        seen = set()
        for child, kind in [(child, "Member") for child in members] + [(plate, "Gusset") for plate in plates]:
            name = child.Name
            if name in seen:
                continue  # Multiple references never multiply a fabricated piece.
            seen.add(name)
            try:
                if document.getObject(name) is not child:
                    raise ValueError("objeto ausente ou de outro documento")
                if (child.GenerationStatus != "Valid"
                        or {"Invalid", "Touched", "Recompute"}.intersection(child.State)):
                    raise ValueError("peça pendente ou inválida")
                shape = child.Shape
                if shape.isNull() or not shape.isValid() or not _solid_only(shape):
                    raise ValueError("Shape sem conjunto válido exclusivamente de sólidos")
                volume = float(shape.Volume)
                solid_volumes = [float(solid.Volume) for solid in shape.Solids]
                if not solid_volumes or any(not math.isfinite(value) or value <= 0 for value in solid_volumes):
                    raise ValueError("sólido com volume inválido")
                solids_volume = math.fsum(solid_volumes)
                if (not math.isfinite(volume) or volume <= 0 or not math.isfinite(solids_volume)
                        or abs(volume - solids_volume) > max(1e-5, volume * 1e-9)):
                    raise ValueError("volume inconsistente")
                pieces.append(PhysicalPiece(name, kind, volume))
            except (AttributeError, ValueError, TypeError, RuntimeError, ReferenceError) as exc:
                diagnostics.append(name + ": " + str(exc))
    except (AttributeError, KeyError, ValueError, TypeError, RuntimeError, ReferenceError) as exc:
        diagnostics.append(str(exc))
    return PhysicalMass(tuple(pieces), tuple(dict.fromkeys(diagnostics)), distance, nominal, density_kg_m3)

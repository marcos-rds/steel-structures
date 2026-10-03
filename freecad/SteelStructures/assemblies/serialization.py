"""Versioned JSON contract, separate from truss C1/C2 persistence."""
from dataclasses import asdict
import json
from ..profiles.models import ProfileRef
from .models import MemberAssemblySpec, AssemblyComponentSpec
from .transforms import SectionTransform
from .interconnectors import InterconnectorSpec
from .distribution import DistributionSpec

SCHEMA_VERSION = 1


def dumps(spec):
    return json.dumps(dict(schema_version=SCHEMA_VERSION, spec=asdict(spec)),
                      ensure_ascii=False, sort_keys=True, allow_nan=False)


def loads(value):
    payload = json.loads(value)
    if set(payload) != {"schema_version", "spec"} or type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Schema de assembly não suportado.")
    data = dict(payload["spec"])
    components = []
    for raw in data.pop("components"):
        raw = dict(raw)
        raw["profile_ref"] = ProfileRef(**raw["profile_ref"])
        raw["section_transform"] = SectionTransform(**raw["section_transform"])
        components.append(AssemblyComponentSpec(**raw))
    interconnectors = []
    for raw in data.pop("interconnectors", ()):
        raw = dict(raw)
        raw["profile_ref"] = ProfileRef(**raw["profile_ref"])
        raw["section_transform"] = SectionTransform(**raw.get("section_transform", {}))
        raw["distribution"] = DistributionSpec(**raw.get("distribution", {}))
        interconnectors.append(InterconnectorSpec(**raw))
    return MemberAssemblySpec(components=tuple(components), interconnectors=tuple(interconnectors), **data)

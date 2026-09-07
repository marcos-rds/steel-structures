"""Strict deterministic JSON; unknown schema versions are never silently rewritten."""
from dataclasses import asdict, is_dataclass
import json
from .models import SCHEMA_VERSION, GENERATOR_VERSION


def dumps(value):
    return json.dumps(asdict(value) if is_dataclass(value) else value, ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"), allow_nan=False)


def loads(text):
    return json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def encode_state(candidate, bindings=None):
    return dumps({"schema_version": SCHEMA_VERSION, "generator_version": GENERATOR_VERSION,
                  "candidate": asdict(candidate), "bindings": bindings or {}})


def decode_state(text):
    result = loads(text)
    if (type(result.get("schema_version")) is not int or type(result.get("generator_version")) is not int
            or result["schema_version"] not in (1, SCHEMA_VERSION) or result["generator_version"] != GENERATOR_VERSION):
        raise ValueError("Versão de treliça não suportada; definição aplicada preservada.")
    return result

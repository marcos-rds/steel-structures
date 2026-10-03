"""Shared immutable regeneration protocol for logical owners and assemblies."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RegenerationAction:
    key: str | tuple
    action: str
    existing_binding: str = ""
    reason: str = ""


@dataclass(frozen=True)
class RegenerationPlan:
    actions: tuple
    structural: bool

    @property
    def conflicts(self):
        return tuple(a for a in self.actions if a.action == "CONFLICT")

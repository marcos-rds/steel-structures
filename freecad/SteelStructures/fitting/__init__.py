"""Pure contracts and resolution for physical member end fitting."""

from .models import (
    FIT_PLAN_SCHEMA_VERSION,
    FitAction,
    FitActionMode,
    FitDiagnostic,
    FitEnd,
    FitSource,
    FittingPolicy,
    GeometryReference,
    NominalMember,
    PhysicalFitMode,
    PhysicalFitPlan,
)
from .resolver import resolve_physical_fit
from .serialization import dumps, loads
from .validation import validate_plan

__all__ = [
    "FIT_PLAN_SCHEMA_VERSION", "FitAction", "FitActionMode", "FitDiagnostic",
    "FitEnd", "FitSource", "FittingPolicy", "GeometryReference", "NominalMember",
    "PhysicalFitMode", "PhysicalFitPlan", "resolve_physical_fit", "validate_plan",
    "dumps", "loads",
]

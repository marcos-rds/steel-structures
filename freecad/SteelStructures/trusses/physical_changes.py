"""Compare realized physical definitions without generating geometry or quantities."""
from dataclasses import asdict, is_dataclass
import math

from .connections import intent_from_data
from .models import MemberSpec, RealizationItem
from .realization import equivalent


def _physical_data(value):
    if isinstance(value,dict):
        return {key:_physical_data(child) for key,child in value.items()
                if key not in ("color","element_label","diagnostics")}
    if isinstance(value,(tuple,list)):
        return [_physical_data(child) for child in value]
    return value


def physical_definition(candidate):
    """Use existing realized items/plans and canonical active Gusset parameters.

    Dataclass defaults also normalize supported older serialized items. Inactive
    panelization inputs, names, colors and connection fastening intent cannot
    make an unchanged physical result stale.
    """
    data=asdict(candidate) if is_dataclass(candidate) else candidate
    items=[]
    for raw in data["items"]:
        item=dict(raw)
        item["spec"]=MemberSpec(**item["spec"])
        physical=asdict(RealizationItem(**item))
        # The physical key already identifies each distinct A/B/connector piece.
        # Later organizational metadata must not stale a supported old record.
        for key in ("run_key","assembly_key","component_key","generated_element_key"):
            physical.pop(key,None)
        plan=physical.get("physical_fit_plan")
        if plan and not any(plan.get(key) for key in ("start_action","end_action","additional_actions")):
            physical["physical_fit_plan"]=None
        items.append(_physical_data(physical))
    config=data["config"]
    plates={}
    for key,value in config.get("connection_intents",{}).items():
        intent=intent_from_data(key,value)
        if intent.form=="Gusset":
            plates[key]=dict(spec=asdict(intent.gusset),participants=intent.participant_run_keys)
    return dict(items=sorted(items,key=lambda value:value["key"]),plates=plates,
                support_distance=math.dist(config["start"],config["end"]),
                nominal_span=config.get("nominal_span",config["span"]))


def same_physical_definition(current, applied):
    return equivalent(physical_definition(current),physical_definition(applied))


def materialization_pending(owner):
    """Separate a pending materialization from a broken final physical result."""
    objects=[owner]+list(owner.GeneratedMembers)+list(getattr(owner,"GeneratedGussetPlates",()))
    if owner.GenerationState not in ("Valid","Pending") or any("Invalid" in obj.State for obj in objects):
        return False
    statuses=[getattr(obj,"GenerationStatus","Valid") for obj in objects]
    if any(value!="Valid" and not value.startswith("Pending") for value in statuses):
        return False
    return (owner.GenerationState=="Pending" or owner.NeedsRegeneration
            or any({"Touched","Recompute"}.intersection(obj.State) for obj in objects)
            or any(value.startswith("Pending") for value in statuses))

# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI-independent controller for native Draft member creation sessions."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum, auto
from typing import Callable

from FreeCAD import Gui

from ..member import create_member
from ..member_axis_source import resolve_axis_source


class ControllerState(Enum):
    INACTIVE = auto()
    READY_NUMERIC = auto()
    CREATING = auto()
    STOPPING = auto()


class CreationGeometryMode(Enum):
    INTERACTIVE = auto()
    SOURCE_AXIS = auto()


@dataclass(frozen=True)
class MemberCreationOptions:
    start: object
    end: object
    designation: str
    element_type: str
    insertion: str
    rotation: float
    color: tuple[float, float, float]
    display_name: str
    axis_source: object = None
    link_axis: bool = False
    geometry_mode: CreationGeometryMode = CreationGeometryMode.INTERACTIVE
    section_geometry_mode: str = "Detailed"


@dataclass(frozen=True)
class CreationResult:
    member: object
    next_default_name: str


def compact_profile_designation(designation: str):
    """Return a catalog designation without spaces for display purposes."""
    return "".join(designation.split())


def next_default_label(document, element_type: str, designation: str):
    """Return the next independent sequence label for an element type."""
    pattern = re.compile(rf"^{re.escape(element_type)}\s+(\d+)\b", re.IGNORECASE)
    highest = 0
    for obj in document.Objects:
        candidates = [str(getattr(obj, "Label", ""))]
        if "DisplayName" in getattr(obj, "PropertiesList", []):
            candidates.append(str(obj.DisplayName))
        for candidate in candidates:
            match = pattern.match(candidate.strip())
            if match:
                highest = max(highest, int(match.group(1)))
    return (
        f"{element_type} {highest + 1:03d} - "
        f"{compact_profile_designation(designation)}"
    )


class MemberController:
    """Own transactions and selection for one native Draft tool session."""

    def __init__(self, document, member_factory: Callable = create_member, selection=None):
        self.document = document
        self._member_factory = member_factory
        self._selection = selection if selection is not None else Gui.Selection
        self.state = ControllerState.INACTIVE

    def start(self):
        if self.state is ControllerState.INACTIVE:
            self.state = ControllerState.READY_NUMERIC

    @staticmethod
    def validate_points(start, end):
        if start.sub(end).Length <= 1e-7:
            raise ValueError("Os pontos inicial e final devem ser diferentes.")

    def create(self, options: MemberCreationOptions):
        if self.state is not ControllerState.READY_NUMERIC:
            raise RuntimeError("A sessão de criação não está ativa.")
        if self.document is None:
            raise RuntimeError("A sessão de criação não está ativa.")
        if options.geometry_mode is CreationGeometryMode.SOURCE_AXIS:
            source_geometry = resolve_axis_source(options.axis_source)
            if source_geometry is None:
                raise ValueError("A linha de origem está inválida.")
            options = replace(
                options, start=source_geometry.start, end=source_geometry.end
            )
        self.validate_points(options.start, options.end)
        if not options.designation.strip():
            raise ValueError("Selecione um perfil cadastrado.")

        previous_state = self.state
        self.state = ControllerState.CREATING
        self.document.openTransaction("Criar elemento estrutural")
        source = options.axis_source[0] if options.axis_source else None
        previous_visibility = None
        try:
            member = self._member_factory(
                document=self.document,
                start=options.start,
                end=options.end,
                designation=options.designation,
                element_type=options.element_type,
                insertion=options.insertion,
                rotation=options.rotation,
                color=options.color,
                display_name=options.display_name,
                axis_source=options.axis_source,
                link_axis=options.link_axis,
                section_geometry_mode=options.section_geometry_mode,
            )
            if source is not None:
                previous_visibility = bool(source.ViewObject.Visibility)
                source.ViewObject.Visibility = False
            self.document.commitTransaction()
        except Exception:
            self.document.abortTransaction()
            if previous_visibility is not None and source is not None:
                try:
                    source.ViewObject.Visibility = previous_visibility
                except (AttributeError, ReferenceError, RuntimeError):
                    pass
            self.state = previous_state
            raise

        self.state = ControllerState.READY_NUMERIC
        if self._selection is not None:
            try:
                self._selection.clearSelection()
                self._selection.addSelection(member)
            except Exception:
                pass
        return CreationResult(
            member=member,
            next_default_name=next_default_label(
                self.document, options.element_type, options.designation
            ),
        )

    def stop(self):
        if self.state is ControllerState.INACTIVE:
            return
        self.state = ControllerState.STOPPING
        self.document = None
        self._selection = None
        self.state = ControllerState.INACTIVE

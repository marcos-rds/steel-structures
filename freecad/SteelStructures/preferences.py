# SPDX-License-Identifier: LGPL-2.1-or-later
"""Persistent user preferences for structural creation tools."""

from __future__ import annotations

import math
from dataclasses import dataclass

import FreeCAD as App

from . import profile_catalog
from .member import INSERTION_OPTIONS


PREFERENCES_ROOT = "User parameter:BaseApp/Preferences/Mod/SteelStructures"
MEMBER_PREFERENCES = f"{PREFERENCES_ROOT}/CreateMember"
COLUMN_PREFERENCES = f"{PREFERENCES_ROOT}/CreateColumn"
GRID_PREFERENCES = f"{PREFERENCES_ROOT}/CreateGrid"
DEFAULT_COLOR = (184.0 / 255.0, 184.0 / 255.0, 194.0 / 255.0)
DEFAULT_GRID_LINE_COLOR = (127.0 / 255.0,) * 3
DEFAULT_GRID_INTERSECTION_COLOR = (0.0, 170.0 / 255.0, 1.0)
DEFAULT_GRID_TEXT_COLOR = (242.0 / 255.0,) * 3
DEFAULT_ROTATION = 0.0
DEFAULT_COLUMN_HEIGHT = 3000.0
DEFAULT_CONTINUE = True
MEMBER_ELEMENT_TYPES = ("Membro", "Viga", "Contraventamento")
ROTATION_MIN = -3600.0
ROTATION_MAX = 3600.0
HEIGHT_MAX = 1000000.0

_INSERTION_KEYS = {
    "Centroide": "center",
    "Face esquerda": "left",
    "Face direita": "right",
    "Face superior": "top",
    "Face inferior": "bottom",
    "Canto superior esquerdo": "top_left",
    "Canto superior direito": "top_right",
    "Canto inferior esquerdo": "bottom_left",
    "Canto inferior direito": "bottom_right",
    "Quina externa": "outer_corner",
    "Ponta superior": "top_tip",
    "Ponta direita": "right_tip",
    "Quina interna": "inner_corner",
    "Centro da alma": "web_center",
    "Face externa da alma": "web_back",
    "Canto superior traseiro": "rear_top",
    "Canto inferior traseiro": "rear_bottom",
    "Ponta superior da mesa": "flange_top_tip",
    "Ponta inferior da mesa": "flange_bottom_tip",
    "Canto externo superior": "outer_top_corner",
    "Canto externo inferior": "outer_bottom_corner",
    "Ponta do enrijecedor superior": "lip_top_tip",
    "Ponta do enrijecedor inferior": "lip_bottom_tip",
    "Centro externo superior": "outer_top_mid",
    "Centro externo inferior": "outer_bottom_mid",
    "Canto externo do enrijecedor superior": "outer_lip_top_corner",
    "Canto externo do enrijecedor inferior": "outer_lip_bottom_corner",
}
_INSERTIONS_BY_KEY = {key: label for label, key in _INSERTION_KEYS.items()}


@dataclass(frozen=True)
class MemberCreationSettings:
    category: str
    series: str
    designation: str
    insertion: str
    rotation: float
    color: tuple[float, float, float]
    element_type: str


@dataclass(frozen=True)
class ColumnCreationSettings:
    category: str
    series: str
    designation: str
    insertion: str
    rotation: float
    color: tuple[float, float, float]
    height: float
    continue_creating: bool


@dataclass(frozen=True)
class GridAppearanceSettings:
    line_color: tuple[float, float, float]
    line_width: float
    show_intersections: bool
    intersection_color: tuple[float, float, float]
    intersection_size: float
    show_labels: bool
    label_position: str
    label_offset: float
    font_name: str
    font_size: float
    text_color: tuple[float, float, float]


def _default_profile():
    for category in profile_catalog.categories():
        for series in profile_catalog.series_for_category(category):
            designations = profile_catalog.designations(category, series)
            if designations:
                return profile_catalog.get(designations[0])
    raise RuntimeError("Nenhum perfil válido foi encontrado no catálogo.")


def _valid_profile(category, series, designation):
    try:
        profile = profile_catalog.get(str(designation))
    except (KeyError, TypeError, ValueError):
        return _default_profile()
    if profile.category != str(category) or profile.series != str(series):
        return _default_profile()
    return profile


def _profile_insertion_options(profile):
    resolver = getattr(profile_catalog, "insertion_options", None)
    return tuple(resolver(profile)) if resolver is not None else tuple(INSERTION_OPTIONS)


def _finite_in_range(value, default, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) and minimum <= number <= maximum else default


def _color(group):
    values = tuple(group.GetFloat(key, default) for key, default in zip(
        ("ColorRed", "ColorGreen", "ColorBlue"), DEFAULT_COLOR
    ))
    if all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values):
        return values
    return DEFAULT_COLOR


def _named_color(group, prefix, default):
    values = tuple(group.GetFloat(prefix + suffix, fallback) for suffix, fallback in zip(
        ("Red", "Green", "Blue"), default
    ))
    if all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values):
        return values
    return default


def default_grid_appearance(font_name=""):
    return GridAppearanceSettings(
        DEFAULT_GRID_LINE_COLOR, 1.0, True, DEFAULT_GRID_INTERSECTION_COLOR,
        5.0, True, "Both", 250.0, str(font_name), 14.0,
        DEFAULT_GRID_TEXT_COLOR,
    )


def _shared_settings(group):
    default = _default_profile()
    profile = _valid_profile(
        group.GetString("Category", default.category),
        group.GetString("Series", default.series),
        group.GetString("Designation", default.designation),
    )
    insertion = _INSERTIONS_BY_KEY.get(group.GetString("Insertion", "center"), "Centroide")
    valid_insertions = _profile_insertion_options(profile) or tuple(INSERTION_OPTIONS)
    if insertion not in valid_insertions:
        insertion = valid_insertions[0]
    rotation = _finite_in_range(
        group.GetFloat("RotationAngle", DEFAULT_ROTATION), DEFAULT_ROTATION,
        ROTATION_MIN, ROTATION_MAX,
    )
    return profile, insertion, rotation, _color(group)


def load_member_creation_settings():
    try:
        group = App.ParamGet(MEMBER_PREFERENCES)
        profile, insertion, rotation, color = _shared_settings(group)
        element_type = group.GetString("ElementType", "Membro")
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
        profile = _default_profile()
        insertion, rotation, color, element_type = (
            "Centroide", DEFAULT_ROTATION, DEFAULT_COLOR, "Membro"
        )
    if element_type not in MEMBER_ELEMENT_TYPES:
        element_type = "Membro"
    return MemberCreationSettings(
        profile.category, profile.series, profile.designation, insertion,
        rotation, color, element_type,
    )


def load_column_creation_settings():
    try:
        group = App.ParamGet(COLUMN_PREFERENCES)
        profile, insertion, rotation, color = _shared_settings(group)
        height = _finite_in_range(
            group.GetFloat("Height", DEFAULT_COLUMN_HEIGHT), DEFAULT_COLUMN_HEIGHT,
            0.01, HEIGHT_MAX,
        )
        continue_creating = bool(group.GetBool("ContinueCreating", DEFAULT_CONTINUE))
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
        profile = _default_profile()
        insertion, rotation, color = "Centroide", DEFAULT_ROTATION, DEFAULT_COLOR
        height, continue_creating = DEFAULT_COLUMN_HEIGHT, DEFAULT_CONTINUE
    return ColumnCreationSettings(
        profile.category, profile.series, profile.designation, insertion,
        rotation, color, height, continue_creating,
    )


def load_grid_appearance_settings():
    default = default_grid_appearance()
    try:
        group = App.ParamGet(GRID_PREFERENCES)
        position = group.GetString("LabelPosition", default.label_position)
        if position not in ("Start", "End", "Both"):
            position = default.label_position
        return GridAppearanceSettings(
            _named_color(group, "LineColor", default.line_color),
            _finite_in_range(group.GetFloat("LineWidth", default.line_width),
                             default.line_width, 1.0, 20.0),
            bool(group.GetBool("ShowIntersections", default.show_intersections)),
            _named_color(group, "IntersectionPointColor", default.intersection_color),
            _finite_in_range(group.GetFloat("IntersectionPointSize", default.intersection_size),
                             default.intersection_size, 1.0, 30.0),
            bool(group.GetBool("ShowLabels", default.show_labels)),
            position,
            _finite_in_range(group.GetFloat("LabelOffset", default.label_offset),
                             default.label_offset, 0.0, 1.0e9),
            group.GetString("FontName", default.font_name),
            _finite_in_range(group.GetFloat("FontSize", default.font_size),
                             default.font_size, 1.0, 200.0),
            _named_color(group, "TextColor", default.text_color),
        )
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
        return default


def _save_shared(group, settings):
    profile = _valid_profile(settings.category, settings.series, settings.designation)
    valid_insertions = _profile_insertion_options(profile) or tuple(INSERTION_OPTIONS)
    insertion = settings.insertion if settings.insertion in valid_insertions else valid_insertions[0]
    rotation = _finite_in_range(
        settings.rotation, DEFAULT_ROTATION, ROTATION_MIN, ROTATION_MAX
    )
    color = settings.color
    if (len(color) != 3 or not all(
            math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0
            for value in color)):
        color = DEFAULT_COLOR
    group.SetString("Category", profile.category)
    group.SetString("Series", profile.series)
    group.SetString("Designation", profile.designation)
    group.SetString("Insertion", _INSERTION_KEYS[insertion])
    group.SetFloat("RotationAngle", rotation)
    for key, value in zip(("ColorRed", "ColorGreen", "ColorBlue"), color):
        group.SetFloat(key, float(value))


def save_member_creation_settings(settings):
    try:
        group = App.ParamGet(MEMBER_PREFERENCES)
        _save_shared(group, settings)
        element_type = settings.element_type if settings.element_type in MEMBER_ELEMENT_TYPES else "Membro"
        group.SetString("ElementType", element_type)
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
        return False
    return True


def save_column_creation_settings(settings):
    try:
        group = App.ParamGet(COLUMN_PREFERENCES)
        _save_shared(group, settings)
        height = _finite_in_range(
            settings.height, DEFAULT_COLUMN_HEIGHT, 0.01, HEIGHT_MAX
        )
        group.SetFloat("Height", height)
        group.SetBool("ContinueCreating", bool(settings.continue_creating))
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
        return False
    return True


def save_grid_appearance_settings(settings):
    try:
        group = App.ParamGet(GRID_PREFERENCES)
        defaults = default_grid_appearance()
        colors = (
            ("LineColor", settings.line_color, defaults.line_color),
            ("IntersectionPointColor", settings.intersection_color,
             defaults.intersection_color),
            ("TextColor", settings.text_color, defaults.text_color),
        )
        for prefix, color, fallback in colors:
            if (len(color) != 3 or not all(
                    math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0
                    for value in color)):
                color = fallback
            for suffix, value in zip(("Red", "Green", "Blue"), color):
                group.SetFloat(prefix + suffix, float(value))
        group.SetFloat("LineWidth", _finite_in_range(
            settings.line_width, defaults.line_width, 1.0, 20.0))
        group.SetBool("ShowIntersections", bool(settings.show_intersections))
        group.SetFloat("IntersectionPointSize", _finite_in_range(
            settings.intersection_size, defaults.intersection_size, 1.0, 30.0))
        group.SetBool("ShowLabels", bool(settings.show_labels))
        position = settings.label_position
        group.SetString("LabelPosition", position if position in ("Start", "End", "Both")
                        else defaults.label_position)
        group.SetFloat("LabelOffset", _finite_in_range(
            settings.label_offset, defaults.label_offset, 0.0, 1.0e9))
        group.SetString("FontName", str(settings.font_name))
        group.SetFloat("FontSize", _finite_in_range(
            settings.font_size, defaults.font_size, 1.0, 200.0))
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
        return False
    return True


__all__ = [
    "COLUMN_PREFERENCES", "GRID_PREFERENCES", "MEMBER_PREFERENCES", "PREFERENCES_ROOT",
    "ColumnCreationSettings", "GridAppearanceSettings", "MemberCreationSettings",
    "default_grid_appearance", "load_column_creation_settings",
    "load_grid_appearance_settings", "load_member_creation_settings",
    "save_column_creation_settings", "save_grid_appearance_settings",
    "save_member_creation_settings",
]

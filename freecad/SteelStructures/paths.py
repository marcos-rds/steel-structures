# SPDX-License-Identifier: LGPL-2.1-or-later
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ADDON_ROOT = PACKAGE_DIR.parents[1]
RESOURCES_DIR = ADDON_ROOT / "Resources"
ICONS_DIR = RESOURCES_DIR / "Icons"
CATALOGS_DIR = PACKAGE_DIR / "catalogs"

WORKBENCH_ICON = str(ICONS_DIR / "SteelStructures.svg")
MEMBER_ICON = str(ICONS_DIR / "CreateMember.svg")
COLUMN_ICON = str(ICONS_DIR / "CreateColumn.svg")
OBJECT_ICON = str(ICONS_DIR / "StructuralMember.svg")
GRID_COMMAND_ICON = str(ICONS_DIR / "CreateGrid.svg")
GRID_OBJECT_ICON = str(ICONS_DIR / "StructuralGrid.svg")
ADJUST_MEMBER_ICON = str(ICONS_DIR / "AdjustMember.svg")
GRID_SPACING_ADD_ICON = str(ICONS_DIR / "GridSpacingAdd.svg")
GRID_SPACING_DUPLICATE_ICON = str(ICONS_DIR / "GridSpacingDuplicate.svg")
GRID_SPACING_REMOVE_ICON = str(ICONS_DIR / "GridSpacingRemove.svg")
GRID_RESET_DEFAULTS_ICON = str(ICONS_DIR / "GridResetDefaults.svg")

TRUSS_ICON = str(ICONS_DIR / "CreateTruss.svg")

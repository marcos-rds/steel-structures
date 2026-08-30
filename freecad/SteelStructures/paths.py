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

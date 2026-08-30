# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI commands for Steel Structures."""

from __future__ import annotations

import traceback

import FreeCAD as App
from FreeCAD import Gui
from PySide import QtWidgets

from .paths import ADJUST_MEMBER_ICON, COLUMN_ICON, GRID_COMMAND_ICON, MEMBER_ICON


_active_member_tool = None
_active_grid_panel = None
_active_adjustment_panel = None
_move_copy_registered = False


class DraftInterfaceUnavailable(RuntimeError):
    """The installed Draft infrastructure cannot provide the native tool."""


class NativeMoveCopyCommand:
    """Start Draft Move with its documented copy mode enabled."""

    def GetResources(self):
        return {
            "Pixmap": "BIM_Copy",
            "MenuText": "Mover copiando",
            "ToolTip": "Inicia a ferramenta Mover nativa do Draft no modo Copiar.",
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        import DraftTools

        tool = DraftTools.Move()
        tool.copymode = True
        tool.Activated()


class ProfileBrowserCommand:
    """Open the read-only catalog browser without requiring a document."""

    def GetResources(self):
        return {
            "MenuText": "Catálogo de Perfis",
            "ToolTip": "Explorar perfis estruturais e propriedades do catálogo",
        }

    def IsActive(self):
        return True

    def Activated(self):
        from .interactive.profile_browser import browse_profiles

        browse_profiles(Gui.getMainWindow())


def register_move_copy_command():
    """Register the thin adapter only when this Draft exposes copy mode."""
    global _move_copy_registered
    try:
        if "SteelStructures_MoveCopy" in set(Gui.listCommands()):
            _move_copy_registered = True
            return True
        import DraftTools
        probe = DraftTools.Move()
        if not hasattr(probe, "copymode"):
            return False
        Gui.addCommand("SteelStructures_MoveCopy", NativeMoveCopyCommand())
        _move_copy_registered = True
        return True
    except (ImportError, AttributeError, RuntimeError, TypeError):
        return False


def _get_active_task_dialog():
    """Return a real active task dialog, normalizing False and API failures."""
    try:
        dialog = Gui.Control.activeDialog()
    except Exception:
        return None
    if dialog is None or dialog is False:
        return None
    return dialog


def _member_session_is_active():
    tool = _active_member_tool
    if tool is None:
        return False
    checker = getattr(tool, "is_active", None)
    return bool(
        callable(checker)
        and checker()
        and getattr(App, "activeDraftCommand", None) is tool
    )


def _discard_stale_member_session():
    global _active_member_tool

    tool = _active_member_tool
    if tool is None:
        return
    checker = getattr(tool, "is_active", None)
    if not callable(checker) or not checker() or getattr(App, "activeDraftCommand", None) is not tool:
        _active_member_tool = None


def _load_native_draft_tool(column=False):
    """Load the required native Draft interface."""
    try:
        import DraftTools  # noqa: F401 - official Draft GUI initialization
        import DraftGui  # noqa: F401 - owns the process-wide DraftToolBar
        if column:
            from .interactive.draft_column_tool import (
                StructuralColumnDraftTool as tool_class,
                draft_native_available,
            )
        else:
            from .interactive.draft_member_tool import (
                StructuralMemberDraftTool as tool_class,
                draft_native_available,
            )
    except (ImportError, AttributeError) as exc:
        raise DraftInterfaceUnavailable(str(exc)) from exc
    try:
        available = tool_class is not None and draft_native_available()
    except Exception as exc:
        raise DraftInterfaceUnavailable(str(exc)) from exc
    if not available:
        raise DraftInterfaceUnavailable("Draft UI unavailable")
    return tool_class


def _start_native_member_tool(tool_class, document, icon=MEMBER_ICON, task_title="Criar elemento estrutural"):
    """Start one native session with Draft's process-wide toolbar."""
    global _active_member_tool
    if getattr(App, "activeDraftCommand", None) is not None:
        raise RuntimeError("A Draft command is already active")
    import DraftTools  # noqa: F401 - official Draft initialization
    import DraftGui  # noqa: F401 - creates draftToolBar only when absent
    if not hasattr(Gui, "draftToolBar"):
        raise DraftInterfaceUnavailable("DraftToolBar was not initialized by Draft")
    Gui.Control.clearTaskWatcher()
    tool = tool_class(on_closed=_member_draft_tool_closed)
    _active_member_tool = tool
    try:
        tool.Activated(icon=icon, task_title=task_title)
    except Exception:
        try:
            tool.abort_activation(skip_native_ui_cleanup=True)
        finally:
            if _active_member_tool is tool:
                _active_member_tool = None
        raise
    return tool


class CreateMemberCommand:
    def GetResources(self):
        return {
            "Pixmap": MEMBER_ICON,
            "MenuText": "Criar elemento estrutural",
            "ToolTip": "Cria um elemento estrutural paramétrico entre dois pontos.",
            "Accel": "S, M",
        }

    def IsActive(self):
        return True

    def Activated(self):
        global _active_member_tool

        _discard_stale_member_session()

        if _member_session_is_active():
            App.Console.PrintWarning(
                "Steel Structures: A ferramenta Criar elemento estrutural já está ativa.\n"
            )
            return

        active_dialog = _get_active_task_dialog()
        if active_dialog is not None:
            message = (
                "Já existe um painel de tarefas ativo. "
                "Feche-o antes de criar outro elemento estrutural."
            )
            App.Console.PrintWarning(f"Steel Structures: {message}\n")
            QtWidgets.QMessageBox.information(
                Gui.getMainWindow(),
                "Steel Structures",
                message,
            )
            return

        document = App.ActiveDocument
        if document is None:
            document = App.newDocument("SteelStructures")

        try:
            tool_class = _load_native_draft_tool()
        except DraftInterfaceUnavailable:
            App.Console.PrintError(
                "Steel Structures: interface Draft indisponível:\n"
                + traceback.format_exc()
            )
            QtWidgets.QMessageBox.warning(
                Gui.getMainWindow(),
                "Steel Structures",
                "Não foi possível iniciar a ferramenta nativa. "
                "Consulte a Vista de relatório.",
            )
            return

        tool = None
        try:
            tool = _start_native_member_tool(tool_class, document)
        except Exception:
            failed_tool = tool or _active_member_tool
            App.Console.PrintError(
                "Steel Structures: falha inesperada ao ativar a ferramenta nativa:\n"
                + traceback.format_exc()
            )
            try:
                if failed_tool is not None:
                    failed_tool.abort_activation(skip_native_ui_cleanup=True)
            except Exception:
                App.Console.PrintError(
                    "Steel Structures: falha adicional ao limpar a ativação parcial:\n"
                    + traceback.format_exc()
                )
            finally:
                if failed_tool is not None and _active_member_tool is failed_tool:
                    _active_member_tool = None
            QtWidgets.QMessageBox.warning(
                Gui.getMainWindow(),
                "Steel Structures",
                "Não foi possível iniciar a ferramenta nativa. "
                "Consulte a Vista de relatório.",
            )


class CreateColumnCommand(CreateMemberCommand):
    """Create a normal StructuralMember from one base point and a height."""

    def GetResources(self):
        return {
            "Pixmap": COLUMN_ICON,
            "MenuText": "Criar Pilar",
            "ToolTip": "Criar pilar estrutural vertical a partir de um ponto de base",
            "Accel": "S, P",
        }

    def Activated(self):
        global _active_member_tool

        _discard_stale_member_session()
        if _member_session_is_active():
            App.Console.PrintWarning(
                "Steel Structures: já existe uma ferramenta estrutural interativa ativa.\n"
            )
            return
        active_dialog = _get_active_task_dialog()
        if active_dialog is not None:
            App.Console.PrintWarning(
                "Steel Structures: feche o painel de tarefas atual antes de criar um pilar.\n"
            )
            return
        document = App.ActiveDocument
        if document is None:
            document = App.newDocument("SteelStructures")
        try:
            tool_class = _load_native_draft_tool(column=True)
            _start_native_member_tool(
                tool_class, document, icon=COLUMN_ICON, task_title="Criar Pilar"
            )
        except DraftInterfaceUnavailable:
            App.Console.PrintError(
                "Steel Structures: interface Draft indisponível:\n" + traceback.format_exc()
            )
            QtWidgets.QMessageBox.warning(
                Gui.getMainWindow(), "Steel Structures",
                "Não foi possível iniciar Criar Pilar. Consulte a Vista de relatório.",
            )
        except Exception:
            failed_tool = _active_member_tool
            App.Console.PrintError(
                "Steel Structures: falha inesperada ao ativar Criar Pilar:\n"
                + traceback.format_exc()
            )
            try:
                if failed_tool is not None:
                    failed_tool.abort_activation(skip_native_ui_cleanup=True)
            finally:
                if failed_tool is not None and _active_member_tool is failed_tool:
                    _active_member_tool = None


class CreateGridCommand:
    """Open one transactional Structural Grid preview task panel."""

    def GetResources(self):
        return {"Pixmap": GRID_COMMAND_ICON, "MenuText": "Criar Grid",
                "ToolTip": "Cria um grid estrutural paramétrico."}

    def IsActive(self):
        return True

    def Activated(self):
        global _active_grid_panel
        if _active_grid_panel is not None and not getattr(_active_grid_panel, "_closed", False):
            App.Console.PrintWarning("Steel Structures: o painel Criar Grid já está ativo.\n")
            return
        if _get_active_task_dialog() is not None:
            App.Console.PrintWarning("Steel Structures: feche o painel de tarefas atual antes de criar um grid.\n")
            return
        document = App.ActiveDocument
        if document is None:
            document = App.newDocument("SteelStructures")
        panel = None
        grid_object = None
        try:
            from .grid import create_grid
            from .interactive.grid_task_panel import GridTaskPanel
            document.openTransaction("Criar Grid Estrutural")
            grid_object = create_grid(
                document, x_start_extension=1000.0, x_end_extension=1000.0,
                y_start_extension=1000.0, y_end_extension=1000.0,
                display_name="Grid Estrutural",
            )
            panel = GridTaskPanel(document, grid_object, _grid_panel_closed)
            _active_grid_panel = panel
            getattr(Gui.Control, "showDialog")(panel)
            try:
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(grid_object)
                Gui.activeDocument().activeView().fitAll()
            except Exception:
                pass
        except Exception:
            App.Console.PrintError("Steel Structures: falha ao iniciar Criar Grid:\n" + traceback.format_exc())
            if panel is not None:
                panel.reject()
            else:
                name = getattr(grid_object, "Name", None)
                remove = getattr(document, "removeObject", None)
                if name is not None and callable(remove):
                    try:
                        remove(name)
                    except Exception:
                        pass
                try:
                    document.abortTransaction()
                except Exception:
                    pass
                try:
                    getattr(Gui.Control, "closeDialog")()
                except Exception:
                    pass
                _active_grid_panel = None


class AdjustMemberCommand:
    """Open the non-preview task panel for one member end adjustment."""

    def GetResources(self):
        return {
            "Pixmap": ADJUST_MEMBER_ICON,
            "MenuText": "Recortar / Ajustar Membro",
            "ToolTip": "Limita ou recorta uma extremidade usando uma referência geométrica.",
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        global _active_adjustment_panel
        if (_active_adjustment_panel is not None
                and not getattr(_active_adjustment_panel, "_closed", False)):
            App.Console.PrintWarning(
                "Steel Structures: o painel Recortar / Ajustar Membro já está ativo.\n"
            )
            return
        if _get_active_task_dialog() is not None:
            App.Console.PrintWarning(
                "Steel Structures: feche o painel de tarefas atual antes de ajustar um membro.\n"
            )
            return
        document = App.ActiveDocument
        if document is None:
            return
        from .interactive.member_adjustment_controller import is_structural_member
        from .interactive.member_adjustment_task_panel import MemberAdjustmentTaskPanel
        selected = [obj for obj in Gui.Selection.getSelection() if is_structural_member(obj)]
        member = selected[0] if len(selected) == 1 and len(Gui.Selection.getSelection()) == 1 else None
        try:
            panel = MemberAdjustmentTaskPanel(document, member, _adjustment_panel_closed)
            _active_adjustment_panel = panel
            Gui.Control.showDialog(panel)
        except Exception:
            _active_adjustment_panel = None
            App.Console.PrintError(
                "Steel Structures: falha ao abrir Recortar / Ajustar Membro:\n"
                + traceback.format_exc()
            )


def _adjustment_panel_closed(panel, _accepted):
    global _active_adjustment_panel
    if _active_adjustment_panel is panel:
        _active_adjustment_panel = None
    try:
        Gui.Control.closeDialog()
    except Exception:
        pass


def close_adjustment_panel():
    global _active_adjustment_panel
    panel = _active_adjustment_panel
    if panel is None:
        return False
    try:
        panel.reject()
    finally:
        if _active_adjustment_panel is panel:
            _active_adjustment_panel = None
    return True


def _grid_panel_closed(panel, _accepted):
    global _active_grid_panel
    if _active_grid_panel is panel:
        _active_grid_panel = None
    try:
        Gui.Control.closeDialog()
    except Exception:
        pass


def close_grid_panel():
    """Cancel the preview owned by this workbench, if any."""
    global _active_grid_panel
    panel = _active_grid_panel
    if panel is None:
        return False
    try:
        panel.reject()
    finally:
        if _active_grid_panel is panel:
            _active_grid_panel = None
    return True


def _member_draft_tool_closed(tool):
    global _active_member_tool
    if _active_member_tool is tool:
        _active_member_tool = None


def close_member_tool():
    """Close only the active native tool owned by Steel Structures."""
    global _active_member_tool

    tool = _active_member_tool
    if tool is None:
        return False
    try:
        tool.finish(cont=False)
    finally:
        if _active_member_tool is tool:
            _active_member_tool = None
    return True


Gui.addCommand("SteelStructures_CreateMember", CreateMemberCommand())
Gui.addCommand("SteelStructures_CreateColumn", CreateColumnCommand())
Gui.addCommand("SteelStructures_CreateGrid", CreateGridCommand())
Gui.addCommand("SteelStructures_AdjustMember", AdjustMemberCommand())
Gui.addCommand("SteelStructures_ProfileBrowser", ProfileBrowserCommand())

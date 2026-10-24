# SPDX-License-Identifier: LGPL-2.1-or-later
"""One transient task session for a fixed, atomic two-member miter."""

import colorsys
import re

import FreeCAD as App
from FreeCAD import Gui
from PySide import QtCore, QtGui, QtWidgets

from .member_adjustment_controller import is_structural_member
from .member_adjustment_task_panel import _PanelLifecycle, _SelectionObserver, standard_buttons_value
from .member_miter_controller import MemberMiterController
from .member_miter_preview import MemberMiterPreview


_ACCEPT_STATE_EVENT = QtCore.QEvent.Type(QtCore.QEvent.registerEventType())


def _member_caption(member):
    """Local presentation only; never rename objects or change other tools."""
    label = str(member.Label or member.Name)
    profile = str(getattr(member, "Profile", ""))
    normalize = lambda value: re.sub(r"\s+", "", value.replace("″", '"').replace("×", "x")).casefold()
    if profile and normalize(label) == normalize(profile):
        return label, ""
    for separator in (" — ", " - "):
        name, found, suffix = label.rpartition(separator)
        if not found or not profile:
            continue
        same_section = normalize(suffix) == normalize(profile)
        # FreeCAD's automatic label uniquifier may replace the final digits
        # of the generated section suffix. Restrict this case to default names.
        automatic = name == str(getattr(member, "ElementType", ""))
        same_stem = re.sub(r"\d+$", "", normalize(suffix)) == re.sub(r"\d+$", "", normalize(profile))
        if same_section or (automatic and same_stem):
            return name, profile
    if profile and normalize(profile) in normalize(label):
        return label, ""
    return label, profile


class _ElidedLabel(QtWidgets.QLabel):
    """One line at any panel width, full content available on hover."""

    def __init__(self):
        super().__init__()
        self._full_text = ""
        self.setTextFormat(QtCore.Qt.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)

    def setText(self, text):
        self._full_text = text
        self.setToolTip(text)
        self._elide()

    def _elide(self):
        super().setText(self.fontMetrics().elidedText(self._full_text, QtCore.Qt.ElideRight, max(0, self.width())))

    def resizeEvent(self, event):
        self._elide()
        super().resizeEvent(event)


def _trim_option_text(end, amount, unavailable=False):
    name = "Início" if end == "Start" else "Fim"
    if unavailable:
        return name + " — indisponível"
    value = format(amount, ",.9g").translate(str.maketrans(",.", ".,"))
    return "%s (%s mm)" % (name, value)


class _TrimEndCombo(QtWidgets.QComboBox):
    opening = QtCore.Signal()

    def showPopup(self):
        # Read current axes/parameters even in the interval before the timer.
        self.opening.emit()
        super().showPopup()


def _luminance(rgb):
    channels = tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb)
    return sum(v * weight for v, weight in zip(channels, (.2126, .7152, .0722)))


def _contrast(first, second):
    values = sorted((_luminance(first), _luminance(second)))
    return (values[1] + .05) / (values[0] + .05)


def _semantic_message_rgb(foreground, background, severity):
    """Tint only the status label, adapting contrast to the themed text/background.

    Transparent QSS widgets can report a default light Window role even when
    their inherited text and actual Task View backing are dark-themed. Such an
    inconsistent pair uses a backing polarity inferred from the readable text.
    """
    if severity not in ("success", "error"):
        return None
    if _contrast(foreground, background) < 3.:
        background = (.25, .25, .25) if _luminance(foreground) > .5 else (.95, .95, .95)
    hue = .35 if severity == "success" else 0.
    light_text = _contrast((1., 1., 1.), background) >= _contrast((0., 0., 0.), background)
    endpoint = 1. if light_text else 0.
    target = min(4.7, _contrast((endpoint,) * 3, background))
    color = lambda lightness: colorsys.hls_to_rgb(hue, lightness, .72)
    lightness = .5
    if _contrast(color(lightness), background) < target:
        low, high = (.5, 1.) if light_text else (0., .5)
        for _ in range(24):
            middle = (low + high) / 2.
            enough = _contrast(color(middle), background) >= target
            if enough == light_text:
                high = middle
            else:
                low = middle
        lightness = high if light_text else low
    return tuple(round(channel * 255) for channel in color(lightness))


class _MiterPanelLifecycle(_PanelLifecycle):
    """Sync the native OK button only after the Task View has mounted the form."""

    def eventFilter(self, obj, event):
        panel = self.panel
        if panel is not None and not panel._closed:
            if event.type() == QtCore.QEvent.Show:
                # A posted event belongs to the form and is discarded if the
                # form is destroyed. No single-shot callback can outlive it.
                QtCore.QCoreApplication.postEvent(panel.form, QtCore.QEvent(_ACCEPT_STATE_EVENT))
            elif event.type() == _ACCEPT_STATE_EVENT:
                panel._set_accept_enabled(panel.isValid())
                panel._apply_message_style()
            elif event.type() in (QtCore.QEvent.PaletteChange, QtCore.QEvent.ApplicationPaletteChange,
                                  QtCore.QEvent.StyleChange):
                panel._apply_message_style()
        return super().eventFilter(obj, event)


class MemberMiterTaskPanel:
    def __init__(self, document, members=(), on_closed=None):
        self.document = document
        self._document_name = document.Name
        self.controller = MemberMiterController(document, members)
        self._on_closed = on_closed
        self._closed = False
        self._capture_mode = None
        self._selection_observer = None
        self._preview = None
        self._candidate = None
        self._watch_state = None
        self._last_error = "Selecione dois membros estruturais."
        self._refreshing = False
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("Meia-esquadria")
        root = QtWidgets.QVBoxLayout(self.form)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(10)
        def heading(text):
            label = QtWidgets.QLabel(text)
            font = label.font()
            font.setBold(True)
            label.setFont(font)
            return label
        root.addWidget(heading("Membros"))
        layout = QtWidgets.QVBoxLayout()
        layout.setSpacing(10)
        self.member_labels, self.profile_labels, self.select_member_buttons = [], [], []
        self.member_rows, self.member_markers, self.member_dividers = [], [], []
        for index, title in enumerate(("A", "B")):
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            marker = heading(title)
            marker.setAlignment(QtCore.Qt.AlignCenter)
            marker.setFixedWidth(marker.fontMetrics().horizontalAdvance("B")+4)
            divider = QtWidgets.QFrame()
            divider.setFrameShape(QtWidgets.QFrame.VLine)
            divider.setFrameShadow(QtWidgets.QFrame.Plain)
            divider.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
            identity = QtWidgets.QVBoxLayout()
            identity.setSpacing(2)
            label, section = _ElidedLabel(), _ElidedLabel()
            font = label.font()
            font.setBold(True)
            label.setFont(font)
            font = section.font()
            font.setPointSizeF(max(8., font.pointSizeF()-1.))
            section.setFont(font)
            identity.addWidget(label)
            identity.addWidget(section)
            button = QtWidgets.QPushButton("Selecionar " + title)
            button.clicked.connect(lambda _checked=False, i=index: self._begin_capture(i))
            row_layout.addWidget(marker)
            row_layout.addWidget(divider)
            row_layout.addLayout(identity, 1)
            row_layout.addWidget(button, 0, QtCore.Qt.AlignVCenter)
            layout.addWidget(row)
            self.member_rows.append(row)
            self.member_markers.append(marker)
            self.member_dividers.append(divider)
            self.member_labels.append(label)
            self.profile_labels.append(section)
            self.select_member_buttons.append(button)
        root.addLayout(layout)
        self.trim_section = QtWidgets.QWidget()
        trims = QtWidgets.QVBoxLayout(self.trim_section)
        trims.setContentsMargins(0, 4, 0, 2)
        trims.setSpacing(8)
        trims.addWidget(heading("Extremidades a aparar"))
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        self.trim_rows, self.trim_end_combos = [], []
        for index in (0, 1):
            marker = heading("A" if index == 0 else "B")
            combo = _TrimEndCombo()
            combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(14)
            combo.setMinimumWidth(0)
            combo.addItem("Escolher…", None)
            combo.addItem("Início", "Start")
            combo.addItem("Fim", "End")
            combo.setToolTip("Comprimentos axiais calculados, incluindo a extensão livre. A ponta oposta será preservada.\n"
                             "A viabilidade do par será verificada na prévia após autorização.")
            combo.opening.connect(self._prepare_trim_popup)
            combo.currentIndexChanged.connect(lambda _value, i=index: self._trim_end_changed(i))
            for column, widget in enumerate((marker, combo)):
                grid.addWidget(widget, index, column)
            self.trim_rows.append((marker, combo))
            self.trim_end_combos.append(combo)
        trims.addLayout(grid)
        self.trim_check = QtWidgets.QCheckBox("Autorizar os aparos indicados")
        self.trim_check.setToolTip("Autoriza o conjunto exato de membros, extremidades e valores apresentados.")
        self.trim_check.toggled.connect(self._trim_allowed_changed)
        trims.addWidget(self.trim_check)
        root.addWidget(self.trim_section)
        self.trim_section.hide()
        self._displayed_trim_token = None
        self.joint_summary = QtWidgets.QLabel()
        self.joint_summary.setWordWrap(True)
        self.joint_summary.setToolTip(
            "Prévia A em azul e B em laranja; o contorno vermelho indica o plano do encontro.")
        self.validation_message = QtWidgets.QLabel()
        self.validation_message.setWordWrap(True)
        self.validation_message.setToolTip(
            "Cortes fixos, sem associação: alterações posteriores em um membro não atualizam o outro.\n"
            "Prévia A em azul e B em laranja; contorno vermelho no plano do encontro.")
        root.addWidget(self.validation_message)
        root.addWidget(self.joint_summary)
        root.addStretch(1)
        self._lifecycle = _MiterPanelLifecycle(self)
        self.form.installEventFilter(self._lifecycle)
        self.form.destroyed.connect(self._form_destroyed)
        self._preview_timer = QtCore.QTimer(self.form)
        self._preview_timer.setInterval(180)
        self._preview_timer.timeout.connect(self._poll_reference)
        self._refresh()
        self._preview_timer.start()

    def _set_message(self, text, error=False, *, severity=None):
        self._message_severity = severity or ("error" if error else "info")
        self.validation_message.setText(text)
        self.validation_message.setProperty("miterMessageSeverity", self._message_severity)
        self._apply_message_style()

    def _apply_message_style(self):
        severity = getattr(self, "_message_severity", "info")
        if severity not in ("success", "error"):
            self.validation_message.setStyleSheet("")
            return
        reference = self.member_labels[0]
        foreground = reference.palette().color(QtGui.QPalette.WindowText)
        backing = reference.parentWidget() or self.form
        background = backing.palette().color(QtGui.QPalette.Window)
        rgb = lambda color: (color.redF(), color.greenF(), color.blueF())
        color = _semantic_message_rgb(rgb(foreground), rgb(background), severity)
        self.validation_message.setStyleSheet("color: rgb(%d, %d, %d); font-weight: 600;" % color)

    def _set_accept_enabled(self, enabled):
        try:
            box = self.form.window().findChild(QtWidgets.QDialogButtonBox)
            button = box.button(QtWidgets.QDialogButtonBox.Ok) if box is not None else None
            if button is not None:
                button.setEnabled(bool(enabled))
        except (RuntimeError, ReferenceError):
            pass

    def _clear_preview(self):
        preview, self._preview = self._preview, None
        self._candidate = None
        if preview is not None:
            preview.clear()

    def _state(self):
        presentation = tuple(
            None if obj is None else (bool(obj.ViewObject.Visibility), str(obj.ViewObject.DisplayMode), str(obj.Label))
            for obj in self.controller.members)
        gui_doc = Gui.activeDocument()
        return (self.controller.input_signature(), presentation,
                gui_doc.Document.Name if gui_doc is not None else None)

    def _active_scene(self):
        gui_doc = Gui.activeDocument()
        if gui_doc is None or gui_doc.Document is not self.document:
            raise ValueError("Ative o documento dos membros para visualizar a meia-esquadria.")
        return gui_doc.activeView().getSceneGraph()

    def _show_candidate(self, candidate):
        scene = self._active_scene()
        if self._preview is not None and self._preview.scene_graph != scene:
            self._clear_preview()
        if self._preview is None:
            self._preview = MemberMiterPreview(scene)
        self._preview.update(candidate)
        self._candidate = candidate

    def _trim_end_changed(self, index):
        if self._refreshing or self._closed:
            return
        self.controller.set_trim_end(index, self.trim_end_combos[index].currentData())
        self._refresh()

    def _prepare_trim_popup(self):
        # A stable editor already has both current values. Rebuilding/hiding it
        # here would interfere with Qt's transition between the A/B popups.
        if self._state() != self._watch_state:
            self._refresh()

    def _trim_allowed_changed(self, checked):
        if self._refreshing or self._closed:
            return
        try:
            if checked and self.controller._trim_token() != self._displayed_trim_token:
                # Consent must refer to the value the user actually saw,
                # including the interval before the next observer poll.
                self._refresh()
                return
            self.controller.set_trim_allowed(checked)
        except Exception as exc:
            self._set_message(str(exc), error=True)
        self._refresh()

    def _sync_trim_controls(self):
        # Hide stale rows even when eligibility/intersection fails next.
        self.trim_section.hide()
        context = self.controller.trim_context()
        required = [i for i, end in enumerate(context.automatic_ends) if end is None]
        for index, automatic in enumerate(context.automatic_ends):
            for widget in self.trim_rows[index]:
                widget.setVisible(automatic is None)
            if automatic is not None:
                if self.controller.trim_ends[index] is not None:
                    self.controller.set_trim_end(index, None)
                continue
            combo = self.trim_end_combos[index]
            end = self.controller.trim_ends[index]
            for option in ("Start", "End"):
                item_index = combo.findData(option)
                occupied = str(getattr(self.controller.members[index], option+"AdjustmentMode")) != "None"
                amount = self.controller.trim_length(context, index, option)
                combo.setItemText(item_index, _trim_option_text(option, amount, occupied))
                combo.model().item(item_index).setEnabled(not occupied)
                reason = ("Esta extremidade já possui ajuste; revise-o antes da meia-esquadria." if occupied else
                          "Comprimento axial calculado. A viabilidade do par será verificada na prévia após autorização.")
                combo.setItemData(item_index, reason, QtCore.Qt.ToolTipRole)
            combo.setCurrentIndex(combo.findData(end))
        self.trim_section.setVisible(bool(required))
        self._trim_required = required
        self.trim_check.setEnabled(bool(required) and all(
            self.controller.trim_ends[i] is not None and self.trim_end_combos[i].model().item(
                self.trim_end_combos[i].currentIndex()).isEnabled() for i in required))
        self.trim_check.setChecked(self.controller.trim_allowed())
        self._displayed_trim_token = self.controller._trim_token()

    def _refresh(self):
        if self._closed or self._refreshing:
            return False
        self._refreshing = True
        start_state = None
        try:
            # Reflect revocation even if the new pair fails eligibility before
            # its contextual rows can be rebuilt (for example different profiles).
            self.trim_check.setChecked(self.controller.trim_allowed())
            for index, obj in enumerate(self.controller.members):
                name, profile = _member_caption(obj) if obj is not None else ("Selecione um membro estrutural.", "")
                self.member_labels[index].setText(name)
                if obj is not None:
                    self.member_labels[index].setToolTip(str(obj.Label))
                self.profile_labels[index].setText(profile)
                self.profile_labels[index].setVisible(bool(profile))
            self.trim_section.hide()
            if any(obj is None for obj in self.controller.members):
                self._clear_preview()
                self._last_error = "Selecione dois membros estruturais."
                self.joint_summary.setText("")
                self._set_message(self._last_error)
                self._set_accept_enabled(False)
                return False
            self.controller.prepare_inputs()
            self._sync_trim_controls()
            start_state = self._state()
            if self._trim_required and not self.controller.trim_allowed():
                self._clear_preview()
                self.joint_summary.setText("")
                complete = all(self.controller.trim_ends[i] is not None for i in self._trim_required)
                self._last_error = ("Autorize os aparos indicados para visualizar o resultado." if complete
                                    else "Escolha as extremidades a aparar.")
                self._set_message(self._last_error, error=complete)
                self._set_accept_enabled(False)
                return False
            candidate = self.controller.evaluate()
            if self._closed:
                return False
            self._show_candidate(candidate)
            if self._state() != start_state:
                self._clear_preview()
                self._last_error = "Os membros mudaram durante o cálculo; atualizando a prévia."
                self.joint_summary.setText("")
                self._set_message(self._last_error)
                self._set_accept_enabled(False)
                return False
            ends = tuple("Início" if end == "Start" else "Fim" for end in candidate.plan.ends)
            self.joint_summary.setText("" if any(candidate.plan.trim_lengths) else "A: %s  •  B: %s" % ends)
            self._last_error = None
            angle = ("%.2f" % candidate.plan.angle_degrees).replace(".", ",")
            self._set_message("Encontro válido · %s°." % angle, severity="success")
            self._set_accept_enabled(True)
            return True
        except Exception as exc:
            self._clear_preview()
            self._last_error = str(exc)
            self.joint_summary.setText("")
            self._set_message(str(exc), error=True)
            self._set_accept_enabled(False)
            return False
        finally:
            # Consume only inputs that were actually evaluated. A change during
            # evaluation must remain visible to the next normal observer poll.
            if start_state is None:
                try:
                    start_state = self._state()
                except (RuntimeError, ReferenceError, AttributeError, ValueError):
                    start_state = ("unavailable",)
            self._watch_state = start_state
            self._refreshing = False

    def _poll_reference(self):
        if self._closed or self._refreshing:
            return
        try:
            if App.listDocuments().get(self._document_name) is not self.document:
                self.reject()
                return
            if any(obj is not None and not is_structural_member(obj) for obj in self.controller.members):
                self.reject()
                return
            if self._capture_mode is not None:
                return
            state = self._state()
            if self._preview is not None and self._active_scene() != self._preview.scene_graph:
                self._refresh()
                return
        except (RuntimeError, ReferenceError, AttributeError, ValueError):
            state = ("unavailable",)
        if state != self._watch_state:
            self._refresh()

    def _begin_capture(self, index):
        if self._closed:
            return
        self._remove_selection_observer()
        self._capture_mode = index
        self._clear_preview()
        self._last_error = "Conclua a seleção do membro antes de confirmar."
        self._set_accept_enabled(False)
        observer = _SelectionObserver(self)
        Gui.Selection.addObserver(observer)
        self._selection_observer = observer
        self._set_message("Selecione o membro %s na vista ou na árvore." % ("A" if index == 0 else "B"))

    def _selection_received(self, document_name, object_name, _subelement=""):
        if self._closed or document_name != self._document_name or self._capture_mode is None:
            return
        try:
            self.controller.set_member(self._capture_mode, self.document.getObject(object_name))
        except Exception as exc:
            self._last_error = str(exc)
            self._set_message(str(exc), error=True)
            return
        self._remove_selection_observer()
        self._refresh()

    def _remove_selection_observer(self):
        observer, self._selection_observer = self._selection_observer, None
        self._capture_mode = None
        if observer is not None:
            try:
                Gui.Selection.removeObserver(observer)
            except (RuntimeError, ReferenceError):
                pass
            observer.clear()

    def _form_destroyed(self, *_args):
        self.form = None
        self._finish(False)

    def _finish(self, accepted):
        if self._closed:
            return
        self._closed = True
        self._remove_selection_observer()
        self._clear_preview()
        try:
            self._preview_timer.stop()
            self._preview_timer.timeout.disconnect(self._poll_reference)
        except RuntimeError:
            pass
        self._lifecycle.panel = None
        callback, self._on_closed = self._on_closed, None
        if callback is not None:
            callback(self, accepted)

    def accept(self):
        if self._closed:
            return False
        if self._capture_mode is not None:
            self._set_message("Conclua a seleção do membro antes de confirmar.")
            return False
        try:
            if not self.isValid() or self._state() != self._watch_state:
                self._refresh()
                return False
            self.controller.apply()
        except Exception as exc:
            self._clear_preview()
            self._last_error = str(exc)
            self._set_message(str(exc), error=True)
            self._set_accept_enabled(False)
            return False
        self._finish(True)
        return True

    def reject(self):
        self._finish(False)
        return True

    def isValid(self):
        return not self._closed and self._capture_mode is None and self._last_error is None

    def getStandardButtons(self):
        return standard_buttons_value(QtWidgets.QDialogButtonBox)

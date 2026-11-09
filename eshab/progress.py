"""Contextual progress cards. The desktop island belongs exclusively to the shelf."""
from __future__ import annotations

import subprocess
import uuid
import weakref
from pathlib import Path

import shiboken6
from PySide6.QtCore import QObject, QPoint, Qt, QTimer, QUrl, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QCursor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget

from . import i18n, theme
from .brand import BrandMark
from .jobs import Job
from .liquid_ui import paint_window, motion_enabled

_ACTIVE = []
_RECENT = []
_events = None


class TaskEvents(QObject):
    started = Signal(object)
    changed = Signal(object, object)


def events():
    global _events
    if _events is None or not shiboken6.isValid(_events):
        _events = TaskEvents(QApplication.instance())
    return _events


def _studio_owner(widget):
    while widget is not None and shiboken6.isValid(widget):
        if hasattr(widget, "bridge"):
            return widget
        widget = widget.parentWidget()
    return None


def tasks_for(owner):
    result = []
    seen = set()
    for window in reversed(_ACTIVE + _RECENT):
        if shiboken6.isValid(window) and window._web_owner() is owner and window.task_id not in seen:
            seen.add(window.task_id)
            result.append(window.snapshot())
    return result[:12]


def task_action(owner, identifier, action):
    window = next((window for window in _ACTIVE + _RECENT
                   if shiboken6.isValid(window) and window.task_id == identifier and window._web_owner() is owner), None)
    if window is None:
        raise ValueError("انتهى سجل هذه العملية" if i18n.is_rtl() else "This task is no longer in the activity log")
    if action == "cancel" and not window._job_done:
        window._cancel()
    elif action == "open":
        window._open_output()
    elif action == "reveal":
        window._reveal_output()
    elif action == "dismiss":
        window._dismissed = True
        window._publish()
        if window._job_done:
            window._end_presentation()
    else:
        return False
    return True


def _reveal(path):
    path = Path(path)
    try:
        subprocess.Popen(["explorer", "/select,", str(path)], creationflags=0x08000000)
    except OSError:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


class ProgressWindow(QWidget):
    """One bounded task card; hiding a card leaves its background job running."""
    finished_closed = Signal(object)

    def __init__(self, title, job, parent=None, anchor=None):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setProperty("glassWindow", True)
        self.setLayoutDirection(theme.direction())
        self.setWindowTitle(title)
        self._acrylic = False
        self.job = job
        job.setParent(self)
        self.title = str(title)
        self.status = i18n.tr("progress.starting")
        self.outputs = []
        self.failed = self._job_done = self._dismissed = self._presentation_ended = False
        self._closed_notified = False
        self.error = ""
        self._value = -1.
        active = parent if parent is not None and parent.isVisible() else QApplication.activeWindow()
        owner = _studio_owner(active)
        self._owner_ref = weakref.ref(owner) if owner is not None else lambda: None
        self._using_web = False
        self.task_id = uuid.uuid4().hex
        self._owner_rect = active.frameGeometry() if active is not None and active.isVisible() else None
        self._anchor = QPoint(anchor) if anchor is not None else QCursor.pos()
        self.setFixedSize(384, 170)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        heading = QHBoxLayout()
        heading.setSpacing(10)
        heading.addWidget(BrandMark(self, size=28))
        self.heading = QLabel(self.title)
        self.heading.setMinimumWidth(0)
        self.heading.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.heading.setToolTip(self.title)
        heading.addWidget(self.heading, 1)
        close = QPushButton("×")
        close.setFixedSize(28, 28)
        close.setAccessibleName(i18n.tr("btn.close"))
        close.clicked.connect(self.close)
        heading.addWidget(close)
        layout.addLayout(heading)
        self.description = QLabel(self.status)
        self.description.setWordWrap(True)
        self.description.setFixedHeight(34)
        self.description.setProperty("dim", True)
        layout.addWidget(self.description)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(5)
        self.bar.setRange(0, 0)
        layout.addWidget(self.bar)
        footer = QHBoxLayout()
        self.percentage = QLabel("…")
        self.percentage.setProperty("dim", True)
        footer.addWidget(self.percentage)
        footer.addStretch()
        self.cancel_button = QPushButton(i18n.tr("btn.cancel"))
        self.cancel_button.clicked.connect(self._cancel)
        footer.addWidget(self.cancel_button)
        self.reveal_button = QPushButton(i18n.tr("progress.show"))
        self.reveal_button.clicked.connect(self._reveal_output)
        footer.addWidget(self.reveal_button)
        self.open_button = QPushButton(i18n.tr("progress.open"))
        self.open_button.clicked.connect(self._open_output)
        footer.addWidget(self.open_button)
        self.details_button = QPushButton(i18n.tr("progress.details"))
        self.details_button.clicked.connect(self._details)
        footer.addWidget(self.details_button)
        for button in (self.reveal_button, self.open_button, self.details_button):
            button.hide()
        layout.addLayout(footer)
        self._auto_hide = QTimer(self)
        self._auto_hide.setSingleShot(True)
        self._auto_hide.timeout.connect(self._maybe_close)
        self._entrance = QPropertyAnimation(self, b"windowOpacity", self)
        self._entrance.setDuration(220)
        self._entrance.setEasingCurve(QEasingCurve.Type.OutCubic)
        job.progress.connect(self._progress)
        job.status.connect(self._status)
        job.finished.connect(self._finished)
        job.failed.connect(self._failed)
        self._style()
        theme.add_theme_listener(self._theme_changed)
        callback = self._theme_changed
        self.destroyed.connect(lambda *_: theme.remove_theme_listener(callback))
        _ACTIVE[:] = [window for window in _ACTIVE if shiboken6.isValid(window)]
        _ACTIVE.append(self)
        events().started.emit(self)

    def _web_owner(self):
        owner = self._owner_ref()
        return owner if owner is not None and shiboken6.isValid(owner) else None

    def snapshot(self):
        return {"id": self.task_id, "title": self.title, "status": self.status,
                "progress": self._value, "done": self._job_done, "failed": self.failed,
                "error": self.error, "cancelled": self.job.cancel_event.is_set(),
                "outputs": [str(path) for path in self.outputs], "dismissed": self._dismissed}

    def _publish(self):
        events().changed.emit(self._web_owner(), self.snapshot())

    def show(self):
        owner = self._web_owner()
        if owner is not None and owner.isVisible():
            self._using_web = True
            self._dismissed = False
            self._publish()
            return
        self._using_web = False
        if not self.isVisible():
            self.setWindowOpacity(0. if motion_enabled() else 1.)
        super().show()

    def raise_(self):
        owner = self._web_owner()
        if self._using_web and owner is not None:
            owner.show()
            owner.raise_()
            self._dismissed = False
            self._publish()
        else:
            super().raise_()

    def _style(self):
        tokens = theme.native_design_tokens()
        self.setStyleSheet(f"""
            QLabel {{ color: {tokens['ink']}; background: transparent; font-size: 12px; }}
            QLabel[dim="true"] {{ color: {tokens['muted']}; font-size: 11px; }}
            QPushButton {{ color: {tokens['ink']}; background: {tokens['soft']};
                border: 1px solid {tokens['line']}; border-radius: 11px; padding: 4px 10px; min-height: 18px; font-size: 11px; }}
            QPushButton:hover {{ background: {tokens['selected']}; }}
            QProgressBar {{ border: 0; background: {tokens['soft']}; border-radius: 2px; }}
            QProgressBar::chunk {{ background: {tokens['blue']}; border-radius: 2px; }}
        """)

    def _theme_changed(self, dark):
        self._style()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._dismissed = False
        screen = QGuiApplication.screenAt(self._anchor) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        owner = self._owner_rect.intersected(area) if self._owner_rect is not None else area
        x = min(area.right() - self.width() - 12, max(area.left() + 12, owner.right() - self.width() - 18))
        y = min(area.bottom() - self.height() - 12, max(area.top() + 12, owner.top() + 80))
        visible = [window for window in _ACTIVE if window is not self and shiboken6.isValid(window) and window.isVisible()]
        for window in reversed(visible):
            if abs(window.x() - x) < self.width():
                candidate = window.y() + self.height() + 10
                if candidate + self.height() <= area.bottom() - 12:
                    y = candidate
                else:
                    window.hide()
        self.move(x, y)
        if motion_enabled():
            self._entrance.stop()
            self._entrance.setStartValue(.0)
            self._entrance.setEndValue(1.)
            self._entrance.start()
        self._refresh()

    def _refresh(self):
        self.heading.setText(self.heading.fontMetrics().elidedText(self.title, Qt.TextElideMode.ElideMiddle, 276))
        value = self.error or self.status
        self.description.setText(self.description.fontMetrics().elidedText(value.replace("\n", " · "), Qt.TextElideMode.ElideMiddle, 640))
        self.description.setToolTip(value)
        self.bar.setRange(0, 0 if self._value < 0 and not self._job_done else 1000)
        self.bar.setValue(round(max(0., min(1., self._value)) * 1000))
        self.percentage.setText("!" if self.failed else f"{round(self._value * 100)}%" if self._value >= 0 else "…")
        self._publish()

    def _progress(self, value):
        self._value = float(value)
        self._refresh()

    def _status(self, text):
        self.status = str(text)
        self._refresh()

    def _finished(self, outputs):
        self._job_done = True
        self.outputs = [Path(path) for path in outputs]
        self._value = 1.
        self.status = i18n.tr("progress.saved_beside") if self.outputs else i18n.tr("progress.done")
        if self.outputs:
            self.title = self.outputs[0].name if len(self.outputs) == 1 else i18n.tr("progress.saved_many", n=len(self.outputs))
        self.cancel_button.hide()
        self.reveal_button.setVisible(bool(self.outputs))
        self.open_button.setVisible(bool(self.outputs))
        self._refresh()
        if self._dismissed:
            self._end_presentation()
        elif self._using_web:
            self._remember()
        else:
            self._auto_hide.start(5200)

    def _failed(self, message):
        self._job_done = self.failed = True
        self.error = str(message)
        self.status = i18n.tr("progress.cancelled") if self.job.cancel_event.is_set() else i18n.tr("progress.failed_title")
        self.title = self.status
        self.cancel_button.hide()
        self.details_button.setVisible(not self.job.cancel_event.is_set())
        self._refresh()
        if self._using_web:
            self._remember()
        if self._dismissed:
            self._end_presentation()
        elif self.job.cancel_event.is_set():
            self._auto_hide.start(1800)

    def _cancel(self):
        self.job.cancel()
        self.cancel_button.setEnabled(False)
        self._publish()

    def _maybe_close(self):
        if self.underMouse():
            self._auto_hide.start(2000)
        else:
            self.close()

    def _reveal_output(self):
        if self.outputs:
            _reveal(self.outputs[0])

    def _open_output(self):
        if self.outputs:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.outputs[0])))

    def _details(self):
        QMessageBox.warning(self, self.title, self.error)

    def closeEvent(self, event):
        self._dismissed = True
        self._publish()
        self._auto_hide.stop()
        if self._job_done:
            self._end_presentation()
        elif not self._closed_notified:
            self._closed_notified = True
            self.finished_closed.emit(self)
        super().closeEvent(event)

    def _end_presentation(self):
        if self._presentation_ended:
            return
        self._presentation_ended = True
        self._remember()
        if not self._closed_notified:
            self._closed_notified = True
            self.finished_closed.emit(self)

    def _remember(self):
        if self in _ACTIVE:
            _ACTIVE.remove(self)
        _RECENT[:] = [window for window in _RECENT if shiboken6.isValid(window)]
        if self not in _RECENT:
            _RECENT.append(self)
        for window in _RECENT[:-8]:
            window.deleteLater()
        del _RECENT[:-8]

    def paintEvent(self, event):
        paint_window(self)


def run_job(title, work, parent=None, anchor=None):
    job = Job(work)
    window = ProgressWindow(title, job, parent, anchor)
    window.show()
    job.start()
    return window

"""The liquid wheel: directional targeting, copy-only drops, cancel and keys.

The field bug this guards against: the wheel opened under the pointer, the
user released right away (pointer still in the middle) and nothing happened.
Selection is now directional, the middle is an explicit cancel zone that
refuses the drop, and every target is reachable at any distance.
"""

import math
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QKeyEvent, QMouseEvent, QWheelEvent

from eshab import wheel as wheel_module
from eshab.wheel import DEAD_ZONE, EXTENT, FanItem, LiquidWheel

KEYS = ("jpg", "webp", "avif", "heic", "pdf", "docx", "tiff")


def _mime(*paths) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    return mime


def _toward(widget, index: int, distance: float) -> QPointF:
    angle = math.radians(widget.scene.angle_of(index))
    return QPointF(widget.width() / 2.0 + math.cos(angle) * distance,
                   widget.height() / 2.0 + math.sin(angle) * distance)


def _center(widget) -> QPointF:
    return QPointF(widget.width() / 2.0, widget.height() / 2.0)


def _enter(widget, mime, actions=Qt.DropAction.CopyAction | Qt.DropAction.MoveAction):
    event = QDragEnterEvent(QPoint(widget.width() // 2, widget.height() // 2), actions, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
    widget.dragEnterEvent(event)
    return event


def _move(widget, point, mime, actions=Qt.DropAction.CopyAction | Qt.DropAction.MoveAction):
    event = QDragMoveEvent(point.toPoint(), actions, mime, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.ShiftModifier)
    widget.dragMoveEvent(event)
    return event


def _drop(widget, point, mime, actions=Qt.DropAction.CopyAction | Qt.DropAction.MoveAction):
    event = QDropEvent(point, actions, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    widget.dropEvent(event)
    return event


def _press(widget, point):
    event = QMouseEvent(QEvent.Type.MouseButtonPress, point, point, point, Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    widget.mousePressEvent(event)


@pytest.fixture
def wheel(qapp, tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0eshab-fixture")
    second = tmp_path / "second.jpg"
    second.write_bytes(b"\xff\xd8\xff\xe0eshab-fixture")
    widget = LiquidWheel()
    widget.set_factory(lambda files: [FanItem(key, key.upper()) for key in KEYS])
    widget.test_file = str(photo)
    widget.test_second = str(second)
    yield widget
    widget.hide()
    widget.deleteLater()


def test_drag_enter_fills_the_drops(wheel):
    enter = _enter(wheel, _mime(wheel.test_file))
    assert enter.isAccepted()
    assert [Path(p) for p in wheel.file_paths()] == [Path(wheel.test_file)]
    assert [item.key for item in wheel._items] == list(KEYS)


@pytest.mark.parametrize("distance", [DEAD_ZONE + 4, 110.0, 152.0, EXTENT - 4, EXTENT + 150])
def test_every_target_is_reachable_by_direction_at_any_distance(wheel, distance):
    mime = _mime(wheel.test_file)
    _enter(wheel, mime)
    for index, key in enumerate(KEYS):
        point = _toward(wheel, index, distance)
        move = _move(wheel, point, mime)
        assert move.isAccepted(), (key, distance)
        assert move.dropAction() == Qt.DropAction.CopyAction
        assert wheel._hover == index


def test_between_two_drops_picks_the_nearer_direction(wheel):
    mime = _mime(wheel.test_file)
    _enter(wheel, mime)
    step = 360.0 / len(KEYS)
    angle = math.radians(wheel.scene.angle_of(2) + step * 0.45)
    point = QPointF(wheel.width() / 2 + math.cos(angle) * 120, wheel.height() / 2 + math.sin(angle) * 120)
    _move(wheel, point, mime)
    assert wheel._hover == 2


def test_drop_toward_a_target_activates_it_with_the_files(wheel):
    mime = _mime(wheel.test_file)
    _enter(wheel, mime)
    captured = []
    wheel.activated.connect(lambda files, key: captured.append((files, key)))
    point = _toward(wheel, 4, 140)
    _move(wheel, point, mime)
    drop = _drop(wheel, point, mime)
    assert drop.isAccepted()
    assert drop.dropAction() == Qt.DropAction.CopyAction
    assert len(captured) == 1
    files, key = captured[0]
    assert key == "pdf"
    assert [Path(p) for p in files] == [Path(wheel.test_file)]


def test_the_orb_is_a_cancel_zone(wheel):
    mime = _mime(wheel.test_file)
    _enter(wheel, mime)
    captured = []
    wheel.activated.connect(lambda files, key: captured.append((files, key)))
    move = _move(wheel, _center(wheel), mime)
    assert not move.isAccepted()  # the "no" cursor tells the user nothing will happen
    assert wheel._hover == -1
    drop = _drop(wheel, _center(wheel), mime)
    assert not drop.isAccepted()
    assert captured == []


def test_drop_is_copy_only(wheel):
    """A drop that can only move the source must be refused (never lose a file)."""
    mime = _mime(wheel.test_file)
    _enter(wheel, mime)
    captured = []
    wheel.activated.connect(lambda files, key: captured.append((files, key)))
    point = _toward(wheel, 1, 140)
    move = _move(wheel, point, mime, Qt.DropAction.MoveAction)
    assert not move.isAccepted()
    drop = _drop(wheel, point, mime, Qt.DropAction.MoveAction)
    assert not drop.isAccepted()
    assert captured == []


def test_no_second_activation_during_the_farewell(wheel):
    mime = _mime(wheel.test_file)
    _enter(wheel, mime)
    captured = []
    wheel.activated.connect(lambda files, key: captured.append((files, key)))
    point = _toward(wheel, 0, 140)
    _drop(wheel, point, mime)
    _drop(wheel, point, mime)
    assert len(captured) == 1


def test_collapsed_payload_keeps_the_full_selection(wheel):
    _enter(wheel, _mime(wheel.test_file, wheel.test_second))
    _enter(wheel, _mime(wheel.test_file))
    assert [Path(p) for p in wheel.file_paths()] == [Path(wheel.test_file), Path(wheel.test_second)]


def test_click_toward_a_drop_activates_and_click_in_the_orb_closes(wheel):
    captured, closed = [], []
    wheel.activated.connect(lambda files, key: captured.append(key))
    wheel.closed.connect(lambda: closed.append(True))
    _enter(wheel, _mime(wheel.test_file))
    _press(wheel, _toward(wheel, 3, 150))
    assert captured == ["heic"]

    wheel.reset()
    _enter(wheel, _mime(wheel.test_file))
    _press(wheel, _center(wheel))
    assert closed == [True]
    assert wheel._items == []


def test_keys_and_scroll_move_the_selection(wheel):
    wheel.set_items([FanItem("png", "PNG"), FanItem("webp", "WEBP"), FanItem("jpg", "JPG")])
    scroll = QWheelEvent(QPointF(), QPointF(), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    wheel.wheelEvent(scroll)
    assert wheel._hover == 0
    right = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    wheel.keyPressEvent(right)
    assert wheel._hover == 1
    wheel.set_files([wheel.test_file])
    captured = []
    wheel.activated.connect(lambda files, key: captured.append(key))
    enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    wheel.keyPressEvent(enter)
    assert captured == ["webp"]
    closed = []
    wheel.closed.connect(lambda: closed.append(True))
    escape = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    wheel.keyPressEvent(escape)
    assert closed == [True]


def test_dismiss_then_a_new_gesture_keeps_the_wheel(wheel, qapp):
    wheel.set_files([wheel.test_file])
    wheel.set_items([FanItem("png", "PNG")])
    wheel.show()
    qapp.processEvents()
    wheel.dismiss()
    wheel.cancel_dismiss()
    from PySide6.QtTest import QTest

    QTest.qWait(320)
    assert wheel.isVisible()
    assert wheel._items


def test_paint_every_state_without_errors(wheel, qapp):
    """Smoke: birth, hover, lens, farewell and the empty state all paint."""
    from PySide6.QtGui import QImage, QPainter

    def paint():
        image = QImage(wheel.size(), QImage.Format.Format_ARGB32_Premultiplied)
        painter = QPainter(image)
        wheel.scene.paint(painter)
        painter.end()

    def advance(seconds):
        for _ in range(int(seconds * 120)):
            for spring in wheel.scene.animator._springs:
                spring.step(1 / 120)

    wheel.scene.appear()
    paint()  # empty, waiting for the payload
    _enter(wheel, _mime(wheel.test_file))
    for _ in range(4):
        advance(0.05)
        paint()
    wheel.scene.set_hover(2)
    advance(0.08)
    paint()
    wheel.scene.set_hover(5)
    advance(0.5)
    paint()
    wheel.scene.depart(chosen=5)
    advance(0.1)
    paint()
    for mode in ("tools", "actions"):
        wheel.set_mode(mode)
        wheel.set_items([FanItem("img.compress", "ضغط", kind="tool"), FanItem("img.crop", "اقتصاص", kind="tool")])
        wheel.scene.set_hover(1)
        advance(0.3)
        paint()


def test_liquid_bridge_never_ends_in_a_point():
    from eshab import glass

    for distance in (10.0, 50.0, 90.0, 150.0):
        path = glass.liquid_bridge(QPointF(0, 0), 44.0, QPointF(distance, 0), 30.0, 0.3)
        if path is None:
            continue
        bounds = path.boundingRect()
        # The far end is rounded: it reaches a full radius beyond the end centre.
        assert bounds.right() >= distance + 29.0
    assert wheel_module.mode_label("tools")

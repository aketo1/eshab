"""The fan wheel's behaviour: open, point, drop, cancel, switch decks."""

import math

import pytest
from PySide6.QtCore import QObject, QPoint, QUrl

from eshab import app as eshab_app, fan
from eshab.fanwheel import FanWheel


@pytest.fixture
def wheel(qapp, tmp_path):
    # Just the parts of the app the wheel needs: its Qt Quick engine.
    host = eshab_app.App.__new__(eshab_app.App)
    QObject.__init__(host)
    host.bridge = eshab_app.Bridge(host)
    host._engine = None
    host._images = None
    engine = eshab_app.App.engine(host)

    def items(files, mode):
        count = {"conversion": 4, "tools": 7, "actions": 5}[mode]
        return [{"key": f"{mode}-{i}", "label": f"{mode} {i}", "text": f"F{i}", "glyph": "", "kind": mode}
                for i in range(count)]

    widget = FanWheel(engine, host._images, items)
    widget.test_files = [str(tmp_path / "one.png"), str(tmp_path / "two.png")]
    for name in widget.test_files:
        open(name, "wb").close()
    yield widget
    widget.window.hide()
    widget.window.deleteLater()


def _toward(wheel, index, distance=120):
    layout = wheel._layout
    card = layout.cards[index]
    rad = math.radians(card.angle)
    return layout.centre[0] + math.cos(rad) * distance, layout.centre[1] + math.sin(rad) * distance


def test_opens_with_one_card_per_option(wheel):
    wheel.show_at(QPoint(800, 600), wheel.test_files[:1], "conversion")
    assert wheel.phase == "open"
    assert len(wheel.cards) == 4 and wheel.selected == -1
    assert all({"x", "y", "key"} <= set(card) for card in wheel.cards)


def test_pointing_selects_and_dropping_activates_a_copy(wheel):
    fired = []
    wheel.activated.connect(lambda files, key, mode: fired.append((files, key, mode)))
    wheel.show_at(QPoint(800, 600), wheel.test_files[:1], "conversion")
    wheel.pointer(*_toward(wheel, 2))
    assert wheel.selected == 2
    assert wheel.drop() is True
    assert fired == [(wheel.test_files[:1], "conversion-2", "conversion")]
    assert wheel.phase == "leaving"


def test_dropping_in_the_orb_cancels(wheel):
    fired = []
    wheel.activated.connect(lambda *args: fired.append(args))
    wheel.show_at(QPoint(800, 600), wheel.test_files[:1], "tools")
    wheel.pointer(fan.SIDE / 2 + 5, fan.SIDE / 2 + 5)
    assert wheel.selected == -1
    assert wheel.drop() is False
    assert not fired and wheel.phase == "leaving"


def test_a_collapsed_explorer_payload_keeps_the_whole_selection(wheel):
    wheel.show_at(QPoint(800, 600), wheel.test_files, "conversion")
    wheel.enter([QUrl.fromLocalFile(wheel.test_files[0])])
    assert wheel.fileCount == 2


def test_switching_decks_replaces_the_cards(wheel, qapp):
    wheel.show_at(QPoint(800, 600), wheel.test_files[:1], "conversion")
    wheel.switch("tools")
    assert wheel.phase == "switching"
    wheel._finish_switch()
    assert wheel.phase == "open" and len(wheel.cards) == 7
    assert [m["active"] for m in wheel.modes if m["mode"] == "tools"] == [True]


def test_label_names_the_choice(wheel):
    wheel.show_at(QPoint(800, 600), wheel.test_files[:1], "conversion")
    wheel.pointer(*_toward(wheel, 0))
    assert "F0" in wheel.label


def test_keyboard_steps_and_confirms(wheel):
    fired = []
    wheel.activated.connect(lambda files, key, mode: fired.append(key))
    wheel.show_at(QPoint(800, 600), wheel.test_files[:1], "actions", keyboard=True)
    wheel.step(1)
    wheel.step(1)
    wheel.confirm()
    assert fired == ["actions-1"]


def test_dismiss_hides_after_the_farewell(wheel):
    wheel.show_at(QPoint(800, 600), wheel.test_files[:1], "conversion")
    wheel.dismiss()
    assert wheel.phase == "leaving"
    wheel._finish_leaving()
    assert wheel.phase == "hidden" and wheel.cards == []

"""What the settings window may change (eshab/app.py Bridge), and how a new
language asks for a restart. The suite's settings live in a temp file."""
from PySide6.QtCore import QObject

from eshab import app as tray
from eshab import i18n, settings


class FakeApp(QObject):
    def __init__(self):
        super().__init__()
        self.themed = 0
        self.synced = 0

    def _apply_theme(self):
        self.themed += 1

    def sync_menu(self):
        self.synced += 1

    def set_material(self, key):
        settings.set("material", key)


def test_only_known_settings_change(qapp, monkeypatch):
    bridge = tray.Bridge(FakeApp())
    monkeypatch.setattr(settings, "save", lambda: None)
    bridge.setSetting("welcomeShown", True)                     # not the window's to change
    assert settings.get("welcomeShown", False) is False
    bridge.setSetting("toolsWheelDragModifierMask", "ctrl+win")  # not one of the choices
    assert settings.get("toolsWheelDragModifierMask") != "ctrl+win"
    bridge.setSetting("toolsWheelDragModifierMask", "ctrl+alt")
    assert bridge.setting("toolsWheelDragModifierMask") == "ctrl+alt"
    settings.set("toolsWheelDragModifierMask", "alt")


def test_the_look_applies_at_once(qapp, monkeypatch):
    fake = FakeApp()
    bridge = tray.Bridge(fake)
    monkeypatch.setattr(settings, "save", lambda: None)
    bridge.setSetting("appearanceTheme", "dark")
    assert fake.themed == 1
    settings.set("appearanceTheme", "system")


def test_every_key_choice_has_a_label(qapp):
    bridge = tray.Bridge(FakeApp())
    labels = {choice["value"]: choice["label"] for choice in bridge.maskChoices}
    assert labels["shift"] == "Shift" and labels["ctrl+shift"] == "Ctrl + Shift"
    assert labels[""] == i18n.tr("settings.mask.none")


def test_a_new_language_asks_for_a_restart(qapp, monkeypatch):
    bridge = tray.Bridge(FakeApp())
    monkeypatch.setattr(settings, "save", lambda: None)
    assert not bridge.restartNeeded
    other = "ar" if i18n.current_language() == "en" else "en"
    bridge.setSetting("language", other)
    try:
        assert bridge.restartNeeded
    finally:
        settings.set("language", "en")


def test_start_with_windows_follows_the_switch(qapp, monkeypatch):
    from eshab import startup

    state = {"on": False}
    monkeypatch.setattr(startup, "enabled", lambda: state["on"])
    monkeypatch.setattr(startup, "set_enabled", lambda on: state.update(on=on))
    fake = FakeApp()
    bridge = tray.Bridge(fake)
    bridge.setStartup(True)
    assert bridge.startup and fake.synced == 1

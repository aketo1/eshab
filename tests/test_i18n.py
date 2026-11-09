"""Internationalization: Arabic first, English fallback, full parity."""

import re

import pytest

from eshab import i18n, settings


@pytest.fixture(autouse=True)
def restore_language():
    original = settings.get("language", "en") or "en"
    yield
    i18n.set_language(original)


def test_english_lookups():
    i18n.set_language("en")
    assert i18n.current_language() == "en"
    assert i18n.tr("wheel.convert") == "Convert"
    assert i18n.tr("tray.quit") == "Quit Eshab"
    assert not i18n.is_rtl()


def test_arabic_lookups_and_direction():
    i18n.set_language("ar")
    assert i18n.tr("app.name") == "اسحب"
    assert i18n.tr("wheel.convert") == "تحويل"
    assert i18n.tr("wheel.to_format", target="PDF") == "تحويل إلى PDF"
    assert i18n.is_rtl()


def test_the_app_defaults_to_arabic():
    assert settings.DEFAULT_LANGUAGE == "ar"


def test_unknown_key_falls_back_to_the_key():
    assert i18n.tr("does.not.exist") == "does.not.exist"


def test_format_kwargs_are_applied():
    i18n.set_language("en")
    assert i18n.tr("action.converting_to", target="PDF") == "Converting to PDF"
    assert i18n.tr("wheel.files_count", n=3) == "3 files"


def test_arabic_covers_every_key_with_the_same_placeholders():
    english = i18n.TRANSLATIONS["en"]
    arabic = i18n.TRANSLATIONS["ar"]
    assert len(english) > 500
    assert set(english) <= set(arabic), sorted(set(english) - set(arabic))
    for key, value in english.items():
        assert set(re.findall(r"\{[^}]*\}", value)) == set(re.findall(r"\{[^}]*\}", arabic[key])), key
        assert "Tangerine" not in value, key


def test_system_locale_resolves(monkeypatch):
    monkeypatch.setattr(i18n, "_system_locale_name", lambda: "ar_SA")
    settings.set("language", "system")
    assert i18n.resolve_language() == "ar"
    monkeypatch.setattr(i18n, "_system_locale_name", lambda: "de_DE")
    assert i18n.resolve_language() == "en"


def test_set_language_persists_and_notifies():
    seen = []
    i18n.add_listener(seen.append)
    try:
        i18n.set_language("ar")
        i18n.set_language("en")
    finally:
        i18n.remove_listener(seen.append)
    assert seen == ["ar", "en"]
    assert settings.get("language") == "en"

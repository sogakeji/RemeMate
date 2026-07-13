"""Small server-side UI translation layer for RemeMate.

UI language is deliberately separate from the language being learned and from
the language used for AI feedback. Catalog keys are stable product terms; the
templates never carry parallel Chinese/English strings.
"""
import json
from functools import lru_cache
from pathlib import Path

from flask import g, request, session
from flask_login import current_user

from app.extensions import db


SUPPORTED_UI_LOCALES = ("zh", "en")
DEFAULT_UI_LOCALE = "zh"
_CATALOG_DIR = Path(__file__).with_name("translations")


@lru_cache(maxsize=None)
def _catalog(locale: str) -> dict[str, str]:
    code = locale if locale in SUPPORTED_UI_LOCALES else DEFAULT_UI_LOCALE
    with (_CATALOG_DIR / f"{code}.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def catalog_keys(locale: str) -> set[str]:
    """Expose catalog coverage for tests and translation audits."""
    return set(_catalog(locale))


def resolve_ui_locale() -> str:
    selected = session.get("ui_locale")
    if selected in SUPPORTED_UI_LOCALES:
        return selected

    if current_user.is_authenticated and current_user.settings:
        selected = current_user.settings.ui_locale
        if selected in SUPPORTED_UI_LOCALES:
            return selected

    best = request.accept_languages.best_match(SUPPORTED_UI_LOCALES)
    return best or DEFAULT_UI_LOCALE


def bind_ui_locale():
    g.ui_locale = resolve_ui_locale()


def get_ui_locale() -> str:
    return getattr(g, "ui_locale", DEFAULT_UI_LOCALE)


def set_ui_locale(locale: str):
    if locale not in SUPPORTED_UI_LOCALES:
        raise ValueError("unsupported UI locale")
    session["ui_locale"] = locale
    g.ui_locale = locale
    if current_user.is_authenticated and current_user.settings:
        current_user.settings.ui_locale = locale
        db.session.commit()


def translate(key: str, **values) -> str:
    locale = get_ui_locale()
    text = _catalog(locale).get(key)
    if text is None:
        text = _catalog(DEFAULT_UI_LOCALE).get(key, key)
    return text.format(**values) if values else text


def localized_language_names() -> dict[str, str]:
    return {
        code: translate(f"language.{code}")
        for code in ("fr", "en", "ja", "de", "es", "ru", "zh")
    }


def localized_timezone_names() -> dict[str, str]:
    return {
        "Asia/Shanghai": translate("timezone.shanghai"),
        "Europe/Paris": translate("timezone.paris"),
        "UTC": "UTC",
        "Asia/Tokyo": translate("timezone.tokyo"),
        "America/New_York": translate("timezone.new_york"),
        "America/Los_Angeles": translate("timezone.los_angeles"),
    }

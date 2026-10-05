"""Choose a translation direction from a detected language."""

from __future__ import annotations

from dataclasses import dataclass

from dydict.config import LANGUAGES

CONFIDENCE_MIN = 0.50

LINGUA_ENUM_NAMES: dict[str, str] = {
    "en": "ENGLISH",
    "tr": "TURKISH",
    "de": "GERMAN",
    "fr": "FRENCH",
    "es": "SPANISH",
    "it": "ITALIAN",
    "pt": "PORTUGUESE",
    "nl": "DUTCH",
    "pl": "POLISH",
    "ru": "RUSSIAN",
    "uk": "UKRAINIAN",
    "sv": "SWEDISH",
    "da": "DANISH",
    "fi": "FINNISH",
    "nb": "BOKMAL",
    "cs": "CZECH",
    "ro": "ROMANIAN",
    "hu": "HUNGARIAN",
    "el": "GREEK",
    "bg": "BULGARIAN",
    "ar": "ARABIC",
    "he": "HEBREW",
    "hi": "HINDI",
    "zh": "CHINESE",
    "ja": "JAPANESE",
    "ko": "KOREAN",
    "vi": "VIETNAMESE",
    "id": "INDONESIAN",
    "fa": "PERSIAN",
    "th": "THAI",
}


@dataclass(frozen=True)
class Direction:
    source: str
    target: str
    uncertain: bool


def language_name(code: str, names: dict[str, str]) -> str:
    if code == "auto":
        return "Auto"
    return names.get(code, code)


def direction_line(source: str, target: str, names: dict[str, str], shortened: bool) -> str:
    line = f"{language_name(source, names)} → {language_name(target, names)}"
    if shortened:
        return f"{line} · shortened"
    return line


def choose_direction(
    detected: str | None,
    confidence: float,
    main: str,
    second: str,
    text_length: int,
) -> Direction:
    if text_length < 2 or detected is None or confidence < CONFIDENCE_MIN:
        return Direction("auto", main, True)
    if detected == main:
        return Direction(main, second, False)
    return Direction(detected, main, False)


def swap_direction(direction: Direction) -> Direction | None:
    if direction.source == "auto":
        return None
    return Direction(direction.target, direction.source, False)


def run_detector(text: str, detector: object) -> tuple[str | None, float]:
    try:
        code, confidence = detector.detect(text)  # type: ignore[attr-defined]
    except Exception:
        return None, 0.0
    if not isinstance(code, str) or isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None, 0.0
    return code, float(confidence)

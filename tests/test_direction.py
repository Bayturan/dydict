import pytest

from dydict.config import LANGUAGES
from dydict.detect import (
    CONFIDENCE_MIN,
    LINGUA_ENUM_NAMES,
    Direction,
    choose_direction,
    direction_line,
    run_detector,
    swap_direction,
)


class Boom:
    def detect(self, text: str) -> tuple[str, float]:
        raise RuntimeError(text)


class Fixed:
    def __init__(self, code: str, confidence: float):
        self.code = code
        self.confidence = confidence

    def detect(self, text: str) -> tuple[str, float]:
        return self.code, self.confidence


def test_main_language_goes_to_second():
    direction = choose_direction("tr", 0.90, "tr", "en", text_length=5)
    assert direction == Direction("tr", "en", False)
    assert direction_line(direction.source, direction.target, LANGUAGES, False) == (
        "Turkish → English"
    )


def test_other_language_goes_to_main():
    direction = choose_direction("de", 0.80, "tr", "en", text_length=6)
    assert direction == Direction("de", "tr", False)
    assert direction_line(direction.source, direction.target, LANGUAGES, False) == (
        "German → Turkish"
    )


def test_second_language_goes_to_main():
    direction = choose_direction("en", 0.80, "tr", "en", text_length=5)
    assert direction == Direction("en", "tr", False)


def test_confidence_boundary():
    assert CONFIDENCE_MIN == 0.50
    confident = choose_direction("tr", 0.50, "tr", "en", text_length=4)
    low = choose_direction("tr", 0.49, "tr", "en", text_length=4)
    assert confident.source == "tr"
    assert low == Direction("auto", "tr", True)
    assert direction_line(low.source, low.target, LANGUAGES, False) == "Auto → Turkish"


def test_short_text_is_auto_even_when_detection_is_sure():
    direction = choose_direction("en", 1.0, "tr", "en", text_length=1)
    assert direction == Direction("auto", "tr", True)


def test_detector_failure_is_auto():
    code, confidence = run_detector("merhaba", Boom())
    direction = choose_direction(code, confidence, "tr", "en", text_length=7)
    assert code is None
    assert confidence == 0.0
    assert direction == Direction("auto", "tr", True)


def test_run_detector_returns_values():
    assert run_detector("hello", Fixed("en", 0.7)) == ("en", 0.7)


def test_swap_exchanges_concrete_codes_and_refuses_auto():
    swapped = swap_direction(Direction("tr", "en", False))
    assert swapped == Direction("en", "tr", False)
    assert swap_direction(Direction("auto", "tr", True)) is None


def test_shortened_suffix():
    assert direction_line("en", "tr", LANGUAGES, True) == "English → Turkish · shortened"


def test_unknown_code_is_shown_as_itself():
    assert direction_line("xx", "tr", LANGUAGES, False) == "xx → Turkish"


def test_every_code_maps_to_a_lingua_language():
    from lingua import Language

    assert list(LINGUA_ENUM_NAMES) == list(LANGUAGES)
    for code, enum_name in LINGUA_ENUM_NAMES.items():
        language = getattr(Language, enum_name)
        assert language.iso_code_639_1.name.lower() == code or (
            language.iso_code_639_1.value == code
        )

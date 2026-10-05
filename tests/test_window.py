import pytest

from dydict.config import LANGUAGES, Config
from dydict.engines import EngineFailure, EngineSuccess, OnlineError, PackageMissing
from dydict.selection import CopyError
from dydict.window import COPY_FAILED, FieldGate, PopupController


class FixedDetect:
    def __init__(self, code, confidence):
        self.code = code
        self.confidence = confidence

    def detect(self, text: str):
        return self.code, self.confidence


class Online:
    def __init__(self, text="merhaba", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def translate(self, text, source, target):
        self.calls.append((source, target))
        if self.error:
            raise self.error
        return self.text


def controller(detect, online, offline=None, config=None):
    return PopupController(
        config or Config(),
        detect,
        online,
        offline or Online("offline-text"),
        LANGUAGES,
    )


def test_programmatic_field_change_is_not_a_user_edit():
    gate = FieldGate()
    seen = []

    def setter():
        seen.append(gate.on_user_change())

    gate.set_programmatic(setter)
    assert seen == [False]
    assert gate.on_user_change() is True


def test_empty_text_makes_no_request():
    online = Online()
    popup = controller(FixedDetect("en", 1), online)
    generation = popup.open_with()
    result = popup.translate_now("   ", generation)
    assert result.kind == "empty"
    assert online.calls == []


def test_prefilled_text_translates_immediately_for_that_generation():
    online = Online("merhaba")
    popup = controller(FixedDetect("en", 0.9), online)
    generation = popup.open_with()
    result = popup.translate_now("hello", generation)
    assert result.kind == "ok"
    assert result.translation == "merhaba"
    assert result.engine == "online"
    assert result.direction_line == "English → Turkish"
    assert online.calls == [("en", "tr")]


def test_one_character_still_requests_auto_to_main():
    online = Online("a-tr")
    popup = controller(FixedDetect("en", 1), online)
    generation = popup.open_with()
    result = popup.translate_now("a", generation)
    assert result.kind == "ok"
    assert online.calls == [("auto", "tr")]
    assert result.direction_line == "Auto → Turkish"


def test_stale_generation_does_not_replace_the_result():
    popup = controller(FixedDetect("en", 1), Online("first"))
    first = popup.open_with()
    popup.translate_now("hello", first)
    second = popup.edit("hello there")
    stale = popup.translate_now("hello", first)
    assert stale is None
    assert popup.result.translation == "first"
    fresh = popup.translate_now("hello there", second)
    assert fresh.translation == "first"
    assert popup.generation == second


def test_edit_clears_swap_override():
    online = Online("x")
    popup = controller(FixedDetect("de", 0.9), online)
    generation = popup.open_with()
    popup.translate_now("hallo", generation)
    swapped = popup.swap("hallo")
    assert swapped.direction_line == "Turkish → German"
    assert online.calls[-1] == ("tr", "de")
    later = popup.edit("hallo!")
    again = popup.translate_now("hallo!", later)
    assert again.direction_line == "German → Turkish"
    assert online.calls[-1] == ("de", "tr")


def test_swap_is_off_for_auto():
    popup = controller(FixedDetect("en", 0.1), Online("x"))
    generation = popup.open_with()
    popup.translate_now("hi", generation)
    assert popup.swap("hi") is None


def test_need_package_keeps_the_online_message():
    offline = Online(error=PackageMissing("de", "tr"))
    popup = controller(FixedDetect("de", 0.9), Online(error=OnlineError("down")), offline)
    generation = popup.open_with()
    result = popup.translate_now("hallo", generation)
    assert result.kind == "need_package"
    assert result.message == "down"
    assert result.package_source == "de"
    assert result.package_target == "tr"


def test_enter_on_error_does_not_copy():
    popup = controller(FixedDetect("en", 0.1), Online(error=OnlineError("down")))
    generation = popup.open_with()
    popup.translate_now("hi", generation)
    copied = []
    assert popup.enter_action(lambda text: copied.append(text)) == "ignored"
    assert copied == []
    assert popup.visible is True


def test_enter_copies_translation_and_copy_failure_sets_notice():
    popup = controller(FixedDetect("en", 0.9), Online("merhaba"))
    generation = popup.open_with()
    popup.translate_now("hello", generation)
    copied = []
    assert popup.enter_action(lambda text: copied.append(text)) == "copied_hide"
    assert copied == ["merhaba"]
    assert popup.copy_action(lambda text: None) == "copied"

    def boom(text):
        raise CopyError("missing")

    assert popup.enter_action(boom) == "copy_failed"
    assert popup.notice == COPY_FAILED
    assert popup.visible is True


def test_hide_and_config_replacement():
    online = Online("x")
    popup = controller(FixedDetect("en", 0.9), online)
    popup.hide()
    assert popup.visible is False
    popup.replace_config(Config("de", "fr"))
    generation = popup.open_with()
    result = popup.translate_now("hello", generation)
    assert result.direction_line == "English → German"
    assert online.calls == [("en", "de")]


def test_long_text_marks_the_direction_line():
    popup = controller(FixedDetect("en", 0.9), Online("x"))
    generation = popup.open_with()
    result = popup.translate_now("a" * 2001, generation)
    assert result.direction_line.endswith(" · shortened")


def test_retry_keeps_the_swap_override():
    online = Online("x")
    popup = controller(FixedDetect("de", 0.9), online)
    generation = popup.open_with()
    popup.translate_now("hallo", generation)
    popup.swap("hallo")
    retry = popup.retry()
    result = popup.translate_now("hallo", retry)
    assert result.direction_line == "Turkish → German"

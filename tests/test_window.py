import re
import threading
import time
from types import SimpleNamespace

import pytest

from dydict.config import LANGUAGES, Config
from dydict.engines import EngineFailure, EngineSuccess, OnlineError
from dydict.selection import CopyError
from dydict.window import (
    COPY_FAILED,
    DEBOUNCE_MS,
    QUERY_MAX_HEIGHT,
    FieldGate,
    Popup,
    PopupController,
    launcher_layout,
    launcher_stylesheet,
    load_launcher_css,
    present_query,
    translate_off_ui,
    window_content_limit,
)


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


def test_settings_panel_can_grow_past_the_compact_popup():
    assert window_content_limit(False) == 480
    assert window_content_limit(True) >= 640


def controller(detect, online, offline=None, config=None):
    return PopupController(
        config or Config(),
        detect,
        online,
        offline,
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


def test_begin_swap_records_no_online_call():
    online = Online("x")
    popup = controller(FixedDetect("de", 0.9), online)
    generation = popup.open_with()
    popup.translate_now("hallo", generation)
    assert online.calls == [("de", "tr")]
    started = popup.begin_swap()
    assert started == generation + 1
    assert popup.generation == started
    assert online.calls == [("de", "tr")]
    result = popup.translate_now("hallo", started)
    assert result is not None
    assert result.direction_line == "Turkish → German"
    assert online.calls == [("de", "tr"), ("tr", "de")]


def test_swap_is_off_for_auto():
    popup = controller(FixedDetect("en", 0.1), Online("x"))
    generation = popup.open_with()
    popup.translate_now("hi", generation)
    assert popup.swap("hi") is None


def test_online_failure_keeps_the_message_and_offers_no_download():
    popup = controller(FixedDetect("de", 0.9), Online(error=OnlineError("down")))
    generation = popup.open_with()
    result = popup.translate_now("hallo", generation)
    assert result.kind == "error"
    assert result.message == "down"
    assert result.package_source is None
    assert result.package_target is None


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


class RecordingSurface:
    def __init__(self, log: list) -> None:
        self.log = log

    def apply_selection(self, text: str) -> None:
        self.log.append(("selection", text))

    def present_window(self) -> None:
        self.log.append("visible")

    def focus_query(self) -> None:
        self.log.append("focus")


def _present_controller(online, factory, log, offline=None):
    popup = PopupController(Config(), None, online, offline, LANGUAGES)

    def begin(text, generation):
        log.append(("begin", text, generation))
        return popup.translate_now(text, generation)

    return popup, begin


def test_present_shows_and_focuses_before_detect_and_translate():
    log = []
    online = Online("merhaba")
    translate = online.translate

    def logged_translate(text, source, target):
        log.append(("translate", text, source, target))
        return translate(text, source, target)

    online.translate = logged_translate

    def factory():
        log.append("detector")
        return FixedDetect("en", 0.9)

    popup, begin = _present_controller(online, factory, log)
    started = time.monotonic()
    generation = present_query(RecordingSurface(log), "  hello \n", popup, factory, begin)
    elapsed = time.monotonic() - started

    assert generation == 1
    assert elapsed < 0.3
    assert log.index(("selection", "hello")) < log.index("visible") < log.index("focus")
    assert log.index("focus") < log.index("detector") < log.index(("translate", "hello", "en", "tr"))
    focus_at = log.index("focus")
    assert "detector" not in log[: focus_at + 1]
    assert ("translate", "hello", "en", "tr") not in log[: focus_at + 1]
    assert online.calls == [("en", "tr")]
    assert popup.result is not None
    assert popup.result.translation == "merhaba"
    assert popup.result.kind == "ok"


def test_empty_selection_still_presents_without_a_request():
    log = []
    online = Online("merhaba")

    def factory():
        log.append("detector")
        return FixedDetect("en", 1)

    popup, begin = _present_controller(online, factory, log)
    present_query(RecordingSurface(log), "   ", popup, factory, begin)
    assert ("selection", "") in log
    assert "visible" in log and "focus" in log
    assert log.index(("selection", "")) < log.index("visible") < log.index("focus")
    assert "detector" not in log
    assert online.calls == []
    assert popup.result.kind == "empty"


def test_newer_generation_from_the_present_path_drops_the_older_result():
    log = []
    online = Online("merhaba")

    def factory():
        log.append("detector")
        return FixedDetect("en", 0.9)

    popup, begin = _present_controller(online, factory, log)
    first = present_query(RecordingSurface(log), "hello", popup, factory, begin)
    assert popup.result.translation == "merhaba"
    second = popup.edit("hello there")
    stale = popup.translate_now("hello", first)
    assert stale is None
    assert popup.result.translation == "merhaba"
    fresh = popup.translate_now("hello there", second)
    assert fresh is not None
    assert fresh.translation == "merhaba"
    assert popup.generation == second
    assert first != second


def _css_blocks(css: str, selector: str) -> str:
    pattern = re.compile(re.escape(selector) + r"\s*\{([^}]*)\}")
    found = pattern.findall(css)
    assert found, selector
    return "\n".join(found)


def test_launcher_stylesheet_is_the_text_the_popup_loads():
    loaded = {}

    class Provider:
        def load_from_string(self, css: str) -> None:
            loaded["css"] = css

    load_launcher_css(Provider())
    css = loaded["css"]
    assert css == launcher_stylesheet()
    card = _css_blocks(css, ".launcher-card")
    query = _css_blocks(css, ".launcher-query")
    meta = _css_blocks(css, ".launcher-meta")
    result = _css_blocks(css, ".launcher-result")
    assert "border-radius" in card
    assert "padding" in card
    assert query != meta
    assert "font-size" in query
    opacity = float(re.search(r"opacity:\s*([0-9.]+)", meta).group(1))
    assert opacity < 1
    assert "font-size" in meta
    assert "background-color" in result
    assert "border-radius" in result
    import inspect

    assert "_install_style" in inspect.getsource(Popup.__init__)
    assert "load_launcher_css" in inspect.getsource(Popup._install_style)
    assert "launcher_layout" in inspect.getsource(Popup.__init__)
    assert "present_query" in inspect.getsource(Popup.show_text)
    assert "present_query" in inspect.getsource(
        __import__("dydict.app", fromlist=["main"]).main
    )


def test_launcher_layout_caps_width_query_and_settings():
    from dydict.shell import WINDOW_WIDTH as shell_width

    layout = launcher_layout()
    assert shell_width == 640
    assert layout["width"] == 640
    assert layout["query_lines"] == 2
    assert layout["query_max_height"] == QUERY_MAX_HEIGHT
    assert layout["query_max_height"] > 0
    assert layout["result_scrolls"] is True
    assert layout["result_max_height"] > 0
    assert layout["window_max_height"] == 480
    assert window_content_limit(False) == 480
    assert layout["settings_window_max"] == window_content_limit(True)
    assert layout["settings_window_max"] >= 640
    assert DEBOUNCE_MS == 300


def test_translate_off_ui_does_not_run_on_the_caller_thread():
    caller = threading.get_ident()
    seen = {}
    done = threading.Event()

    class Controller:
        def translate_now(self, text, generation):
            seen["thread"] = threading.get_ident()
            seen["text"] = text
            done.set()
            return None

    thread = translate_off_ui(Controller(), "hello", 1, lambda *_args: None, lambda *_args: None)
    assert done.wait(2)
    thread.join(1)
    assert seen["thread"] != caller
    assert seen["text"] == "hello"


def test_popup_start_translation_delivers_on_a_worker():
    caller = threading.get_ident()
    online = Online("merhaba")
    popup = controller(FixedDetect("en", 0.9), online)
    generation = popup.open_with()
    idle = []

    class GLib:
        def idle_add(self, fn, *args):
            idle.append((threading.get_ident(), fn, args))
            return 1

    fake = SimpleNamespace(controller=popup, _GLib=GLib(), _apply=Popup._apply)
    Popup.start_translation(fake, "hello", generation)
    for _ in range(50):
        if idle:
            break
        time.sleep(0.02)
    assert idle
    worker, fn, args = idle[0]
    assert worker != caller
    assert fn == Popup._apply
    assert args[0].translation == "merhaba"
    assert args[1] == generation
    assert online.calls == [("en", "tr")]


def test_off_ui_worker_drops_a_stale_generation():
    online = Online("first")
    popup = controller(FixedDetect("en", 0.9), online)
    first = popup.open_with()
    popup.translate_now("hello", first)
    popup.edit("hello there")
    delivered = []
    done = threading.Event()

    def on_result(result, generation):
        delivered.append((result, generation))
        done.set()

    def on_error(message, generation):
        delivered.append((message, generation))
        done.set()

    thread = translate_off_ui(popup, "hello", first, on_result, on_error)
    thread.join(2)
    assert not done.is_set()
    assert delivered == []
    assert popup.result.translation == "first"


def _pump(glib, ms):
    ctx = glib.MainContext.default()
    deadline = glib.get_monotonic_time() + ms * 1000
    while glib.get_monotonic_time() < deadline:
        if ctx.pending():
            ctx.iteration(False)
        else:
            glib.usleep(2_000)


def _run_fit(popup, glib):
    """Run the shipped fitter and drop the idle so it cannot redo the layout."""
    source = popup._fit_source
    if source is not None:
        glib.source_remove(source)
        popup._fit_source = None
    popup._fit_to_content()


def _settings_bottom(popup):
    ok, bounds = popup.settings.compute_bounds(popup.window)
    assert ok
    return bounds.get_y() + bounds.get_height()


def test_mapped_popup_shrinks_on_settings_close_and_keeps_save_reachable():
    """A shown window must adopt the capped height, and Save must stay reachable."""
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib

    popup = Popup(controller(FixedDetect("en", 1), Online()), lambda _config: None)
    if Gdk.Display.get_default() is None:
        pytest.skip("no GTK display")
    popup._arm_leave = lambda: False
    try:
        popup.apply_selection("hello")
        popup.present_window()
        _run_fit(popup, GLib)
        _pump(GLib, 200)
        assert popup.window.get_width() == 640
        assert popup.window.get_resizable() is False
        assert popup.window.get_height() <= window_content_limit(False)

        popup._toggle_settings()
        _run_fit(popup, GLib)
        opened = popup.window.get_height()
        _width, chosen = popup.window.get_default_size()
        assert opened == chosen
        assert opened <= window_content_limit(True)
        assert _settings_bottom(popup) <= opened + 1

        popup._toggle_settings()
        _run_fit(popup, GLib)
        closed = popup.window.get_height()
        _width, chosen = popup.window.get_default_size()
        assert closed == chosen
        assert closed <= window_content_limit(False)
        assert closed < opened

        popup.result.set_text("translated line\n" * 40)
        popup._toggle_settings()
        _run_fit(popup, GLib)
        tall = popup.window.get_height()
        _width, chosen = popup.window.get_default_size()
        assert tall == chosen
        assert tall <= window_content_limit(True)
        assert tall > window_content_limit(False)
        _pinned_width, pinned = popup._outer.get_child().get_size_request()
        if pinned >= window_content_limit(True):
            assert tall == window_content_limit(True)
        assert _settings_bottom(popup) <= tall + 1

        popup._outer.set_max_content_height(360)
        _run_fit(popup, GLib)
        capped = popup.window.get_height()
        _pinned_width, pinned = popup._outer.get_child().get_size_request()
        assert capped <= 360
        assert pinned > capped
        adjustment = popup._outer.get_vadjustment()
        assert adjustment.get_upper() > adjustment.get_page_size() + 1
        adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        _pump(GLib, 40)
        assert _settings_bottom(popup) <= capped + 1

        _pump(GLib, 300)
        surface = popup.window.get_surface()
        assert popup.window.get_height() == capped
        assert surface is not None
        assert surface.get_height() == capped
    finally:
        popup.window.destroy()
        _pump(GLib, 40)


def test_retry_keeps_the_swap_override():
    online = Online("x")
    popup = controller(FixedDetect("de", 0.9), online)
    generation = popup.open_with()
    popup.translate_now("hallo", generation)
    popup.swap("hallo")
    retry = popup.retry()
    result = popup.translate_now("hallo", retry)
    assert result.direction_line == "Turkish → German"

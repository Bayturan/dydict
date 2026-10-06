"""Popup state, launcher styling, and the show-then-translate startup path."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from dydict.config import Config
from dydict.detect import choose_direction, direction_line, run_detector, swap_direction
from dydict.engines import EngineFailure, EngineSuccess, is_current
from dydict.selection import CopyError, prepare_query

COPY_FAILED = "Could not copy"


@dataclass(frozen=True)
class QueryResult:
    kind: str
    translation: str
    engine: str | None
    direction_line: str
    message: str
    package_source: str | None
    package_target: str | None


class FieldGate:
    def __init__(self) -> None:
        self.suppress = False

    def set_programmatic(self, setter) -> None:
        self.suppress = True
        try:
            setter()
        finally:
            self.suppress = False

    def on_user_change(self) -> bool:
        return not self.suppress


class PopupController:
    def __init__(self, config: Config, detect, online, offline, names: dict[str, str]) -> None:
        self._config = config
        self._detect = detect
        self._detector_factory = None
        self._online = online
        self._offline = offline
        self._names = names
        self._generation = 0
        self._override = None
        self._direction = None
        self._result: QueryResult | None = None
        self._visible = False
        self.notice = ""

    @property
    def detector_factory(self):
        return self._detector_factory

    def set_detector_factory(self, factory) -> None:
        if factory is not None:
            self._detector_factory = factory

    def _resolve_detect(self):
        if self._detect is None:
            factory = self._detector_factory
            if factory is None:
                raise RuntimeError("language detector is not available")
            self._detect = factory()
        return self._detect

    @property
    def result(self) -> QueryResult | None:
        return self._result

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def visible(self) -> bool:
        return self._visible

    @property
    def direction(self):
        return self._direction

    def replace_config(self, config: Config) -> None:
        self._config = config

    def hide(self) -> None:
        self._visible = False

    def open_with(self) -> int:
        self._visible = True
        self._override = None
        self.notice = ""
        self._generation += 1
        return self._generation

    def retry(self) -> int:
        self._generation += 1
        return self._generation

    def edit(self, text: str) -> int:
        self._override = None
        self.notice = ""
        self._generation += 1
        return self._generation

    def translate_now(self, text: str, generation: int) -> QueryResult | None:
        if not is_current(generation, self._generation):
            return None
        result, direction = self._compute(text)
        if not is_current(generation, self._generation):
            return None
        self._direction = direction
        self._result = result
        return result

    def begin_swap(self) -> int | None:
        if self._direction is None:
            return None
        swapped = swap_direction(self._direction)
        if swapped is None:
            return None
        self._override = swapped
        self._generation += 1
        return self._generation

    def swap(self, text: str) -> QueryResult | None:
        generation = self.begin_swap()
        if generation is None:
            return None
        return self.translate_now(text, generation)

    def enter_action(self, copy) -> str:
        return self._copy(copy, hide_token="copied_hide")

    def copy_action(self, copy) -> str:
        return self._copy(copy, hide_token="copied")

    def _copy(self, copy, hide_token: str) -> str:
        if self._result is None or self._result.kind != "ok":
            return "ignored"
        try:
            copy(self._result.translation)
        except CopyError:
            self.notice = COPY_FAILED
            return "copy_failed"
        self.notice = ""
        return hide_token

    def _compute(self, text: str) -> tuple[QueryResult, object]:
        prepared, shortened = prepare_query(text)
        if prepared == "":
            empty = QueryResult("empty", "", None, "", "", None, None)
            return empty, None
        if self._override is not None:
            direction = self._override
        elif len(prepared) < 2:
            direction = choose_direction(
                None, 0.0, self._config.main_language, self._config.second_language, len(prepared)
            )
        else:
            detected, confidence = run_detector(prepared, self._resolve_detect())
            direction = choose_direction(
                detected,
                confidence,
                self._config.main_language,
                self._config.second_language,
                len(prepared),
            )
        line = direction_line(direction.source, direction.target, self._names, shortened)
        outcome = self._online_or_offline(prepared, direction.source, direction.target)
        if isinstance(outcome, EngineSuccess):
            result = QueryResult("ok", outcome.text, outcome.engine, line, "", None, None)
        else:
            result = QueryResult("error", "", None, line, outcome.message, None, None)
        return result, direction

    def _online_or_offline(self, text: str, source: str, target: str):
        from dydict.engines import translate_with_fallback

        return translate_with_fallback(text, source, target, self._online, self._offline)


DEBOUNCE_MS = 300
WINDOW_WIDTH = 640
QUERY_MAX_HEIGHT = 52
RESULT_MAX_HEIGHT = 300
WINDOW_MAX_HEIGHT = 480
# The settings form sits under the translation. 480px clips Save, so open
# settings raise the cap. Content that is still taller scrolls.
SETTINGS_WINDOW_MAX = 720


def window_content_limit(settings_open: bool) -> int:
    return SETTINGS_WINDOW_MAX if settings_open else WINDOW_MAX_HEIGHT


# Two lines of the 16px query face fit in this cap; a third line scrolls.
QUERY_VISIBLE_LINES = 2

CLASS_POPUP = "dydict-popup"
CLASS_CARD = "launcher-card"
CLASS_SHELL = "launcher-shell"
CLASS_QUERY = "launcher-query"
CLASS_META = "launcher-meta"
CLASS_RESULT = "launcher-result"

LAUNCHER_STYLESHEET = """
window.dydict-popup {
  background-color: transparent;
  border-radius: 16px;
}

.launcher-shell,
.launcher-shell > viewport {
  background-color: transparent;
}

.launcher-card {
  background-color: @window_bg_color;
  color: @window_fg_color;
  border-radius: 16px;
  padding: 14px;
  border: 1px solid alpha(@window_fg_color, 0.12);
}

.launcher-query {
  font-size: 16px;
  padding: 8px 10px;
  border-radius: 10px;
  background-color: @theme_base_color;
  border: 1px solid alpha(@window_fg_color, 0.14);
}

.launcher-query text {
  background-color: transparent;
  font-size: 16px;
}

.launcher-meta {
  opacity: 0.62;
  font-size: 12px;
}

.launcher-result {
  border-radius: 12px;
  background-color: alpha(@window_fg_color, 0.07);
}

.launcher-result > viewport {
  background-color: transparent;
  border-radius: 12px;
}

.launcher-result label {
  padding: 8px 12px;
}

.launcher-card button {
  border-radius: 8px;
  padding: 4px 10px;
}
"""


def launcher_stylesheet() -> str:
    return LAUNCHER_STYLESHEET


def load_launcher_css(provider) -> None:
    """Load the same stylesheet text the popup applies."""
    css = launcher_stylesheet()
    loader = getattr(provider, "load_from_string", None)
    if loader is not None:
        loader(css)
        return
    provider.load_from_data(css.encode())


def launcher_layout() -> dict:
    """Sizes the popup actually applies. Height follows content inside the caps."""
    return {
        "width": WINDOW_WIDTH,
        "query_lines": QUERY_VISIBLE_LINES,
        "query_max_height": QUERY_MAX_HEIGHT,
        "result_scrolls": True,
        "result_max_height": RESULT_MAX_HEIGHT,
        "window_max_height": window_content_limit(False),
        "settings_window_max": window_content_limit(True),
    }


def present_query(surface, raw: str, controller: PopupController, detector_factory, begin_translate) -> int:
    """Put the selection in the field, show the window, focus it, then translate.

    The detector factory is not called here. Translation runs immediately for
    this generation, with no edit debounce, and builds the detector only after
    the window is already visible.
    """
    prepared, _shortened = prepare_query(raw)
    generation = controller.open_with()
    surface.apply_selection(prepared)
    surface.present_window()
    surface.focus_query()
    controller.set_detector_factory(detector_factory)
    begin_translate(prepared, generation)
    return generation


def run_detached(work) -> threading.Thread:
    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    return thread


def translate_off_ui(controller, text: str, generation: int, on_result, on_error) -> threading.Thread:
    """Run translate_now off the calling thread. A stale generation returns None and is not delivered."""

    def work() -> None:
        try:
            result = controller.translate_now(text, generation)
        except Exception as exc:
            on_error(str(exc), generation)
            return
        if result is not None:
            on_result(result, generation)

    return run_detached(work)


class OnlineEngine:
    def __init__(self, config_getter) -> None:
        self._config_getter = config_getter

    def translate(self, text: str, source: str, target: str) -> str:
        from dydict.engines import online_translate, urllib_post

        config = self._config_getter()
        return online_translate(
            config.online_url,
            text,
            source,
            target,
            config.online_api_key,
            config.timeout_ms,
            urllib_post,
        )


class Popup:
    def __init__(self, controller: PopupController, on_save_config) -> None:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        from gi.repository import Gdk, GLib, Gtk

        self._GLib = GLib
        self._Gtk = Gtk
        self.controller = controller
        self._on_save_config = on_save_config
        self._gate = FieldGate()
        self._debounce_id = None
        self._accept_leave = False
        self._shown_generation = None
        self._fit_source = None

        layout = launcher_layout()
        self.window = Gtk.Window(title="DyDict")
        self.window.add_css_class(CLASS_POPUP)
        self.window.set_default_size(layout["width"], -1)
        self.window.set_size_request(layout["width"], -1)
        self.window.set_resizable(False)
        self._install_style()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.add_css_class(CLASS_CARD)

        self.buffer = Gtk.TextBuffer()
        self.view = Gtk.TextView(buffer=self.buffer, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.view.add_css_class(CLASS_QUERY)
        self.view.set_hexpand(True)
        query_scroll = Gtk.ScrolledWindow()
        query_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        query_scroll.set_propagate_natural_height(True)
        query_scroll.set_max_content_height(layout["query_max_height"])
        query_scroll.set_child(self.view)
        self._query_scroll = query_scroll
        self.direction = Gtk.Label(label="", xalign=0, hexpand=True)
        self.engine = Gtk.Label(label="", xalign=1)
        self.direction.add_css_class(CLASS_META)
        self.engine.add_css_class(CLASS_META)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(self.direction)
        head.append(self.engine)
        self.message = Gtk.Label(label="", xalign=0, wrap=True)
        self.result = Gtk.Label(label="", xalign=0, wrap=True, selectable=True)
        scroller = Gtk.ScrolledWindow()
        scroller.add_css_class(CLASS_RESULT)
        result_policy = Gtk.PolicyType.AUTOMATIC if layout["result_scrolls"] else Gtk.PolicyType.NEVER
        scroller.set_policy(Gtk.PolicyType.NEVER, result_policy)
        scroller.set_propagate_natural_height(True)
        scroller.set_max_content_height(layout["result_max_height"])
        scroller.set_child(self.result)
        self._result_scroll = scroller
        self.copy_button = Gtk.Button(label="Copy")
        self.settings_button = Gtk.Button(label="Settings")
        from dydict.settings_view import build_settings

        self.settings = build_settings(controller._config, self._save_config)
        self.settings.set_visible(False)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.swap_button = Gtk.Button(label="Swap")
        actions.append(self.swap_button)
        actions.append(self.copy_button)
        actions.append(self.settings_button)

        root.append(query_scroll)
        root.append(head)
        root.append(self.message)
        root.append(scroller)
        root.append(actions)
        root.append(self.settings)
        outer = Gtk.ScrolledWindow()
        outer.add_css_class(CLASS_SHELL)
        outer.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer.set_overlay_scrolling(False)
        outer.set_propagate_natural_height(True)
        outer.set_max_content_height(layout["window_max_height"])
        outer.set_child(root)
        self.window.set_child(outer)
        self._outer = outer

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.window.add_controller(keys)
        self.buffer.connect("changed", self._on_changed)
        self.swap_button.connect("clicked", lambda _b: self._swap_clicked())
        self.copy_button.connect("clicked", lambda _b: self._copy_clicked())
        self.settings_button.connect("clicked", lambda _b: self._toggle_settings())
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", self._on_leave)
        self.window.add_controller(focus)
        self.window.connect("close-request", self._on_close)
        self._Gdk = Gdk

    def _install_style(self) -> None:
        provider = self._Gtk.CssProvider()
        load_launcher_css(provider)
        from gi.repository import Gdk

        display = Gdk.Display.get_default()
        if display is None:
            return
        self._Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            self._Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _schedule_fit(self) -> None:
        if self._fit_source is not None:
            return
        self._fit_source = self._GLib.idle_add(self._fit_to_content)

    def _fit_to_content(self) -> bool:
        """Grow or shrink the card with its content, inside the active cap.

        ``set_default_size`` only records the size a compositor may apply later.
        A mapped window keeps its old allocation until then, so closing settings
        left the card above the 480px cap and a tall result never reached the
        settings cap. Allocate the target immediately, and ask the toplevel to
        match it without flipping ``resizable`` (a tiling compositor would
        swallow a resizable window). The card's minimum height is its content,
        which lets the outer scroller reach Save when that content is taller
        than the cap. The scroller's own minimum stays small, so the cap holds.
        """
        self._fit_source = None
        if not self.window.get_visible():
            return False
        layout = launcher_layout()
        width = layout["width"]
        card = self._outer.get_child()
        if card is None:
            return False
        # A height pinned by the previous fit would report that old height.
        _pinned_width, pinned_height = card.get_size_request()
        card.set_size_request(-1, -1)
        _minimum, natural, _baseline, _natural_baseline = card.measure(
            self._Gtk.Orientation.VERTICAL, width
        )
        natural = int(natural)
        if natural <= 0:
            return False
        cap = int(self._outer.get_max_content_height())
        height = min(natural, cap) if cap > 0 else natural
        if height <= 0:
            return False
        if (
            self.window.get_width() == width
            and self.window.get_height() == height
            and pinned_height == natural
        ):
            card.set_size_request(-1, natural)
            return False
        card.set_size_request(-1, natural)
        focused = self.window.get_focus()
        self.window.set_resizable(False)
        self.window.set_default_size(width, height)
        surface = self.window.get_surface()
        if surface is not None:
            toplevel = self._Gdk.ToplevelLayout.new()
            toplevel.set_resizable(False)
            surface.present(toplevel)
        rect = self._Gdk.Rectangle()
        rect.x = 0
        rect.y = 0
        rect.width = width
        rect.height = height
        self.window.size_allocate(rect, -1)
        if focused is not None:
            focused.grab_focus()
        return False

    def _toggle_settings(self) -> None:
        show = not self.settings.get_visible()
        self.settings.set_visible(show)
        self._outer.set_max_content_height(window_content_limit(show))
        self._schedule_fit()

    def apply_selection(self, text: str) -> None:
        self._clear_query_view()
        self._set_text(text)

    def present_window(self) -> None:
        self.window.set_visible(True)
        self._schedule_fit()
        self._GLib.idle_add(self._arm_leave)

    def focus_query(self) -> None:
        self.view.grab_focus()

    def show_text(self, raw: str) -> None:
        present_query(
            self,
            raw,
            self.controller,
            self.controller.detector_factory,
            self.start_translation,
        )

    def start_translation(self, text: str, generation: int) -> None:
        translate_off_ui(
            self.controller,
            text,
            generation,
            lambda result, gen: self._GLib.idle_add(self._apply, result, gen),
            lambda message, gen: self._GLib.idle_add(self._worker_failed, message, gen),
        )

    def _clear_query_view(self) -> None:
        self._shown_generation = None
        self.direction.set_text("")
        self.engine.set_text("")
        self.result.set_text("")
        self.message.set_text("")
        self.swap_button.set_sensitive(False)

    def _focus_in_settings(self) -> bool:
        widget = self.window.get_focus()
        while widget is not None:
            if widget == self.settings:
                return True
            widget = widget.get_parent()
        return False

    def _arm_leave(self) -> bool:
        self._accept_leave = True
        return False

    def _on_leave(self, _controller) -> None:
        if self._accept_leave:
            self._hide()

    def toggle(self) -> None:
        if self.controller.visible:
            self._hide()
            return
        import os
        import shutil

        from dydict.selection import read_primary, subprocess_run

        raw = read_primary(os.environ, subprocess_run, shutil.which)
        self.show_text(raw)

    def _hide(self) -> None:
        self._accept_leave = False
        self.controller.hide()
        self.window.set_visible(False)

    def _swap_clicked(self) -> None:
        generation = self.controller.begin_swap()
        if generation is None:
            return
        self._clear_query_view()
        self._start(self._current_text(), generation)

    def _on_close(self, _window) -> bool:
        self._hide()
        return True

    def _set_text(self, text: str) -> None:
        def setter():
            self.buffer.set_text(text)
            start, end = self.buffer.get_bounds()
            self.buffer.select_range(start, end)

        self._gate.set_programmatic(setter)

    def _on_changed(self, _buffer) -> None:
        if not self._gate.on_user_change():
            return
        text = self.buffer.get_text(*self.buffer.get_bounds(), False)
        generation = self.controller.edit(text)
        self._clear_query_view()
        if self._debounce_id is not None:
            self._GLib.source_remove(self._debounce_id)
        self._debounce_id = self._GLib.timeout_add(DEBOUNCE_MS, self._fire, text, generation)

    def _fire(self, text: str, generation: int) -> bool:
        self._debounce_id = None
        self._start(text, generation)
        return False

    def _start(self, text: str, generation: int) -> None:
        self.start_translation(text, generation)

    def _worker_failed(self, message: str, generation: int) -> bool:
        if generation != self.controller.generation:
            return False
        self.message.set_text(message)
        self._schedule_fit()
        return False

    def _apply(self, result, generation=None) -> bool:
        if generation is not None and generation != self.controller.generation:
            return False
        self.direction.set_text(result.direction_line)
        self.engine.set_text(result.engine or "")
        self.result.set_text(result.translation)
        notice = self.controller.notice or result.message
        self.message.set_text(notice)
        direction = self.controller.direction
        self.swap_button.set_sensitive(direction is not None and direction.source != "auto")
        self._shown_generation = self.controller.generation
        self._schedule_fit()
        return False

    def _current_text(self) -> str:
        return self.buffer.get_text(*self.buffer.get_bounds(), False)

    def _copy_clicked(self) -> None:
        if self._shown_generation != self.controller.generation:
            return
        self._dispatch(self.controller.copy_action(self._clipboard))

    def _clipboard(self, text: str) -> None:
        import os
        import shutil

        from dydict.selection import copy_text, subprocess_run

        copy_text(text, os.environ, subprocess_run, shutil.which)

    def _dispatch(self, action: str) -> None:
        if action == "copy_failed":
            self.message.set_text(self.controller.notice)
            return
        if action == "copied_hide":
            self._hide()

    def _on_key(self, _controller, keyval, _keycode, state):
        enter = keyval in (self._Gdk.KEY_Return, self._Gdk.KEY_KP_Enter)
        if enter and state & self._Gdk.ModifierType.SHIFT_MASK:
            return False
        if enter:
            if self._focus_in_settings():
                return False
            if self._shown_generation == self.controller.generation:
                self._dispatch(self.controller.enter_action(self._clipboard))
            return True
        if keyval == self._Gdk.KEY_Escape:
            self._hide()
            return True
        if keyval == self._Gdk.KEY_s and state & self._Gdk.ModifierType.CONTROL_MASK:
            self._swap_clicked()
            return True
        return False

    def _save_config(self, config) -> None:
        self._on_save_config(config)
        self.controller.replace_config(config)
        text = self._current_text()
        generation = self.controller.edit(text)
        self._clear_query_view()
        self._start(text, generation)


def build_popup(controller: PopupController, on_save_config) -> Popup:
    return Popup(controller, on_save_config)

"""Popup state. GTK construction lives in build_popup and is added in Task 7."""

from __future__ import annotations

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
            detected, confidence = run_detector(prepared, self._detect)
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
        elif outcome.package_source:
            result = QueryResult(
                "need_package", "", None, line, outcome.message,
                outcome.package_source, outcome.package_target,
            )
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
# The settings form sits under the translation. 480px clips Save, and this
# scrolled window compresses its child instead of scrolling, so open settings
# raise the cap enough for the form to stay on screen.
SETTINGS_WINDOW_MAX = 720


def window_content_limit(settings_open: bool) -> int:
    return SETTINGS_WINDOW_MAX if settings_open else WINDOW_MAX_HEIGHT


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


class OfflineEngine:
    def translate(self, text: str, source: str, target: str) -> str:
        from dydict.engines import argos_offline_translate

        return argos_offline_translate(text, source, target)


class Popup:
    def __init__(self, controller: PopupController, on_save_config) -> None:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gdk, GLib, Gtk

        self._GLib = GLib
        self._Gtk = Gtk
        self.controller = controller
        self._on_save_config = on_save_config
        self._gate = FieldGate()
        self._debounce_id = None
        self._accept_leave = False
        self._shown_generation = None

        self.window = Gtk.Window(title="DyDict")
        self.window.set_default_size(WINDOW_WIDTH, -1)
        self.window.set_resizable(False)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)

        self.buffer = Gtk.TextBuffer()
        self.view = Gtk.TextView(buffer=self.buffer, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.view.set_size_request(WINDOW_WIDTH - 24, QUERY_MAX_HEIGHT)
        query_scroll = Gtk.ScrolledWindow()
        query_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        query_scroll.set_propagate_natural_height(True)
        query_scroll.set_max_content_height(QUERY_MAX_HEIGHT)
        query_scroll.set_child(self.view)
        self.direction = Gtk.Label(label="", xalign=0)
        self.engine = Gtk.Label(label="", xalign=1)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(self.direction)
        head.append(self.engine)
        self.message = Gtk.Label(label="", xalign=0, wrap=True)
        self.result = Gtk.Label(label="", xalign=0, wrap=True, selectable=True)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(True)
        scroller.set_max_content_height(RESULT_MAX_HEIGHT)
        scroller.set_child(self.result)
        self.download = Gtk.Button(label="Download languages")
        self.download.set_visible(False)
        self.copy_button = Gtk.Button(label="Copy")
        self.settings_button = Gtk.Button(label="Settings")
        from dydict.settings_view import build_settings

        self.settings = build_settings(controller._config, self._save_config)
        self.settings.set_visible(False)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.swap_button = Gtk.Button(label="Swap")
        actions.append(self.swap_button)
        actions.append(self.copy_button)
        actions.append(self.download)
        actions.append(self.settings_button)

        root.append(query_scroll)
        root.append(head)
        root.append(self.message)
        root.append(scroller)
        root.append(actions)
        root.append(self.settings)
        outer = Gtk.ScrolledWindow()
        outer.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer.set_overlay_scrolling(False)
        outer.set_propagate_natural_height(True)
        outer.set_max_content_height(WINDOW_MAX_HEIGHT)
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
        self.download.connect("clicked", lambda _b: self._download_clicked())
        self.settings_button.connect("clicked", lambda _b: self._toggle_settings())
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", self._on_leave)
        self.window.add_controller(focus)
        self.window.connect("close-request", self._on_close)
        self._Gdk = Gdk

    def _toggle_settings(self) -> None:
        show = not self.settings.get_visible()
        self.settings.set_visible(show)
        self._outer.set_max_content_height(window_content_limit(show))

    def show_text(self, raw: str) -> None:
        from dydict.selection import prepare_query

        prepared, _shortened = prepare_query(raw)
        generation = self.controller.open_with()
        self._clear_query_view()
        self.window.set_visible(True)
        self._set_text(prepared)
        self.view.grab_focus()
        self._GLib.idle_add(self._arm_leave)
        self._start(prepared, generation)

    def _clear_query_view(self) -> None:
        self._shown_generation = None
        self.direction.set_text("")
        self.engine.set_text("")
        self.result.set_text("")
        self.message.set_text("")
        self.download.set_visible(False)
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
        import threading

        def work():
            try:
                result = self.controller.translate_now(text, generation)
            except Exception as exc:
                self._GLib.idle_add(self._worker_failed, str(exc), generation)
                return
            if result is not None:
                self._GLib.idle_add(self._apply, result, generation)

        threading.Thread(target=work, daemon=True).start()

    def _worker_failed(self, message: str, generation: int) -> bool:
        if generation != self.controller.generation:
            return False
        self.message.set_text(message)
        return False

    def _apply(self, result, generation=None) -> bool:
        if generation is not None and generation != self.controller.generation:
            return False
        self.direction.set_text(result.direction_line)
        self.engine.set_text(result.engine or "")
        self.result.set_text(result.translation)
        notice = self.controller.notice or result.message
        self.message.set_text(notice)
        self.download.set_visible(result.kind == "need_package")
        if result.kind == "need_package":
            from dydict.detect import language_name

            left = language_name(result.package_source, self.controller._names)
            right = language_name(result.package_target, self.controller._names)
            self.download.set_label(f"Download {left} and {right}")
        direction = self.controller.direction
        self.swap_button.set_sensitive(direction is not None and direction.source != "auto")
        self._shown_generation = self.controller.generation
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

    def _download_clicked(self) -> None:
        result = self.controller.result
        if result is None or result.kind != "need_package":
            return
        self.download.set_sensitive(False)

        def work():
            from dydict.engines import DownloadError, argos_install

            try:
                argos_install(result.package_source, result.package_target)
            except DownloadError as exc:
                self._GLib.idle_add(self._download_finished, str(exc))
                return
            self._GLib.idle_add(self._download_finished, "")

        import threading

        threading.Thread(target=work, daemon=True).start()

    def _download_finished(self, error: str) -> bool:
        self.download.set_sensitive(True)
        if error:
            self.message.set_text(error)
            return False
        text = self._current_text()
        generation = self.controller.retry()
        self._clear_query_view()
        self._start(text, generation)
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

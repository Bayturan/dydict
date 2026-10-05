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

    def swap(self, text: str) -> QueryResult | None:
        if self._direction is None:
            return None
        swapped = swap_direction(self._direction)
        if swapped is None:
            return None
        self._override = swapped
        self._generation += 1
        return self.translate_now(text, self._generation)

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

"""Read the primary selection and write the clipboard."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass

MAX_CHARS = 2000
READ_TIMEOUT_SEC = 0.2
COPY_TIMEOUT_SEC = 2.0

WAYLAND_READ = ["wl-paste", "--primary", "--no-newline", "--type", "text/plain"]
WAYLAND_WRITE = ["wl-copy"]
XCLIP_READ = ["xclip", "-out", "-selection", "primary"]
XCLIP_WRITE = ["xclip", "-selection", "clipboard", "-in"]
XSEL_READ = ["xsel", "--primary", "--output"]
XSEL_WRITE = ["xsel", "--clipboard", "--input"]


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str


class CopyError(Exception):
    pass


def prepare_query(text: str) -> tuple[str, bool]:
    trimmed = text.strip()
    if len(trimmed) <= MAX_CHARS:
        return trimmed, False
    return trimmed[:MAX_CHARS], True


def clipboard_plan(
    env: Mapping[str, str],
    which: Callable[[str], str | None],
) -> tuple[list[str], list[str]] | None:
    if env.get("WAYLAND_DISPLAY"):
        return WAYLAND_READ, WAYLAND_WRITE
    if env.get("DISPLAY"):
        if which("xclip"):
            return XCLIP_READ, XCLIP_WRITE
        if which("xsel"):
            return XSEL_READ, XSEL_WRITE
    return None


def read_primary(env: Mapping[str, str], run, which: Callable[[str], str | None]) -> str:
    plan = clipboard_plan(env, which)
    if plan is None:
        return ""
    argv, _write = plan
    try:
        result = run(argv, READ_TIMEOUT_SEC, None)
    except (FileNotFoundError, TimeoutError, OSError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def copy_text(text: str, env: Mapping[str, str], run, which: Callable[[str], str | None]) -> None:
    plan = clipboard_plan(env, which)
    if plan is None:
        raise CopyError("missing tool")
    _read, argv = plan
    try:
        result = run(argv, COPY_TIMEOUT_SEC, text)
    except (FileNotFoundError, TimeoutError, OSError) as exc:
        raise CopyError("missing tool") from exc
    if result.returncode != 0:
        raise CopyError("copy failed")


def subprocess_run(argv: list[str], timeout: float, stdin: str | None) -> CommandResult:
    try:
        if stdin is None:
            completed = subprocess.run(
                argv,
                input=None,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            stdout = completed.stdout
        else:
            # wl-copy, xclip, and xsel fork a resident process that inherits
            # stdout and stderr. Open pipes from capture_output never close,
            # so the parent waits until the copy timeout.
            completed = subprocess.run(
                argv,
                input=stdin,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
            )
            stdout = ""
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(argv[0]) from exc
    return CommandResult(completed.returncode, stdout)

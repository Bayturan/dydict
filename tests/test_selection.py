import pytest

from dydict.selection import (
    COPY_TIMEOUT_SEC,
    READ_TIMEOUT_SEC,
    CommandResult,
    CopyError,
    clipboard_plan,
    copy_text,
    prepare_query,
    read_primary,
)


def which_factory(found: set[str]):
    def which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in found else None
    return which


def test_prepare_query_trims_and_cuts():
    assert prepare_query("  hello \n") == ("hello", False)
    assert prepare_query("   \n") == ("", False)
    text, shortened = prepare_query("  " + ("a" * 2001))
    assert shortened is True
    assert text == "a" * 2000
    assert len(text) == 2000


def test_wayland_wins_when_display_is_also_set():
    env = {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0"}
    read_argv, write_argv = clipboard_plan(env, which_factory({"xclip"}))
    assert read_argv == ["wl-paste", "--primary", "--no-newline", "--type", "text/plain"]
    assert write_argv == ["wl-copy"]


def test_x11_prefers_xclip_then_xsel():
    xclip = clipboard_plan({"DISPLAY": ":0"}, which_factory({"xclip", "xsel"}))
    xsel = clipboard_plan({"DISPLAY": ":0"}, which_factory({"xsel"}))
    neither = clipboard_plan({"DISPLAY": ":0"}, which_factory(set()))
    assert xclip[0][0] == "xclip"
    assert xclip[1] == ["xclip", "-selection", "clipboard", "-in"]
    assert xsel[0] == ["xsel", "--primary", "--output"]
    assert xsel[1] == ["xsel", "--clipboard", "--input"]
    assert neither is None


def test_timeout_and_missing_tool_are_empty():
    def explode(argv, timeout, stdin):
        raise TimeoutError("hung")

    def missing(argv, timeout, stdin):
        raise FileNotFoundError(argv[0])

    env = {"WAYLAND_DISPLAY": "wayland-1"}
    which = which_factory(set())
    assert read_primary(env, explode, which) == ""
    assert read_primary(env, missing, which) == ""
    assert READ_TIMEOUT_SEC == 0.2


def test_nonzero_exit_is_empty():
    def run(argv, timeout, stdin):
        assert timeout == READ_TIMEOUT_SEC
        return CommandResult(1, "not text")

    assert read_primary({"WAYLAND_DISPLAY": "wayland-1"}, run, which_factory(set())) == ""


def test_copy_sends_translation_on_stdin():
    seen = {}

    def run(argv, timeout, stdin):
        seen["argv"] = argv
        seen["timeout"] = timeout
        seen["stdin"] = stdin
        return CommandResult(0, "")

    copy_text("merhaba", {"WAYLAND_DISPLAY": "wayland-1"}, run, which_factory(set()))
    assert seen == {"argv": ["wl-copy"], "timeout": COPY_TIMEOUT_SEC, "stdin": "merhaba"}


def test_copy_without_a_tool_raises():
    with pytest.raises(CopyError):
        copy_text("x", {}, lambda *args: CommandResult(0, ""), which_factory(set()))

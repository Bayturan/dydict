"""Single-instance socket. GTK startup is added in Task 7."""

from __future__ import annotations

import os
import socket
import threading
from collections.abc import Callable, Mapping
from pathlib import Path

SOCKET_MESSAGE = "DyDict is not running and the instance socket could not be opened."


class InstanceError(Exception):
    pass


def socket_path(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    values = os.environ if env is None else env
    runtime = values.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "dydict.sock"
    base = Path.home() if home is None else home
    return base / ".cache" / "dydict" / "dydict.sock"


class InstanceServer:
    def __init__(self, path: Path, on_toggle: Callable[[], None]) -> None:
        self.path = path
        self.on_toggle = on_toggle
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def bind(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(self.path))
        except OSError:
            sock.close()
            raise
        sock.listen(8)
        sock.settimeout(0.2)
        self._sock = sock

    def serve_forever(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _addr = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            try:
                data = b""
                while b"\n" not in data:
                    chunk = conn.recv(64)
                    if not chunk:
                        break
                    data += chunk
                    if len(data) > 64:
                        break
                if data.startswith(b"toggle"):
                    self.on_toggle()
            finally:
                conn.close()

    def start(self) -> None:
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        sock = self._sock
        self._sock = None
        if sock is not None:
            sock.close()
            if self.path.exists():
                self.path.unlink()
        if self._thread is not None:
            self._thread.join(timeout=1)


def send_toggle(path: Path) -> bool:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        sock.connect(str(path))
        sock.sendall(b"toggle\n")
        return True
    except OSError:
        return False
    finally:
        sock.close()


def claim_or_toggle(path: Path, on_toggle: Callable[[], None]) -> InstanceServer | None:
    if path.exists() and send_toggle(path):
        return None
    if path.exists():
        try:
            path.unlink()
        except OSError as exc:
            raise InstanceError(SOCKET_MESSAGE) from exc
    server = InstanceServer(path, on_toggle)
    try:
        server.bind()
    except OSError:
        server.close()
        if send_toggle(path):
            return None
        raise InstanceError(SOCKET_MESSAGE)
    return server


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    floating = "--floating" in args
    path = socket_path()
    holder = {"toggle": lambda: None}
    try:
        server = claim_or_toggle(path, lambda: holder["toggle"]())
    except InstanceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if server is None:
        return 0

    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk

    GLib.set_prgname("dydict")
    from dydict.config import LANGUAGES, config_path, load_config, save_config
    from dydict.window import OfflineEngine, OnlineEngine, PopupController, build_popup

    class LinguaDetect:
        def __init__(self) -> None:
            from lingua import Language, LanguageDetectorBuilder
            from dydict.detect import LINGUA_ENUM_NAMES

            languages = [getattr(Language, name) for name in LINGUA_ENUM_NAMES.values()]
            self._detector = LanguageDetectorBuilder.from_languages(*languages).build()

        def detect(self, text: str):
            values = self._detector.compute_language_confidence_values(text)
            if not values:
                return None, 0.0
            best = values[0]
            return best.language.iso_code_639_1.value, best.value

    cfg_path = config_path()
    state = {"config": load_config(cfg_path)}

    def current_config():
        return state["config"]

    def on_save(config):
        state["config"] = config
        save_config(config, cfg_path)

    controller = PopupController(
        state["config"],
        LinguaDetect(),
        OnlineEngine(current_config),
        OfflineEngine(),
        LANGUAGES,
    )
    popup = build_popup(controller, on_save)

    import os
    import shutil

    from dydict.selection import read_primary, subprocess_run
    from dydict.shell import apply_shell, center_plain_x11

    overlay = apply_shell(popup.window, floating)
    raw = read_primary(os.environ, subprocess_run, shutil.which)
    popup.show_text(raw)
    if not overlay:
        center_plain_x11(popup.window)

    def toggle():
        GLib.idle_add(popup.toggle)

    holder["toggle"] = toggle
    server.start()
    loop = GLib.MainLoop()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, __import__("signal").SIGINT, loop.quit)
    try:
        loop.run()
    finally:
        server.close()
    return 0

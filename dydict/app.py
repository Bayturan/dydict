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

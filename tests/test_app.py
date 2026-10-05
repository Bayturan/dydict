import threading
from pathlib import Path

import pytest

from dydict.app import InstanceError, claim_or_toggle, send_toggle, socket_path


def test_socket_path_uses_runtime_dir_or_cache():
    home = Path("/home/tester")
    assert socket_path({"XDG_RUNTIME_DIR": "/run/user/1"}, home) == Path("/run/user/1/dydict.sock")
    assert socket_path({}, home) == home / ".cache" / "dydict" / "dydict.sock"
    assert socket_path({"XDG_RUNTIME_DIR": ""}, home) == home / ".cache" / "dydict" / "dydict.sock"


def test_second_process_toggles_and_does_not_bind(tmp_path: Path):
    path = tmp_path / "dydict.sock"
    fired = threading.Event()
    server = claim_or_toggle(path, fired.set)
    assert server is not None
    server.start()
    try:
        assert claim_or_toggle(path, lambda: None) is None
        assert fired.wait(1)
    finally:
        server.close()


def test_stale_socket_file_is_replaced(tmp_path: Path):
    path = tmp_path / "dydict.sock"
    path.write_text("stale", encoding="utf-8")
    fired = threading.Event()
    server = claim_or_toggle(path, fired.set)
    assert server is not None
    server.start()
    try:
        assert send_toggle(path) is True
        assert fired.wait(1)
    finally:
        server.close()


def test_unlink_failure_raises(tmp_path: Path):
    path = tmp_path / "dydict.sock"
    path.mkdir()
    with pytest.raises(InstanceError, match="could not be opened"):
        claim_or_toggle(path, lambda: None)

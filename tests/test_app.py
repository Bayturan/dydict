import socket
import threading
import time
from pathlib import Path

import pytest

from dydict.app import InstanceError, InstanceServer, claim_or_toggle, send_toggle, socket_path


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


def test_silent_client_does_not_block_the_next_toggle(tmp_path: Path):
    path = tmp_path / "dydict.sock"
    fired = threading.Event()
    server = InstanceServer(path, fired.set)
    server.bind()
    server.start()
    silent = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        silent.connect(str(path))
        time.sleep(0.15)
        started = time.monotonic()
        assert send_toggle(path) is True
        assert fired.wait(1.5)
        assert time.monotonic() - started < 1.5
    finally:
        silent.close()
        server.close()


def test_unlink_failure_raises(tmp_path: Path):
    path = tmp_path / "dydict.sock"
    path.mkdir()
    with pytest.raises(InstanceError, match="could not be opened"):
        claim_or_toggle(path, lambda: None)


def test_language_code_reads_the_iso_name():
    from lingua import Language

    from dydict.app import language_code

    class Code:
        name = "TR"

    class FakeLanguage:
        iso_code_639_1 = Code()

    assert language_code(FakeLanguage()) == "tr"
    assert language_code(Language.ENGLISH) == "en"
    assert language_code(Language.BOKMAL) == "nb"

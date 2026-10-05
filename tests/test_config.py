import os
from pathlib import Path

import pytest

from dydict.config import (
    DEFAULT_SECOND,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_URL,
    LANGUAGES,
    Config,
    config_path,
    load_config,
    save_config,
    settings_error,
    valid_online_url,
)


SPEC_CODES = [
    "en", "tr", "de", "fr", "es", "it", "pt", "nl", "pl", "ru", "uk", "sv",
    "da", "fi", "nb", "cs", "ro", "hu", "el", "bg", "ar", "he", "hi", "zh",
    "ja", "ko", "vi", "id", "fa", "th",
]


def test_language_list_matches_spec():
    assert list(LANGUAGES) == SPEC_CODES
    assert LANGUAGES["nb"] == "Norwegian Bokmål"
    assert LANGUAGES["tr"] == "Turkish"


def test_config_path_uses_xdg_then_home():
    home = Path("/home/tester")
    assert config_path(env={}, home=home) == home / ".config" / "dydict" / "config.toml"
    assert config_path(env={"XDG_CONFIG_HOME": "/tmp/cfg"}, home=home) == Path(
        "/tmp/cfg/dydict/config.toml"
    )


def test_missing_file_loads_defaults(tmp_path: Path):
    loaded = load_config(tmp_path / "missing.toml")
    assert loaded == Config()
    assert loaded.main_language == "tr"
    assert loaded.second_language == DEFAULT_SECOND
    assert loaded.online_url == DEFAULT_URL
    assert loaded.online_api_key == ""
    assert loaded.timeout_ms == DEFAULT_TIMEOUT_MS


def test_broken_toml_loads_defaults(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("main_language = [\n", encoding="utf-8")
    assert load_config(path) == Config()


def test_unknown_language_resets_both_languages_only(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '\n'.join([
            'main_language = "de"',
            'second_language = "xx"',
            'online_url = "http://127.0.0.1:5000"',
            'online_api_key = "secret"',
            'timeout_ms = 900',
        ]),
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert loaded.main_language == "tr"
    assert loaded.second_language == "en"
    assert loaded.online_url == "http://127.0.0.1:5000"
    assert loaded.online_api_key == "secret"
    assert loaded.timeout_ms == 900


def test_equal_languages_reset_both(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('main_language = "en"\nsecond_language = "en"\n', encoding="utf-8")
    loaded = load_config(path)
    assert loaded.main_language == "tr"
    assert loaded.second_language == "en"


def test_bad_url_and_bad_timeout_reset_those_keys(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '\n'.join([
            'main_language = "de"',
            'second_language = "fr"',
            'online_url = "ftp://example.com"',
            'timeout_ms = 0',
        ]),
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert loaded.main_language == "de"
    assert loaded.second_language == "fr"
    assert loaded.online_url == DEFAULT_URL
    assert loaded.timeout_ms == DEFAULT_TIMEOUT_MS


def test_boolean_timeout_is_rejected(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("timeout_ms = true\n", encoding="utf-8")
    assert load_config(path).timeout_ms == DEFAULT_TIMEOUT_MS


def test_round_trip_keeps_api_key(tmp_path: Path):
    path = tmp_path / "dydict" / "config.toml"
    key = 'abc"def#ghi\\'
    original = Config("de", "fr", "https://example.com/lt", key, 1800)
    save_config(original, path)
    assert load_config(path) == original


def test_save_forces_mode_0600(tmp_path: Path):
    path = tmp_path / "config.toml"
    old = os.umask(0)
    try:
        save_config(Config(), path)
    finally:
        os.umask(old)
    assert path.stat().st_mode & 0o777 == 0o600


def test_settings_error_messages():
    assert valid_online_url("https://libretranslate.com")
    assert valid_online_url("http://127.0.0.1:5000")
    assert not valid_online_url("ftp://example.com")
    assert not valid_online_url("https://")
    assert settings_error("en", "en", "https://example.com") == (
        "Main and second language must differ."
    )
    assert settings_error("en", "tr", "ftp://example.com") == (
        "Server URL must be http or https."
    )
    assert settings_error("en", "en", "ftp://example.com") == (
        "Main and second language must differ."
    )
    assert settings_error("de", "fr", "https://example.com") is None

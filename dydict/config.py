"""Load and save DyDict settings."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import tomli_w

LANGUAGES: dict[str, str] = {
    "en": "English",
    "tr": "Turkish",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "uk": "Ukrainian",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "nb": "Norwegian Bokmål",
    "cs": "Czech",
    "ro": "Romanian",
    "hu": "Hungarian",
    "el": "Greek",
    "bg": "Bulgarian",
    "ar": "Arabic",
    "he": "Hebrew",
    "hi": "Hindi",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "fa": "Persian",
    "th": "Thai",
}

DEFAULT_MAIN = "tr"
DEFAULT_SECOND = "en"
DEFAULT_URL = "https://libretranslate.com"
DEFAULT_TIMEOUT_MS = 2500

DIFFER_MESSAGE = "Main and second language must differ."
URL_MESSAGE = "Server URL must be http or https."


@dataclass(frozen=True)
class Config:
    main_language: str = DEFAULT_MAIN
    second_language: str = DEFAULT_SECOND
    online_url: str = DEFAULT_URL
    online_api_key: str = ""
    timeout_ms: int = DEFAULT_TIMEOUT_MS


def config_path(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    values = os.environ if env is None else env
    custom = values.get("XDG_CONFIG_HOME")
    if custom:
        root = Path(custom)
    elif home is not None:
        root = home / ".config"
    else:
        root = Path.home() / ".config"
    return root / "dydict" / "config.toml"


def valid_online_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def settings_error(main: str, second: str, url: str) -> str | None:
    if main not in LANGUAGES or second not in LANGUAGES or main == second:
        return DIFFER_MESSAGE
    if not valid_online_url(url):
        return URL_MESSAGE
    return None


def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return Config()
    if not isinstance(raw, dict):
        return Config()
    return _from_mapping(raw)


def _from_mapping(raw: dict) -> Config:
    main = raw.get("main_language", DEFAULT_MAIN)
    second = raw.get("second_language", DEFAULT_SECOND)
    languages_ok = (
        isinstance(main, str)
        and isinstance(second, str)
        and main in LANGUAGES
        and second in LANGUAGES
        and main != second
    )
    if not languages_ok:
        main = DEFAULT_MAIN
        second = DEFAULT_SECOND
    url = raw.get("online_url", DEFAULT_URL)
    if not isinstance(url, str) or not valid_online_url(url):
        url = DEFAULT_URL
    key = raw.get("online_api_key", "")
    if not isinstance(key, str):
        key = ""
    timeout = raw.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        timeout = DEFAULT_TIMEOUT_MS
    return Config(main, second, url, key, timeout)


def save_config(config: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "main_language": config.main_language,
        "second_language": config.second_language,
        "online_url": config.online_url,
        "online_api_key": config.online_api_key,
        "timeout_ms": config.timeout_ms,
    }
    path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    path.chmod(0o600)

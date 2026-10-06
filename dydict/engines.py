"""Online LibreTranslate or DeepL.

A local API is not part of this install. The optional ``dydict-local``
package registers one through the ``dydict.engines`` entry point.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from dydict.config import valid_online_url

# A pasted server field often repeats the scheme or includes /v2/translate.
_REPEATED_SCHEME = re.compile(r"^(?:https?://)+", re.IGNORECASE)
_DEEPL_HOSTS = frozenset({"api-free.deepl.com", "api.deepl.com"})
# DeepL rejects bare EN, PT, and ZH as target languages.
_DEEPL_TARGETS = {"en": "EN-US", "pt": "PT-BR", "zh": "ZH-HANS"}


class OnlineError(Exception):
    def __init__(self, message: str = "online failed") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class EngineSuccess:
    text: str
    engine: str


@dataclass(frozen=True)
class EngineFailure:
    message: str
    package_source: str | None
    package_target: str | None


def is_current(started: int, current: int) -> bool:
    return started == current


def normalize_online_url(online_url: str) -> str:
    url = online_url.strip()
    match = _REPEATED_SCHEME.match(url)
    if match is None or match.group(0).lower().count("://") < 2:
        return url
    first = url[: url.lower().find("://") + 3]
    return first + url[match.end() :]


def deepl_host(online_url: str) -> str | None:
    host = urlparse(online_url).hostname
    if host in _DEEPL_HOSTS:
        return host
    return None


def deepl_code(code: str, *, target: bool) -> str:
    folded = code.strip().lower()
    if target and folded in _DEEPL_TARGETS:
        return _DEEPL_TARGETS[folded]
    return folded.upper()


def translate_endpoint(online_url: str) -> str:
    return online_url.rstrip("/") + "/translate"


def deepl_endpoint(online_url: str) -> str:
    return f"https://{deepl_host(online_url)}/v2/translate"


def build_translate_body(text: str, source: str, target: str, api_key: str) -> dict:
    body = {"q": text, "source": source, "target": target, "format": "text"}
    if api_key:
        body["api_key"] = api_key
    return body


def build_deepl_body(text: str, source: str, target: str) -> dict:
    body: dict = {"text": [text], "target_lang": deepl_code(target, target=True)}
    if source != "auto":
        body["source_lang"] = deepl_code(source, target=False)
    return body


def parse_online_response(status: int, payload: bytes) -> str:
    if status != 200:
        raise OnlineError(f"HTTP {status}")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise OnlineError("bad response") from exc
    text = data.get("translatedText") if isinstance(data, dict) else None
    if not isinstance(text, str):
        raise OnlineError("bad response")
    return text


def parse_deepl_response(status: int, payload: bytes) -> str:
    if status != 200:
        raise OnlineError(f"HTTP {status}")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise OnlineError("bad response") from exc
    translations = data.get("translations") if isinstance(data, dict) else None
    first = translations[0] if isinstance(translations, list) and translations else None
    if not isinstance(first, dict):
        raise OnlineError("bad response")
    text = first.get("text")
    if not isinstance(text, str):
        raise OnlineError("bad response")
    return text


def online_translate(
    online_url: str,
    text: str,
    source: str,
    target: str,
    api_key: str,
    timeout_ms: int,
    post,
) -> str:
    normalized = normalize_online_url(online_url)
    if not valid_online_url(normalized):
        raise OnlineError("bad url")
    if deepl_host(normalized) is not None:
        url = deepl_endpoint(normalized)
        body = build_deepl_body(text, source, target)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"DeepL-Auth-Key {api_key}"
        finish = parse_deepl_response
    else:
        url = translate_endpoint(normalized)
        body = build_translate_body(text, source, target, api_key)
        headers = {"Content-Type": "application/json"}
        finish = parse_online_response
    data = json.dumps(body).encode("utf-8")
    try:
        status, payload = post(url, data, headers, timeout_ms / 1000)
    except OnlineError:
        raise
    except Exception as exc:
        raise OnlineError(str(exc)) from exc
    return finish(status, payload)


def translate_with_fallback(text: str, source: str, target: str, online, offline=None):
    """Translate online. ``offline`` is the optional local API, never Argos."""
    try:
        translated = online.translate(text, source, target)
        return EngineSuccess(translated, "online")
    except OnlineError as exc:
        if offline is None:
            return EngineFailure(str(exc), None, None)
        try:
            translated = offline.translate(text, source, target)
        except OnlineError as local_exc:
            return EngineFailure(str(local_exc), None, None)
        return EngineSuccess(translated, "local")


def load_local_engine():
    """Load the ``dydict-local`` engine when that package is installed."""
    from importlib.metadata import entry_points

    matches = [item for item in entry_points(group="dydict.engines") if item.name == "local"]
    if not matches:
        return None
    return matches[0].load()()


def urllib_post(url: str, data: bytes, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        raise OnlineError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise OnlineError(str(exc.reason)) from exc

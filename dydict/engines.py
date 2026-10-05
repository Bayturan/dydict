"""Online LibreTranslate and offline Argos Translate."""

from __future__ import annotations

import json
from dataclasses import dataclass

from dydict.config import LANGUAGES, valid_online_url


class OnlineError(Exception):
    def __init__(self, message: str = "online failed") -> None:
        super().__init__(message)


class PackageMissing(Exception):
    def __init__(self, source: str, target: str) -> None:
        super().__init__(f"{source} → {target}")
        self.source = source
        self.target = target


class DownloadError(Exception):
    pass


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


def translate_endpoint(online_url: str) -> str:
    return online_url.rstrip("/") + "/translate"


def build_translate_body(text: str, source: str, target: str, api_key: str) -> dict:
    body = {"q": text, "source": source, "target": target, "format": "text"}
    if api_key:
        body["api_key"] = api_key
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


def online_translate(
    online_url: str,
    text: str,
    source: str,
    target: str,
    api_key: str,
    timeout_ms: int,
    post,
) -> str:
    if not valid_online_url(online_url):
        raise OnlineError("bad url")
    url = translate_endpoint(online_url)
    body = build_translate_body(text, source, target, api_key)
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    try:
        status, payload = post(url, data, headers, timeout_ms / 1000)
    except OnlineError:
        raise
    except Exception as exc:
        raise OnlineError(str(exc)) from exc
    return parse_online_response(status, payload)


def translate_with_fallback(text: str, source: str, target: str, online, offline):
    try:
        translated = online.translate(text, source, target)
        return EngineSuccess(translated, "online")
    except OnlineError as exc:
        message = str(exc)
        if source == "auto":
            return EngineFailure(message, None, None)
        try:
            translated = offline.translate(text, source, target)
        except PackageMissing:
            return EngineFailure(message, source, target)
        except OnlineError as offline_exc:
            return EngineFailure(str(offline_exc), None, None)
        return EngineSuccess(translated, "offline")


def directions_to_install(source: str, target: str, allowed: set[str]) -> list[tuple[str, str]]:
    if source == "auto" or source not in allowed or target not in allowed or source == target:
        return []
    return [(source, target), (target, source)]


def install_directions(source: str, target: str, allowed: set[str], packages, download, install) -> None:
    pairs = directions_to_install(source, target, allowed)
    if not pairs:
        raise DownloadError("no package")
    by_pair = {(pkg.from_code, pkg.to_code): pkg for pkg in packages}
    for pair in pairs:
        pkg = by_pair.get(pair)
        if pkg is None:
            raise DownloadError(f"no package for {pair[0]} → {pair[1]}")
        try:
            path = download(pkg)
            install(path)
        except DownloadError:
            raise
        except Exception as exc:
            raise DownloadError(str(exc)) from exc


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


def argos_offline_translate(text: str, source: str, target: str) -> str:
    import argostranslate.translate

    languages = argostranslate.translate.get_installed_languages()
    from_lang = next((item for item in languages if item.code == source), None)
    to_lang = next((item for item in languages if item.code == target), None)
    if from_lang is None or to_lang is None:
        raise PackageMissing(source, target)
    translation = from_lang.get_translation(to_lang)
    if translation is None:
        raise PackageMissing(source, target)
    return translation.translate(text)


def argos_install(source: str, target: str) -> None:
    import argostranslate.package

    try:
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(str(exc)) from exc
    install_directions(
        source,
        target,
        set(LANGUAGES),
        available,
        download=lambda pkg: pkg.download(),
        install=lambda path: argostranslate.package.install_from_path(path),
    )

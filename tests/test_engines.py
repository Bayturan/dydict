import json

import pytest

from dydict.config import LANGUAGES
from dydict.engines import (
    DownloadError,
    EngineFailure,
    EngineSuccess,
    OnlineError,
    PackageMissing,
    build_translate_body,
    directions_to_install,
    install_directions,
    is_current,
    online_translate,
    parse_online_response,
    translate_endpoint,
    translate_with_fallback,
)


class Online:
    def __init__(self, text: str | None = None, error: Exception | None = None):
        self.text = text
        self.error = error
        self.calls = []

    def translate(self, text: str, source: str, target: str) -> str:
        self.calls.append((text, source, target))
        if self.error:
            raise self.error
        return self.text or ""


class Offline(Online):
    pass


def test_online_success_does_not_call_offline():
    offline = Offline("nope")
    result = translate_with_fallback("hi", "en", "tr", Online("merhaba"), offline)
    assert result == EngineSuccess("merhaba", "online")
    assert offline.calls == []


def test_concrete_online_failure_calls_offline():
    result = translate_with_fallback(
        "hi", "en", "tr", Online(error=OnlineError("down")), Offline("merhaba")
    )
    assert result == EngineSuccess("merhaba", "offline")


def test_auto_online_failure_skips_offline():
    offline = Offline("merhaba")
    result = translate_with_fallback(
        "hi", "auto", "tr", Online(error=OnlineError("down")), offline
    )
    assert result == EngineFailure("down", None, None)
    assert offline.calls == []


def test_missing_package_offers_that_pair():
    offline = Offline(error=PackageMissing("de", "tr"))
    result = translate_with_fallback(
        "hallo", "de", "tr", Online(error=OnlineError("down")), offline
    )
    assert result == EngineFailure("down", "de", "tr")


def test_stale_generation_is_not_current():
    assert is_current(1, 2) is False
    assert is_current(2, 2) is True


def test_endpoint_collapses_trailing_slash():
    assert translate_endpoint("https://libretranslate.com/") == (
        "https://libretranslate.com/translate"
    )
    assert translate_endpoint("https://libretranslate.com") == (
        "https://libretranslate.com/translate"
    )


def test_body_omits_empty_api_key_and_includes_a_real_one():
    assert "api_key" not in build_translate_body("hi", "en", "tr", "")
    body = build_translate_body("hi", "en", "tr", "secret")
    assert body == {
        "q": "hi",
        "source": "en",
        "target": "tr",
        "format": "text",
        "api_key": "secret",
    }


def test_non_string_translation_is_rejected():
    with pytest.raises(OnlineError):
        parse_online_response(200, b'{"translatedText": null}')
    with pytest.raises(OnlineError):
        parse_online_response(500, b'{"translatedText": "x"}')


def test_non_string_translation_falls_back():
    def post(url, data, headers, timeout):
        return 200, b'{"translatedText": null}'

    class HttpOnline:
        def translate(self, text, source, target):
            return online_translate(
                "https://example.com", text, source, target, "", 2500, post
            )

    result = translate_with_fallback("hello", "en", "tr", HttpOnline(), Offline("yerel"))
    assert result == EngineSuccess("yerel", "offline")


def test_online_translate_posts_json_with_timeout_seconds():
    seen = {}

    def post(url, data, headers, timeout):
        seen["url"] = url
        seen["body"] = json.loads(data)
        seen["timeout"] = timeout
        seen["content_type"] = headers["Content-Type"]
        return 200, b'{"translatedText": "merhaba"}'

    text = online_translate(
        "https://libretranslate.com/", "hello", "en", "tr", "", 2500, post
    )
    assert text == "merhaba"
    assert seen["url"] == "https://libretranslate.com/translate"
    assert seen["body"]["q"] == "hello"
    assert seen["timeout"] == 2.5
    assert seen["content_type"] == "application/json"


def test_bad_scheme_does_not_post():
    def post(url, data, headers, timeout):
        raise AssertionError("posted")

    with pytest.raises(OnlineError):
        online_translate("ftp://example.com", "hi", "en", "tr", "", 2500, post)


def test_german_download_is_both_directions_of_that_pair():
    assert directions_to_install("de", "tr", set(LANGUAGES)) == [("de", "tr"), ("tr", "de")]
    assert directions_to_install("auto", "tr", set(LANGUAGES)) == []

    class Package:
        def __init__(self, source, target):
            self.from_code = source
            self.to_code = target

    downloaded = []
    packages = [Package("de", "tr"), Package("tr", "de"), Package("en", "tr")]
    install_directions(
        "de",
        "tr",
        set(LANGUAGES),
        packages,
        download=lambda pkg: downloaded.append((pkg.from_code, pkg.to_code)) or "path",
        install=lambda path: None,
    )
    assert downloaded == [("de", "tr"), ("tr", "de")]


def test_download_failure_is_not_retried():
    class Package:
        from_code = "de"
        to_code = "tr"

    calls = []

    def download(pkg):
        calls.append(pkg)
        raise RuntimeError("disk full")

    with pytest.raises(DownloadError, match="disk full"):
        install_directions(
            "de", "tr", set(LANGUAGES), [Package()], download, lambda path: None
        )
    assert len(calls) == 1

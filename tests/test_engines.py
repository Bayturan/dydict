import json

import pytest

from dydict.engines import (
    EngineFailure,
    EngineSuccess,
    OnlineError,
    build_translate_body,
    is_current,
    load_local_engine,
    online_translate,
    parse_deepl_response,
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


def test_online_success_does_not_call_the_local_engine():
    local = Online("nope")
    result = translate_with_fallback("hi", "en", "tr", Online("merhaba"), local)
    assert result == EngineSuccess("merhaba", "online")
    assert local.calls == []


def test_online_failure_without_a_local_engine_is_the_online_error():
    result = translate_with_fallback("hi", "en", "tr", Online(error=OnlineError("down")))
    assert result == EngineFailure("down", None, None)


def test_installed_local_engine_runs_after_online_failure():
    result = translate_with_fallback(
        "hi", "en", "tr", Online(error=OnlineError("down")), Online("yerel")
    )
    assert result == EngineSuccess("yerel", "local")


def test_default_install_has_no_local_engine():
    assert load_local_engine() is None


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

    result = translate_with_fallback("hello", "en", "tr", HttpOnline())
    assert result == EngineFailure("bad response", None, None)


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


def test_doubled_deepl_url_posts_to_the_free_api():
    seen = {}

    def post(url, data, headers, timeout):
        seen["url"] = url
        seen["body"] = json.loads(data)
        seen["authorization"] = headers.get("Authorization")
        seen["timeout"] = timeout
        return 200, b'{"translations":[{"text":"merhaba","detected_source_language":"EN"}]}'

    text = online_translate(
        "https://https://api-free.deepl.com/v2/translate",
        "hello",
        "en",
        "tr",
        "secret",
        2500,
        post,
    )
    assert text == "merhaba"
    assert seen["url"] == "https://api-free.deepl.com/v2/translate"
    assert seen["body"] == {"text": ["hello"], "source_lang": "EN", "target_lang": "TR"}
    assert seen["authorization"] == "DeepL-Auth-Key secret"
    assert seen["timeout"] == 2.5


def test_deepl_auto_omits_source_and_uses_english_variant():
    seen = {}

    def post(url, data, headers, timeout):
        seen["url"] = url
        seen["body"] = json.loads(data)
        seen["authorization"] = headers.get("Authorization")
        return 200, b'{"translations":[{"text":"hello"}]}'

    text = online_translate(
        "https://api.deepl.com",
        "merhaba",
        "auto",
        "en",
        "",
        2500,
        post,
    )
    assert text == "hello"
    assert seen["url"] == "https://api.deepl.com/v2/translate"
    assert seen["body"] == {"text": ["merhaba"], "target_lang": "EN-US"}
    assert seen["authorization"] is None


def test_deepl_regional_codes_are_target_only():
    bodies = []

    def post(url, data, headers, timeout):
        bodies.append(json.loads(data))
        return 200, b'{"translations":[{"text":"ok"}]}'

    online_translate("https://api-free.deepl.com/v2", "oi", "pt", "zh", "k", 1000, post)
    online_translate("https://api-free.deepl.com/v2/translate/", "hi", "zh", "pt", "k", 1000, post)
    assert bodies[0] == {"text": ["oi"], "source_lang": "PT", "target_lang": "ZH-HANS"}
    assert bodies[1] == {"text": ["hi"], "source_lang": "ZH", "target_lang": "PT-BR"}


def test_deepl_bad_payload_is_rejected():
    with pytest.raises(OnlineError):
        parse_deepl_response(200, b'{"translations":[]}')
    with pytest.raises(OnlineError):
        parse_deepl_response(403, b'{"message":"Forbidden"}')


def test_repeated_scheme_on_libretranslate_uses_the_real_host():
    seen = {}

    def post(url, data, headers, timeout):
        seen["url"] = url
        seen["body"] = json.loads(data)
        return 200, b'{"translatedText": "merhaba"}'

    text = online_translate(
        "https://https://libretranslate.com",
        "hello",
        "en",
        "tr",
        "",
        2500,
        post,
    )
    assert text == "merhaba"
    assert seen["url"] == "https://libretranslate.com/translate"
    assert seen["body"]["q"] == "hello"

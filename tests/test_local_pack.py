import importlib
import json
import sys
from pathlib import Path

from dydict.engines import EngineFailure, EngineSuccess, OnlineError, translate_with_fallback


def _load_local_module():
    root = Path(__file__).resolve().parents[1] / "dydict-local"
    sys.path.insert(0, str(root))
    import dydict_local

    return importlib.reload(dydict_local)


class _FailOnline:
    def translate(self, text, source, target):
        raise OnlineError("down")


def test_local_pack_posts_to_its_own_url(monkeypatch):
    dydict_local = _load_local_module()
    monkeypatch.setenv("DYDICT_LOCAL_URL", "http://127.0.0.1:5000")
    monkeypatch.setenv("DYDICT_LOCAL_API_KEY", "local-key")
    monkeypatch.delenv("DYDICT_LOCAL_TIMEOUT_MS", raising=False)
    seen = {}

    def post(url, data, headers, timeout):
        seen["url"] = url
        seen["body"] = json.loads(data)
        seen["timeout"] = timeout
        return 200, b'{"translatedText": "yerel"}'

    monkeypatch.setattr(dydict_local, "urllib_post", post)
    engine = dydict_local.engine()
    assert engine.translate("hello", "en", "tr") == "yerel"
    assert seen["url"] == "http://127.0.0.1:5000/translate"
    assert seen["body"]["q"] == "hello"
    assert seen["body"]["api_key"] == "local-key"
    assert seen["timeout"] == 2.5

    result = translate_with_fallback("hello", "en", "tr", _FailOnline(), engine)
    assert result == EngineSuccess("yerel", "local")


def test_local_pack_bad_timeout_uses_the_default(monkeypatch):
    dydict_local = _load_local_module()
    monkeypatch.setenv("DYDICT_LOCAL_TIMEOUT_MS", "nope")
    monkeypatch.delenv("DYDICT_LOCAL_API_KEY", raising=False)
    seen = {}

    def post(url, data, headers, timeout):
        seen["timeout"] = timeout
        seen["body"] = json.loads(data)
        return 200, b'{"translatedText": "yerel"}'

    monkeypatch.setattr(dydict_local, "urllib_post", post)
    assert dydict_local.LocalApiEngine().translate("hello", "en", "tr") == "yerel"
    assert seen["timeout"] == 2.5
    assert "api_key" not in seen["body"]


def test_local_failure_replaces_the_online_error(monkeypatch):
    dydict_local = _load_local_module()

    def post(url, data, headers, timeout):
        return 500, b"{}"

    monkeypatch.setattr(dydict_local, "urllib_post", post)
    result = translate_with_fallback(
        "hello", "en", "tr", _FailOnline(), dydict_local.LocalApiEngine()
    )
    assert result == EngineFailure("HTTP 500", None, None)


def test_local_pack_does_not_depend_on_argos():
    text = (Path(__file__).resolve().parents[1] / "dydict-local" / "pyproject.toml").read_text()
    assert "argostranslate" not in text
    assert "torch" not in text
    assert 'dependencies = ["dydict"]' in text

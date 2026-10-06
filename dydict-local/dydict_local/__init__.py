"""Connect DyDict to a local translation API.

This package is not part of the default DyDict install. It does not
download Argos models, PyTorch, or CUDA.
"""

from __future__ import annotations

import os

from dydict.engines import online_translate, urllib_post

DEFAULT_LOCAL_URL = "http://127.0.0.1:5000"


class LocalApiEngine:
    def translate(self, text: str, source: str, target: str) -> str:
        url = os.environ.get("DYDICT_LOCAL_URL", DEFAULT_LOCAL_URL)
        key = os.environ.get("DYDICT_LOCAL_API_KEY", "")
        raw_timeout = os.environ.get("DYDICT_LOCAL_TIMEOUT_MS", "2500")
        try:
            timeout_ms = int(raw_timeout)
        except ValueError:
            timeout_ms = 2500
        return online_translate(url, text, source, target, key, timeout_ms, urllib_post)


def engine() -> LocalApiEngine:
    return LocalApiEngine()

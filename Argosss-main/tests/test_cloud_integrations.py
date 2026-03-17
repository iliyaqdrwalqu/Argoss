import types

import pytest
import requests

from src.connectivity.cloud_object_storage import IBMCloudObjectStorage
from src.connectivity import xai_tts


def test_ibm_cos_status_not_configured(monkeypatch):
    for key in [
        "IBM_COS_ENDPOINT",
        "IBM_COS_API_KEY",
        "IBM_COS_RESOURCE_INSTANCE_ID",
        "IBM_COS_ACCESS_KEY_ID",
        "IBM_COS_SECRET_ACCESS_KEY",
        "IBM_COS_BUCKET",
    ]:
        monkeypatch.delenv(key, raising=False)

    cfg = IBMCloudObjectStorage.from_env()
    assert cfg.is_configured() is False
    assert "не настроен" in cfg.status()


def test_xai_tts_generates_bytes(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key")

    class _Resp:
        ok = True
        status_code = 200
        content = b"audio-bytes"

        def raise_for_status(self):
            return None

    captured = {}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(xai_tts.requests, "post", _fake_post)

    audio = xai_tts.generate_speech_bytes("Привет, Аргос!", language="ru", voice_id="eve")
    assert audio == b"audio-bytes"
    assert captured["url"] == xai_tts.XAI_TTS_ENDPOINT
    assert captured["json"]["text"] == "Привет, Аргос!"
    assert captured["json"]["language"] == "ru"
    assert captured["json"]["voice_id"] == "eve"


def test_xai_tts_requires_api_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        xai_tts.generate_speech_bytes("hello")


def test_xai_tts_rejects_empty_text(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    with pytest.raises(ValueError):
        xai_tts.generate_speech_bytes("   ")


def test_xai_tts_rejects_too_long_text(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    with pytest.raises(ValueError):
        xai_tts.generate_speech_bytes("a" * 15001)


def test_xai_tts_does_not_retry_non_retryable_http_errors(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    monkeypatch.setattr(xai_tts.time, "sleep", lambda *_: None)

    calls = {"count": 0}

    class _Resp:
        ok = False
        status_code = 400
        content = b""

        def raise_for_status(self):
            raise requests.HTTPError("bad request", response=self)

    def _fake_post(url, headers=None, json=None, timeout=None):
        calls["count"] += 1
        return _Resp()

    monkeypatch.setattr(xai_tts.requests, "post", _fake_post)

    with pytest.raises(requests.HTTPError):
        xai_tts.generate_speech_bytes("hello", max_retries=3)

    assert calls["count"] == 1


def test_xai_tts_retries_retryable_status_then_succeeds(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    monkeypatch.setattr(xai_tts.time, "sleep", lambda *_: None)

    calls = {"count": 0}

    class _RetryResp:
        ok = False
        status_code = 503
        content = b""

        def raise_for_status(self):
            raise requests.HTTPError("retryable", response=self)

    class _OkResp:
        ok = True
        status_code = 200
        content = b"audio"

        def raise_for_status(self):
            pass

    def _fake_post(url, headers=None, json=None, timeout=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return _RetryResp()
        return _OkResp()

    monkeypatch.setattr(xai_tts.requests, "post", _fake_post)

    audio = xai_tts.generate_speech_bytes("hello", max_retries=3)
    assert audio == b"audio"
    assert calls["count"] == 2

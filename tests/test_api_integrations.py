"""Tests for Shodan scanner and HuggingFace AI integrations."""
import pytest
import requests

from src.skills.shodan_scanner import ShodanScanner
from src.skills.huggingface_ai import HuggingFaceAI


# ── ShodanScanner ────────────────────────────────────────────────────────────

def test_shodan_not_configured(monkeypatch):
    monkeypatch.delenv("SHODAN_API_KEY", raising=False)
    scanner = ShodanScanner()
    assert scanner.is_configured() is False


def test_shodan_configured(monkeypatch):
    monkeypatch.setenv("SHODAN_API_KEY", "test-key")
    scanner = ShodanScanner()
    assert scanner.is_configured() is True


def test_shodan_explicit_key():
    scanner = ShodanScanner(api_key="explicit-key")
    assert scanner.is_configured() is True


def test_shodan_search_no_key(monkeypatch):
    monkeypatch.delenv("SHODAN_API_KEY", raising=False)
    scanner = ShodanScanner()
    result = scanner._get("/shodan/host/search", {"query": "test"})
    assert result == {"error": "SHODAN_API_KEY is not configured"}


def test_shodan_my_ip_error(monkeypatch):
    monkeypatch.setenv("SHODAN_API_KEY", "test-key")
    scanner = ShodanScanner()

    def _raise(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", _raise)
    result = scanner.my_ip()
    assert result.startswith("error:")


def test_shodan_search_makes_request(monkeypatch):
    monkeypatch.setenv("SHODAN_API_KEY", "test-key")
    scanner = ShodanScanner()
    calls = []

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"matches": [], "total": 0}

    def _get(url, params=None, timeout=None):
        calls.append((url, params))
        return _Resp()

    monkeypatch.setattr(requests, "get", _get)
    result = scanner.search("apache")
    assert result == {"matches": [], "total": 0}
    assert len(calls) == 1
    assert "shodan" in calls[0][0]


# ── HuggingFaceAI ────────────────────────────────────────────────────────────

def test_hf_not_configured(monkeypatch):
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)
    hf = HuggingFaceAI()
    assert hf.is_configured() is False


def test_hf_configured(monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "hf_test")
    hf = HuggingFaceAI()
    assert hf.is_configured() is True


def test_hf_ask_raises_without_token(monkeypatch):
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)
    hf = HuggingFaceAI()
    with pytest.raises(ValueError, match="HUGGINGFACE_TOKEN"):
        hf.ask("hello")


def test_hf_ask_returns_text(monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "hf_test")
    hf = HuggingFaceAI(model="test/model")

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"generated_text": "Hello world"}]

    monkeypatch.setattr(requests, "post", lambda *a, **kw: _Resp())
    result = hf.ask("hi")
    assert result == "Hello world"


def test_hf_embed_returns_floats(monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "hf_test")
    hf = HuggingFaceAI()

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return [0.1, 0.2, 0.3]

    monkeypatch.setattr(requests, "post", lambda *a, **kw: _Resp())
    result = hf.embed("test text")
    assert result == [0.1, 0.2, 0.3]
    assert all(isinstance(v, float) for v in result)


def test_hf_embed_invalid_response(monkeypatch):
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "hf_test")
    hf = HuggingFaceAI()

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"error": "model loading"}

    monkeypatch.setattr(requests, "post", lambda *a, **kw: _Resp())
    result = hf.embed("test text")
    assert result == []


def test_hf_default_model(monkeypatch):
    monkeypatch.delenv("HUGGINGFACE_MODEL", raising=False)
    hf = HuggingFaceAI()
    assert "Mistral" in hf.model or hf.model  # default model is set

#!/usr/bin/env python3
"""
scripts/smoke_api.py — Smoke test for ARGOS Remote Control API.

Usage:
    python scripts/smoke_api.py [BASE_URL] [TOKEN]

Environment variables:
    ARGOS_BASE_URL     Base URL of ARGOS server (default: http://localhost:8080)
    ARGOS_REMOTE_TOKEN Bearer token for API auth (default: empty)

Example:
    ARGOS_BASE_URL=https://xxxx.trycloudflare.com \
    ARGOS_REMOTE_TOKEN=mysecret \
    python scripts/smoke_api.py
"""

import os
import sys
import json

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is required. Run: pip install requests")
    sys.exit(1)

BASE_URL = (
    (sys.argv[1] if len(sys.argv) > 1 else None)
    or os.environ.get("ARGOS_BASE_URL", "http://localhost:8080")
).rstrip("/")

TOKEN = (
    (sys.argv[2] if len(sys.argv) > 2 else None)
    or os.environ.get("ARGOS_REMOTE_TOKEN", "")
)

HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

_pass = 0
_fail = 0


def _ok(label: str, detail: str = ""):
    global _pass
    _pass += 1
    print(f"  ✅  PASS  {label}" + (f"  — {detail}" if detail else ""))


def _fail_msg(label: str, detail: str = ""):
    global _fail
    _fail += 1
    print(f"  ❌  FAIL  {label}" + (f"  — {detail}" if detail else ""))


def test_health():
    """GET /api/health should return status=ok without auth."""
    try:
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200, f"HTTP {r.status_code}"
        data = r.json()
        assert data.get("status") == "ok", f"status={data.get('status')}"
        assert "version" in data, "missing 'version'"
        assert "uptime_seconds" in data, "missing 'uptime_seconds'"
        _ok("GET /api/health", f"version={data['version']}, uptime={data['uptime_seconds']}s")
    except Exception as exc:
        _fail_msg("GET /api/health", str(exc))


def test_health_no_auth_required():
    """GET /api/health must succeed even without auth header."""
    try:
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200, f"HTTP {r.status_code}"
        _ok("GET /api/health (no auth)")
    except Exception as exc:
        _fail_msg("GET /api/health (no auth)", str(exc))


def test_command_auth():
    """POST /api/command should return 401 when token is wrong."""
    if not TOKEN:
        print("  ⏭   SKIP  POST /api/command auth check (no token configured)")
        return
    try:
        r = requests.post(
            f"{BASE_URL}/api/command",
            json={"cmd": "статус"},
            headers={"Authorization": "Bearer wrong_token_xyz"},
            timeout=10,
        )
        assert r.status_code == 401, f"Expected 401 but got HTTP {r.status_code}"
        _ok("POST /api/command (wrong token → 401)")
    except Exception as exc:
        _fail_msg("POST /api/command (wrong token → 401)", str(exc))


def test_command_empty():
    """POST /api/command with empty cmd should return 400."""
    try:
        r = requests.post(
            f"{BASE_URL}/api/command",
            json={"cmd": ""},
            headers=HEADERS,
            timeout=10,
        )
        assert r.status_code == 400, f"Expected 400 but got HTTP {r.status_code}"
        _ok("POST /api/command (empty cmd → 400)")
    except Exception as exc:
        _fail_msg("POST /api/command (empty cmd → 400)", str(exc))


def test_command_execute():
    """POST /api/command with valid cmd should return answer."""
    try:
        r = requests.post(
            f"{BASE_URL}/api/command",
            json={"cmd": "помощь"},
            headers=HEADERS,
            timeout=15,
        )
        assert r.status_code == 200, f"HTTP {r.status_code}"
        data = r.json()
        assert "answer" in data, f"missing 'answer' in response: {data}"
        _ok("POST /api/command", f"answer[:60]={str(data['answer'])[:60]!r}")
    except Exception as exc:
        _fail_msg("POST /api/command", str(exc))


def test_events():
    """GET /api/events should return list."""
    try:
        r = requests.get(
            f"{BASE_URL}/api/events?limit=5",
            headers=HEADERS,
            timeout=10,
        )
        assert r.status_code == 200, f"HTTP {r.status_code}"
        data = r.json()
        assert "events" in data, f"missing 'events': {data}"
        assert isinstance(data["events"], list), "events must be a list"
        _ok("GET /api/events", f"count={data.get('count', '?')}")
    except Exception as exc:
        _fail_msg("GET /api/events", str(exc))


def test_events_auth():
    """GET /api/events should return 401 with wrong token."""
    if not TOKEN:
        print("  ⏭   SKIP  GET /api/events auth check (no token configured)")
        return
    try:
        r = requests.get(
            f"{BASE_URL}/api/events?limit=5",
            headers={"Authorization": "Bearer wrong_token_xyz"},
            timeout=10,
        )
        assert r.status_code == 401, f"Expected 401 but got HTTP {r.status_code}"
        _ok("GET /api/events (wrong token → 401)")
    except Exception as exc:
        _fail_msg("GET /api/events (wrong token → 401)", str(exc))


def test_cors_header():
    """API responses should include CORS headers."""
    try:
        r = requests.options(
            f"{BASE_URL}/api/health",
            headers={"Origin": "http://example.com", "Access-Control-Request-Method": "GET"},
            timeout=10,
        )
        assert "access-control-allow-origin" in {k.lower() for k in r.headers}, \
            f"Missing CORS header. Response headers: {dict(r.headers)}"
        _ok("CORS headers present on /api/health")
    except Exception as exc:
        _fail_msg("CORS headers", str(exc))


def main():
    print(f"\n{'━' * 55}")
    print(f"  ARGOS API Smoke Test")
    print(f"  Base URL : {BASE_URL}")
    print(f"  Token    : {'***' if TOKEN else '(none — unauthenticated)'}")
    print(f"{'━' * 55}\n")

    test_health()
    test_health_no_auth_required()
    test_command_auth()
    test_command_empty()
    test_command_execute()
    test_events()
    test_events_auth()
    test_cors_header()

    print(f"\n{'━' * 55}")
    print(f"  Results: {_pass} passed, {_fail} failed")
    print(f"{'━' * 55}\n")

    sys.exit(0 if _fail == 0 else 1)


if __name__ == "__main__":
    main()

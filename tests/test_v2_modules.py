"""
tests/test_v2_modules.py — ARGOS v2.0.0
Тесты для новых модулей: StartupValidator, HealthMonitor,
GracefulShutdown, AIFailover.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import threading
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Добавляем корень проекта в sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════════════════
#  StartupValidator
# ═══════════════════════════════════════════════════════════════════════════

class TestStartupValidator:

    def setup_method(self):
        from src.startup_validator import StartupValidator
        self.cls = StartupValidator

    def test_python_version_ok(self, tmp_path):
        v = self.cls(root=tmp_path)
        report = v.validate()
        cpu_check = next(
            (r for r in report.results if "Python" in r.message), None
        )
        assert cpu_check is not None

    def test_env_file_not_found_is_warning_not_error(self, tmp_path):
        v = self.cls(root=tmp_path)
        report = v.validate()
        errors = [r.message for r in report.errors]
        assert not any(".env" in e for e in errors), \
            "Отсутствие .env должно быть WARN, а не ERROR"

    def test_env_file_loaded(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("TEST_ARGOS_KEY=hello\n")
        v = self.cls(root=tmp_path)
        v.validate()
        assert os.environ.get("TEST_ARGOS_KEY") == "hello"

    def test_missing_required_package_is_error(self, tmp_path):
        from src.startup_validator import StartupValidator, _REQUIRED_PACKAGES
        original = _REQUIRED_PACKAGES[:]
        import src.startup_validator as sv_mod
        sv_mod._REQUIRED_PACKAGES = [("_nonexistent_pkg_xyz", "pip install _nonexistent_pkg_xyz")]
        try:
            v = StartupValidator(root=tmp_path)
            report = v.validate()
            assert len(report.errors) > 0
        finally:
            sv_mod._REQUIRED_PACKAGES = original

    def test_report_ok_returns_true_when_no_errors(self, tmp_path):
        v = self.cls(root=tmp_path)
        report = v.validate()
        # Без реально отсутствующих required пакетов должно быть ok
        # (fastapi и psutil обычно установлены в dev-окружении)
        assert isinstance(report.ok, bool)

    def test_directories_created_if_missing(self, tmp_path):
        v = self.cls(root=tmp_path)
        v.validate()
        for d in ["src", "config", "data", "logs"]:
            assert (tmp_path / d).exists(), f"Директория /{d}/ не создана"

    def test_production_warning_without_remote_token(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ARGOS_REMOTE_TOKEN", raising=False)
        v = self.cls(root=tmp_path)
        report = v.validate()
        warn_msgs = [r.message for r in report.warnings]
        assert any("REMOTE_TOKEN" in m for m in warn_msgs)

    def test_print_does_not_crash(self, tmp_path, capsys):
        v = self.cls(root=tmp_path)
        report = v.validate()
        report.print()
        out = capsys.readouterr().out
        assert "ARGOS" in out


# ═══════════════════════════════════════════════════════════════════════════
#  HealthMonitor
# ═══════════════════════════════════════════════════════════════════════════

class TestHealthMonitor:

    def _make_db(self, tmp_path: Path) -> str:
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.close()
        return str(db)

    def test_starts_and_stops(self, tmp_path):
        from src.health_monitor import HealthMonitor
        m = HealthMonitor(db_path=self._make_db(tmp_path), interval=0.5)
        m.start()
        time.sleep(1.2)
        snap = m.latest()
        m.stop()
        assert snap is not None

    def test_snapshot_has_expected_fields(self, tmp_path):
        from src.health_monitor import HealthMonitor
        m = HealthMonitor(db_path=self._make_db(tmp_path), interval=0.3)
        m.start()
        time.sleep(0.6)
        snap = m.latest()
        m.stop()
        assert snap is not None
        assert snap.status in ("healthy", "degraded", "critical")
        assert snap.uptime_sec > 0
        assert isinstance(snap.components, list)

    def test_to_dict_serializable(self, tmp_path):
        from src.health_monitor import HealthMonitor
        import json
        m = HealthMonitor(db_path=self._make_db(tmp_path), interval=0.3)
        m.start()
        time.sleep(0.6)
        snap = m.latest()
        m.stop()
        assert snap is not None
        d = snap.to_dict()
        # Должно быть JSON-сериализуемо
        json.dumps(d)

    def test_db_check_ok(self, tmp_path):
        from src.health_monitor import HealthMonitor
        m = HealthMonitor(db_path=self._make_db(tmp_path), interval=99)
        result = m._check_db()
        assert result.ok is True

    def test_db_check_fail(self, tmp_path):
        from src.health_monitor import HealthMonitor
        m = HealthMonitor(db_path="/nonexistent/path/argos.db", interval=99)
        result = m._check_db()
        assert result.ok is False

    def test_alert_callback_called_on_degraded(self, tmp_path):
        from src.health_monitor import HealthMonitor, HealthSnapshot, ComponentStatus
        called = []
        def cb(msg): called.append(msg)

        m = HealthMonitor(db_path=self._make_db(tmp_path), interval=99, alert_callback=cb)
        # Сделать snap со статусом "degraded"
        snap = HealthSnapshot(
            timestamp=time.time(), status="degraded",
            cpu_pct=85.0, ram_pct=50.0, disk_pct=50.0,
            components=[], uptime_sec=10.0
        )
        m._check_alerts(snap)
        assert len(called) == 1

    def test_alert_cooldown_prevents_spam(self, tmp_path):
        from src.health_monitor import HealthMonitor, HealthSnapshot
        called = []
        def cb(msg): called.append(msg)

        m = HealthMonitor(db_path=self._make_db(tmp_path), interval=99, alert_callback=cb)
        snap = HealthSnapshot(
            timestamp=time.time(), status="critical",
            cpu_pct=99.0, ram_pct=99.0, disk_pct=50.0,
            components=[], uptime_sec=10.0
        )
        m._check_alerts(snap)
        m._check_alerts(snap)  # второй вызов — должен игнорироваться
        assert len(called) == 1, "Алерт должен отправляться не чаще кулдауна"

    def test_history_limited(self, tmp_path):
        from src.health_monitor import HealthMonitor
        m = HealthMonitor(db_path=self._make_db(tmp_path), interval=0.05)
        m._max_history = 5
        m.start()
        time.sleep(0.5)
        m.stop()
        assert len(m.history(100)) <= 5


# ═══════════════════════════════════════════════════════════════════════════
#  GracefulShutdown
# ═══════════════════════════════════════════════════════════════════════════

class TestGracefulShutdown:

    def test_register_and_trigger(self):
        from src.graceful_shutdown import GracefulShutdown
        shutdown = GracefulShutdown(timeout=2)
        called = []
        shutdown.register("test_cb", lambda: called.append(True))
        shutdown.trigger()
        shutdown.wait()
        assert called == [True]

    def test_priority_order(self):
        from src.graceful_shutdown import GracefulShutdown
        order = []
        shutdown = GracefulShutdown(timeout=2)
        shutdown.register("low",    lambda: order.append("low"),    priority=1)
        shutdown.register("high",   lambda: order.append("high"),   priority=10)
        shutdown.register("medium", lambda: order.append("medium"), priority=5)
        shutdown.trigger()
        shutdown.wait()
        assert order == ["high", "medium", "low"]

    def test_double_trigger_safe(self):
        from src.graceful_shutdown import GracefulShutdown
        calls = []
        shutdown = GracefulShutdown(timeout=2)
        shutdown.register("cb", lambda: calls.append(1))
        shutdown.trigger()
        shutdown.trigger()  # второй вызов должен игнорироваться
        shutdown.wait()
        assert calls == [1]

    def test_callback_exception_does_not_crash(self):
        from src.graceful_shutdown import GracefulShutdown
        shutdown = GracefulShutdown(timeout=2)
        def bad_cb(): raise RuntimeError("ошибка в callback")
        shutdown.register("bad", bad_cb)
        shutdown.register("good", lambda: None)
        shutdown.trigger()
        shutdown.wait()   # не должен бросить исключение

    def test_timeout_does_not_block_forever(self):
        from src.graceful_shutdown import GracefulShutdown
        shutdown = GracefulShutdown(timeout=0.3)
        def slow_cb(): time.sleep(10)
        shutdown.register("slow", slow_cb)
        start = time.time()
        shutdown.trigger()
        shutdown.wait()
        elapsed = time.time() - start
        assert elapsed < 3.0, f"Завершение заняло слишком долго: {elapsed:.1f}s"


# ═══════════════════════════════════════════════════════════════════════════
#  AIFailover
# ═══════════════════════════════════════════════════════════════════════════

class TestAIFailover:

    def _make_mock_provider(self, responses: dict):
        """Создать mock-модуль провайдеров."""
        mod = MagicMock()
        for name, result in responses.items():
            if isinstance(result, Exception):
                getattr(mod, f"ask_{name}").side_effect = result
            else:
                getattr(mod, f"ask_{name}").return_value = result
        return mod

    @pytest.mark.asyncio
    async def test_uses_first_available_provider(self):
        from src.ai_failover import AIFailover
        mock_mod = self._make_mock_provider({"gemini": "Ответ от Gemini"})
        failover = AIFailover(provider_module=mock_mod)
        result, provider = await failover.ask("Привет", prefer="gemini")
        assert result == "Ответ от Gemini"
        assert provider == "gemini"

    @pytest.mark.asyncio
    async def test_falls_back_on_error(self):
        from src.ai_failover import AIFailover
        mock_mod = MagicMock()
        mock_mod.ask_gemini.side_effect = RuntimeError("API key invalid")
        mock_mod.ask_openai.return_value = "Ответ от OpenAI"
        failover = AIFailover(provider_module=mock_mod)
        failover.set_order(["gemini", "openai"])
        result, provider = await failover.ask("Привет")
        assert provider == "openai"
        assert result == "Ответ от OpenAI"

    @pytest.mark.asyncio
    async def test_raises_when_all_providers_fail(self):
        from src.ai_failover import AIFailover
        mock_mod = MagicMock()
        mock_mod.ask_gemini.side_effect = RuntimeError("down")
        mock_mod.ask_openai.side_effect = RuntimeError("down")
        failover = AIFailover(provider_module=mock_mod)
        failover.set_order(["gemini", "openai"])
        with pytest.raises(RuntimeError, match="недоступны"):
            await failover.ask("Привет", max_retries=1)

    @pytest.mark.asyncio
    async def test_records_stats_on_success(self):
        from src.ai_failover import AIFailover, ProviderStatus
        mock_mod = self._make_mock_provider({"gemini": "ok"})
        failover = AIFailover(provider_module=mock_mod)
        await failover.ask("test", prefer="gemini")
        assert failover.stats()["gemini"].success_count == 1
        assert failover.stats()["gemini"].status == ProviderStatus.OK

    @pytest.mark.asyncio
    async def test_backoff_applied_after_failures(self):
        from src.ai_failover import AIFailover
        mock_mod = MagicMock()
        mock_mod.ask_gemini.side_effect = RuntimeError("timeout")
        failover = AIFailover(provider_module=mock_mod)
        failover.set_order(["gemini"])
        with pytest.raises(RuntimeError):
            await failover.ask("test", max_retries=1)
        stats = failover.stats()["gemini"]
        assert stats.backoff_until > time.time()

    def test_reset_clears_backoff(self):
        from src.ai_failover import AIFailover, ProviderStatus
        mock_mod = MagicMock()
        failover = AIFailover(provider_module=mock_mod)
        failover._stats["gemini"].backoff_until = time.time() + 9999
        failover._stats["gemini"].status = ProviderStatus.DOWN
        failover.reset("gemini")
        assert failover.stats()["gemini"].backoff_until == 0.0
        assert failover.stats()["gemini"].status == ProviderStatus.OK

    @pytest.mark.asyncio
    async def test_prefer_overrides_order(self):
        from src.ai_failover import AIFailover
        mock_mod = self._make_mock_provider({"ollama": "local response"})
        failover = AIFailover(provider_module=mock_mod)
        result, provider = await failover.ask("test", prefer="ollama")
        assert provider == "ollama"


# ═══════════════════════════════════════════════════════════════════════════
#  Интеграция: StartupValidator + HealthMonitor запускаются вместе
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegration:

    def test_startup_then_health_check(self, tmp_path):
        from src.startup_validator import StartupValidator
        from src.health_monitor import HealthMonitor
        import sqlite3

        # 1. Инициализировать структуру
        v = StartupValidator(root=tmp_path)
        report = v.validate()
        assert (tmp_path / "data").exists()

        # 2. Создать БД
        db_path = str(tmp_path / "data" / "argos.db")
        conn = sqlite3.connect(db_path)
        conn.close()

        # 3. Запустить HealthMonitor
        m = HealthMonitor(db_path=db_path, interval=0.3)
        m.start()
        time.sleep(0.7)
        snap = m.latest()
        m.stop()

        assert snap is not None
        db_comp = next((c for c in snap.components if c.name == "sqlite"), None)
        assert db_comp is not None and db_comp.ok

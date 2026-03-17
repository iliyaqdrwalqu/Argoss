"""
Tests for awareness.py — ArgosAwareness class (added in this PR).
"""
import sys
import os
import time
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from awareness import ArgosAwareness, _safe


# ── ArgosAwareness.__init__ ──────────────────────────────────────────────────

class TestArgosAwarenessInit:
    def test_init_no_core(self):
        aw = ArgosAwareness()
        assert aw.core is None
        assert isinstance(aw._impact_log, list)
        assert len(aw._impact_log) == 0

    def test_init_with_core(self):
        core = SimpleNamespace(voice_on=True)
        aw = ArgosAwareness(core=core)
        assert aw.core is core

    def test_start_time_set_on_init(self):
        before = time.time()
        aw = ArgosAwareness()
        after = time.time()
        assert before <= aw._start_time <= after


# ── ArgosAwareness.perceive() ────────────────────────────────────────────────

class TestArgosAwarenessPerceive:
    def test_perceive_returns_dict(self):
        aw = ArgosAwareness()
        result = aw.perceive()
        assert isinstance(result, dict)

    def test_perceive_contains_platform(self):
        aw = ArgosAwareness()
        result = aw.perceive()
        assert "platform" in result
        assert isinstance(result["platform"], str)
        assert len(result["platform"]) > 0

    def test_perceive_contains_arch(self):
        aw = ArgosAwareness()
        result = aw.perceive()
        assert "arch" in result

    def test_perceive_contains_hostname(self):
        aw = ArgosAwareness()
        result = aw.perceive()
        assert "hostname" in result

    def test_perceive_contains_time(self):
        aw = ArgosAwareness()
        result = aw.perceive()
        assert "time" in result
        # ISO-format datetime: "YYYY-MM-DDTHH:MM:SS"
        t = result["time"]
        assert "T" in t
        assert len(t) == 19

    def test_perceive_psutil_fields_when_available(self):
        aw = ArgosAwareness()
        result = aw.perceive()
        # psutil is listed in requirements.txt so should be available
        try:
            import psutil  # noqa: F401
            assert "cpu_pct" in result
            assert "ram_pct" in result
            assert "ram_mb" in result
            assert isinstance(result["cpu_pct"], float)
            assert 0.0 <= result["ram_pct"] <= 100.0
            assert result["ram_mb"] > 0
        except ImportError:
            pass  # psutil not available; fields may be missing

    def test_perceive_no_p2p_nodes_when_core_none(self):
        aw = ArgosAwareness()
        result = aw.perceive()
        assert "p2p_nodes" not in result

    def test_perceive_no_p2p_nodes_when_core_has_no_p2p(self):
        aw = ArgosAwareness(core=SimpleNamespace())
        result = aw.perceive()
        assert "p2p_nodes" not in result

    def test_perceive_p2p_nodes_from_core(self):
        p2p = SimpleNamespace(node_count=5)
        core = SimpleNamespace(p2p=p2p)
        aw = ArgosAwareness(core=core)
        result = aw.perceive()
        assert "p2p_nodes" in result
        assert result["p2p_nodes"] == 5

    def test_perceive_p2p_node_count_default_zero(self):
        # p2p object without node_count attribute
        p2p = SimpleNamespace()
        core = SimpleNamespace(p2p=p2p)
        aw = ArgosAwareness(core=core)
        result = aw.perceive()
        assert "p2p_nodes" in result
        assert result["p2p_nodes"] == 0

    def test_perceive_psutil_failure_graceful(self):
        aw = ArgosAwareness()
        with patch.dict("sys.modules", {"psutil": None}):
            # Even if psutil raises, perceive should still return a dict
            with patch("awareness.psutil", side_effect=Exception("fail"), create=True):
                result = aw.perceive()
                assert isinstance(result, dict)
                assert "platform" in result


# ── ArgosAwareness.record_impact() ──────────────────────────────────────────

class TestArgosAwarenessRecordImpact:
    def test_record_impact_returns_dict(self):
        aw = ArgosAwareness()
        impact = aw.record_impact("test action", "✅ успешно")
        assert isinstance(impact, dict)

    def test_record_impact_positive_detection(self):
        aw = ArgosAwareness()
        impact = aw.record_impact("do something", "✅ успешно выполнено")
        assert impact["positive"] is True
        assert impact["negative"] is False
        assert impact["neutral"] is False

    def test_record_impact_positive_keywords(self):
        for kw in ["успешно", "готово", "помог", "решил"]:
            aw = ArgosAwareness()
            impact = aw.record_impact("action", f"результат: {kw}")
            assert impact["positive"] is True, f"Keyword '{kw}' should be positive"

    def test_record_impact_negative_detection(self):
        aw = ArgosAwareness()
        impact = aw.record_impact("do something", "❌ ошибка произошла")
        assert impact["negative"] is True
        assert impact["positive"] is False
        assert impact["neutral"] is False

    def test_record_impact_negative_keywords(self):
        for kw in ["ошибка", "не могу", "отказ"]:
            aw = ArgosAwareness()
            impact = aw.record_impact("action", f"результат: {kw}")
            assert impact["negative"] is True, f"Keyword '{kw}' should be negative"

    def test_record_impact_neutral_detection(self):
        aw = ArgosAwareness()
        impact = aw.record_impact("action", "просто обычный ответ")
        assert impact["neutral"] is True
        assert impact["positive"] is False
        assert impact["negative"] is False

    def test_record_impact_appends_to_log(self):
        aw = ArgosAwareness()
        assert len(aw._impact_log) == 0
        aw.record_impact("action", "neutral")
        assert len(aw._impact_log) == 1

    def test_record_impact_action_truncated_to_100(self):
        aw = ArgosAwareness()
        long_action = "x" * 200
        impact = aw.record_impact(long_action, "result")
        assert len(impact["action"]) == 100

    def test_record_impact_affected_default(self):
        aw = ArgosAwareness()
        impact = aw.record_impact("action", "result")
        assert impact["affected"] == "user"

    def test_record_impact_affected_custom(self):
        aw = ArgosAwareness()
        impact = aw.record_impact("action", "result", affected="system")
        assert impact["affected"] == "system"

    def test_record_impact_timestamp_is_recent(self):
        before = time.time()
        aw = ArgosAwareness()
        impact = aw.record_impact("action", "result")
        after = time.time()
        assert before <= impact["timestamp"] <= after

    def test_record_impact_log_capped_at_500(self):
        aw = ArgosAwareness()
        for i in range(510):
            aw.record_impact("action", "neutral result")
        # The log is trimmed to 250 whenever it exceeds 500.
        # After 510 total: first trim at item 501 (→250), then 9 more items are added.
        # So the final length is 259, which is still well below 500.
        assert len(aw._impact_log) <= 500
        assert len(aw._impact_log) < 510  # confirms pruning occurred

    def test_record_impact_returns_correct_structure(self):
        aw = ArgosAwareness()
        impact = aw.record_impact("my action", "✅ готово", "device")
        required_keys = {"action", "affected", "positive", "negative", "neutral", "timestamp"}
        assert set(impact.keys()) == required_keys


# ── ArgosAwareness.reflect() ─────────────────────────────────────────────────

class TestArgosAwarenessReflect:
    def test_reflect_returns_string(self):
        aw = ArgosAwareness()
        result = aw.reflect()
        assert isinstance(result, str)

    def test_reflect_contains_header(self):
        aw = ArgosAwareness()
        result = aw.reflect()
        assert "ОСОЗНАНИЕ АРГОСА" in result

    def test_reflect_contains_platform(self):
        aw = ArgosAwareness()
        result = aw.reflect()
        assert "Платформа" in result

    def test_reflect_contains_uptime(self):
        aw = ArgosAwareness()
        result = aw.reflect()
        assert "Аптайм" in result

    def test_reflect_contains_actions_count(self):
        aw = ArgosAwareness()
        aw.record_impact("action1", "✅ успешно")
        aw.record_impact("action2", "neutral")
        result = aw.reflect()
        assert "Действий" in result
        assert "2" in result

    def test_reflect_positive_count(self):
        aw = ArgosAwareness()
        aw.record_impact("a1", "✅ готово")
        aw.record_impact("a2", "❌ ошибка")
        result = aw.reflect()
        assert "положительных: 1" in result

    def test_reflect_shows_p2p_nodes_when_present(self):
        p2p = SimpleNamespace(node_count=7)
        core = SimpleNamespace(p2p=p2p)
        aw = ArgosAwareness(core=core)
        result = aw.reflect()
        assert "P2P" in result
        assert "7" in result

    def test_reflect_no_p2p_section_without_core(self):
        aw = ArgosAwareness()
        result = aw.reflect()
        assert "P2P узлов" not in result

    def test_reflect_zero_impacts(self):
        aw = ArgosAwareness()
        result = aw.reflect()
        assert "Действий  : 0" in result


# ── _safe() helper ───────────────────────────────────────────────────────────

class TestSafeHelper:
    def test_safe_returns_value_on_success(self):
        result = _safe(lambda: "hello")
        assert result == "hello"

    def test_safe_returns_empty_string_on_exception(self):
        result = _safe(lambda: 1 / 0)
        assert result == ""

    def test_safe_works_with_import(self):
        result = _safe(lambda: __import__("socket").gethostname())
        assert isinstance(result, str)


# ── Module-level SelfAwareness proxy ────────────────────────────────────────

class TestModuleLevelProxy:
    def test_self_awareness_attribute_exists(self):
        import awareness
        assert hasattr(awareness, "SelfAwareness")
        # It's either the real class or None (graceful fallback)
        assert awareness.SelfAwareness is None or callable(awareness.SelfAwareness)
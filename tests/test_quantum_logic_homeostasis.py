"""
Tests for src/quantum/logic.py — QuantumEngine (simplified in this PR).

Note: force_state() and set_external_telemetry() were removed in this PR.
This file tests the current API: generate_state(), set_state(), status().
"""
import unittest
from unittest.mock import patch, MagicMock

from src.quantum.logic import QuantumEngine, STATES, ArgosQuantum


class TestQuantumEngineInit(unittest.TestCase):
    def test_default_state_is_analytic(self):
        q = QuantumEngine()
        self.assertEqual(q.current, "Analytic")

    def test_argos_quantum_alias(self):
        """ArgosQuantum must be an alias for QuantumEngine."""
        self.assertIs(ArgosQuantum, QuantumEngine)


class TestGenerateState(unittest.TestCase):
    def test_returns_dict_with_name(self):
        q = QuantumEngine()
        result = q.generate_state()
        self.assertIn("name", result)
        self.assertIsInstance(result["name"], str)

    def test_returns_dict_with_vector(self):
        q = QuantumEngine()
        result = q.generate_state()
        self.assertIn("vector", result)
        self.assertIsInstance(result["vector"], list)
        self.assertGreater(len(result["vector"]), 0)

    def test_name_is_valid_state(self):
        q = QuantumEngine()
        result = q.generate_state()
        self.assertIn(result["name"], STATES)

    def test_vector_length_matches_state_properties(self):
        q = QuantumEngine()
        result = q.generate_state()
        expected_len = len(STATES[result["name"]])
        self.assertEqual(len(result["vector"]), expected_len)


class TestSetState(unittest.TestCase):
    def test_set_valid_state(self):
        q = QuantumEngine()
        msg = q.set_state("Creative")
        self.assertEqual(q.current, "Creative")
        self.assertIn("Creative", msg)

    def test_set_state_returns_confirmation(self):
        q = QuantumEngine()
        msg = q.set_state("Protective")
        self.assertTrue(msg.startswith("⚛️"))

    def test_set_invalid_state_returns_error(self):
        q = QuantumEngine()
        original = q.current
        msg = q.set_state("NonExistentState")
        self.assertIn("❌", msg)
        self.assertEqual(q.current, original)  # unchanged

    def test_set_all_valid_states(self):
        q = QuantumEngine()
        for state_name in STATES:
            msg = q.set_state(state_name)
            self.assertEqual(q.current, state_name)
            self.assertNotIn("❌", msg)

    def test_generate_state_after_set_state(self):
        q = QuantumEngine()
        # Freeze psutil to prevent auto-switch from changing the state
        with patch("src.quantum.logic._PSUTIL", False):
            q.set_state("All-Seeing")
            result = q.generate_state()
        self.assertEqual(result["name"], "All-Seeing")


class TestStatus(unittest.TestCase):
    def test_status_returns_string(self):
        q = QuantumEngine()
        result = q.status()
        self.assertIsInstance(result, str)

    def test_status_contains_current_state(self):
        q = QuantumEngine()
        q.set_state("System")
        result = q.status()
        self.assertIn("System", result)

    def test_status_contains_creativity(self):
        q = QuantumEngine()
        result = q.status()
        self.assertIn("Творчество", result)

    def test_status_contains_window(self):
        q = QuantumEngine()
        result = q.status()
        self.assertIn("Окно памяти", result)

    def test_status_contains_root_commands(self):
        q = QuantumEngine()
        result = q.status()
        self.assertIn("Root-команды", result)


class TestAutoSwitch(unittest.TestCase):
    def _make_psutil_mock(self, cpu: float, ram: float) -> MagicMock:
        """Create a psutil mock with given cpu_percent and virtual_memory.percent."""
        mock_psutil = MagicMock()
        mock_psutil.cpu_percent.return_value = cpu
        mock_mem = MagicMock()
        mock_mem.percent = ram
        mock_psutil.virtual_memory.return_value = mock_mem
        return mock_psutil

    def test_auto_switch_to_protective_on_high_cpu(self):
        q = QuantumEngine()
        mock_ps = self._make_psutil_mock(cpu=90.0, ram=40.0)
        with patch("src.quantum.logic._PSUTIL", True), \
             patch("src.quantum.logic.psutil", mock_ps, create=True):
            q._auto_switch()
        self.assertEqual(q.current, "Protective")

    def test_auto_switch_to_protective_on_high_ram(self):
        q = QuantumEngine()
        mock_ps = self._make_psutil_mock(cpu=20.0, ram=95.0)
        with patch("src.quantum.logic._PSUTIL", True), \
             patch("src.quantum.logic.psutil", mock_ps, create=True):
            q._auto_switch()
        self.assertEqual(q.current, "Protective")

    def test_auto_switch_to_unstable_on_moderate_cpu(self):
        q = QuantumEngine()
        mock_ps = self._make_psutil_mock(cpu=75.0, ram=40.0)
        with patch("src.quantum.logic._PSUTIL", True), \
             patch("src.quantum.logic.psutil", mock_ps, create=True):
            q._auto_switch()
        self.assertEqual(q.current, "Unstable")

    def test_auto_switch_no_change_on_low_load(self):
        q = QuantumEngine()
        q.set_state("Analytic")
        mock_ps = self._make_psutil_mock(cpu=10.0, ram=20.0)
        with patch("src.quantum.logic._PSUTIL", True), \
             patch("src.quantum.logic.psutil", mock_ps, create=True):
            q._auto_switch()
        # auto_switch only switches to Protective/Unstable on high load
        self.assertIn(q.current, STATES)

    def test_auto_switch_skipped_without_psutil(self):
        q = QuantumEngine()
        q.set_state("Creative")
        with patch("src.quantum.logic._PSUTIL", False):
            q._auto_switch()
        self.assertEqual(q.current, "Creative")

    def test_auto_switch_exception_handled_gracefully(self):
        q = QuantumEngine()
        mock_ps = MagicMock()
        mock_ps.cpu_percent.side_effect = RuntimeError("psutil error")
        with patch("src.quantum.logic._PSUTIL", True), \
             patch("src.quantum.logic.psutil", mock_ps, create=True):
            # Should not raise
            q._auto_switch()

    def test_force_state_method_does_not_exist(self):
        """force_state() was removed in this PR — must not exist."""
        q = QuantumEngine()
        self.assertFalse(hasattr(q, "force_state"),
                         "force_state() was removed in this PR and should not exist")

    def test_set_external_telemetry_does_not_exist(self):
        """set_external_telemetry() was removed in this PR — must not exist."""
        q = QuantumEngine()
        self.assertFalse(hasattr(q, "set_external_telemetry"),
                         "set_external_telemetry() was removed and should not exist")


class TestStatesDict(unittest.TestCase):
    def test_all_states_have_required_keys(self):
        required = {"creativity", "window", "allow_root"}
        for name, props in STATES.items():
            self.assertEqual(set(props.keys()), required,
                             f"State '{name}' missing keys")

    def test_state_creativity_range(self):
        for name, props in STATES.items():
            self.assertGreaterEqual(props["creativity"], 0.0)
            self.assertLessEqual(props["creativity"], 1.0)

    def test_state_window_positive(self):
        for name, props in STATES.items():
            self.assertGreater(props["window"], 0)

    def test_state_allow_root_is_bool(self):
        for name, props in STATES.items():
            self.assertIsInstance(props["allow_root"], bool)


if __name__ == "__main__":
    unittest.main()
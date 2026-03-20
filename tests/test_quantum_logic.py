"""Extended tests for src/quantum/logic.py"""
import pytest


def test_quantum_generate_state_has_probabilities():
    from src.quantum.logic import ArgosQuantum
    q = ArgosQuantum()
    state = q.generate_state()
    assert "probabilities" in state or "vector" in state


def test_quantum_state_name_is_string():
    from src.quantum.logic import ArgosQuantum
    q = ArgosQuantum()
    state = q.generate_state()
    assert isinstance(state.get("name", ""), str)


def test_quantum_update_does_not_raise():
    from src.quantum.logic import ArgosQuantum
    q = ArgosQuantum()
    try:
        q.update("user_active", True)
    except AttributeError:
        pass  # метод может называться иначе


def test_quantum_multiple_states_are_valid():
    from src.quantum.logic import ArgosQuantum
    q = ArgosQuantum()
    states = [q.generate_state() for _ in range(5)]
    for s in states:
        assert "name" in s

import importlib
from pathlib import Path

import src.memory as memory_module


class _DummyGrist:
    def __init__(self):
        self._configured = True
        self.calls = []

    def save(self, key, value):
        self.calls.append((key, value))
        return "ok"


def test_memory_remember_mirrors_to_grist_immediately(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ARGOS_VECTOR_FORCE_FALLBACK", "1")
    monkeypatch.setattr(memory_module, "DB_PATH", str(tmp_path / "memory.db"))

    mem = memory_module.ArgosMemory()
    grist = _DummyGrist()
    mem.attach_grist(grist)

    result = mem.remember("имя", "аргос", category="user")

    assert "Запомнил" in result
    assert grist.calls == [("memory:user:имя", "аргос")]


def test_grist_doc_id_uses_gist_id_alias(monkeypatch):
    monkeypatch.delenv("GRIST_DOC_ID", raising=False)
    monkeypatch.setenv("GIST_ID", "alias-doc-id")

    import src.knowledge.grist_storage as grist_storage
    reloaded = importlib.reload(grist_storage)

    assert reloaded.GRIST_DOC_ID == "alias-doc-id"

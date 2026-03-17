from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseModule(ABC):
    module_id = "base"
    title = "Base Module"

    def __init__(self):
        self.core = None

    def setup(self, core):
        self.core = core

    @abstractmethod
    def can_handle(self, text: str, lowered: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def handle(self, text: str, lowered: str, admin=None, flasher=None) -> str | None:
        raise NotImplementedError

    def health(self) -> dict[str, Any]:
        return {"id": self.module_id, "title": self.title, "ok": True}

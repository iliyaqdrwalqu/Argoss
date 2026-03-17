"""
p2p_transport.py — Транспортный слой P2P (миграция на libp2p).
"""
from abc import ABC, abstractmethod
from typing import Tuple


class P2PTransportBase(ABC):
    name = "base"

    @abstractmethod
    def is_available(self) -> bool: ...
    def request(self, addr: str, payload: dict, timeout: int = 8) -> dict:
        return {}
    def send(self, peer_id: str, payload: bytes) -> None: ...
    def recv(self) -> Tuple[str, bytes]:
        return ("", b"")


class TransportRegistry:
    def __init__(self):
        self._transports: dict[str, P2PTransportBase] = {}
        self._weights: dict[str, float] = {}

    def register(self, transport: P2PTransportBase, weight: float = 1.0):
        self._transports[transport.name] = transport
        self._weights[transport.name] = weight

    def best(self) -> P2PTransportBase | None:
        available = [(n, t) for n, t in self._transports.items()
                     if t.is_available() and self._weights.get(n, 0) > 0]
        if not available:
            return None
        return self._transports[max(available, key=lambda x: self._weights.get(x[0], 0))[0]]

    def status(self) -> str:
        lines = ["📡 TRANSPORT REGISTRY:"]
        for name, t in self._transports.items():
            avail = "✓" if t.is_available() else "✗"
            lines.append(f"  {name}: weight={self._weights.get(name, 1):.2f} {avail}")
        return "\\n".join(lines) if len(lines) > 1 else "📡 Транспортов нет"


class ZKPTransportWrapper(P2PTransportBase):
    name = "zkp-wrapped"

    def __init__(self, inner: P2PTransportBase, zkp_engine=None):
        self.inner = inner
        self.zkp = zkp_engine
        self.name = f"zkp+{inner.name}"

    def is_available(self) -> bool:
        return self.inner.is_available()

    def request(self, addr: str, payload: dict, timeout: int = 8) -> dict:
        return self.inner.request(addr, payload, timeout)

    def send(self, peer_id: str, payload: bytes) -> None:
        self.inner.send(peer_id, payload)

    def recv(self) -> Tuple[str, bytes]:
        return self.inner.recv()

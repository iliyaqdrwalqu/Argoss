"""
event_bus.py — Централизованная шина событий Аргоса
  Все подсистемы публикуют события → подписчики реагируют асинхронно.
  Архитектура publish/subscribe с фильтрацией по типу и приоритету.
"""
import threading
import time
import json
from queue import Queue, PriorityQueue
from typing import Callable, Any
from dataclasses import dataclass, field
from src.argos_logger import get_logger

log = get_logger("argos.events")

# ── ТИПЫ СОБЫТИЙ ──────────────────────────────────────────
class EventType:
    # Система
    SYSTEM_START     = "system.start"
    SYSTEM_STOP      = "system.stop"
    SYSTEM_ALERT     = "system.alert"
    SYSTEM_METRIC    = "system.metric"
    # Устройства IoT
    SENSOR_UPDATE    = "sensor.update"
    DEVICE_ONLINE    = "device.online"
    DEVICE_OFFLINE   = "device.offline"
    DEVICE_CMD       = "device.command"
    # Сеть
    NODE_JOIN        = "p2p.node.join"
    NODE_LEAVE       = "p2p.node.leave"
    SKILL_SYNC       = "p2p.skill.sync"
    # Умные системы
    SMART_TRIGGER    = "smart.trigger"
    SMART_RULE_FIRE  = "smart.rule.fire"
    SMART_ALERT      = "smart.alert"
    # Диалог
    USER_INPUT       = "dialog.user_input"
    ARGOS_RESPONSE   = "dialog.argos_response"
    AGENT_STEP       = "agent.step"
    AGENT_DONE       = "agent.done"
    # Mesh
    MESH_PACKET      = "mesh.packet"
    MESH_NODE_FOUND  = "mesh.node.found"


@dataclass(order=True)
class Event:
    priority: int
    type:     str      = field(compare=False)
    payload:  Any      = field(compare=False, default=None)
    source:   str      = field(compare=False, default="system")
    ts:       float    = field(compare=False, default_factory=time.time)

    @property
    def data(self):
        """Совместимость с src.event_bus.Event (поле data)."""
        return self.payload

    @property
    def topic(self):
        """Совместимость с src.event_bus.Event (поле topic)."""
        return self.type

    def get(self, key: str, default=None):
        """Dict-like доступ к payload."""
        if isinstance(self.payload, dict):
            return self.payload.get(key, default)
        return default

    def to_json(self) -> str:
        return json.dumps({
            "type":    self.type,
            "source":  self.source,
            "ts":      self.ts,
            "payload": self.payload if isinstance(self.payload, (dict, list, str, int, float, bool, type(None))) else str(self.payload),
        }, ensure_ascii=False)


class EventBus:
    """Глобальная шина событий. Singleton."""
    _instance = None
    _lock     = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
        return cls._instance

    def _init(self):
        self._subscribers: dict[str, list[Callable]] = {}
        self._wildcard: list[Callable] = []
        self._queue   = PriorityQueue()
        self._history = []
        self._max_history = 500
        self._running = False
        self._thread  = None
        self.start()

    # ── ПОДПИСКА ──────────────────────────────────────────
    def subscribe(self, event_type: str, callback: Callable, wildcard: bool = False):
        """Подписаться на тип события. '*' — все события."""
        if wildcard or event_type == "*":
            if callback not in self._wildcard:
                self._wildcard.append(callback)
        else:
            self._subscribers.setdefault(event_type, [])
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                c for c in self._subscribers[event_type] if c != callback
            ]

    # ── ПУБЛИКАЦИЯ ────────────────────────────────────────
    def publish(self, event_type: str, payload: Any = None,
                source: str = "system", priority: int = 5):
        ev = Event(priority=priority, type=event_type,
                   payload=payload, source=source)
        self._queue.put(ev)

    def publish_urgent(self, event_type: str, payload: Any = None, source: str = "system"):
        self.publish(event_type, payload, source, priority=1)

    # ── ОБРАБОТКА ─────────────────────────────────────────
    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _dispatch_loop(self):
        while self._running:
            try:
                ev = self._queue.get(timeout=0.1)
                self._dispatch(ev)
                self._history.append(ev)
                if len(self._history) > self._max_history:
                    self._history.pop(0)
            except Exception:
                pass

    def _dispatch(self, ev: Event):
        callbacks = list(self._subscribers.get(ev.type, []))
        callbacks += self._wildcard
        for cb in callbacks:
            try:
                threading.Thread(target=cb, args=(ev,), daemon=True).start()
            except Exception as e:
                log.error("EventBus dispatch error [%s]: %s", ev.type, e)

    # ── ИСТОРИЯ ───────────────────────────────────────────
    def recent(self, limit: int = 20, event_type: str = None) -> list:
        events = self._history[-limit:]
        if event_type:
            events = [e for e in events if e.type == event_type]
        return events

    def history_report(self, limit: int = 10) -> str:
        events = self.recent(limit)
        if not events:
            return "📭 История событий пуста."
        lines = [f"📡 СОБЫТИЯ (последние {limit}):"]
        for ev in reversed(events):
            t  = time.strftime("%H:%M:%S", time.localtime(ev.ts))
            pl = str(ev.payload)[:50] if ev.payload else ""
            lines.append(f"  [{t}] {ev.type:30s} ← {ev.source:15s} {pl}")
        return "\n".join(lines)

    def stats(self) -> str:
        types = {}
        for ev in self._history:
            types[ev.type] = types.get(ev.type, 0) + 1
        top = sorted(types.items(), key=lambda x: -x[1])[:5]
        lines = [
            f"📡 EVENT BUS:",
            f"  В очереди:     {self._queue.qsize()}",
            f"  В истории:     {len(self._history)}",
            f"  Подписчиков:   {sum(len(v) for v in self._subscribers.values()) + len(self._wildcard)}",
            f"  Топ событий:",
        ]
        for etype, cnt in top:
            lines.append(f"    {cnt:4d}× {etype}")
        return "\n".join(lines)


# ── ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ──────────────────────────────────
bus = EventBus()

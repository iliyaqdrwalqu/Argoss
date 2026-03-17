"""
event_bus.py — Шина событий Аргоса
  Все подсистемы публикуют и подписываются на события.
  Async-first, thread-safe, с историей и replay.
  
  Использование:
    bus = get_bus()
    bus.subscribe("sensor.cpu_high", handler)
    bus.publish("sensor.cpu_high", {"value": 92.5})
"""
import threading
import time
import json
import queue
from collections import defaultdict, deque
from typing import Callable, Any
from src.argos_logger import get_logger

log = get_logger("argos.eventbus")

# Категории событий
class Events:
    # Система
    SYSTEM_BOOT       = "system.boot"
    SYSTEM_SHUTDOWN   = "system.shutdown"
    SYSTEM_ERROR      = "system.error"
    # Сенсоры
    SENSOR_CPU_HIGH   = "sensor.cpu_high"
    SENSOR_RAM_HIGH   = "sensor.ram_high"
    SENSOR_DISK_HIGH  = "sensor.disk_high"
    SENSOR_TEMP_HIGH  = "sensor.temp_high"
    SENSOR_UPDATE     = "sensor.update"
    # IoT
    IOT_DEVICE_FOUND  = "iot.device_found"
    IOT_DEVICE_LOST   = "iot.device_lost"
    IOT_VALUE_CHANGED = "iot.value_changed"
    IOT_ALERT         = "iot.alert"
    IOT_COMMAND       = "iot.command"
    # P2P
    P2P_NODE_JOINED   = "p2p.node_joined"
    P2P_NODE_LEFT     = "p2p.node_left"
    P2P_SKILL_SYNCED  = "p2p.skill_synced"
    P2P_TASK_ROUTED   = "p2p.task_routed"
    # ИИ
    AI_QUERY          = "ai.query"
    AI_RESPONSE       = "ai.response"
    AI_INTENT         = "ai.intent"
    # Диалог
    DIALOG_USER       = "dialog.user"
    DIALOG_ARGOS      = "dialog.argos"
    DIALOG_WAKE_WORD  = "dialog.wake_word"
    # Алерты
    ALERT_FIRED       = "alert.fired"
    ALERT_CLEARED     = "alert.cleared"
    # Навыки
    SKILL_LOADED      = "skill.loaded"
    SKILL_EXECUTED    = "skill.executed"
    SKILL_ERROR       = "skill.error"
    SKILL_UPDATED     = "skill.updated"
    # Core
    CORE_READY        = "core.ready"
    CORE_ERROR        = "core.error"
    # DAG
    DAG_STARTED       = "dag.started"
    DAG_NODE_DONE     = "dag.node_done"
    DAG_COMPLETED     = "dag.completed"
    DAG_FAILED        = "dag.failed"
    # Smart environments
    ENV_TEMP_CHANGED  = "env.temp_changed"
    ENV_HUMIDITY      = "env.humidity_changed"
    ENV_LIGHT_CHANGED = "env.light_changed"
    ENV_ALERT         = "env.alert"


class Event:
    __slots__ = ("topic", "data", "ts", "source")
    def __init__(self, topic: str, data: Any = None, source: str = "core"):
        self.topic  = topic
        self.data   = data
        self.ts     = time.time()
        self.source = source

    @property
    def payload(self):
        """Совместимость с src.connectivity.event_bus.Event (поле payload)."""
        return self.data

    @property
    def type(self):
        """Совместимость с src.connectivity.event_bus.Event (поле type)."""
        return self.topic

    def get(self, key: str, default=None):
        """Dict-like доступ к data для обратной совместимости."""
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        return default

    def __getitem__(self, key):
        if isinstance(self.data, dict):
            return self.data[key]
        raise KeyError(key)

    def __contains__(self, key):
        return isinstance(self.data, dict) and key in self.data

    def to_dict(self) -> dict:
        return {"topic": self.topic, "data": self.data,
                "ts": self.ts, "source": self.source}

    def __repr__(self):
        return f"Event({self.topic}, src={self.source})"


class EventBus:
    def __init__(self, history_size: int = 500):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._wildcard: list[Callable] = []          # подписчики на "*"
        self._history  = deque(maxlen=history_size)
        self._lock     = threading.Lock()
        self._async_q  = queue.Queue()
        self._running  = True
        self._worker   = threading.Thread(target=self._dispatch_worker, daemon=True)
        self._worker.start()
        log.info("EventBus запущен (history=%d)", history_size)

    # ── ПУБЛИКАЦИЯ ────────────────────────────────────────
    def publish(self, topic: str, data: Any = None,
                source: str = "core", sync: bool = True):
        ev = Event(topic, data, source)
        with self._lock:
            self._history.append(ev)
        log.debug("EVENT %-30s ← %s", topic, source)
        if sync:
            self._dispatch(ev)
        else:
            self._async_q.put(ev)
        return ev

    def emit(self, topic: str, data: Any = None, source: str = "core"):
        """Синоним publish для красивого кода (синхронный)."""
        return self.publish(topic, data, source, sync=True)

    # ── ПОДПИСКА ──────────────────────────────────────────
    def subscribe(self, topic: str, handler: Callable):
        """Подписаться на конкретный топик или '*' для всех."""
        if topic == "*":
            self._wildcard.append(handler)
        else:
            self._handlers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable):
        if topic == "*":
            self._wildcard = [h for h in self._wildcard if h != handler]
        else:
            self._handlers[topic] = [h for h in self._handlers[topic] if h != handler]

    def on(self, topic: str):
        """Декоратор: @bus.on('sensor.cpu_high')"""
        def decorator(fn: Callable):
            self.subscribe(topic, fn)
            return fn
        return decorator

    # ── DISPATCH ──────────────────────────────────────────
    def _dispatch_worker(self):
        while self._running:
            try:
                ev = self._async_q.get(timeout=1)
                self._dispatch(ev)
            except queue.Empty:
                pass
            except Exception as e:
                log.error("EventBus worker error: %s", e)

    def _dispatch(self, ev: Event):
        handlers = list(self._handlers.get(ev.topic, []))
        # Prefix-match: "sensor.*" ловит "sensor.cpu_high"
        parts = ev.topic.split(".")
        for key, hs in self._handlers.items():
            if key.endswith(".*"):
                prefix = key[:-2]
                if ev.topic.startswith(prefix):
                    handlers += hs
        handlers += self._wildcard
        for h in handlers:
            try:
                try:
                    h(ev)  # Новый API: хендлер получает Event объект
                except TypeError:
                    h(ev.topic, ev.data)  # Старый API: (topic, data)
            except Exception as e:
                log.error("EventBus handler error: %s", e)

    # ── ИСТОРИЯ ───────────────────────────────────────────
    def history(self, topic: str = None, limit: int = 20) -> list:
        with self._lock:
            events = list(self._history)
        if topic:
            events = [e for e in events if e.topic == topic]
        return events[-limit:]

    def replay(self, topic: str, handler: Callable, limit: int = 50):
        """Воспроизвести прошлые события для нового подписчика."""
        for ev in self.history(topic, limit):
            try:
                try:
                    handler(ev)
                except TypeError:
                    handler(ev.topic, ev.data)
            except Exception as e:
                log.error("Replay error: %s", e)

    def stats(self) -> str:
        topics = set(e.topic for e in self._history)
        return (f"📡 EVENT BUS:\n"
                f"  История: {len(self._history)} событий\n"
                f"  Топиков: {len(topics)}\n"
                f"  Подписчиков: {sum(len(v) for v in self._handlers.values())}\n"
                f"  Очередь: {self._async_q.qsize()}")

    def stop(self):
        self._running = False


# Синглтон
_bus: EventBus | None = None

def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus

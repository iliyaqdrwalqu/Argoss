"""
task_queue.py — Очередь задач и worker pool Аргоса.
  PriorityQueue + worker pool для фонового выполнения команд.
  Поддерживает классы задач: system, iot, ai, heavy.
  Backpressure по acceptance rate + idle learning.
"""

import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.argos_logger import get_logger

log = get_logger("argos.taskqueue")

try:
    from src.observability import Metrics, get_acceptance_snapshot, log_event
except Exception:
    class Metrics:
        @classmethod
        def inc(cls, n, v=1, tags=None): pass
        @classmethod
        def gauge(cls, n, v, tags=None): pass
        @classmethod
        def observe(cls, n, v, tags=None): pass

    def log_event(t, d, source="argos"): pass
    def get_acceptance_snapshot(window=120): return {"rate": 1.0, "samples": 0}


@dataclass(order=True)
class TaskEnvelope:
    priority: int
    next_run_at: float
    created_at: float
    task_id: int = field(compare=False)
    kind: str = field(compare=False)
    payload: dict = field(compare=False)
    task_class: str = field(compare=False, default="ai")
    attempt: int = field(compare=False, default=0)
    max_retries: int = field(compare=False, default=0)
    deadline_ts: float = field(compare=False, default=0.0)
    backoff_ms: int = field(compare=False, default=500)


class TaskQueueManager:
    TASK_CLASSES = ("system", "iot", "ai", "heavy")

    def __init__(self, worker_count: int = 2):
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._lock = threading.Lock()
        self._running = False
        self._workers: list[threading.Thread] = []
        self._next_id = 1
        self._runners: dict[str, Callable] = {}

        self._processed = 0
        self._failed = 0
        self._durations_ms: deque = deque(maxlen=300)
        self._results: deque = deque(maxlen=100)

        self._class_rps: dict[str, int] = {
            "system": int(os.getenv("ARGOS_TASK_RPS_SYSTEM", "8")),
            "iot": int(os.getenv("ARGOS_TASK_RPS_IOT", "6")),
            "ai": int(os.getenv("ARGOS_TASK_RPS_AI", "3")),
            "heavy": int(os.getenv("ARGOS_TASK_RPS_HEAVY", "1")),
        }
        self._baseline_ai_rps = self._class_rps["ai"]
        self._acceptance_floor = float(os.getenv("ARGOS_ACCEPTANCE_FLOOR", "0.50"))
        self._idle_handlers: list[Callable] = []
        self._last_idle_learning_ts = 0.0
        self._idle_learning_min_sec = 120.0
        self._last_backpressure_check_ts = 0.0
        self._last_backpressure_action_ts = 0.0
        self._backpressure_check_sec = 20
        self._acceptance_samples_min = 8

    def register_runner(self, kind: str, fn: Callable):
        self._runners[kind] = fn

    def register_idle_learning_handler(self, fn: Callable):
        self._idle_handlers.append(fn)

    def enqueue(self, kind: str, payload: dict, *,
                priority: int = 5,
                task_class: str = "ai",
                max_retries: int = 0,
                deadline_ts: float = 0.0) -> int:
        with self._lock:
            tid = self._next_id
            self._next_id += 1
        env = TaskEnvelope(
            priority=priority,
            next_run_at=time.time(),
            created_at=time.time(),
            task_id=tid,
            kind=kind,
            payload=payload,
            task_class=task_class,
            max_retries=max_retries,
            deadline_ts=deadline_ts,
        )
        self._queue.put(env)
        return tid

    def start(self, worker_count: int = 2):
        if self._running:
            return
        self._running = True
        for i in range(worker_count):
            t = threading.Thread(target=self._worker_loop,
                                 name=f"tq-worker-{i}", daemon=True)
            t.start()
            self._workers.append(t)
        log.info("TaskQueue: %d workers запущено", worker_count)

    def stop(self):
        self._running = False

    def _worker_loop(self):
        while self._running:
            try:
                env = self._queue.get(timeout=0.5)
            except queue.Empty:
                now = time.time()
                self._run_idle_learning_cycle(now)
                self._check_acceptance_backpressure(now)
                continue

            now = time.time()
            if env.deadline_ts and now > env.deadline_ts:
                log.debug("Task %d expired", env.task_id)
                continue

            runner = self._runners.get(env.kind)
            if not runner:
                log.warning("No runner for kind=%s", env.kind)
                continue

            t0 = time.time()
            try:
                result = runner(env)
                dt = (time.time() - t0) * 1000
                self._durations_ms.append(dt)
                self._results.append({"id": env.task_id, "kind": env.kind,
                                       "ok": True, "ms": round(dt)})
                with self._lock:
                    self._processed += 1
            except Exception as e:
                with self._lock:
                    self._failed += 1
                if env.attempt < env.max_retries:
                    env.attempt += 1
                    env.next_run_at = time.time() + env.backoff_ms / 1000
                    self._queue.put(env)
                else:
                    log.error("Task %d failed: %s", env.task_id, e)

    def _run_idle_learning_cycle(self, now: float, force: bool = False):
        if not self._idle_handlers:
            return
        if not force and (now - self._last_idle_learning_ts) < self._idle_learning_min_sec:
            return
        for handler in self._idle_handlers:
            try:
                handler(force)
            except Exception as e:
                log.warning("Idle learning error: %s", e)
        self._last_idle_learning_ts = now

    def _check_acceptance_backpressure(self, now: float):
        if (now - self._last_backpressure_check_ts) < self._backpressure_check_sec:
            return
        self._last_backpressure_check_ts = now

        snap = get_acceptance_snapshot(window=120)
        rate = float(snap.get("rate", 1.0))
        samples = int(snap.get("samples", 0))

        if samples < self._acceptance_samples_min:
            return

        current_ai_rps = self._class_rps.get("ai", 1)
        if rate < self._acceptance_floor:
            if (now - self._last_backpressure_action_ts) < 30:
                return
            new_rps = max(1, int(current_ai_rps * 0.7))
            self._class_rps["ai"] = new_rps
            os.environ["ARGOS_TASK_RPS_AI"] = str(new_rps)
            self._last_backpressure_action_ts = now
            Metrics.inc("taskqueue.backpressure.applied")
            self._run_idle_learning_cycle(now, force=True)

    def status(self) -> str:
        lines = ["⚙️ TASK QUEUE:"]
        lines.append(f"  Обработано: {self._processed}  Ошибок: {self._failed}")
        lines.append(f"  В очереди:  {self._queue.qsize()}")
        lines.append(f"  RPS:        {self._class_rps}")
        if self._durations_ms:
            avg = sum(self._durations_ms) / len(self._durations_ms)
            lines.append(f"  Avg time:   {avg:.0f}ms")
        return "\n".join(lines)


# README alias
TaskQueue = TaskQueueManager

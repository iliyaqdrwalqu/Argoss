"""
observability.py — Observability Layer Аргоса
  JSON-структурированные логи + метрики + трейсинг спанов.
  Унифицированный слой наблюдаемости поверх argos_logger.py.
  
  Паттерн: каждое действие — span с duration, tags, статусом.
"""
import time, json, os, threading, contextlib
from collections import defaultdict, deque
from src.argos_logger import get_logger
from src.event_bus import get_bus, Events

log    = get_logger("argos.obs")
_bus   = get_bus()
_lock  = threading.Lock()

# JSON-лог
JSON_LOG = "logs/argos_structured.jsonl"
os.makedirs("logs", exist_ok=True)


# ── МЕТРИКИ ───────────────────────────────────────────────
class Metrics:
    _counters  : dict = defaultdict(int)
    _gauges    : dict = defaultdict(float)
    _histograms: dict = defaultdict(list)

    @classmethod
    def inc(cls, name: str, value: int = 1, tags: dict = None):
        key = _tag_key(name, tags)
        cls._counters[key] += value

    @classmethod
    def gauge(cls, name: str, value: float, tags: dict = None):
        key = _tag_key(name, tags)
        cls._gauges[key] = value

    @classmethod
    def observe(cls, name: str, value: float, tags: dict = None):
        """Histogram / summary."""
        key = _tag_key(name, tags)
        cls._histograms[key].append(value)
        if len(cls._histograms[key]) > 1000:
            cls._histograms[key] = cls._histograms[key][-500:]

    @classmethod
    def snapshot(cls) -> dict:
        hist_summary = {}
        for k, vals in cls._histograms.items():
            if vals:
                s = sorted(vals)
                hist_summary[k] = {
                    "count": len(s), "min": s[0], "max": s[-1],
                    "avg": sum(s)/len(s),
                    "p50": s[len(s)//2], "p95": s[int(len(s)*.95)],
                }
        return {
            "counters": dict(cls._counters),
            "gauges":   dict(cls._gauges),
            "histograms": hist_summary,
        }

    @classmethod
    def report(cls) -> str:
        snap = cls.snapshot()
        lines = ["📊 МЕТРИКИ АРГОСА:"]
        if snap["counters"]:
            lines.append("  Счётчики:")
            for k, v in sorted(snap["counters"].items()):
                lines.append(f"    {k}: {v}")
        if snap["gauges"]:
            lines.append("  Измерения:")
            for k, v in sorted(snap["gauges"].items()):
                lines.append(f"    {k}: {v:.2f}")
        if snap["histograms"]:
            lines.append("  Гистограммы:")
            for k, v in snap["histograms"].items():
                lines.append(f"    {k}: avg={v['avg']:.1f}ms p95={v['p95']:.1f}ms")
        return "\n".join(lines) if len(lines) > 1 else "📊 Метрик пока нет."


def _tag_key(name: str, tags: dict = None) -> str:
    if not tags:
        return name
    t = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
    return f"{name}{{{t}}}"


# ── ТРЕЙСИНГ СПАНОВ ───────────────────────────────────────
class Span:
    def __init__(self, name: str, tags: dict = None):
        self.name     = name
        self.tags     = tags or {}
        self._start   = time.perf_counter()
        self._start_t = time.time()
        self.status   = "ok"
        self.error    = None

    def set_tag(self, key: str, value):
        self.tags[key] = value

    def finish(self, status: str = "ok", error: str = None):
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        self.status = status
        self.error  = error
        Metrics.observe("span.duration_ms", elapsed_ms, {"name": self.name})
        Metrics.inc("span.count", tags={"name": self.name, "status": status})
        record = {
            "type":  "span",
            "name":  self.name,
            "tags":  self.tags,
            "ms":    round(elapsed_ms, 2),
            "status": status,
            "ts":    self._start_t,
            "error": error,
        }
        _write_json(record)
        if status == "error":
            log.error("SPAN %-25s %6.1fms [%s] %s", self.name, elapsed_ms, status, error or "")
        else:
            log.debug("SPAN %-25s %6.1fms [%s]",    self.name, elapsed_ms, status)
        return elapsed_ms

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.finish("error", str(exc_val))
        else:
            self.finish("ok")
        return False


@contextlib.contextmanager
def trace(name: str, tags: dict = None):
    span = Span(name, tags)
    try:
        yield span
        span.finish("ok")
    except Exception as e:
        span.finish("error", str(e))
        raise


# ── JSON СТРУКТУРИРОВАННЫЙ ЛОГ ────────────────────────────
_jsonl_lock = threading.Lock()

def _write_json(record: dict):
    try:
        with _jsonl_lock:
            with open(JSON_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def log_event(event_type: str, data: dict, source: str = "argos"):
    """Записать произвольное структурированное событие."""
    record = {"type": event_type, "source": source,
              "ts": time.time(), **data}
    _write_json(record)
    Metrics.inc(f"event.{event_type}")
    _bus.emit(f"obs.{event_type}", data, source)


def log_iot(device: str, metric: str, value, unit: str = ""):
    """Удобная запись IoT-данных."""
    Metrics.gauge(f"iot.{device}.{metric}", float(value) if isinstance(value, (int, float)) else 0)
    log_event("iot_reading", {"device": device, "metric": metric,
                               "value": value, "unit": unit})


def log_intent(text: str, intent: str, state: str, ms: float):
    """Запись распознанного интента."""
    Metrics.inc("intent.count", tags={"intent": intent[:30]})
    Metrics.observe("intent.latency_ms", ms)
    log_event("intent", {"text": text[:100], "intent": intent, "state": state, "ms": ms})


# ── ЧТЕНИЕ ПОСЛЕДНИХ ЗАПИСЕЙ ──────────────────────────────
def tail_json(n: int = 20, event_type: str = None) -> str:
    try:
        if not os.path.exists(JSON_LOG):
            return "Структурированных логов ещё нет."
        with open(JSON_LOG, encoding="utf-8") as f:
            lines = f.readlines()
        records = []
        for l in reversed(lines):
            try:
                r = json.loads(l)
                if event_type and r.get("type") != event_type:
                    continue
                records.append(r)
                if len(records) >= n:
                    break
            except Exception:
                pass
        if not records:
            return "Нет записей."
        out = [f"📋 ПОСЛЕДНИЕ {len(records)} ЗАПИСЕЙ ({JSON_LOG}):"]
        for r in reversed(records):
            ts   = time.strftime("%H:%M:%S", time.localtime(r.get("ts", 0)))
            rtype = r.get("type","?")
            out.append(f"  [{ts}] {rtype}: {_format_record(r)}")
        return "\n".join(out)
    except Exception as e:
        return f"❌ {e}"


def _format_record(r: dict) -> str:
    if r.get("type") == "span":
        return f"{r['name']} {r['ms']}ms [{r['status']}]"
    if r.get("type") == "iot_reading":
        return f"{r['device']}.{r['metric']}={r['value']}{r.get('unit','')}"
    if r.get("type") == "intent":
        return f"\"{r.get('text','')[:40]}\" → {r.get('intent','?')}"
    return str({k: v for k, v in r.items() if k not in ("type","ts","source")})[:80]

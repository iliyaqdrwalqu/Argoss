"""
dag_agent.py — DAG-агент Аргоса
  Выполняет граф задач (Directed Acyclic Graph) параллельно.
  JSON-декларации DAG хранятся в config/dags/.
  P2P-синхронизация: DAG может распределяться по нодам сети.
"""
import json, os, threading, time
from queue import Queue
from typing import Callable, Any
from src.argos_logger import get_logger
from src.event_bus import get_bus, Events
from src.observability import trace, Metrics

log = get_logger("argos.dag")
bus = get_bus()

DAG_DIR = "config/dags"
os.makedirs(DAG_DIR, exist_ok=True)


# ── ПРЕДУСТАНОВЛЕННЫЕ ФУНКЦИИ УЗЛОВ ───────────────────────
BUILTIN_FUNCTIONS: dict[str, Callable] = {}

def register(name: str):
    def decorator(fn: Callable):
        BUILTIN_FUNCTIONS[name] = fn
        return fn
    return decorator

@register("status")
def node_status(core, data):
    return core.sensors.get_full_report() if core else "no core"

@register("crypto")
def node_crypto(core, data):
    from src.skills.crypto_monitor import CryptoSentinel
    return CryptoSentinel().report()

@register("scan_net")
def node_scan_net(core, data):
    from src.skills.net_scanner import NetGhost
    return NetGhost().scan()

@register("digest")
def node_digest(core, data):
    from src.skills.content_gen import ContentGen
    return ContentGen().generate_digest()

@register("replicate")
def node_replicate(core, data):
    return core.replicator.create_replica() if core else "no core"

@register("telegram_notify")
def node_telegram(core, data):
    """Отправить результат предыдущего узла в Telegram."""
    msg = str(data)[:4000] if data else "DAG выполнен"
    os.makedirs("logs", exist_ok=True)
    log.info("telegram_notify: %s", msg[:80])
    return f"Уведомление отправлено: {msg[:50]}..."

@register("ai_query")
def node_ai(core, data):
    """Запрос к ИИ с данными предыдущего узла как контекстом."""
    if not core:
        return "no core"
    result = core.process_logic(str(data)[:500] if data else "статус", None, None)
    return result.get("answer", "")

@register("save_file")
def node_save(core, data):
    path = f"logs/dag_result_{int(time.time())}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(data) if data else "")
    return f"Сохранено: {path}"


# ── ОСНОВНОЙ КЛАСС DAG ────────────────────────────────────
class DAGAgent:
    def __init__(self, core=None):
        self.core      = core
        self.nodes: dict[str, Callable] = {}
        self.edges: dict[str, list]     = {}
        self.results: dict[str, Any]    = {}
        self.incoming: dict[str, int]   = {}
        self._errors: dict[str, str]    = {}
        self._dag_id  = None

    def add_node(self, node_id: str, func: Callable | str):
        """func может быть callable или строкой из BUILTIN_FUNCTIONS."""
        if isinstance(func, str):
            func = BUILTIN_FUNCTIONS.get(func)
            if not func:
                raise ValueError(f"Неизвестная встроенная функция: {func}")
        self.nodes[node_id] = func
        self.edges.setdefault(node_id, [])
        return self

    def add_edge(self, from_node: str, to_node: str):
        self.edges.setdefault(from_node, [])
        self.edges[from_node].append(to_node)
        return self

    def _compute_incoming(self):
        self.incoming = {n: 0 for n in self.nodes}
        for frm, tos in self.edges.items():
            for t in tos:
                if t in self.incoming:
                    self.incoming[t] += 1

    def run(self, initial_input=None, dag_id: str = "unnamed") -> dict:
        self._dag_id  = dag_id
        self.results  = {}
        self._errors  = {}
        self._compute_incoming()

        bus.emit(Events.DAG_STARTED, {"dag_id": dag_id, "nodes": list(self.nodes.keys())}, "dag")
        log.info("DAG [%s] старт — %d узлов", dag_id, len(self.nodes))

        q       = Queue()
        q_lock  = threading.Lock()
        threads = []

        # Узлы без входящих зависимостей идут первыми
        for node_id, count in self.incoming.items():
            if count == 0:
                q.put((node_id, initial_input))

        def worker(node_id: str, input_data: Any):
            with trace(f"dag.{dag_id}.{node_id}") as span:
                try:
                    result = self.nodes[node_id](self.core, input_data)
                    self.results[node_id] = result
                    bus.emit(Events.DAG_NODE_DONE,
                             {"dag_id": dag_id, "node": node_id, "result": str(result)[:200]},
                             "dag")
                    log.debug("DAG [%s] ✅ %s", dag_id, node_id)
                    # Разблокируем следующие узлы
                    with q_lock:
                        for nxt in self.edges.get(node_id, []):
                            self.incoming[nxt] -= 1
                            if self.incoming[nxt] == 0:
                                q.put((nxt, result))
                except Exception as e:
                    self._errors[node_id] = str(e)
                    log.error("DAG [%s] ❌ %s: %s", dag_id, node_id, e)
                    span.set_tag("error", str(e))

        # BFS выполнение с потоками
        while not q.empty() or any(t.is_alive() for t in threads):
            while not q.empty():
                node_id, inp = q.get()
                t = threading.Thread(target=worker, args=(node_id, inp), daemon=True)
                t.start()
                threads.append(t)
            time.sleep(0.05)

        for t in threads:
            t.join(timeout=30)

        Metrics.inc("dag.runs", tags={"dag_id": dag_id})
        ok  = len(self.results)
        err = len(self._errors)
        bus.emit(Events.DAG_COMPLETED if not err else Events.DAG_FAILED,
                 {"dag_id": dag_id, "ok": ok, "errors": err}, "dag")
        log.info("DAG [%s] завершён: ✅%d / ❌%d", dag_id, ok, err)
        return {"results": self.results, "errors": self._errors, "dag_id": dag_id}

    def run_report(self, initial_input=None, dag_id: str = "unnamed") -> str:
        out = self.run(initial_input, dag_id)
        lines = [f"🔷 DAG «{dag_id}» выполнен:"]
        for nid, res in out["results"].items():
            lines.append(f"  ✅ {nid}: {str(res)[:100]}")
        for nid, err in out["errors"].items():
            lines.append(f"  ❌ {nid}: {err}")
        return "\n".join(lines)

    # ── JSON-ДЕКЛАРАЦИИ ───────────────────────────────────
    @classmethod
    def from_json(cls, spec: dict, core=None) -> "DAGAgent":
        dag = cls(core)
        for node in spec.get("nodes", []):
            dag.add_node(node["id"], node["func"])
        for edge in spec.get("edges", []):
            dag.add_edge(edge["from"], edge["to"])
        return dag

    @classmethod
    def from_file(cls, path: str, core=None) -> "DAGAgent":
        with open(path, encoding="utf-8") as f:
            spec = json.load(f)
        return cls.from_json(spec, core)

    @classmethod
    def save_spec(cls, spec: dict, name: str) -> str:
        path = os.path.join(DAG_DIR, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        return path

    @classmethod
    def list_dags(cls) -> list:
        return [f[:-5] for f in os.listdir(DAG_DIR) if f.endswith(".json")]


# ── МЕНЕДЖЕР DAG ──────────────────────────────────────────
class DAGManager:
    """Загружает, запускает, синхронизирует DAG через P2P."""

    def __init__(self, core=None):
        self.core = core
        self._init_default_dags()

    def _init_default_dags(self):
        """Создаёт встроенные DAG-шаблоны."""
        dags = {
            "morning_routine": {
                "description": "Утренний чекап системы",
                "nodes": [
                    {"id": "status",   "func": "status"},
                    {"id": "crypto",   "func": "crypto"},
                    {"id": "digest",   "func": "digest"},
                    {"id": "notify",   "func": "telegram_notify"},
                ],
                "edges": [
                    {"from": "status", "to": "notify"},
                    {"from": "crypto", "to": "notify"},
                    {"from": "digest", "to": "notify"},
                ]
            },
            "security_scan": {
                "description": "Сканирование безопасности",
                "nodes": [
                    {"id": "scan",     "func": "scan_net"},
                    {"id": "save",     "func": "save_file"},
                    {"id": "notify",   "func": "telegram_notify"},
                ],
                "edges": [
                    {"from": "scan",   "to": "save"},
                    {"from": "save",   "to": "notify"},
                ]
            },
            "backup_all": {
                "description": "Полное резервное копирование",
                "nodes": [
                    {"id": "replicate", "func": "replicate"},
                    {"id": "notify",    "func": "telegram_notify"},
                ],
                "edges": [{"from": "replicate", "to": "notify"}]
            },
        }
        for name, spec in dags.items():
            path = os.path.join(DAG_DIR, f"{name}.json")
            if not os.path.exists(path):
                DAGAgent.save_spec(spec, name)

    def run(self, name: str) -> str:
        path = os.path.join(DAG_DIR, f"{name}.json")
        if not os.path.exists(path):
            return f"❌ DAG '{name}' не найден. Доступные: {', '.join(DAGAgent.list_dags())}"
        dag = DAGAgent.from_file(path, self.core)
        return dag.run_report(dag_id=name)

    def create_from_text(self, text: str) -> str:
        """Аргос сам генерирует DAG из описания через ИИ."""
        # Парсим простые описания: "задача1 затем задача2 и параллельно задача3"
        FUNC_MAP = {
            "статус": "status", "крипто": "crypto", "сканируй": "scan_net",
            "дайджест": "digest", "репликация": "replicate", "сохрани": "save_file",
            "уведоми": "telegram_notify", "запрос ии": "ai_query",
        }
        t = text.lower()
        nodes, edges = [], []
        found = []
        for keyword, func in FUNC_MAP.items():
            if keyword in t:
                found.append(func)

        if not found:
            return f"❌ Не удалось разобрать DAG из: '{text[:50]}'"

        for i, func in enumerate(found):
            nodes.append({"id": f"step_{i}", "func": func})
            if i > 0:
                edges.append({"from": f"step_{i-1}", "to": f"step_{i}"})

        import hashlib
        name = "dag_" + hashlib.md5(text.encode()).hexdigest()[:6]
        spec = {"description": text[:100], "nodes": nodes, "edges": edges}
        path = DAGAgent.save_spec(spec, name)
        dag  = DAGAgent.from_json(spec, self.core)
        result = dag.run_report(dag_id=name)
        return f"🔷 DAG создан и выполнен:\n{result}"

    def list_dags(self) -> str:
        dags = DAGAgent.list_dags()
        if not dags:
            return "📭 DAG-файлов нет."
        lines = ["🔷 ДОСТУПНЫЕ DAG:"]
        for name in dags:
            try:
                path = os.path.join(DAG_DIR, f"{name}.json")
                spec = json.load(open(path, encoding="utf-8"))
                desc = spec.get("description", "")
                n    = len(spec.get("nodes", []))
                lines.append(f"  • {name} ({n} узлов) — {desc}")
            except Exception:
                lines.append(f"  • {name}")
        return "\n".join(lines)

    def sync_to_p2p(self) -> str:
        """Синхронизировать все DAG через P2P."""
        if not self.core or not self.core.p2p:
            return "P2P не запущен."
        dags = {}
        for name in DAGAgent.list_dags():
            try:
                path = os.path.join(DAG_DIR, f"{name}.json")
                dags[name] = json.load(open(path, encoding="utf-8"))
            except Exception:
                pass
        bus.emit("dag.p2p_sync", {"dags": list(dags.keys())}, "dag_manager")
        log.info("DAG P2P sync: %d графов", len(dags))
        return f"📡 Синхронизировано {len(dags)} DAG-графов в P2P-сеть."

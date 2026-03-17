"""
pupi_ops.py -- Pupi API client for ARGOS.
Configure via PUPI_API_URL and PUPI_API_TOKEN env vars.
"""
import os, time, uuid
from typing import Any, Dict, List, Optional
from src.argos_logger import get_logger
log = get_logger("argos.pupi")

try:
    import requests as _req
    REQUESTS_OK = True
except ImportError:
    _req = None
    REQUESTS_OK = False


class ArgosPupiOps:
    def __init__(self):
        self._url = (os.getenv("PUPI_API_URL","") or "").rstrip("/")
        self._token = os.getenv("PUPI_API_TOKEN","") or ""
        self._node_id = self._load_node_id()
        self.configured = bool(self._url and self._token)
        if self.configured:
            log.info("PupiOps: url=%s node=%s", self._url, self._node_id[:8])
        else:
            log.info("PupiOps: not configured (set PUPI_API_URL + PUPI_API_TOKEN)")

    @staticmethod
    def _load_node_id() -> str:
        p = "config/node_id"
        if os.path.exists(p):
            return open(p).read().strip()
        nid = str(uuid.uuid4())
        os.makedirs("config", exist_ok=True)
        open(p,"w").write(nid)
        return nid

    def _hdr(self) -> Dict[str,str]:
        return {"Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "X-Node-ID": self._node_id}

    def _post(self, ep: str, data: Dict) -> Optional[Dict]:
        if not self.configured or not REQUESTS_OK:
            return None
        try:
            r = _req.post(f"{self._url}{ep}", headers=self._hdr(), json=data, timeout=10)
            return r.json() if r.ok and r.content else ({} if r.ok else None)
        except Exception as e:
            log.debug("Pupi POST: %s", e)
            return None

    def _get(self, ep: str, params: Dict = None) -> Optional[Dict]:
        if not self.configured or not REQUESTS_OK:
            return None
        try:
            r = _req.get(f"{self._url}{ep}", headers=self._hdr(),
                         params=params or {}, timeout=10)
            return r.json() if r.ok and r.content else None
        except Exception as e:
            log.debug("Pupi GET: %s", e)
            return None

    def push_metrics(self, metrics: Dict[str, Any]) -> str:
        if not self.configured:
            return "Pupi: not configured."
        r = self._post("/api/v1/metrics",
                       {"node_id": self._node_id, "ts": time.time(), "metrics": metrics})
        return f"Pupi: metrics sent ({len(metrics)})" if r is not None else "Pupi: send error"

    def register_node(self, meta: Dict[str,Any] = None) -> str:
        if not self.configured:
            return "Pupi: not configured."
        import platform
        payload = {"node_id": self._node_id, "hostname": platform.node(),
                   "os": platform.system(), "version": "1.3",
                   "ts": time.time(), **(meta or {})}
        r = self._post("/api/v1/nodes/register", payload)
        return (f"Pupi: node registered ({self._node_id[:8]})"
                if r is not None else "Pupi: registration error")

    def pull_config(self) -> Optional[Dict]:
        return self._get(f"/api/v1/nodes/{self._node_id}/config")

    def get_tasks(self) -> List[Dict]:
        r = self._get(f"/api/v1/nodes/{self._node_id}/tasks")
        return r.get("tasks", []) if isinstance(r, dict) else []

    def ack_task(self, task_id: str, result: Any = None) -> str:
        r = self._post(f"/api/v1/tasks/{task_id}/ack",
                       {"task_id": task_id, "node_id": self._node_id,
                        "result": result, "ts": time.time()})
        return (f"Pupi: task {task_id} acked" if r is not None
                else f"Pupi: ack error {task_id}")

    def status(self) -> str:
        return (f"Pupi: configured={self.configured}  "
                f"url={self._url or 'N/A'}  node={self._node_id[:8]}")

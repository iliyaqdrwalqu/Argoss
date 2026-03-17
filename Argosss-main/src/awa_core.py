\
"""awa_core.py — AWA-Core: Absolute Workflow Agent"""
from __future__ import annotations
import json, os, threading, time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional
from src.argos_logger import get_logger
log = get_logger("argos.awa")

class ModuleDescriptor:
    __slots__ = ("name","ref","priority","category","capabilities","health","last_heartbeat")
    def __init__(self, name, ref, priority=50, category="general", capabilities=None):
        self.name=name; self.ref=ref; self.priority=priority
        self.category=category; self.capabilities=capabilities or []
        self.health="ok"; self.last_heartbeat=time.time()
    def to_dict(self):
        return {"name":self.name,"priority":self.priority,"category":self.category,
                "capabilities":self.capabilities,"health":self.health,
                "last_heartbeat":round(self.last_heartbeat,1)}

class DecisionRecord:
    __slots__ = ("ts","intent","routed_to","result","latency_ms")
    def __init__(self, intent, routed_to, result, latency_ms):
        self.ts=time.time(); self.intent=intent; self.routed_to=routed_to
        self.result=result; self.latency_ms=latency_ms

class AWACore:
    VERSION = "1.0.0"
    def __init__(self, core=None):
        self.core = core
        self._modules: Dict[str,ModuleDescriptor] = {}
        self._capability_index: Dict[str,List[str]] = defaultdict(list)
        self._pipelines: Dict[str,List[Dict[str,Any]]] = {}
        self._decision_log: deque[DecisionRecord] = deque(maxlen=500)
        self._cascade_depth_limit = int(os.getenv("AWA_CASCADE_DEPTH","8") or "8")
        self._heartbeat_max_age_sec = float(os.getenv("AWA_HEARTBEAT_MAX_AGE","120") or "120")
        self._heartbeat_check_interval_sec = float(os.getenv("AWA_HEARTBEAT_CHECK_INTERVAL","15") or "15")
        self._lock = threading.Lock()
        self._running = True
        self._policy = os.getenv("AWA_POLICY","bypass").strip().lower()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        log.info("AWA-Core v%s init | policy=%s | cascade_depth=%d",
                 self.VERSION, self._policy, self._cascade_depth_limit)

    def register(self, name, ref, *, priority=50, category="general", capabilities=None):
        desc = ModuleDescriptor(name, ref, priority, category, capabilities)
        with self._lock:
            self._modules[name] = desc
            for cap in desc.capabilities:
                if name not in self._capability_index[cap]:
                    self._capability_index[cap].append(name)
        log.info("AWA: зарегистрирован [%s] cat=%s", name, category)

    def unregister(self, name):
        with self._lock:
            desc = self._modules.pop(name, None)
            if desc:
                for cap in desc.capabilities:
                    lst = self._capability_index.get(cap,[])
                    if name in lst: lst.remove(name)

    def resolve(self, capability) -> Optional[Any]:
        with self._lock:
            names = self._capability_index.get(capability,[])
            if not names: return None
            candidates = [(self._modules[n].priority,n) for n in names
                          if n in self._modules and self._modules[n].health=="ok"]
        if not candidates: return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return self._modules[candidates[0][1]].ref

    def route(self, intent, payload=None) -> str:
        t0 = time.time()
        ref = self.resolve(intent)
        if ref is None:
            self._decision_log.append(DecisionRecord(intent,"none","no_module",0))
            return f"⚠️ AWA: нет модуля для '{intent}'"
        result = "ok"
        try:
            if hasattr(ref,"handle"): result = ref.handle(intent,payload)
            elif callable(ref): result = ref(intent,payload)
        except Exception as e:
            result = f"error: {e}"; log.error("AWA route error [%s]: %s", intent, e)
        latency = (time.time()-t0)*1000
        name = getattr(ref,"__class__",type(ref)).__name__
        self._decision_log.append(DecisionRecord(intent,name,str(result)[:120],latency))
        return str(result)

    def register_pipeline(self, name, steps) -> str:
        if not name.strip(): return "⚠️ имя пустое"
        if not steps: return "⚠️ pipeline пустой"
        with self._lock: self._pipelines[name.strip()] = steps
        return f"✅ AWA pipeline '{name}' ({len(steps)} шагов)"

    def cascade(self, steps) -> List[str]:
        results = []
        for i,step in enumerate(steps):
            if i >= self._cascade_depth_limit:
                results.append(f"⚠️ AWA: лимит каскада ({self._cascade_depth_limit})"); break
            res = self.route(step.get("intent",""), step.get("payload"))
            results.append(res)
            if "error" in res.lower():
                log.warning("AWA cascade остановлен на шаге %d", i); break
        return results

    def heartbeat(self, name):
        with self._lock:
            desc = self._modules.get(name)
            if desc: desc.last_heartbeat=time.time(); desc.health="ok"

    def mark_unhealthy(self, name, reason=""):
        with self._lock:
            desc = self._modules.get(name)
            if desc: desc.health=f"unhealthy: {reason}" if reason else "unhealthy"

    def check_stale(self, max_age_sec=120) -> List[str]:
        now = time.time()
        with self._lock:
            return [n for n,d in self._modules.items() if now-d.last_heartbeat>max_age_sec]

    def _heartbeat_loop(self):
        while self._running:
            time.sleep(self._heartbeat_check_interval_sec)
            stale = self.check_stale(self._heartbeat_max_age_sec)
            for name in stale:
                self.mark_unhealthy(name,"stale heartbeat")

    def status(self) -> str:
        with self._lock:
            mods = list(self._modules.values())
        lines = [f"🧠 AWA-Core v{self.VERSION} | policy={self._policy}",
                 f"  Модулей: {len(mods)}  Решений: {len(self._decision_log)}"]
        for m in sorted(mods, key=lambda x: x.name):
            lines.append(f"  {'✅' if m.health=='ok' else '⚠️'} [{m.name}] "
                         f"cat={m.category} prio={m.priority} caps={m.capabilities}")
        return "\\n".join(lines)

    def history(self, n=10) -> str:
        recs = list(self._decision_log)[-n:]
        if not recs: return "🧠 AWA история пуста."
        lines = ["🧠 AWA ИСТОРИЯ:"]
        for r in recs:
            t = time.strftime("%H:%M:%S", time.localtime(r.ts))
            lines.append(f"  [{t}] {r.intent} → {r.routed_to} ({r.latency_ms:.0f}ms) : {r.result[:50]}")
        return "\\n".join(lines)

    def health_check(self) -> str:
        stale = self.check_stale(self._heartbeat_max_age_sec)
        if not stale: return "✅ AWA: все модули здоровы."
        return "⚠️ AWA: устаревшие модули:\\n" + "\\n".join(f"  - {n}" for n in stale)

"""
fastapi_dashboard.py — современный dashboard Аргоса на FastAPI.
Если FastAPI/uvicorn недоступны, core автоматически использует legacy dashboard.

Дополнительные REST-эндпоинты для удалённого управления (Android APK):
  GET  /api/health          → версия, uptime, статус
  POST /api/command         → выполнить команду (JSON: {"cmd": "..."})
  GET  /api/events?limit=N  → последние события из EventBus

Аутентификация: Bearer-токен из переменной окружения ARGOS_REMOTE_TOKEN.
CORS включён (по умолчанию allow all) для доступа с мобильного клиента.
"""
import json
import os
import threading
import time
from collections import deque

from src.argos_logger import get_logger

log = get_logger("argos.fastapi_dashboard")

ARGOS_VERSION = "1.4.0"


class FastAPIDashboard:
    def __init__(self, core, admin, flasher, port: int = 8080):
        self.core = core
        self.admin = admin
        self.flasher = flasher
        self.port = port
        self._start_t = time.time()
        self._thread = None
        self._server = None
        self._history = deque(maxlen=120)

    def start(self) -> str:
        try:
            from fastapi import FastAPI, Request, status
            from fastapi.responses import HTMLResponse, JSONResponse
            from fastapi.middleware.cors import CORSMiddleware
            import psutil
            import uvicorn
        except Exception as e:
            return f"❌ FastAPI Dashboard: {e}"

        # ── Токен аутентификации ──────────────────────────────────────
        _remote_token: str = os.environ.get("ARGOS_REMOTE_TOKEN", "")

        def _check_auth(request: Request):
            """Возвращает True если токен не задан или совпадает с Bearer-токеном."""
            if not _remote_token:
                return True
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return False
            return auth_header[len("Bearer "):] == _remote_token

        app = FastAPI(title="Argos Dashboard", docs_url="/docs")

        # ── CORS ──────────────────────────────────────────────────────
        cors_origins = os.environ.get("ARGOS_CORS_ORIGINS", "*").split(",")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        html = """<!doctype html><html lang='ru'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><title>Argos FastAPI Dashboard</title><script src='https://cdn.jsdelivr.net/npm/chart.js'></script><style>body{font-family:Inter,Arial,sans-serif;background:#0b1020;color:#dce7ff;margin:0;padding:20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.card{background:#131b35;border:1px solid #243055;border-radius:12px;padding:14px}button{padding:8px 12px;border-radius:8px;border:1px solid #3d4f88;background:#1b2957;color:#dce7ff;cursor:pointer}input{padding:8px;border-radius:8px;border:1px solid #3d4f88;background:#0f1732;color:#dce7ff;width:100%}pre{background:#0a1024;padding:10px;border-radius:8px;max-height:260px;overflow:auto}.row{display:flex;gap:8px}.small{opacity:.8;font-size:.9em}</style></head><body><h2>👁️ Argos FastAPI Dashboard</h2><div class='small'>Метрики, логи, команды</div><div class='grid'><div class='card'><canvas id='chart'></canvas></div><div class='card'><div id='stats'>Loading...</div><div class='row' style='margin-top:10px'><button onclick='toggleVoice()' id='voiceBtn'>Toggle Voice</button><button onclick='quick(`iot статус`)'>IoT</button><button onclick='quick(`шаблоны шлюзов`)'>Gateways</button></div></div><div class='card'><div class='row'><input id='cmd' placeholder='Команда...' onkeydown='if(event.key===`Enter`)sendCmd()'/><button onclick='sendCmd()'>Send</button></div><pre id='resp'></pre></div><div class='card'><pre id='log'></pre></div></div><script>const ctx=document.getElementById('chart');const chart=new Chart(ctx,{type:'line',data:{labels:[],datasets:[{label:'CPU %',data:[],borderColor:'#40c4ff'},{label:'RAM %',data:[],borderColor:'#7CFF6B'}]}});let voiceOn=false;async function tick(){const r=await fetch('/api/status');const d=await r.json();voiceOn=!!d.voice_on;document.getElementById('voiceBtn').innerText=voiceOn?'🔇 Voice OFF':'🔊 Voice ON';document.getElementById('stats').innerHTML=`<b>${d.state}</b><br/>CPU: ${d.cpu.toFixed(1)}% · RAM: ${d.ram.toFixed(1)}% · Disk: ${d.disk.toFixed(1)}%<br/>Uptime: ${d.uptime} · P2P: ${d.p2p_nodes}`;chart.data.labels.push(new Date().toLocaleTimeString());chart.data.datasets[0].data.push(d.cpu);chart.data.datasets[1].data.push(d.ram);if(chart.data.labels.length>30){chart.data.labels.shift();chart.data.datasets[0].data.shift();chart.data.datasets[1].data.shift()}chart.update();const lg=await fetch('/api/log');const j=await lg.json();document.getElementById('log').textContent=j.lines||'';}async function sendCmd(){const v=document.getElementById('cmd').value.trim();if(!v)return;document.getElementById('cmd').value='';const r=await fetch('/api/cmd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd:v})});const d=await r.json();document.getElementById('resp').textContent=d.answer||d.error||'-';setTimeout(tick,200);}function quick(cmd){document.getElementById('cmd').value=cmd;sendCmd();}function toggleVoice(){quick(voiceOn?'голос выкл':'голос вкл')}setInterval(tick,2500);tick();</script></body></html>"""

        @app.get("/", response_class=HTMLResponse)
        async def index():
            return HTMLResponse(content=html)

        @app.get("/api/status")
        async def api_status():
            uptime_s = int(time.time() - self._start_t)
            h, m = divmod(uptime_s // 60, 60)
            uptime = f"{h}ч {m}мин"
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent
            state = self.core.quantum.generate_state()["name"] if self.core else "Offline"
            voice = bool(self.core.voice_on) if self.core else False
            p2p_nodes = len(self.core.p2p.registry.all()) if self.core and self.core.p2p else 0
            self._history.append({"ts": time.time(), "cpu": cpu, "ram": ram, "disk": disk})
            return JSONResponse({
                "state": state,
                "voice_on": voice,
                "uptime": uptime,
                "cpu": cpu,
                "ram": ram,
                "disk": disk,
                "p2p_nodes": p2p_nodes,
                "history": list(self._history),
            })

        @app.get("/api/log")
        async def logs():
            lines = ""
            try:
                log_path = "logs/argos.log"
                if os.path.exists(log_path):
                    with open(log_path, encoding="utf-8") as f:
                        lines = "".join(f.readlines()[-120:])
            except Exception:
                pass
            return JSONResponse({"lines": lines})

        @app.post("/api/cmd")
        async def cmd(payload: dict):
            command = (payload or {}).get("cmd", "")
            if not command:
                return JSONResponse({"error": "Пустая команда"}, status_code=400)
            try:
                result = await self.core.process_logic_async(command, self.admin, self.flasher)
                return JSONResponse(result)
            except Exception as e:
                return JSONResponse({"answer": f"Ошибка: {e}"})

        # ── НОВЫЕ ЭНДПОИНТЫ ДЛЯ УДАЛЁННОГО УПРАВЛЕНИЯ ────────────────

        @app.get("/api/health")
        async def health(request: Request):
            """Проверка доступности API. Не требует авторизации."""
            uptime_s = int(time.time() - self._start_t)
            return JSONResponse({
                "status": "ok",
                "version": ARGOS_VERSION,
                "uptime_seconds": uptime_s,
            })

        @app.post("/api/command")
        async def remote_command(request: Request):
            """Выполнить команду ARGOS. Требует Bearer-токен."""
            if not _check_auth(request):
                return JSONResponse({"error": "Unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
            try:
                payload = await request.json()
            except Exception:
                payload = {}
            command = (payload or {}).get("cmd", "").strip()
            if not command:
                return JSONResponse({"error": "Пустая команда"}, status_code=400)
            try:
                result = await self.core.process_logic_async(command, self.admin, self.flasher)
                answer = result.get("answer", "") if isinstance(result, dict) else str(result)
                return JSONResponse({"answer": answer, "raw": result})
            except Exception as e:
                return JSONResponse({"answer": f"Ошибка: {e}", "raw": None})

        @app.get("/api/events")
        async def remote_events(request: Request, limit: int = 20):
            """Последние события из EventBus. Требует Bearer-токен."""
            if not _check_auth(request):
                return JSONResponse({"error": "Unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED)
            try:
                from src.connectivity.event_bus import bus as event_bus
                limit = max(1, min(limit, 200))
                events = event_bus.recent(limit=limit)
                serialized = []
                for ev in events:
                    payload = ev.payload
                    if not isinstance(payload, (dict, list, str, int, float, bool, type(None))):
                        payload = str(payload)
                    serialized.append({
                        "type": ev.type,
                        "source": ev.source,
                        "ts": ev.ts,
                        "payload": payload,
                    })
                return JSONResponse({"events": serialized, "count": len(serialized)})
            except Exception as e:
                return JSONResponse({"events": [], "count": 0, "error": str(e)})

        config = uvicorn.Config(app=app, host="0.0.0.0", port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)

        def _run():
            self._server.run()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        log.info("FastAPI Dashboard запущен на http://localhost:%d", self.port)
        return f"🌐 FastAPI панель: http://localhost:{self.port}"

    def stop(self):
        if self._server:
            self._server.should_exit = True

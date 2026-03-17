\
"""
web_engine.py — ARGOS v1.3 Web Dashboard (Aether Interface)
FastAPI + Matrix canvas + полный REST API
Запуск: python main.py --dashboard  →  http://localhost:8080
"""
import threading
import os

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
    FASTAPI_OK = True
except ImportError:
    FASTAPI_OK = False

# ── HTML шаблон (Sovereign Emerald + Matrix) ─────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ARGOS v1.33 MASTER</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  * { box-sizing: border-box; }
  body { background:#000; color:#00FF41; font-family:monospace; overflow-x:hidden; margin:0; }
  .hud { background:rgba(0,255,65,0.03); border:1px solid rgba(0,255,65,0.2); backdrop-filter:blur(12px); }
  .btn-hud { background:rgba(0,255,65,0.06); border:1px solid rgba(0,255,65,0.25);
             color:#00ff41; cursor:pointer; transition:all .2s; padding:12px 8px;
             border-radius:10px; font-family:monospace; font-size:13px; }
  .btn-hud:hover { background:rgba(0,255,65,0.18); box-shadow:0 0 12px rgba(0,255,65,0.3); }
  .btn-hud:active { transform:scale(0.97); }
  #console { background:rgba(0,10,0,0.8); border:1px solid rgba(0,255,65,0.15);
             border-radius:10px; padding:14px; height:220px; overflow-y:auto;
             font-size:13px; line-height:1.6; }
  #console .entry-ok  { color:#00ff88; }
  #console .entry-err { color:#ff4444; }
  #console .entry-sys { color:#00aaff; }
  #cmd-input { background:rgba(0,20,0,0.9); border:1px solid rgba(0,255,65,0.3);
               color:#00ff41; padding:10px 14px; border-radius:8px;
               font-family:monospace; font-size:14px; outline:none; width:100%; }
  #cmd-input:focus { border-color:#00ff88; box-shadow:0 0 8px rgba(0,255,65,0.2); }
  .status-dot { width:8px; height:8px; border-radius:50%; background:#00ff41;
                display:inline-block; animation:pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
  .quantum-badge { padding:3px 10px; border-radius:20px; font-size:11px; font-weight:bold; }
  .q-Analytic   { background:rgba(0,200,255,0.15); color:#00ccff; border:1px solid #00ccff55; }
  .q-Creative   { background:rgba(180,0,255,0.15); color:#cc88ff; border:1px solid #cc88ff55; }
  .q-Protective { background:rgba(255,50,50,0.15);  color:#ff6666; border:1px solid #ff666655; }
  .q-Unstable   { background:rgba(255,220,0,0.15);  color:#ffdd00; border:1px solid #ffdd0055; }
  .q-AllSeeing  { background:rgba(0,255,65,0.15);   color:#00ff41; border:1px solid #00ff4155; }
  canvas#matrix { position:fixed; top:0; left:0; z-index:-1; opacity:0.18; pointer-events:none; }
  .omni-card { background:#050a15cc; border:1px solid #243055; border-radius:12px; padding:12px; min-height:128px; }
  .omni-title { font-size:12px; letter-spacing:.08em; font-weight:bold; opacity:.95; }
</style>
</head>
<body>
<canvas id="matrix"></canvas>

<div class="p-5 flex flex-col gap-4 min-h-screen">

  <!-- Заголовок -->
  <div class="hud p-4 rounded-xl flex justify-between items-center">
    <div class="flex items-center gap-3">
      <span class="text-2xl font-bold tracking-widest">🔱 ARGOS SOVEREIGN</span>
      <span class="status-dot"></span>
      <span id="q-badge" class="quantum-badge q-Analytic">Analytic</span>
    </div>
    <div class="text-right text-xs opacity-60">
      <div>NODE_ID: Master_7F2A | STATUS: ONLINE</div>
      <div id="clock">--:--:--</div>
      <div id="sys-mini">CPU: -- | RAM: --</div>
    </div>
  </div>

  <!-- Быстрые кнопки -->
  <div class="grid grid-cols-3 md:grid-cols-6 gap-3">
    <button class="btn-hud" onclick="sendCmd('статус системы')">📊 Статус</button>
    <button class="btn-hud" onclick="sendCmd('root статус')">🛡️ Root</button>
    <button class="btn-hud" onclick="sendCmd('nfc статус')">📡 NFC</button>
    <button class="btn-hud" onclick="sendCmd('bt статус')">🔵 BT</button>
    <button class="btn-hud" onclick="sendCmd('квантовое состояние')">⚛️ Quantum</button>
    <button class="btn-hud" onclick="sendCmd('awa статус')">🧠 AWA</button>
    <button class="btn-hud" onclick="sendCmd('умные системы')">🏠 Smart</button>
    <button class="btn-hud" onclick="sendCmd('найди usb чипы')">🔌 USB</button>
    <button class="btn-hud" onclick="sendCmd('healing статус')">🩹 Healing</button>
    <button class="btn-hud" onclick="sendCmd('p2p статус сети')">🌐 P2P</button>
    <button class="btn-hud" onclick="sendCmd('git статус')">🔧 Git</button>
    <button class="btn-hud" onclick="sendCmd('список навыков')">🧬 Skills</button>
  </div>

  <!-- Консоль -->
  <div id="console">
    <div class="entry-sys">&gt; ARGOS v1.33 ONLINE</div>
    <div class="entry-sys">&gt; Aether Interface активирован</div>
  </div>

  <!-- Omni Presence standard -->
  <div class="grid grid-cols-1 md:grid-cols-4 gap-3" id="omni-presence">
    <div class="omni-card border-[#00ff41]">
      <div class="omni-title text-[#00ff41]">DESKTOP MASTER</div>
      <div class="text-[11px] mt-2 text-[#00ff41]">SWARM METRICS</div>
      <div class="text-[10px] mt-1 opacity-80">&gt; shell: root_active</div>
      <div class="text-[10px] opacity-80">&gt; aether: synced</div>
    </div>
    <div class="omni-card border-[#00f2ff]">
      <div class="omni-title text-[#00f2ff]">PHONE NODE</div>
      <div class="text-[11px] mt-2 text-[#00f2ff]">TAP TO SYNC</div>
      <div class="text-[10px] mt-2 text-[#00ff41]">Neural Core: ONLINE</div>
    </div>
    <div class="omni-card border-[#ff4b4b]">
      <div class="omni-title text-[#ff4b4b]">WEARABLE</div>
      <div class="text-[20px] mt-2">💓 82</div>
      <div class="text-[11px] text-[#ff4b4b]">STABLE</div>
    </div>
    <div class="omni-card border-[#8b5cf6]">
      <div class="omni-title text-[#8b5cf6]">WEB PORTAL</div>
      <div class="text-[11px] mt-2 text-[#8b5cf6] font-bold">C2 OVERRIDE</div>
      <div class="text-[10px] mt-1 text-[#00ff41] opacity-70">matrix uplink</div>
    </div>
  </div>

  <!-- Ввод -->
  <div class="flex gap-2">
    <input id="cmd-input" type="text" placeholder="Команда Аргосу..."
           onkeydown="if(event.key==='Enter') sendCmd()"/>
    <button class="btn-hud px-6" onclick="sendCmd()">▶ SEND</button>
  </div>

  <!-- Метрики -->
  <div class="grid grid-cols-3 gap-3" id="metrics-grid">
    <div class="hud p-3 rounded-xl text-center">
      <div class="text-xs opacity-50 mb-1">CPU</div>
      <div id="m-cpu" class="text-xl font-bold">—</div>
    </div>
    <div class="hud p-3 rounded-xl text-center">
      <div class="text-xs opacity-50 mb-1">RAM</div>
      <div id="m-ram" class="text-xl font-bold">—</div>
    </div>
    <div class="hud p-3 rounded-xl text-center">
      <div class="text-xs opacity-50 mb-1">DISK</div>
      <div id="m-disk" class="text-xl font-bold">—</div>
    </div>
  </div>

</div>

<script>
// ── Matrix Rain ──────────────────────────────────────
const c = document.getElementById('matrix');
const ctx = c.getContext('2d');
function resizeMatrix() { c.width = window.innerWidth; c.height = window.innerHeight; }
resizeMatrix(); window.addEventListener('resize', resizeMatrix);
const chars = "01⚛🔱📡🛡🌐αβγδ";
let drops = [];
function initDrops() { drops = Array(Math.floor(c.width / 18)).fill(1); }
initDrops();
setInterval(() => {
  ctx.fillStyle = "rgba(0,0,0,0.055)";
  ctx.fillRect(0, 0, c.width, c.height);
  ctx.fillStyle = "#00FF41"; ctx.font = "14px monospace";
  drops.forEach((y, i) => {
    const ch = chars[Math.floor(Math.random() * chars.length)];
    ctx.fillText(ch, i * 18, y * 18);
    if (y * 18 > c.height && Math.random() > 0.975) drops[i] = 0;
    drops[i]++;
  });
}, 45);

// ── Консоль ──────────────────────────────────────────
const con = document.getElementById('console');
function addLog(text, cls='entry-ok') {
  const d = document.createElement('div');
  d.className = cls;
  d.textContent = '> ' + text;
  con.appendChild(d);
  con.scrollTop = con.scrollHeight;
}

// ── Команды ──────────────────────────────────────────
const history = []; let hIdx = -1;
const inp = document.getElementById('cmd-input');
inp.addEventListener('keydown', e => {
  if (e.key === 'ArrowUp') { if (hIdx < history.length - 1) hIdx++; inp.value = history[history.length - 1 - hIdx] || ''; }
  if (e.key === 'ArrowDown') { if (hIdx > 0) hIdx--; inp.value = history[history.length - 1 - hIdx] || ''; }
});

async function sendCmd(preset) {
  const cmd = preset || inp.value.trim();
  if (!cmd) return;
  if (!preset) { inp.value = ''; history.push(cmd); hIdx = -1; }
  addLog(cmd, 'entry-sys');
  try {
    const r = await fetch('/api/command', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: cmd})
    });
    const data = await r.json();
    const ans = data.answer || data.error || JSON.stringify(data);
    ans.split('\\n').forEach(line => addLog(line));
  } catch(e) {
    addLog('❌ ' + e, 'entry-err');
  }
}

// ── Авто-обновление метрик ───────────────────────────
const qColors = {
  'Analytic':'q-Analytic','Creative':'q-Creative',
  'Protective':'q-Protective','Unstable':'q-Unstable','All-Seeing':'q-AllSeeing'
};
async function updateMetrics() {
  try {
    const r = await fetch('/api/metrics');
    const d = await r.json();
    document.getElementById('m-cpu').textContent  = (d.cpu  || '--') + '%';
    document.getElementById('m-ram').textContent  = (d.ram  || '--') + '%';
    document.getElementById('m-disk').textContent = (d.disk || '--') + '%';
    document.getElementById('sys-mini').textContent = `CPU: ${d.cpu||'--'}% | RAM: ${d.ram||'--'}%`;
    const qb = document.getElementById('q-badge');
    const qs = d.quantum || 'Analytic';
    qb.textContent = qs;
    qb.className = 'quantum-badge ' + (qColors[qs] || 'q-Analytic');
  } catch(_) {}
}
setInterval(updateMetrics, 3000);
updateMetrics();

// ── Часы ─────────────────────────────────────────────
setInterval(() => {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString('ru');
}, 1000);
</script>
</body>
</html>
"""


def create_app(core=None):
    if not FASTAPI_OK:
        return None, None

    app = FastAPI(title="Argos Universal OS", version="1.3.0")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTML_TEMPLATE

    @app.get("/api/health")
    async def health():
        return JSONResponse({"status": "ok", "version": "1.3.0"})

    @app.get("/api/metrics")
    async def metrics():
        try:
            import psutil
            cpu  = psutil.cpu_percent(interval=0.2)
            ram  = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/").percent
            quantum = "Analytic"
            if core and hasattr(core, "quantum"):
                quantum = getattr(core.quantum, "state", "Analytic")
            return JSONResponse({
                "cpu": round(cpu, 1),
                "ram": round(ram, 1),
                "disk": round(disk, 1),
                "quantum": quantum
            })
        except Exception as e:
            return JSONResponse({"error": str(e)})

    @app.post("/api/command")
    async def command(request: Request):
        try:
            body = await request.json()
            text = (body.get("text") or "").strip()
            if not text:
                return JSONResponse({"error": "empty"}, status_code=400)
            if core:
                r = core.process(text)
                answer = r.get("answer", str(r)) if isinstance(r, dict) else str(r)
            else:
                answer = f"[Core не подключён] {text}"
            return JSONResponse({"answer": answer})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/api/status")
    async def status():
        if not core:
            return JSONResponse({"status": "core_not_loaded"})
        try:
            r = core.process("статус системы")
            answer = r.get("answer", "") if isinstance(r, dict) else str(r)
            return JSONResponse({"status": "ok", "answer": answer})
        except Exception as e:
            return JSONResponse({"error": str(e)})

    return app, uvicorn


def run_web_sync(core=None, host="0.0.0.0", port=8080):
    app, uvicorn_mod = create_app(core)
    if app is None:
        print("❌ FastAPI не установлен: pip install fastapi uvicorn")
        return
    print(f"🌐 [AETHER]: Веб-дашборд запущен на порту {port}")
    uvicorn_mod.run(app, host=host, port=port, log_level="warning")


class WebDashboard:
    """Обёртка для запуска из main.py."""
    def __init__(self, core=None):
        self.core = core
        self.port = int(os.getenv("ARGOS_DASHBOARD_PORT", "8080"))

    def run(self):
        run_web_sync(self.core, port=self.port)

# Alias для совместимости
ArgosWebEngine = WebDashboard

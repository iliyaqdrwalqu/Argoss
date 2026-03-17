"""
web_dashboard.py — Веб-панель Аргоса (встроенный HTTP-сервер)
  Открывается в браузере: http://localhost:8080
  Показывает: статус, ноды P2P, логи, отправка команд.
"""
import threading
import json
import time
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from src.argos_logger import get_logger

log = get_logger("argos.dashboard")

HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>👁️ Argos Universal OS</title>
<style>
  :root { --cyan:#00ffff; --bg:#060A1A; --card:#0d1628; --border:#1a2a4a; --green:#00ff88; --red:#ff3333; --yellow:#ffff00; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:#cce; font-family:'Courier New',monospace; padding:20px; }
  h1 { color:var(--cyan); text-align:center; font-size:2em; margin-bottom:4px; letter-spacing:4px; }
  .subtitle { text-align:center; color:#556; margin-bottom:24px; font-size:0.85em; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:16px; }
  .card h2 { color:var(--cyan); font-size:0.9em; margin-bottom:12px; border-bottom:1px solid var(--border); padding-bottom:6px; letter-spacing:2px; }
  .metric { display:flex; justify-content:space-between; margin:6px 0; font-size:0.85em; }
  .val { color:var(--green); font-weight:bold; }
  .val.warn { color:var(--yellow); }
  .val.crit { color:var(--red); }
  .orb { text-align:center; font-size:3em; margin:8px 0; }
  #log { background:#000; border:1px solid var(--border); border-radius:4px; padding:10px; font-size:0.75em; height:180px; overflow-y:auto; white-space:pre; color:#8af; }
  input[type=text] { width:100%; padding:8px; background:#0a1020; border:1px solid var(--border); color:#cce; border-radius:4px; font-family:inherit; font-size:0.9em; margin-top:8px; }
  button { width:100%; padding:8px; margin-top:8px; background:#0d2a4a; border:1px solid var(--cyan); color:var(--cyan); border-radius:4px; cursor:pointer; font-family:inherit; letter-spacing:2px; }
  button:hover { background:#1a3a6a; }
  .node { border-left:3px solid var(--cyan); padding:6px 10px; margin:6px 0; font-size:0.8em; }
  .badge { display:inline-block; padding:2px 6px; border-radius:10px; font-size:0.7em; margin-left:6px; }
  .master { background:#1a3a0a; color:var(--green); }
  .peer { background:#0a1a3a; color:var(--cyan); }
  .bar { background:#0a1020; border-radius:4px; height:8px; margin-top:4px; overflow:hidden; }
  .bar-fill { height:100%; border-radius:4px; background:linear-gradient(90deg,#0af,#0ff); transition:width 0.5s; }
  .bar-fill.warn { background:linear-gradient(90deg,#fa0,#ff0); }
  .bar-fill.crit { background:linear-gradient(90deg,#f00,#f50); }
  .ts { color:#445; font-size:0.7em; float:right; }
</style>
</head>
<body>
<h1>👁️ ARGOS UNIVERSAL OS</h1>
<p class="subtitle">Панель управления · <span id="ts">—</span></p>

<div class="grid">
  <!-- СТАТУС -->
  <div class="card">
    <h2>⚛️ КВАНТОВОЕ ЯДРО</h2>
    <div class="orb" id="orb">●</div>
    <div class="metric"><span>Состояние</span><span class="val" id="state">—</span></div>
    <div class="metric"><span>Голос</span><span class="val" id="voice">—</span></div>
    <div class="metric"><span>P2P ноды</span><span class="val" id="nodes">—</span></div>
    <div class="metric"><span>Uptime</span><span class="val" id="uptime">—</span></div>
  </div>

  <!-- РЕСУРСЫ -->
  <div class="card">
    <h2>📊 РЕСУРСЫ</h2>
    <div class="metric"><span>CPU</span><span class="val" id="cpu">—</span></div>
    <div class="bar"><div class="bar-fill" id="cpu-bar" style="width:0%"></div></div>
    <div class="metric" style="margin-top:10px"><span>RAM</span><span class="val" id="ram">—</span></div>
    <div class="bar"><div class="bar-fill" id="ram-bar" style="width:0%"></div></div>
    <div class="metric" style="margin-top:10px"><span>Диск</span><span class="val" id="disk">—</span></div>
    <div class="bar"><div class="bar-fill" id="disk-bar" style="width:0%"></div></div>
    <div class="metric" style="margin-top:10px"><span>Сеть</span><span class="val" id="net">—</span></div>
    <div class="metric"><span>Батарея</span><span class="val" id="bat">—</span></div>
  </div>

  <!-- КОМАНДЫ -->
  <div class="card">
    <h2>⌨️ ДИРЕКТИВА</h2>
    <input type="text" id="cmd" placeholder="Введи команду для Аргоса..." onkeydown="if(event.key==='Enter')sendCmd()">
    <button onclick="sendCmd()">▶ ВЫПОЛНИТЬ</button>
    <button id="voice-toggle" onclick="quickVoiceToggle()">🔊 ВКЛЮЧИТЬ ГОЛОС</button>
    <button onclick="quickIotStatus()">📡 IoT СТАТУС</button>
    <button onclick="quickIotProtocols()">🏭 IoT ПРОТОКОЛЫ</button>
    <button onclick="quickGatewayTemplates()">🧩 ШАБЛОНЫ ШЛЮЗОВ</button>
    <button onclick="quickDeviceStatus()">📟 СТАТУС УСТРОЙСТВА</button>
    <button onclick="quickCreateFirmware()">🛠 СОЗДАЙ ПРОШИВКУ</button>
    <div id="resp" style="margin-top:10px;font-size:0.8em;color:#8cf;min-height:40px"></div>
  </div>

  <!-- P2P СЕТЬ -->
  <div class="card">
    <h2>🌐 P2P СЕТЬ</h2>
    <div id="p2p-nodes"><div style="color:#445">Загружаю...</div></div>
  </div>

  <!-- ЛОГ -->
  <div class="card" style="grid-column: 1/-1">
    <h2>📋 СИСТЕМНЫЙ ЛОГ</h2>
    <div id="log">Подключение к ядру...</div>
  </div>
</div>

<script>
const ORB_COLORS = {
  Analytic:'#00ffff', Protective:'#ff3333', Creative:'#00ff88',
  Unstable:'#ffff00', 'All-Seeing':'#ffffff', System:'#ff8800', Offline:'#444'
};
let voiceOn = false;

async function fetch_status() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();

    document.getElementById('ts').textContent = new Date().toLocaleTimeString('ru');
    document.getElementById('state').textContent = d.state || '—';
    document.getElementById('voice').textContent = d.voice_on ? '🔊 ВКЛ' : '🔇 ВЫКЛ';
    voiceOn = !!d.voice_on;
    const voiceBtn = document.getElementById('voice-toggle');
    if (voiceBtn) {
      voiceBtn.textContent = voiceOn ? '🔇 ОТКЛЮЧИТЬ ГОЛОС' : '🔊 ВКЛЮЧИТЬ ГОЛОС';
    }
    document.getElementById('nodes').textContent = d.p2p_nodes ?? '0';
    document.getElementById('uptime').textContent = d.uptime || '—';

    const orb = document.getElementById('orb');
    orb.textContent = '●';
    orb.style.color = ORB_COLORS[d.state?.split(' ')[0]] || '#aaa';

    setMetric('cpu', d.cpu, '%');
    setMetric('ram', d.ram, '%');
    setMetric('disk', d.disk, '%');
    document.getElementById('net').textContent = d.net || '—';
    document.getElementById('bat').textContent = d.bat || '—';

    // P2P ноды
    const p2p = document.getElementById('p2p-nodes');
    if (d.p2p_list && d.p2p_list.length) {
      p2p.innerHTML = d.p2p_list.map(n =>
        `<div class="node">
          <b>${n.hostname}</b> <span class="badge ${n.is_master?'master':'peer'}">${n.is_master?'МАСТЕР':'нода'}</span>
          <br><small>⚡ ${n.power}/100 · 📅 ${n.age_days?.toFixed(1)}д · 🏅 ${n.authority}</small>
        </div>`
      ).join('');
    } else {
      p2p.innerHTML = '<div style="color:#445">Ноды не обнаружены</div>';
    }
  } catch(e) {}
}

function setMetric(id, val, suffix) {
  if (val === undefined) return;
  const el = document.getElementById(id);
  const bar = document.getElementById(id+'-bar');
  el.textContent = val.toFixed(1) + suffix;
  el.className = 'val' + (val>90?' crit':val>75?' warn':'');
  if (bar) {
    bar.style.width = Math.min(val,100)+'%';
    bar.className = 'bar-fill' + (val>90?' crit':val>75?' warn':'');
  }
}

async function fetch_log() {
  try {
    const r = await fetch('/api/log');
    const d = await r.json();
    const el = document.getElementById('log');
    el.textContent = d.lines || '';
    el.scrollTop = el.scrollHeight;
  } catch(e) {}
}

async function sendCmd() {
  const inp = document.getElementById('cmd');
  const cmd = inp.value.trim();
  if (!cmd) return;
  inp.value = '';
  document.getElementById('resp').textContent = '⚙️ Выполняю...';
  try {
    const r = await fetch('/api/cmd', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({cmd})});
    const d = await r.json();
    document.getElementById('resp').textContent = d.answer || d.error || '—';
  } catch(e) { document.getElementById('resp').textContent = '❌ '+e; }
}

function quickVoiceToggle() {
  const inp = document.getElementById('cmd');
  inp.value = voiceOn ? 'голос выкл' : 'голос вкл';
  sendCmd();
  setTimeout(fetch_status, 300);
}

function quickIotProtocols() {
  const inp = document.getElementById('cmd');
  inp.value = 'iot протоколы';
  sendCmd();
}

function quickIotStatus() {
  const inp = document.getElementById('cmd');
  inp.value = 'iot статус';
  sendCmd();
}

function quickGatewayTemplates() {
  const inp = document.getElementById('cmd');
  inp.value = 'шаблоны шлюзов';
  sendCmd();
}

function quickDeviceStatus() {
  const devId = prompt('ID устройства (пример: zb_kitchen_sensor):', '');
  if (!devId || !devId.trim()) return;
  const inp = document.getElementById('cmd');
  inp.value = `статус устройства ${devId.trim()}`;
  sendCmd();
}

function quickCreateFirmware() {
  const args = prompt('Формат: id шаблон [порт]\nПример: gw1 esp32_lora /dev/ttyUSB0', '');
  if (!args || !args.trim()) return;
  const inp = document.getElementById('cmd');
  inp.value = `создай прошивку ${args.trim()}`;
  sendCmd();
}

setInterval(fetch_status, 3000);
setInterval(fetch_log, 5000);
fetch_status();
fetch_log();
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    core    = None
    admin   = None
    flasher = None
    start_t = time.time()

    def log_message(self, *args): pass  # Отключаем стандартный вывод

    def do_GET(self):
        if self.path == "/":
            self._send(200, "text/html", HTML.encode())
        elif self.path == "/api/status":
            self._send(200, "application/json", self._status_json())
        elif self.path == "/api/log":
            self._send(200, "application/json", self._log_json())
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path == "/api/cmd":
            length  = int(self.headers.get("Content-Length", 0))
            body    = json.loads(self.rfile.read(length))
            cmd     = body.get("cmd", "")
            try:
                result = self.core.process_logic(cmd, self.admin, self.flasher)
                self._send(200, "application/json",
                           json.dumps(result, ensure_ascii=False).encode())
            except Exception as e:
                self._send(200, "application/json",
                           json.dumps({"answer": f"Ошибка: {e}"}).encode())

    def _send(self, code, ctype, data):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _status_json(self) -> bytes:
        import psutil, json
        uptime_s = int(time.time() - self.start_t)
        h, m = divmod(uptime_s // 60, 60)
        uptime = f"{h}ч {m}мин"

        cpu  = psutil.cpu_percent(interval=0.3)
        ram  = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent

        # Сеть
        try:
            import socket
            st = time.time()
            with socket.create_connection(("8.8.8.8",53), timeout=1):
                pass
            net = f"{int((time.time()-st)*1000)}ms"
        except Exception:
            net = "Offline"

        # Батарея
        bat = "N/A"
        try:
            b = psutil.sensors_battery()
            if b: bat = f"{b.percent:.0f}% {'🔌' if b.power_plugged else '🔋'}"
        except Exception as e:
          log.debug("Battery metrics unavailable: %s", e)

        # P2P
        p2p_nodes = 0
        p2p_list  = []
        if self.core and self.core.p2p:
            nodes = self.core.p2p.registry.all()
            master = self.core.p2p.registry.get_master()
            p2p_nodes = len(nodes)
            for n in nodes:
                p2p_list.append({
                    "hostname":  n.get("hostname","?"),
                    "power":     n.get("power",{}).get("index",0),
                    "age_days":  n.get("age_days",0),
                    "authority": n.get("authority",0),
                    "is_master": master and n.get("node_id") == master.get("node_id"),
                })

        state = "Offline"
        voice = False
        if self.core:
            state = self.core.quantum.generate_state()["name"]
            voice = self.core.voice_on

        data = dict(state=state, voice_on=voice, p2p_nodes=p2p_nodes,
                    p2p_list=p2p_list, uptime=uptime, cpu=cpu, ram=ram,
                    disk=disk, net=net, bat=bat)
        return json.dumps(data, ensure_ascii=False).encode()

    def _log_json(self) -> bytes:
        lines = ""
        try:
            log_path = "logs/argos.log"
            if os.path.exists(log_path):
                with open(log_path, encoding="utf-8") as f:
                    all_lines = f.readlines()
                lines = "".join(all_lines[-50:])  # Последние 50 строк
        except Exception as e:
          log.warning("Dashboard log read error: %s", e)
        return json.dumps({"lines": lines}, ensure_ascii=False).encode()


class WebDashboard:
    def __init__(self, core, admin, flasher, port: int = 8080):
        DashboardHandler.core    = core
        DashboardHandler.admin   = admin
        DashboardHandler.flasher = flasher
        DashboardHandler.start_t = time.time()
        self.port   = port
        self.server = None

    def start(self) -> str:
        try:
            self.server = HTTPServer(("0.0.0.0", self.port), DashboardHandler)
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
            log.info("Dashboard запущен на http://localhost:%d", self.port)
            return f"🌐 Веб-панель: http://localhost:{self.port}"
        except Exception as e:
            return f"❌ Dashboard ошибка: {e}"

    def stop(self):
        if self.server:
            self.server.shutdown()

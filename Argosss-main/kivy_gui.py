# ======================================================
# ᑧ ARGOS v1.33 - MODULE: WEB_INTERFACE (AETHER)
# ======================================================
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>ARGOS v1.33 MASTER</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background: #000; color: #00FF41; font-family: monospace; overflow: hidden; }
        .hud-card { background: rgba(0, 255, 65, 0.02); border: 1px solid rgba(0,255,65,0.2); backdrop-filter: blur(10px); }
    </style>
</head>
<body class="p-10 flex flex-col h-screen">
    <canvas id="m" class="fixed top-0 left-0 -z-10 opacity-30"></canvas>
    <div class="flex justify-between items-center hud-card p-6 rounded-2xl shadow-2xl">
        <h1 class="text-3xl font-bold tracking-widest">🔱 ARGOS SOVEREIGN</h1>
        <div class="text-right">NODE_ID: Master_7F2A | STATUS: ONLINE</div>
    </div>
    
    <div class="grid grid-cols-3 gap-10 mt-10">
        <div class="hud-card p-10 rounded-2xl text-center hover:bg-green-900/10 cursor-pointer transition">📡 SCAN NFC</div>
        <div class="hud-card p-10 rounded-2xl text-center hover:bg-green-900/10 cursor-pointer transition">🔵 BT SHIELD</div>
        <div class="hud-card p-10 rounded-2xl text-center hover:bg-green-900/10 cursor-pointer transition">🛡️ ROOT SHELL</div>
    </div>

    <div class="mt-auto hud-card h-48 rounded-2xl p-6 overflow-hidden">
        <div class="text-green-600 opacity-60">CONSOLE_OUT: v1.33 ONLINE</div>
    </div>

    <script>
        const c = document.getElementById('m'); const ctx = c.getContext('2d');
        c.width = window.innerWidth; c.height = window.innerHeight;
        const q = "01🔱📡"; const drops = Array(Math.floor(c.width/20)).fill(1);
        function draw() {
            ctx.fillStyle = "rgba(0,0,0,0.05)"; ctx.fillRect(0,0,c.width,c.height);
            ctx.fillStyle = "#00F2FF"; ctx.font = "15px monospace";
            drops.forEach((y,i) => {
                ctx.fillText(q[Math.floor(Math.random()*q.length)], i*20, y*20);
                if(y*20 > c.height && Math.random() > 0.975) drops[i] = 0; drops[i]++;
            });
        } setInterval(draw, 50);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return HTML_TEMPLATE

def run_web_sync(port=8080):
    print("🌐 [AETHER]: Веб-дашборд запущен на порту " + str(port))
    uvicorn.run(app, host="0.0.0.0", port=port)
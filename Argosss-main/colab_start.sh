%%bash
# ======================================================
#  ARGOS v1.3 — Единая ячейка запуска для Google Colab
# ======================================================

echo "======================================================"
echo "  ARGOS v1.3 — COLAB BOOTSTRAP"
echo "======================================================"

# ── 1. Системные зависимости ──────────────────────────
echo "[1/7] Установка системных пакетов..."
apt-get update -qq
apt-get install -y -qq zstd build-essential git \
    libffi-dev python3-dev openjdk-17-jdk-headless \
    ffmpeg espeak sqlite3 pciutils > /dev/null
echo "[+] Готово."

# ── 2. Python-зависимости ─────────────────────────────
echo "[2/7] Python-модули..."
pip install -q -r requirements.txt
echo "[+] Готово."

# ── 3. Ollama ─────────────────────────────────────────
echo "[3/7] Ollama..."
if [ ! -f "/usr/local/bin/ollama" ]; then
    curl -fsSL https://ollama.com/install.sh | sh > /dev/null 2>&1
fi
pkill ollama 2>/dev/null || true
sleep 1
nohup ollama serve > /tmp/ollama.log 2>&1 &
echo "[~] Ожидаю порт 11434..."
for i in $(seq 1 20); do
    curl -s http://localhost:11434 > /dev/null 2>&1 && echo "[+] Ollama готова." && break
    sleep 3
done

# ── 4. Модель ─────────────────────────────────────────
echo "[4/7] Модель llama3..."
ollama list 2>/dev/null | grep -q 'llama3' || ollama pull llama3:8b
echo "[+] Готово."

# ── 5. Репозиторий ────────────────────────────────────
echo "[5/7] Репозиторий..."
cd /content
if [ ! -d "v1-3" ]; then
    if [ -n "$GITHUB_TOKEN" ]; then
        git clone "https://${GITHUB_TOKEN}@github.com/sigtrip/v1-3.git" v1-3
    else
        git clone "https://github.com/sigtrip/v1-3.git" v1-3
    fi
else
    cd v1-3 && git pull origin main 2>/dev/null || true && cd /content
fi
cd /content/v1-3
echo "[+] Готово."

# ── 6. Инициализация ──────────────────────────────────
echo "[6/7] Инициализация..."
python3 genesis.py 2>/dev/null || true

# Настройка .env если нет
if [ ! -f ".env" ]; then
    echo ""
    echo "======================================================"
    echo "  ПЕРВЫЙ ЗАПУСК — НАСТРОЙКА КЛЮЧЕЙ"
    echo "  Нажми Enter чтобы пропустить любой пункт"
    echo "======================================================"
    echo ""
    read -p "  Gemini API Key: " GEMINI_KEY
    read -p "  Telegram Bot Token: " TG_TOKEN
    read -p "  Твой Telegram ID: " TG_USER
    read -p "  GitHub Token (для APK): " GH_TOKEN
    read -p "  P2P Secret (придумай): " NET_SECRET
    NET_SECRET=${NET_SECRET:-argos_secret_2026}

    cat > .env << ENVEOF
GEMINI_API_KEY=${GEMINI_KEY}
TELEGRAM_BOT_TOKEN=${TG_TOKEN}
USER_ID=${TG_USER}
GITHUB_TOKEN=${GH_TOKEN}
ARGOS_NETWORK_SECRET=${NET_SECRET}
ARGOS_HOMEOSTASIS=on
ARGOS_CURIOSITY=on
ARGOS_VOICE_DEFAULT=off
ARGOS_TASK_WORKERS=2
ARGOS_OLLAMA_AUTOSTART=on
ENVEOF
    echo "[+] .env сохранён!"
fi

# ── 7. Самоосознание ──────────────────────────────────
echo ""
echo "[7/7] Аргос сканирует свою структуру..."
# Копируем awareness.py если его нет
if [ ! -f "awareness.py" ]; then
    curl -s "https://raw.githubusercontent.com/sigtrip/v1-3/main/awareness.py" \
         -o awareness.py 2>/dev/null || true
fi
python3 awareness.py 2>/dev/null || python3 -c "
import os
files = []
for r,d,f in os.walk('.'):
    d[:] = [x for x in d if x not in ['.git','__pycache__','.buildozer']]
    files += [os.path.join(r,ff) for ff in f]
py = [f for f in files if f.endswith('.py')]
print(f'  Файлов всего: {len(files)}')
print(f'  Python: {len(py)}')
print(f'  Целостность: {\"OK (83+)\" if len(py)>=83 else str(len(py))+\" (ожидается 83+)\"}')
"

echo ""
echo "======================================================"
echo "  АРГОС ЗАПУСКАЕТСЯ | Ollama: localhost:11434"
echo "======================================================"
python3 main.py --no-gui

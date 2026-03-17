\
"""genesis.py — Первичная настройка Аргоса"""
from __future__ import annotations
import os
from pathlib import Path

ENV_TEMPLATE = """
# ARGOS .env — заполни свои ключи
# ── Системные ─────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=
USER_ID=
ARGOS_NETWORK_SECRET=
ARGOS_MASTER_KEY=
PYPI_TOKEN=
PUPI_API_URL=
PUPI_API_TOKEN=
ARGOS_HOMEOSTASIS=on
ARGOS_CURIOSITY=on
ARGOS_LOG_LEVEL=INFO

# ── AI-провайдеры (бесплатные / freemium) ─────────────────────
# DeepSeek (V3 / R1) | RPM: 15 | контекст: 128k | ~2-5M токенов разово
DEEPSEEK_API_KEY=

# GigaChat (Сбер)    | RPM: 60 | контекст: 32k  | 1M токенов разово
GIGACHAT_API_KEY=

# YandexGPT (Lite)   | RPH: 300 | контекст: 32k | грант ~4 000 ₽ / 60 дней
YANDEX_API_KEY=
YANDEX_FOLDER_ID=

# Gemini 2.5 Flash   | RPM: 15 | TPM: 1M | RPD: 1500 | контекст: 1M токенов
GEMINI_API_KEY=

# Groq (Llama 3)     | RPM: 30 | TPM: 30k | контекст: 128k | бесплатно
GROQ_API_KEY=

# IBM WatsonX (Lite) | RPM: 120 | контекст: 128k | 300k токенов/мес
WATSONX_API_KEY=
WATSONX_PROJECT_ID=
WATSONX_URL=https://us-south.ml.cloud.ibm.com

# OpenAI (GPT-4o)    | RPM: 3 | TPM: 30k | контекст: 128k | $5 стартовый баланс
OPENAI_API_KEY=

# Ollama (локальный) | бесплатно | инференс на своём железе
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3
""".strip()

def main():
    print("🔱 ARGOS Genesis — первичная инициализация\\n")
    env_path = Path(".env")
    if env_path.exists():
        print("⚠️  .env уже существует. Пропускаю.")
    else:
        env_path.write_text(ENV_TEMPLATE + "\\n")
        print("✅ .env создан — заполни ключи!")

    dirs = ["data","logs","src/skills","src/modules","config/dags",
            "tests/generated","assets/firmware"]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
    print("✅ Папки созданы")

    try:
        from src.db_init import init_db
        init_db()
        print("✅ SQLite инициализирована")
    except Exception as e:
        print(f"⚠️  DB: {e}")

    print("\\n▶ Теперь запусти: python main.py --no-gui")

if __name__ == "__main__":
    main()

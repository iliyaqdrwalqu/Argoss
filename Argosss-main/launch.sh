#!/usr/bin/env bash
# launch.sh — Быстрый запуск ARGOS Universal OS
# Использование: bash launch.sh [аргументы main.py]
set -e

PYTHON=${PYTHON:-python3}
ARGS=("$@")
if [ ${#ARGS[@]} -eq 0 ]; then
    ARGS=(--full)
fi

echo "══════════════════════════════════════════"
echo "  🔱 ARGOS UNIVERSAL OS v1.3 — ЗАПУСК"
echo "══════════════════════════════════════════"

# 1. Проверка Python
if ! command -v "$PYTHON" &>/dev/null; then
    echo "❌ Python не найден. Установи Python 3.10+"
    exit 1
fi
PYVER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python: $PYVER"

# 2. Установка зависимостей (если нужно)
if ! "$PYTHON" -c "import psutil" &>/dev/null 2>&1; then
    echo "  📦 Устанавливаю зависимости..."
    "$PYTHON" -m pip install -r requirements.txt --quiet
fi

# 3. Первичная инициализация (если .env отсутствует)
if [ ! -f ".env" ]; then
    echo "  🔧 Первый запуск — инициализация..."
    "$PYTHON" genesis.py
fi

# 4. Создать папки если их нет
mkdir -p data logs src/skills modules tests/generated

# 5. Запуск
echo "  🚀 Запуск Аргоса (${ARGS[*]})..."
echo "══════════════════════════════════════════"
exec "$PYTHON" main.py "${ARGS[@]}"

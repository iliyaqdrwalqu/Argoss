# User Guide: Запуск и установка

## 1) Установка зависимостей

```bash
pip install -r requirements.txt

# Установка Ollama (для локального ИИ-режима)
# (рекомендуется сначала просмотреть скрипт install.sh)
curl -fsSL https://ollama.com/install.sh | sh
```

Для голосовых функций также могут понадобиться системные пакеты (например, PortAudio).

## 2) Настройка окружения

Создай `.env` в корне проекта и укажи минимально необходимые ключи:

```env
GEMINI_API_KEY=...
ARGOS_NETWORK_SECRET=...
```

Если используешь Telegram и Home Assistant — добавь соответствующие переменные из README.

## 3) Инициализация и запуск

```bash
python genesis.py
python main.py
bash launch.sh       # по умолчанию запускает полную конфигурацию (--full)
```

Режимы запуска:

- Desktop: `python main.py`
- Headless: `python main.py --no-gui`
- Dashboard: `python main.py --dashboard`
- Full configuration: `python main.py --full`

## 4) Первые команды

- `статус системы`
- `что ты знаешь`
- `найди в памяти кот`
- `граф знаний`
- `запусти p2p`

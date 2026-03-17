# 📋 CHANGELOG — ARGOS Universal OS

Все значимые изменения проекта документируются здесь.

---

## [1.4.0] — 2026-03-15

### 🆕 Добавлено
- **Промышленные протоколы** (`industrial_protocols.py`) — полная интеграция в `ArgosCore`:
  - 🏗️ **KNX** (EN 50090 / ISO 14543) — умные здания, HVAC, освещение, шторы  
    KNXBridge: `connect`, `read_group`, `write_group`, `discover`, `scan_bus`
  - 🏭 **LonWorks** (ISO/IEC 14908) — промышленная автоматизация, HVAC  
    LonWorksBridge: `discover`, `read_nv`, `write_nv`, `commission_node`
  - 📊 **M-Bus** (EN 13757) — счётчики энергии, воды, газа  
    MBusBridge: `connect_serial`, `connect_tcp`, `discover`, `read_device`
  - 🔗 **OPC UA** (IEC 62541) — промышленный IoT / SCADA  
    OPCUABridge: `connect`, `discover`, `browse`, `read_node`, `write_node`
- `IndustrialProtocolsManager` — единая точка управления, интегрирован как `core.industrial`
- Graceful degradation: полностью работает без `xknx`, `opcua`, `mbus` (режим симуляции)
- 18 новых unit-тестов в `tests/test_industrial_protocols.py`
- Команды через Telegram/CLI:
  ```
  industrial статус
  industrial discovery / industrial поиск
  industrial устройства
  knx подключи <host>
  opcua подключи <url>
  mbus serial <port> / mbus tcp <host>
  opcua browse [node_id]
  ```
- Статус промышленных протоколов включён в `оператор диагностика`

### 🔄 Изменено
- `src/core.py` — добавлена инициализация `_init_industrial()` и обработка команд
- `README.md` — обновлён до v1.4.0: статус KNX/LonWorks/M-Bus/OPC UA → ✅ Реализован, добавлена секция команд
- `pyproject.toml` — версия `1.3.0` → `1.4.0`
- `pack_archive.py` — версия по умолчанию `1.3.0` → `1.4.0`

### 🔧 CI/CD
- Добавлен workflow `.github/workflows/release.yml`:
  - Автоматический запуск при `push tag v*.*.*` или `workflow_dispatch`
  - Прогон тестов → health_check → сборка ZIP → создание GitHub Release с ZIP-ассетом
  - Сохранение артефакта на 90 дней

---

## [1.3.0] — 2026-01-01

### 🆕 Добавлено
- ArgosCore v2.0 (src/core.py) — 80+ команд
- Tool Calling Engine с multi-round планированием (до 5 раундов)
- Consciousness module (src/consciousness.py) — awaken/sleep/full_status/handle_command
- ColibriDaemon — daemon-режим с python-daemon + --pid-file
- EventBus — двойной API (Event-объект и legacy topic/data)
- GitOps — git статус/коммит/пуш/автокоммит
- Grist Storage — P2P-хранилище знаний
- IBM Cloud Object Storage
- BACnet bridge (bacnet_bridge.py)
- SmartHome Override · Power Sentry · Emergency Purge · Container Isolation
- JARVIS Engine (HuggingGPT 4-stage pipeline)
- AWA-Core — центральный координатор модулей
- Adaptive Drafter (TLT) — LRU-кэш 512 энтри
- Self-Healing Engine — автоисправление Python-кода
- AirSnitch (SDR) — сканер эфира
- WiFi Sentinel — Evil Twin детект

---

## [1.0.0-Absolute] — 2025-06-01

### 🎉 Первый публичный релиз
- ArgosCore с базовыми AI-возможностями (Gemini, GigaChat, YandexGPT, Ollama)
- Голос: TTS + STT + Wake Word
- Память: SQLite (факты, заметки, история)
- P2P сеть нод с авторитетом
- IoT/Mesh: Zigbee, LoRa, WiFi Mesh, MQTT, Modbus
- Умные системы: дом, теплица, гараж, погреб, инкубатор, аквариум, террариум
- Telegram + Desktop GUI + Android APK + Docker

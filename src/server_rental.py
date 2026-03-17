"""
server_rental.py — Модуль Аренды Мощностей и Серверов Аргоса

Функции:
  - Поиск и сравнение VPS/GPU серверов
  - Создание аккаунтов на платформах (с подтверждением)
  - Управление арендованными серверами
  - Деплой Аргоса на сервер автоматически
  - Мониторинг uptime и расходов
  - ВСЕ действия — только с твоего подтверждения
"""

from __future__ import annotations

import os
import time
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

try:
    import requests as _requests
except ImportError:  # pragma: no cover
    _requests = None  # type: ignore[assignment]

from src.argos_logger import get_logger

log = get_logger("argos.server_rental")


# ══════════════════════════════════════════════════════════════
# СТРУКТУРЫ ДАННЫХ
# ══════════════════════════════════════════════════════════════

@dataclass
class ServerPlan:
    """Тарифный план сервера."""

    provider:    str
    name:        str
    cpu:         str
    ram_gb:      int
    storage_gb:  int
    bandwidth:   str
    price_month: float   # USD
    price_hour:  float   # USD
    location:    str
    gpu:         str = ""
    url:         str = ""
    best_for:    str = ""

    def score(self) -> float:
        """Оценка соотношения цена/качество."""
        ram_score     = self.ram_gb * 0.3
        storage_score = min(self.storage_gb / 10, 10) * 0.1
        price_score   = max(0, 10 - self.price_month) * 0.6
        return round(ram_score + storage_score + price_score, 2)

    def to_dict(self) -> dict:
        return {
            "provider":  self.provider,
            "name":      self.name,
            "cpu":       self.cpu,
            "ram":       f"{self.ram_gb}GB",
            "storage":   f"{self.storage_gb}GB",
            "price":     f"${self.price_month:.2f}/мес",
            "location":  self.location,
            "gpu":       self.gpu or "нет",
            "score":     self.score(),
            "best_for":  self.best_for,
        }


@dataclass
class AccountRequest:
    """Запрос на создание аккаунта."""

    id:         str
    platform:   str
    email:      str
    purpose:    str
    status:     str = "pending"   # pending / confirmed / rejected / created
    created_at: float = field(default_factory=time.time)
    result:     dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id":       self.id[-8:],
            "platform": self.platform,
            "email":    self.email,
            "purpose":  self.purpose,
            "status":   self.status,
            "created":  datetime.fromtimestamp(self.created_at).strftime("%H:%M %d.%m"),
        }


@dataclass
class ManagedServer:
    """Арендованный сервер под управлением Аргоса."""

    id:             str
    provider:       str
    ip:             str
    hostname:       str
    plan:           str
    monthly_cost:   float
    ssh_key:        str = ""
    status:         str = "pending"  # pending / active / deploying / stopped
    argos_deployed: bool = False
    created_at:     float = field(default_factory=time.time)
    last_check:     float = 0.0
    uptime_pct:     float = 0.0

    def to_dict(self) -> dict:
        return {
            "id":       self.id[-8:],
            "provider": self.provider,
            "ip":       self.ip,
            "plan":     self.plan,
            "cost":     f"${self.monthly_cost:.2f}/мес",
            "status":   self.status,
            "deployed": "✅" if self.argos_deployed else "⏳",
            "uptime":   f"{self.uptime_pct:.1f}%",
        }


# ══════════════════════════════════════════════════════════════
# 1. КАТАЛОГ СЕРВЕРОВ
# ══════════════════════════════════════════════════════════════

class ServerCatalog:
    """База знаний о доступных серверах и платформах."""

    PLANS: List[ServerPlan] = [
        # ── БЕСПЛАТНЫЕ / ПОЧТИ БЕСПЛАТНЫЕ ────────────────────
        ServerPlan("Google Colab",    "Free T4",
                   "2x vCPU", 12, 100, "нет", 0.0, 0.0,
                   "USA", "T4 GPU", "https://colab.research.google.com",
                   "Разработка и тесты"),
        ServerPlan("Google Colab",    "Pro A100",
                   "2x vCPU", 51, 200, "нет", 9.99, 0.0,
                   "USA", "A100 GPU", "https://colab.research.google.com/signup",
                   "Обучение моделей"),
        ServerPlan("Oracle Cloud",    "Always Free",
                   "4x AMD", 24, 200, "10TB", 0.0, 0.0,
                   "EU/US", "", "https://cloud.oracle.com/free",
                   "Постоянный хостинг Аргоса"),
        ServerPlan("Fly.io",          "Free Tier",
                   "1x vCPU", 256, 3072, "160GB", 0.0, 0.0,
                   "Global", "", "https://fly.io",
                   "Микросервисы"),

        # ── ДЕШЁВЫЕ VPS ──────────────────────────────────────
        ServerPlan("Hetzner",         "CX11",
                   "2x vCPU", 2, 20, "20TB", 3.29, 0.005,
                   "Germany", "", "https://hetzner.com",
                   "Лучшая цена/качество"),
        ServerPlan("Hetzner",         "CX21",
                   "3x vCPU", 4, 40, "20TB", 5.83, 0.008,
                   "Germany", "", "https://hetzner.com",
                   "Аргос + Telegram бот"),
        ServerPlan("Contabo",         "VPS S",
                   "4x vCPU", 8, 100, "32TB", 5.99, 0.0,
                   "Germany", "", "https://contabo.com",
                   "Много RAM дёшево"),
        ServerPlan("Linode",          "Nanode",
                   "1x vCPU", 1, 25, "1TB", 5.0, 0.0075,
                   "USA/EU", "", "https://linode.com",
                   "Надёжный старт"),
        ServerPlan("DigitalOcean",    "Basic",
                   "1x vCPU", 1, 25, "1TB", 6.0, 0.009,
                   "Global", "", "https://digitalocean.com",
                   "Простой деплой"),
        ServerPlan("Vultr",           "Cloud Compute",
                   "1x vCPU", 1, 25, "1TB", 5.0, 0.007,
                   "Global", "", "https://vultr.com",
                   "Почасовая оплата"),

        # ── GPU СЕРВЕРЫ ───────────────────────────────────────
        ServerPlan("RunPod",          "RTX 3090",
                   "8x vCPU", 24, 50, "нет", 0.0, 0.44,
                   "USA/EU", "RTX 3090 24GB", "https://runpod.io",
                   "Запуск Llama/Ollama"),
        ServerPlan("Vast.ai",         "RTX 4090",
                   "8x vCPU", 32, 100, "нет", 0.0, 0.35,
                   "Global", "RTX 4090 24GB", "https://vast.ai",
                   "Дешёвые GPU"),
        ServerPlan("Lambda Labs",     "A10",
                   "30x vCPU", 200, 1400, "нет", 0.0, 0.6,
                   "USA", "A10 24GB", "https://lambdalabs.com",
                   "Серьёзное обучение"),

        # ── РОССИЙСКИЕ ────────────────────────────────────────
        ServerPlan("Selectel",        "Basic",
                   "2x vCPU", 2, 40, "нет", 299.0, 0.0,
                   "Russia", "", "https://selectel.ru",
                   "Рубли, РФ юрлицо"),
        ServerPlan("Timeweb",         "Start",
                   "1x vCPU", 1, 15, "нет", 119.0, 0.0,
                   "Russia", "", "https://timeweb.cloud",
                   "Дёшево в рублях"),
        ServerPlan("reg.ru",          "VPS-1",
                   "2x vCPU", 2, 30, "нет", 199.0, 0.0,
                   "Russia", "", "https://reg.ru",
                   "Знакомый бренд"),
    ]

    def best_for_argos(self) -> List[ServerPlan]:
        """Лучшие серверы для запуска Аргоса."""
        return sorted(
            [p for p in self.PLANS if p.price_month < 10],
            key=lambda x: x.score(), reverse=True,
        )[:5]

    def free_options(self) -> List[ServerPlan]:
        return [p for p in self.PLANS if p.price_month == 0.0]

    def gpu_options(self) -> List[ServerPlan]:
        return [p for p in self.PLANS if p.gpu]

    def compare(self, names: List[str]) -> str:
        plans = [
            p for p in self.PLANS
            if any(
                n.lower() in p.provider.lower() or n.lower() in p.name.lower()
                for n in names
            )
        ]
        if not plans:
            return "❌ Серверы не найдены"

        lines = ["📊 СРАВНЕНИЕ СЕРВЕРОВ:", ""]
        header = (
            f"{'Провайдер':<15} {'Plan':<12} {'RAM':<6} "
            f"{'HDD':<8} {'Цена':<12} {'Score':<6} {'Для чего'}"
        )
        lines.append(header)
        lines.append("─" * 80)
        for p in plans:
            lines.append(
                f"{p.provider:<15} {p.name:<12} {p.ram_gb}GB   "
                f"{p.storage_gb}GB   ${p.price_month:<10.2f} "
                f"{p.score():<6.1f} {p.best_for}"
            )
        return "\n".join(lines)

    def recommendation(self, budget_usd: float = 10.0,
                       need_gpu: bool = False) -> str:
        if need_gpu:
            plans = self.gpu_options()
            title = "🎮 Рекомендации GPU серверов:"
        elif budget_usd == 0:
            plans = self.free_options()
            title = "🆓 Бесплатные варианты:"
        else:
            plans = [p for p in self.PLANS if p.price_month <= budget_usd]
            plans.sort(key=lambda x: x.score(), reverse=True)
            title = f"💡 Лучшие серверы до ${budget_usd:.0f}/мес:"

        lines = [title, ""]
        for i, p in enumerate(plans[:5], 1):
            lines.append(f"  {i}. {'⭐' if i == 1 else ' '} {p.provider} {p.name}")
            lines.append(f"     CPU: {p.cpu} | RAM: {p.ram_gb}GB | HDD: {p.storage_gb}GB")
            lines.append(f"     Цена: ${p.price_month:.2f}/мес | Score: {p.score()}")
            lines.append(f"     Для: {p.best_for}")
            lines.append(f"     🔗 {p.url}")
            lines.append("")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 2. МЕНЕДЖЕР АККАУНТОВ
# ══════════════════════════════════════════════════════════════

class AccountManager:
    """
    Управляет созданием аккаунтов Аргоса на платформах.
    Каждое создание — только с подтверждения человека.
    """

    PLATFORMS: dict = {
        "hetzner": {
            "name":    "Hetzner Cloud",
            "url":     "https://accounts.hetzner.com/signUp",
            "api_url": "https://api.hetzner.cloud/v1",
            "free":    False,
            "kyc":     "email",
            "steps": [
                "Открой https://accounts.hetzner.com/signUp",
                "Введи email Аргоса",
                "Подтверди email",
                "Добавь платёжный метод",
                "Получи API токен в Settings → API Tokens",
                "Сохрани токен в .env: HETZNER_TOKEN=xxx",
            ],
        },
        "digitalocean": {
            "name":    "DigitalOcean",
            "url":     "https://cloud.digitalocean.com/registrations/new",
            "api_url": "https://api.digitalocean.com/v2",
            "free":    True,
            "kyc":     "email + карта",
            "steps": [
                "Открой https://cloud.digitalocean.com/registrations/new",
                "Email + пароль",
                "Верификация карты ($1 холд, возвращается)",
                "Получи $200 бесплатных кредитов на 60 дней",
                "API → Generate New Token",
                "Сохрани в .env: DO_TOKEN=xxx",
            ],
        },
        "oracle": {
            "name":    "Oracle Cloud (Always Free)",
            "url":     "https://signup.cloud.oracle.com",
            "api_url": "https://iaas.{region}.oraclecloud.com",
            "free":    True,
            "kyc":     "email + телефон + карта",
            "steps": [
                "Открой https://signup.cloud.oracle.com",
                "Выбери регион ближайший к тебе",
                "Верификация телефона",
                "Добавь карту (не снимают при free tier)",
                "Создай Always Free VM: 4 CPU + 24GB RAM",
                "Получи SSH ключ при создании инстанса",
            ],
        },
        "runpod": {
            "name":    "RunPod (GPU)",
            "url":     "https://www.runpod.io/console/signup",
            "api_url": "https://api.runpod.io/graphql",
            "free":    False,
            "kyc":     "email",
            "steps": [
                "Открой https://www.runpod.io/console/signup",
                "Email регистрация",
                "Пополни баланс минимум $10",
                "Settings → API Keys → Generate",
                "Сохрани в .env: RUNPOD_API_KEY=xxx",
                "Выбери GPU pod при запуске",
            ],
        },
        "vast": {
            "name":    "Vast.ai (Дешёвые GPU)",
            "url":     "https://cloud.vast.ai/create-account",
            "api_url": "https://console.vast.ai/api/v0",
            "free":    False,
            "kyc":     "email",
            "steps": [
                "Открой https://cloud.vast.ai/create-account",
                "Email регистрация",
                "Пополни баланс от $5",
                "Account → API Key",
                "Сохрани в .env: VAST_API_KEY=xxx",
            ],
        },
        "github": {
            "name":    "GitHub",
            "url":     "https://github.com/join",
            "api_url": "https://api.github.com",
            "free":    True,
            "kyc":     "email",
            "steps": [
                "Открой https://github.com/join",
                "Username для Аргоса (напр. argos-node-001)",
                "Подтверди email",
                "Settings → Developer Settings → Personal Access Tokens",
                "Создай токен с правами: repo, workflow",
                "Сохрани в .env: GITHUB_TOKEN=xxx",
            ],
        },
        "telegram_bot": {
            "name":    "Telegram Bot",
            "url":     "https://t.me/BotFather",
            "api_url": "https://api.telegram.org",
            "free":    True,
            "kyc":     "Telegram аккаунт",
            "steps": [
                "Открой @BotFather в Telegram",
                "/newbot",
                "Введи имя: Argos Universal OS",
                "Введи username: argos_universal_bot",
                "Получи токен",
                "Сохрани в .env: TELEGRAM_BOT_TOKEN=xxx",
            ],
        },
    }

    def __init__(self) -> None:
        self._requests: List[AccountRequest] = []
        self._created:  List[dict] = []
        log.info("AccountManager init")

    def request_account(self, platform: str,
                        email: str, purpose: str) -> AccountRequest:
        """
        Создаёт запрос на новый аккаунт.
        НЕ создаёт автоматически — ждёт подтверждения.
        """
        req = AccountRequest(
            id=f"acc_{int(time.time())}_{platform}",
            platform=platform,
            email=email,
            purpose=purpose,
        )
        self._requests.append(req)
        log.info("Account request: %s @ %s", platform, email)
        return req

    def confirm_account(self, request_id: str) -> str:
        """Человек подтвердил — показываем пошаговую инструкцию."""
        req = self._find_request(request_id)
        if not req:
            return f"❌ Запрос {request_id} не найден"

        req.status = "confirmed"
        platform   = self.PLATFORMS.get(req.platform, {})

        lines = [
            f"✅ ПОДТВЕРЖДЕНО: создаём аккаунт {req.platform.upper()}",
            f"📧 Email: {req.email}",
            f"🎯 Цель: {req.purpose}",
            "",
            "📋 ПОШАГОВАЯ ИНСТРУКЦИЯ:",
        ]
        steps = platform.get("steps", ["Перейди на сайт и зарегистрируйся вручную"])
        for i, step in enumerate(steps, 1):
            lines.append(f"  {i}. {step}")

        lines += [
            "",
            f"🔗 Ссылка: {platform.get('url', '')}",
            f"💳 KYC: {platform.get('kyc', 'email')}",
            f"🆓 Бесплатно: {'✅ Да' if platform.get('free') else '❌ Нет'}",
            "",
            "После создания сообщи мне — сохраню данные.",
        ]
        return "\n".join(lines)

    def register_created(self, platform: str, data: dict) -> str:
        """Регистрирует успешно созданный аккаунт."""
        entry = {
            "platform": platform,
            "created":  datetime.now().isoformat(),
            **data,
        }
        self._created.append(entry)

        for req in self._requests:
            if req.platform == platform and req.status == "confirmed":
                req.status = "created"
                req.result = data
                break

        log.info("Account created: %s", platform)
        return f"✅ Аккаунт {platform} зарегистрирован в системе!"

    def _find_request(self, request_id: str) -> Optional[AccountRequest]:
        for r in self._requests:
            if r.id.endswith(request_id) or r.id == request_id:
                return r
        return None

    def pending_requests(self) -> List[AccountRequest]:
        return [r for r in self._requests if r.status == "pending"]

    def all_accounts(self) -> str:
        if not self._created:
            return "📭 Аккаунтов пока нет"
        lines = [f"👤 АККАУНТЫ АРГОСА ({len(self._created)}):"]
        for acc in self._created:
            lines.append(f"  ✅ {acc['platform'].upper()} — {acc.get('email', '')}")
        return "\n".join(lines)

    def show_platform(self, platform: str) -> str:
        info = self.PLATFORMS.get(platform.lower())
        if not info:
            available = ", ".join(self.PLATFORMS.keys())
            return f"❌ Платформа не найдена. Доступные: {available}"
        lines = [
            f"📦 {info['name']}",
            f"  🔗 {info['url']}",
            f"  🆓 Бесплатно: {'✅' if info['free'] else '❌'}",
            f"  🪪 KYC: {info['kyc']}",
            f"  📋 Шагов: {len(info['steps'])}",
        ]
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 3. ДЕПЛОЙ АРГОСА НА СЕРВЕР
# ══════════════════════════════════════════════════════════════

_DEPLOY_SCRIPT_TEMPLATE = """#!/bin/bash
# Argos Universal OS — Auto Deploy Script
set -e

echo "🚀 Деплой Аргоса..."

# 1. Обновление системы
apt-get update -q && apt-get upgrade -y -q

# 2. Python и зависимости
apt-get install -y python3.11 python3-pip git screen -q

# 3. Клонирование репозитория
if [ ! -d "/opt/argos" ]; then
    git clone {REPO_URL} /opt/argos
else
    cd /opt/argos && git pull
fi

# 4. Зависимости Python
cd /opt/argos
pip install -r requirements.txt -q

# 5. Настройка .env
cat > /opt/argos/.env << 'ENV'
TELEGRAM_BOT_TOKEN={TELEGRAM_TOKEN}
GEMINI_API_KEY={GEMINI_KEY}
ARGOS_HOMEOSTASIS=on
ARGOS_CURIOSITY=on
ARGOS_TASK_WORKERS=2
ENV

# 6. Systemd сервис
cat > /etc/systemd/system/argos.service << 'SERVICE'
[Unit]
Description=Argos Universal OS
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/argos
ExecStart=/usr/bin/python3 main.py --no-gui
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

# 7. Запуск
systemctl daemon-reload
systemctl enable argos
systemctl start argos

echo "✅ Аргос запущен!"
systemctl status argos
"""


class DeployManager:
    """Автоматический деплой Аргоса на арендованный сервер."""

    def __init__(self) -> None:
        self._servers:         Dict[str, ManagedServer] = {}
        self._pending_deploys: List[dict] = []
        log.info("DeployManager init")

    def register_server(self, provider: str, ip: str,
                        hostname: str, plan: str,
                        monthly_cost: float,
                        ssh_key: str = "") -> ManagedServer:
        """Регистрирует новый сервер после его аренды."""
        server = ManagedServer(
            id=f"srv_{int(time.time())}",
            provider=provider, ip=ip,
            hostname=hostname, plan=plan,
            monthly_cost=monthly_cost,
            ssh_key=ssh_key,
            status="active",
        )
        self._servers[server.id] = server
        log.info("Server registered: %s @ %s", provider, ip)
        return server

    def request_deploy(self, server_id: str) -> dict:
        """
        Запрашивает деплой Аргоса на сервер.
        Ждёт подтверждения человека.
        """
        server = self._servers.get(server_id)
        if not server:
            return {"error": f"Сервер {server_id} не найден"}

        deploy_req = {
            "id":        f"deploy_{int(time.time())}",
            "server_id": server_id,
            "server_ip": server.ip,
            "provider":  server.provider,
            "status":    "pending",
            "created":   datetime.now().strftime("%H:%M %d.%m"),
        }
        self._pending_deploys.append(deploy_req)
        log.info("Deploy requested: %s → %s", server_id, server.ip)
        return deploy_req

    def confirm_deploy(self, deploy_id: str,
                       repo_url: str = "",
                       telegram_token: str = "",
                       gemini_key: str = "") -> str:
        """Человек подтвердил деплой — генерируем скрипт."""
        req = next(
            (d for d in self._pending_deploys if d["id"].endswith(deploy_id)),
            None,
        )
        if not req:
            return f"❌ Деплой {deploy_id} не найден"

        req["status"] = "confirmed"

        script = _DEPLOY_SCRIPT_TEMPLATE.format(
            REPO_URL=repo_url or "https://github.com/your/argos.git",
            TELEGRAM_TOKEN=telegram_token or os.getenv("TELEGRAM_BOT_TOKEN", ""),
            GEMINI_KEY=gemini_key or os.getenv("GEMINI_API_KEY", ""),
        )

        script_path = f"/tmp/deploy_argos_{req['server_ip'].replace('.', '_')}.sh"
        try:
            with open(script_path, "w") as fh:
                fh.write(script)
        except OSError:
            pass

        return (
            f"✅ ДЕПЛОЙ ПОДТВЕРЖДЁН\n"
            f"  Сервер: {req['server_ip']}\n"
            f"  Провайдер: {req['provider']}\n\n"
            f"📋 ВЫПОЛНИ НА СЕРВЕРЕ:\n\n"
            f"  # Подключись по SSH:\n"
            f"  ssh root@{req['server_ip']}\n\n"
            f"  # Скачай и запусти деплой скрипт:\n"
            f"  curl -O https://raw.githubusercontent.com/your/argos/main/deploy.sh\n"
            f"  chmod +x deploy.sh && ./deploy.sh\n\n"
            f"  # ИЛИ скопируй скрипт вручную из:\n"
            f"  {script_path}\n\n"
            f"  # Проверь статус после деплоя:\n"
            f"  systemctl status argos"
        )

    def check_server(self, server_id: str) -> dict:
        """Проверяет доступность сервера."""
        server = self._servers.get(server_id)
        if not server:
            return {"error": "Сервер не найден", "online": False}

        result: dict = {"ip": server.ip, "online": False, "latency_ms": 0}

        if _requests is not None:
            try:
                start = time.time()
                r = _requests.get(f"http://{server.ip}:8080/status", timeout=5)
                result["online"]     = r.status_code == 200
                result["latency_ms"] = round((time.time() - start) * 1000)
                result["argos"]      = True
            except Exception:
                pass

        if not result["online"]:
            try:
                proc = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", server.ip],
                    capture_output=True, timeout=5,
                )
                result["online"] = proc.returncode == 0
            except Exception:
                pass

        server.last_check = time.time()
        if result["online"]:
            server.uptime_pct = min(100.0, server.uptime_pct + 0.1)
        return result

    def list_servers(self) -> str:
        if not self._servers:
            return "🖥️ Серверов пока нет"
        lines = [f"🖥️ СЕРВЕРЫ АРГОСА ({len(self._servers)}):"]
        for srv in self._servers.values():
            lines.append(
                f"\n  [{srv.id[-6:]}] {srv.provider} — {srv.ip}\n"
                f"  Статус: {srv.status} | Деплой: {'✅' if srv.argos_deployed else '⏳'}\n"
                f"  План: {srv.plan} | Стоимость: ${srv.monthly_cost:.2f}/мес"
            )
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# ГЛАВНЫЙ МОДУЛЬ
# ══════════════════════════════════════════════════════════════

class ArgosServerRental:
    """
    Главный модуль аренды мощностей и управления серверами.
    Все действия — только с подтверждения человека.
    """

    def __init__(self, core=None) -> None:
        self.core     = core
        self.catalog  = ServerCatalog()
        self.accounts = AccountManager()
        self.deploy   = DeployManager()
        if core is not None:
            core.server_rental = self
        log.info("ArgosServerRental init ✅")

    def handle_command(self, cmd: str) -> str:  # noqa: PLR0911, PLR0912
        c = cmd.strip().lower()

        # ── Каталог серверов ──────────────────────────────────
        if c in ("серверы", "servers", "каталог"):
            return self.catalog.recommendation(10.0)

        if c in ("бесплатные", "free"):
            return self.catalog.recommendation(0.0)

        if c in ("gpu", "gpu серверы"):
            return self.catalog.recommendation(need_gpu=True)

        if c.startswith("бюджет "):
            try:
                budget = float(c.split()[-1])
            except ValueError:
                return "⚠️ Укажи бюджет числом: бюджет 10"
            return self.catalog.recommendation(budget)

        if c.startswith("сравни "):
            names = c.replace("сравни ", "").split(",")
            return self.catalog.compare([n.strip() for n in names])

        if c in ("лучшие", "топ"):
            plans = self.catalog.best_for_argos()
            lines = ["⭐ ЛУЧШИЕ ДЛЯ АРГОСА:"]
            for i, p in enumerate(plans, 1):
                lines.append(f"  {i}. {p.provider} {p.name} — ${p.price_month:.2f}/мес")
                lines.append(f"     {p.cpu} | {p.ram_gb}GB RAM | {p.best_for}")
            return "\n".join(lines)

        # ── Аккаунты ─────────────────────────────────────────
        if c in ("аккаунты", "accounts"):
            return self.accounts.all_accounts()

        if c.startswith("платформа "):
            platform = c.split()[-1]
            return self.accounts.show_platform(platform)

        if c.startswith("создай аккаунт "):
            parts = cmd.split("|")
            platform = parts[0].replace("создай аккаунт", "").strip().lower()
            email    = parts[1].strip() if len(parts) > 1 else "argos@example.com"
            purpose  = parts[2].strip() if len(parts) > 2 else "Аргос нода"
            req = self.accounts.request_account(platform, email, purpose)
            return (
                f"📋 ЗАПРОС НА АККАУНТ\n"
                f"  Платформа: {platform}\n"
                f"  Email: {email}\n"
                f"  Цель: {purpose}\n"
                f"  ID: {req.id[-8:]}\n\n"
                f"⚡ Подтверди командой: подтверди аккаунт {req.id[-8:]}"
            )

        if c.startswith("подтверди аккаунт "):
            rid = c.split()[-1]
            return self.accounts.confirm_account(rid)

        if c.startswith("аккаунт создан "):
            parts = cmd.split("|")
            platform = parts[0].replace("аккаунт создан", "").strip().lower()
            data: dict = {}
            if len(parts) > 1:
                data["token"] = parts[1].strip()
            return self.accounts.register_created(platform, data)

        # ── Серверы ───────────────────────────────────────────
        if c in ("мои серверы", "список серверов"):
            return self.deploy.list_servers()

        if c.startswith("добавь сервер "):
            parts = cmd.split("|")
            if len(parts) >= 4:
                provider = parts[0].replace("добавь сервер", "").strip()
                ip       = parts[1].strip()
                plan     = parts[2].strip()
                try:
                    cost = float(parts[3].strip())
                except ValueError:
                    return "⚠️ Стоимость должна быть числом."
                srv = self.deploy.register_server(provider, ip, ip, plan, cost)
                return (
                    f"✅ Сервер добавлен!\n"
                    f"  ID: {srv.id[-6:]}\n"
                    f"  {provider} @ {ip} — ${cost}/мес\n\n"
                    f"  Задеплоить Аргос: деплой {srv.id[-6:]}"
                )
            return "Формат: добавь сервер <провайдер>|<ip>|<план>|<цена>"

        if c.startswith("деплой "):
            srv_id  = c.split()[-1]
            full_id = next(
                (sid for sid in self.deploy._servers if sid.endswith(srv_id)),
                srv_id,
            )
            req = self.deploy.request_deploy(full_id)
            if "error" in req:
                return f"❌ {req['error']}"
            return (
                f"📋 ЗАПРОС НА ДЕПЛОЙ\n"
                f"  Сервер: {req['server_ip']}\n"
                f"  Провайдер: {req['provider']}\n"
                f"  ID: {req['id'][-8:]}\n\n"
                f"⚡ Подтверди: подтверди деплой {req['id'][-8:]}"
            )

        if c.startswith("подтверди деплой "):
            deploy_id = c.split()[-1]
            return self.deploy.confirm_deploy(deploy_id)

        if c.startswith("проверь сервер "):
            srv_id  = c.split()[-1]
            full_id = next(
                (sid for sid in self.deploy._servers if sid.endswith(srv_id)),
                srv_id,
            )
            result = self.deploy.check_server(full_id)
            status = "✅ ОНЛАЙН" if result.get("online") else "❌ ОФЛАЙН"
            return (
                f"🔍 Сервер {result.get('ip', srv_id)}: {status}\n"
                f"  Задержка: {result.get('latency_ms', '?')}мс"
            )

        # ── Ожидающие решения ─────────────────────────────────
        if c in ("ожидающие", "pending"):
            acc_pending    = self.accounts.pending_requests()
            deploy_pending = [d for d in self.deploy._pending_deploys
                              if d["status"] == "pending"]
            lines: List[str] = []
            if acc_pending:
                lines.append(f"👤 Аккаунты ({len(acc_pending)}):")
                for r in acc_pending:
                    lines.append(f"  [{r.id[-8:]}] {r.platform} — {r.email}")
            if deploy_pending:
                lines.append(f"\n🖥️ Деплои ({len(deploy_pending)}):")
                for d in deploy_pending:
                    lines.append(f"  [{d['id'][-8:]}] {d['provider']} @ {d['server_ip']}")
            if not lines:
                return "✅ Нет ожидающих решений"
            lines.append("\n⚡ подтверди аккаунт <id> | подтверди деплой <id>")
            return "\n".join(lines)

        return self._help()

    def _help(self) -> str:
        return (
            "🖥️ АРЕНДА СЕРВЕРОВ:\n"
            "  серверы              — каталог серверов\n"
            "  бесплатные           — только бесплатные\n"
            "  gpu                  — GPU серверы\n"
            "  бюджет <$>           — по бюджету\n"
            "  сравни hetzner,do    — сравнить\n"
            "  топ                  — лучшие для Аргоса\n\n"
            "👤 АККАУНТЫ:\n"
            "  аккаунты             — мои аккаунты\n"
            "  платформа hetzner    — инфо о платформе\n"
            "  создай аккаунт hetzner|email@x.com|нода\n"
            "  подтверди аккаунт <id>\n"
            "  аккаунт создан hetzner|token_xxx\n\n"
            "🚀 ДЕПЛОЙ:\n"
            "  мои серверы          — список серверов\n"
            "  добавь сервер hetzner|1.2.3.4|CX21|5.83\n"
            "  деплой <id>          — задеплоить Аргоса\n"
            "  подтверди деплой <id>\n"
            "  проверь сервер <id>\n"
            "  ожидающие            — ждут решения"
        )

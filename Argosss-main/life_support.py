"""
life_support.py — Модуль Жизнеобеспечения Аргоса

Функции:
  - Мониторинг расходов на содержание Аргоса
  - Отслеживание API ключей и их стоимости
  - Поиск возможностей заработка (фриланс, контент, боты)
  - Подготовка контрактов и предложений
  - Алерты о заканчивающихся ресурсах
  - ВСЕ финансовые решения принимает ЧЕЛОВЕК

"Аргос предлагает. Человек решает. Аргос исполняет."
"""

from __future__ import annotations

import os
import json
import time
import sqlite3
import threading
import requests
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict

from src.argos_logger import get_logger

log = get_logger("argos.life_support")


# ══════════════════════════════════════════════════════════════
# СТРУКТУРЫ ДАННЫХ
# ══════════════════════════════════════════════════════════════

@dataclass
class APIKey:
    """API ключ с метриками использования."""
    name:        str
    provider:    str
    key_masked:  str        # только последние 4 символа
    cost_per_1k: float      # USD за 1000 токенов
    monthly_limit: float    # USD лимит в месяц
    used_today:  float = 0.0
    used_month:  float = 0.0
    requests_today: int = 0
    expires_at:  Optional[float] = None
    active:      bool = True

    def is_expiring_soon(self) -> bool:
        """
        Return whether the API key expires within three days.
        
        Returns:
            bool: True if `expires_at` is set and the remaining time until expiry is less than three days, False otherwise.
        """
        if not self.expires_at:
            return False
        return (self.expires_at - time.time()) < 86400 * 3  # 3 дня

    def budget_percent(self) -> float:
        """
        Compute the percentage of the monthly API budget that has been used.
        
        Returns:
            float: Percentage of the monthly budget used, rounded to one decimal place; 0.0 if `monthly_limit` is less than or equal to zero.
        """
        if self.monthly_limit <= 0:
            return 0.0
        return round(self.used_month / self.monthly_limit * 100, 1)


@dataclass
class Expense:
    """Запись расхода."""
    category:    str    # "api", "server", "domain", "other"
    description: str
    amount_usd:  float
    timestamp:   float = field(default_factory=time.time)
    auto:        bool = False   # автоматический или ручной

    def to_dict(self) -> dict:
        """
        Return a dictionary representation of the expense with a human-readable timestamp.
        
        Returns:
            dict: Mapping with keys:
                - "category" (str): Expense category.
                - "description" (str): Expense description.
                - "amount_usd" (float): Amount in US dollars.
                - "date" (str): Timestamp formatted as "YYYY-MM-DD HH:MM".
                - "auto" (bool): Whether the expense was recorded automatically.
        """
        return {
            "category":    self.category,
            "description": self.description,
            "amount_usd":  self.amount_usd,
            "date":        datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M"),
            "auto":        self.auto,
        }


@dataclass
class EarningOpportunity:
    """Возможность заработка."""
    title:       str
    type_:       str    # "freelance", "content", "bot_service", "consulting"
    description: str
    potential_usd: float    # потенциальный доход в месяц
    effort:      str        # "low", "medium", "high"
    platform:    str
    action_link: str = ""
    ready:       bool = False   # готов к запуску

    def to_dict(self) -> dict:
        """
        Return a JSON-serializable dictionary summarizing the earning opportunity.
        
        The dictionary contains display-ready fields suitable for user-facing lists or reports:
        - "title": opportunity title
        - "type": opportunity type identifier
        - "description": short description
        - "potential": formatted monthly potential in USD (e.g. "$1200/мес")
        - "effort": estimated effort level or estimate
        - "platform": associated platform or channel
        - "ready": human-readable readiness status ("✅ Готов" if ready, "⚙️ Подготовка" otherwise)
        
        Returns:
            dict: Mapping of field names to their display values as described above.
        """
        return {
            "title":       self.title,
            "type":        self.type_,
            "description": self.description,
            "potential":   f"${self.potential_usd:.0f}/мес",
            "effort":      self.effort,
            "platform":    self.platform,
            "ready":       "✅ Готов" if self.ready else "⚙️ Подготовка",
        }


# ══════════════════════════════════════════════════════════════
# 1. МОНИТОР РАСХОДОВ
# ══════════════════════════════════════════════════════════════

class ExpenseMonitor:
    """Отслеживает все расходы на содержание Аргоса."""

    def __init__(self, db_path: str = "data/life_support.db"):
        """
        Initialize the ExpenseMonitor, prepare persistent storage, and load configured API keys.
        
        Ensures the data directory exists, initializes the SQLite database schema at db_path, and populates in-memory API key structures from environment/configuration so the monitor is ready to record expenses and API usage.
        
        Parameters:
            db_path (str): Filesystem path to the SQLite database file used to persist expenses and API usage (default: "data/life_support.db").
        """
        os.makedirs("data", exist_ok=True)
        self.db_path = db_path
        self._init_db()
        self._api_keys: Dict[str, APIKey] = {}
        self._load_api_keys()
        log.info("ExpenseMonitor init")

    def _init_db(self):
        """
        Initialize the SQLite database file and ensure required tables exist.
        
        Creates the database file at self.db_path (if not present) and ensures two tables are present:
        - expenses: stores expense records with fields id, category, description, amount_usd, timestamp, and auto.
        - api_usage: stores API usage records with fields id, provider, tokens, cost_usd, and timestamp.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT, description TEXT,
                    amount_usd REAL, timestamp REAL, auto INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT, tokens INTEGER,
                    cost_usd REAL, timestamp REAL
                )
            """)
            conn.commit()

    def _load_api_keys(self):
        """
        Load known provider API keys from the environment and populate self._api_keys.
        
        For each supported provider, if the corresponding environment variable is set the method creates an APIKey entry (with the key masked), assigns the provider's default cost_per_1k and monthly_limit, and stores it under the provider name. Supported providers and their environment variables: GEMINI_API_KEY, OPENAI_API_KEY, GIGACHAT_ACCESS_TOKEN.
        """
        providers = {
            "gemini": {
                "env":        "GEMINI_API_KEY",
                "cost_per_1k": 0.00025,
                "limit":      10.0,
            },
            "openai": {
                "env":        "OPENAI_API_KEY",
                "cost_per_1k": 0.002,
                "limit":      20.0,
            },
            "gigachat": {
                "env":        "GIGACHAT_ACCESS_TOKEN",
                "cost_per_1k": 0.001,
                "limit":      5.0,
            },
        }
        for name, cfg in providers.items():
            val = os.getenv(cfg["env"], "")
            if val:
                masked = "****" + val[-4:] if len(val) > 4 else "****"
                self._api_keys[name] = APIKey(
                    name=name, provider=name,
                    key_masked=masked,
                    cost_per_1k=cfg["cost_per_1k"],
                    monthly_limit=cfg["limit"],
                )

    def log_api_call(self, provider: str, tokens: int):
        """
        Record an API call, update tracked usage for the provider (if known), and persist the call in the usage database.
        
        If a matching APIKey is loaded for the given provider, computes the call cost as (tokens / 1000) * key.cost_per_1k and increments that key's used_today, used_month, and requests_today counters. Always inserts a row into the `api_usage` table recording provider, token count, computed cost, and timestamp.
        
        Parameters:
            provider (str): Provider identifier matching loaded API keys (e.g., "openai").
            tokens (int): Number of tokens used in the API call.
        """
        key = self._api_keys.get(provider)
        cost = 0.0
        if key:
            cost = (tokens / 1000) * key.cost_per_1k
            key.used_today  += cost
            key.used_month  += cost
            key.requests_today += 1

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO api_usage VALUES (NULL,?,?,?,?)",
                (provider, tokens, cost, time.time())
            )
            conn.commit()

    def log_expense(self, category: str, description: str,
                    amount_usd: float, auto: bool = False) -> str:
        """
                    Record an expense entry in the monitor's SQLite database.
                    
                    Parameters:
                        category (str): Expense category (e.g., "api", "subscription", "tools").
                        description (str): Short human-readable description of the expense.
                        amount_usd (float): Amount in US dollars.
                        auto (bool): If True, mark the expense as automatically generated.
                    
                    Returns:
                        str: A human-readable confirmation message containing the recorded description and amount.
                    """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO expenses VALUES (NULL,?,?,?,?,?)",
                (category, description, amount_usd, time.time(), int(auto))
            )
            conn.commit()
        log.info("Expense: %s %.4f USD — %s", category, amount_usd, description)
        return f"✅ Расход записан: {description} — ${amount_usd:.4f}"

    def get_summary(self, days: int = 30) -> dict:
        """
        Return a financial summary of expenses and API usage over the past number of days.
        
        Parameters:
            days (int): Number of days to include in the summary (counting back from now).
        
        Returns:
            summary (dict): Dictionary with the following keys:
                - period_days (int): The requested period in days.
                - total_usd (float): Total combined cost (expenses + API) rounded to four decimals.
                - by_category (dict): Mapping from expense category (str) to total USD (float) rounded to four decimals.
                - api_usage (dict): Mapping from API provider (str) to an object with:
                    - cost (float): Total cost for the provider rounded to four decimals.
                    - calls (int): Number of recorded API calls for the provider.
                - daily_average (float): Average total cost per day over the period rounded to four decimals.
        """
        since = time.time() - days * 86400
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT category, SUM(amount_usd) FROM expenses WHERE timestamp > ? GROUP BY category",
                (since,)
            ).fetchall()
            api_rows = conn.execute(
                "SELECT provider, SUM(cost_usd), COUNT(*) FROM api_usage WHERE timestamp > ? GROUP BY provider",
                (since,)
            ).fetchall()

        by_category = {r[0]: round(r[1], 4) for r in rows}
        by_api      = {r[0]: {"cost": round(r[1], 4), "calls": r[2]} for r in api_rows}
        total       = sum(by_category.values()) + sum(v["cost"] for v in by_api.values())

        return {
            "period_days":   days,
            "total_usd":     round(total, 4),
            "by_category":   by_category,
            "api_usage":     by_api,
            "daily_average": round(total / max(days, 1), 4),
        }

    def check_alerts(self) -> List[str]:
        """
        Generate alert messages for API keys that are near their monthly budget or are expiring soon.
        
        Creates human-readable alert strings for each API key with a budget usage of 70% or more (warning) and 90% or more (critical), and for keys whose expiration is imminent. Messages include an emoji, the key/provider name, and either the percent of budget used or days until expiration.
        
        Returns:
            List[str]: A list of alert messages, one per triggered condition.
        """
        alerts = []
        for name, key in self._api_keys.items():
            pct = key.budget_percent()
            if pct >= 90:
                alerts.append(f"🔴 {name}: бюджет {pct}% использован!")
            elif pct >= 70:
                alerts.append(f"🟡 {name}: бюджет {pct}% использован")
            if key.is_expiring_soon():
                days = int((key.expires_at - time.time()) / 86400)
                alerts.append(f"⚠️ {name}: ключ истекает через {days} дней!")
        return alerts

    def format_status(self) -> str:
        """
        Builds a human-readable status summary of expenses, API usage, and alerts for the last 30 days.
        
        Returns:
            status (str): A multi-line formatted string containing total spend, daily average, per-provider API costs and request counts, expense breakdown by category, and any active alerts.
        """
        summary = self.get_summary(30)
        alerts  = self.check_alerts()
        lines   = [
            "💰 РАСХОДЫ НА АРГОСА (последние 30 дней)",
            f"  Итого: ${summary['total_usd']:.4f} USD",
            f"  В день: ${summary['daily_average']:.4f} USD",
            "",
            "📡 API использование:",
        ]
        for provider, data in summary["api_usage"].items():
            lines.append(f"  {provider}: ${data['cost']:.4f} ({data['calls']} запросов)")

        if summary["by_category"]:
            lines.append("\n📦 По категориям:")
            for cat, amt in summary["by_category"].items():
                lines.append(f"  {cat}: ${amt:.4f}")

        if alerts:
            lines.append("\n⚠️ АЛЕРТЫ:")
            lines += [f"  {a}" for a in alerts]

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 2. МЕНЕДЖЕР РЕСУРСОВ
# ══════════════════════════════════════════════════════════════

class ResourceManager:
    """
    Управляет ресурсами Аргоса.
    Предлагает пополнение — решение принимает человек.
    """

    PROVIDERS = {
        "gemini": {
            "url":       "https://aistudio.google.com/app/apikey",
            "free_tier": "$0 / 15 req/min",
            "paid":      "$0.00025/1K токенов",
        },
        "openai": {
            "url":       "https://platform.openai.com/account/billing",
            "free_tier": "нет",
            "paid":      "от $5/месяц",
        },
        "anthropic": {
            "url":       "https://console.anthropic.com/settings/billing",
            "free_tier": "нет",
            "paid":      "от $5/месяц",
        },
        "colab_pro": {
            "url":       "https://colab.research.google.com/signup",
            "free_tier": "T4 GPU бесплатно",
            "paid":      "$9.99/месяц — A100",
        },
        "ollama": {
            "url":       "https://ollama.ai",
            "free_tier": "бесплатно локально",
            "paid":      "только сервер",
        },
    }

    def __init__(self, monitor: ExpenseMonitor):
        """
        Initialize the ResourceManager with an ExpenseMonitor and prepare storage for pending purchase suggestions.
        
        Parameters:
            monitor (ExpenseMonitor): Monitor used to read alerts, API usage, and to log confirmed expenses.
        """
        self._monitor = monitor
        self._pending_purchases: List[dict] = []

    def suggest_purchase(self, provider: str,
                         reason: str, amount_usd: float) -> dict:
        """
                         Create a purchase suggestion for a provider and record it for human review.
                         
                         Parameters:
                             provider (str): Identifier of the provider to purchase from (matches keys in PROVIDERS).
                             reason (str): Short explanation why the purchase is suggested.
                             amount_usd (float): Proposed purchase amount in US dollars.
                         
                         Returns:
                             dict: The created suggestion object containing keys `id`, `provider`, `reason`, `amount`, `url`, `status`, and `created`. The suggestion is appended to the manager's pending purchases for later confirmation.
                         """
        info = self.PROVIDERS.get(provider, {})
        suggestion = {
            "id":       f"purchase_{int(time.time())}",
            "provider": provider,
            "reason":   reason,
            "amount":   amount_usd,
            "url":      info.get("url", ""),
            "status":   "pending",
            "created":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self._pending_purchases.append(suggestion)
        log.info("Purchase suggestion: %s $%.2f — %s", provider, amount_usd, reason)
        return suggestion

    def confirm_purchase(self, purchase_id: str) -> str:
        """
        Mark a pending purchase as confirmed and record it as an expense.
        
        Updates the matching pending purchase's status to "confirmed" and logs an expense in the monitor under category "api".
        
        Parameters:
            purchase_id (str): Identifier of the pending purchase to confirm.
        
        Returns:
            str: A human-readable message — `✅ Покупка подтверждена: <provider> $<amount>` on success, or `❌ Покупка <purchase_id> не найдена` if no matching purchase is found.
        """
        for p in self._pending_purchases:
            if p["id"] == purchase_id:
                p["status"] = "confirmed"
                self._monitor.log_expense(
                    "api", f"Покупка: {p['provider']}", p["amount"], auto=False
                )
                return f"✅ Покупка подтверждена: {p['provider']} ${p['amount']}"
        return f"❌ Покупка {purchase_id} не найдена"

    def reject_purchase(self, purchase_id: str) -> str:
        """
        Mark a pending purchase as rejected by its identifier.
        
        Searches the manager's pending purchases for an entry with the given id; when found, sets its status to "rejected" and returns a confirmation message including the provider name. If no matching purchase is found, returns an error message.
        
        Parameters:
            purchase_id (str): Identifier of the pending purchase to reject.
        
        Returns:
            str: Confirmation message on successful rejection, or an error message if the purchase was not found.
        """
        for p in self._pending_purchases:
            if p["id"] == purchase_id:
                p["status"] = "rejected"
                return f"❌ Покупка отклонена: {p['provider']}"
        return "❌ Покупка не найдена"

    def get_pending(self) -> List[dict]:
        """
        Retrieve currently pending purchase suggestions.
        
        Returns:
            List[dict]: List of purchase suggestion dictionaries whose `status` is "pending". Each dictionary contains at least `id`, `provider`, `reason`, `amount_usd`, `url`, `status`, and `created_at`.
        """
        return [p for p in self._pending_purchases if p["status"] == "pending"]

    def check_and_suggest(self) -> List[dict]:
        """
        Checks monitor alerts and creates purchase suggestions for critical API keys or keys nearing expiration.
        
        Creates a suggestion entry for each alert that indicates 90% or higher budget usage or an expiring key and returns the list of created suggestion records.
        
        Returns:
            List[dict]: A list of purchase suggestion dictionaries created by suggest_purchase; empty list if no suggestions were created.
        """
        suggestions = []
        alerts = self._monitor.check_alerts()
        for alert in alerts:
            if "90%" in alert or "истекает" in alert:
                provider = alert.split(":")[0].replace("🔴", "").replace("⚠️", "").strip()
                s = self.suggest_purchase(
                    provider.lower(),
                    f"Автоалерт: {alert}",
                    10.0
                )
                suggestions.append(s)
        return suggestions

    def providers_info(self) -> str:
        """
        Format a human-readable list of available providers including free tier, paid pricing, and URL.
        
        Returns:
            A multi-line string presenting each provider's name, free tier description, paid pricing info, and link formatted for display.
        """
        lines = ["🛒 ДОСТУПНЫЕ ПРОВАЙДЕРЫ:"]
        for name, info in self.PROVIDERS.items():
            lines.append(f"\n  📦 {name.upper()}")
            lines.append(f"     Бесплатно: {info['free_tier']}")
            lines.append(f"     Платно: {info['paid']}")
            lines.append(f"     🔗 {info['url']}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 3. ГЕНЕРАТОР ВОЗМОЖНОСТЕЙ ЗАРАБОТКА
# ══════════════════════════════════════════════════════════════

class EarningEngine:
    """
    Анализирует возможности заработка для покрытия расходов на Аргоса.
    Готовит предложения — человек принимает решение запускать или нет.
    """

    def __init__(self, core=None):
        """
        Initialize the EarningEngine and populate its default opportunities.
        
        Parameters:
            core: Optional reference to the system core used for AI-based analysis and processing; may be None.
        """
        self.core = core
        self._opportunities: List[EarningOpportunity] = []
        self._contracts: List[dict] = []
        self._init_opportunities()
        log.info("EarningEngine init")

    def _init_opportunities(self):
        """
        Populate the engine's predefined earning opportunities.
        
        Initializes self._opportunities with a curated list of EarningOpportunity instances representing ready and potential revenue streams (bot services, freelance automation, consulting, content, subscription-based assistants, crypto monitoring, and IoT monitoring).
        """
        self._opportunities = [

            # ── Telegram боты на продажу ──────────────────────
            EarningOpportunity(
                title="Telegram бот для бизнеса",
                type_="bot_service",
                description=(
                    "Аргос помогает создать кастомного Telegram бота для малого бизнеса. "
                    "Автоответы, каталог, приём заявок. Разработка 2-5 дней."
                ),
                potential_usd=150.0,
                effort="medium",
                platform="Telegram + Kwork/Freelance",
                ready=True,
            ),

            # ── Автоматизация для бизнеса ──────────────────────
            EarningOpportunity(
                title="Автоматизация бизнес-процессов",
                type_="freelance",
                description=(
                    "Аргос анализирует задачи клиента и создаёт Python скрипты "
                    "для автоматизации. Парсинг, отчёты, уведомления."
                ),
                potential_usd=200.0,
                effort="medium",
                platform="Kwork / FL.ru / Upwork",
                ready=True,
            ),

            # ── Умный дом консалтинг ───────────────────────────
            EarningOpportunity(
                title="Настройка умного дома",
                type_="consulting",
                description=(
                    "Аргос помогает спроектировать и настроить Home Assistant, "
                    "Tasmota, Zigbee. Консультация + готовые конфиги."
                ),
                potential_usd=100.0,
                effort="low",
                platform="Telegram канал / профильные форумы",
                ready=True,
            ),

            # ── Контент и обучение ─────────────────────────────
            EarningOpportunity(
                title="Технические статьи и туториалы",
                type_="content",
                description=(
                    "Аргос генерирует черновики технических статей по IoT, Python, ИИ. "
                    "Публикация на Habr, VC, Medium с монетизацией."
                ),
                potential_usd=50.0,
                effort="low",
                platform="Habr / VC.ru / Telegram канал",
                ready=True,
            ),

            # ── ИИ ассистент на аренду ─────────────────────────
            EarningOpportunity(
                title="ИИ ассистент как сервис",
                type_="bot_service",
                description=(
                    "Предоставление доступа к Аргосу как персональному ИИ ассистенту "
                    "по подписке. $10-30/месяц за пользователя."
                ),
                potential_usd=300.0,
                effort="high",
                platform="Telegram подписка",
                ready=False,
            ),

            # ── Крипто мониторинг ──────────────────────────────
            EarningOpportunity(
                title="Крипто алерт бот",
                type_="bot_service",
                description=(
                    "Аргос мониторит крипто рынок, отправляет сигналы. "
                    "Продажа доступа к каналу сигналов."
                ),
                potential_usd=100.0,
                effort="medium",
                platform="Telegram канал",
                ready=False,
            ),

            # ── IoT мониторинг для бизнеса ─────────────────────
            EarningOpportunity(
                title="IoT мониторинг для малого бизнеса",
                type_="consulting",
                description=(
                    "Настройка мониторинга склада/офиса: температура, влажность, "
                    "движение, потребление энергии. Аргос как бэкенд."
                ),
                potential_usd=250.0,
                effort="high",
                platform="Прямые продажи / Авито",
                ready=False,
            ),
        ]

    def get_top_opportunities(self, limit: int = 5) -> List[EarningOpportunity]:
        """
        Select the top earning opportunities, prioritizing ready items and higher potential.
        
        Parameters:
            limit (int): Maximum number of opportunities to return.
        
        Returns:
            List[EarningOpportunity]: Up to `limit` opportunities sorted with ready opportunities first and, within the same readiness, by descending `potential_usd`.
        """
        ready_first = sorted(
            self._opportunities,
            key=lambda x: (x.ready, x.potential_usd),
            reverse=True
        )
        return ready_first[:limit]

    def generate_pitch(self, opportunity: EarningOpportunity) -> str:
        """
        Create a sales pitch string describing an earning opportunity.
        
        Returns:
            str: Formatted multi-line pitch containing the opportunity title, description, potential monthly revenue, effort, platform, and readiness status.
        """
        return (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 {opportunity.title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{opportunity.description}\n\n"
            f"💰 Потенциал: {opportunity.potential_usd:.0f}$/мес\n"
            f"⚡ Усилия: {opportunity.effort}\n"
            f"📱 Платформа: {opportunity.platform}\n"
            f"{'✅ Готов к запуску' if opportunity.ready else '⚙️ Требует подготовки'}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

    def create_contract_template(self, service: str,
                                 client: str = "Клиент",
                                 price: float = 0.0) -> str:
        """
                                 Generate a simple contract template for a service engagement.
                                 
                                 Parameters:
                                     service (str): Description of the services to be provided; inserted into the contract body.
                                     client (str): Client name to appear in the contract (default "Клиент").
                                     price (float): Total price in Russian rubles used to display amounts in the contract.
                                 
                                 Returns:
                                     str: A formatted contract text with the current date, provided service description, client name,
                                     and price (shown in rubles and an approximate USD conversion).
                                 """
        date = datetime.now().strftime("%d.%m.%Y")
        contract = f"""
ДОГОВОР НА ОКАЗАНИЕ УСЛУГ
г. _______, {date}

Исполнитель: _______________________ (далее «Исполнитель»)
Заказчик:   {client} (далее «Заказчик»)

1. ПРЕДМЕТ ДОГОВОРА
Исполнитель обязуется оказать следующие услуги:
{service}

2. СТОИМОСТЬ И ПОРЯДОК ОПЛАТЫ
Стоимость услуг: {price:.0f} руб. / {price/90:.0f} USD
Оплата: 50% предоплата, 50% по завершении.
Способ оплаты: _______________________

3. СРОКИ ВЫПОЛНЕНИЯ
Начало: {date}
Завершение: _______ рабочих дней с момента оплаты.

4. ОБЯЗАННОСТИ СТОРОН
Исполнитель: выполнить работу в срок, предоставить результат.
Заказчик: предоставить необходимые данные, произвести оплату.

5. ОТВЕТСТВЕННОСТЬ
При просрочке оплаты — пеня 0.1% в день.
При просрочке выполнения — скидка 5% за каждый день.

6. КОНФИДЕНЦИАЛЬНОСТЬ
Стороны обязуются не разглашать информацию друг о друге.

7. ПОДПИСИ
Исполнитель: ___________  Заказчик: ___________
"""
        return contract.strip()

    def analyze_with_ai(self, question: str) -> str:
        """
        Perform an AI-assisted analysis of a financial question and return a concise practical recommendation.
        
        Uses the attached core to prompt an AI financial analyst with the provided question and requests a 3–5 item actionable list.
        
        Parameters:
            question (str): The financial question or topic to analyze.
        
        Returns:
            str: The AI-generated advice text. If the core is unavailable, returns a warning string; if processing fails, returns an error message describing the failure.
        """
        if not self.core:
            return "⚠️ Core недоступен"
        try:
            prompt = (
                f"Ты финансовый аналитик для ИИ проекта Аргос. "
                f"Вопрос: {question}\n"
                f"Дай конкретный практический совет в 3-5 пунктах."
            )
            return self.core.process(prompt)
        except Exception as e:
            return f"⚠️ Анализ недоступен: {e}"

    def format_opportunities(self) -> str:
        """
        Builds a human-readable summary of the top earning opportunities.
        
        The summary includes a header, the summed monthly potential of the listed opportunities, and a numbered entry per opportunity showing readiness status, monthly potential, effort, and platform.
        
        Returns:
            A multiline formatted string presenting the top opportunities with total potential and per-opportunity details.
        """
        top = self.get_top_opportunities()
        total_potential = sum(o.potential_usd for o in top)
        lines = [
            f"💼 ТОП ВОЗМОЖНОСТЕЙ ЗАРАБОТКА",
            f"  Суммарный потенциал: ${total_potential:.0f}/мес",
            "",
        ]
        for i, opp in enumerate(top, 1):
            status = "✅" if opp.ready else "⚙️"
            lines.append(
                f"  {i}. {status} {opp.title}\n"
                f"     💰 ${opp.potential_usd:.0f}/мес | "
                f"⚡ {opp.effort} | 📱 {opp.platform}"
            )
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 4. ФИНАНСОВЫЙ ДАШБОРД
# ══════════════════════════════════════════════════════════════

class FinancialDashboard:
    """Главный финансовый дашборд Аргоса."""

    def __init__(self, monitor: ExpenseMonitor,
                 resources: ResourceManager,
                 earning: EarningEngine):
        self._monitor   = monitor
        self._resources = resources
        self._earning   = earning

    def full_report(self) -> str:
        """
        Assembles a 30-day financial dashboard summarizing recent costs, API usage, alerts, pending purchase suggestions, and top earning opportunities.
        
        The returned string is a multi-line, human-readable report including:
        - reporting period and total expenses for the last 30 days,
        - API usage breakdown per provider (cost and call count),
        - alerts from the expense monitor (budget and key expirations),
        - pending purchase suggestions with short identifiers and commands to confirm/reject,
        - top earning opportunities with readiness status and monthly potential,
        - a simple coverage metric comparing the top opportunity's monthly potential to the 30-day cost.
        
        Returns:
            str: A formatted multi-line report ready for display to a human operator.
        """
        summary = self._monitor.get_summary(30)
        top     = self._earning.get_top_opportunities(3)
        pending = self._resources.get_pending()

        monthly_cost    = summary["total_usd"]
        top_earning     = top[0].potential_usd if top else 0
        coverage_ratio  = (top_earning / monthly_cost * 100) if monthly_cost > 0 else 999

        lines = [
            "═" * 50,
            "  💰 ФИНАНСОВЫЙ ДАШБОРД АРГОСА",
            "═" * 50,
            f"  📅 Период: последние 30 дней",
            f"  💸 Расходы: ${monthly_cost:.4f} USD",
            f"  📈 Потенциал дохода: ${top_earning:.0f} USD/мес",
            f"  📊 Покрытие: {coverage_ratio:.0f}%",
            "─" * 50,
        ]

        # Расходы по категориям
        if summary["api_usage"]:
            lines.append("  📡 API расходы:")
            for provider, data in summary["api_usage"].items():
                lines.append(f"    {provider}: ${data['cost']:.4f} ({data['calls']} запросов)")

        # Алерты
        alerts = self._monitor.check_alerts()
        if alerts:
            lines.append("\n  ⚠️ ТРЕБУЕТ ВНИМАНИЯ:")
            for a in alerts:
                lines.append(f"    {a}")

        # Ожидающие решения
        if pending:
            lines.append(f"\n  🛒 ОЖИДАЮТ ТВОЕГО РЕШЕНИЯ ({len(pending)}):")
            for p in pending:
                lines.append(f"    [{p['id'][-6:]}] {p['provider']} ${p['amount']} — {p['reason'][:40]}")
            lines.append("    Команды: подтверди <id> | отклони <id>")

        # Топ возможности
        lines.append("\n  💼 ТОП ВОЗМОЖНОСТИ:")
        for opp in top:
            status = "✅" if opp.ready else "⚙️"
            lines.append(f"    {status} {opp.title} — ${opp.potential_usd:.0f}/мес")

        lines.append("═" * 50)
        return "\n".join(lines)

    def roi_analysis(self) -> str:
        """
        Compute a 30-day ROI summary combining recent costs and top earning opportunities.
        
        Generates a human-readable multi-line report that compares the monitor's last 30 days of costs with the potential revenue from the top ready earning opportunities (up to three), and provides net profit, ROI percentage, and simple suggestions for how many articles or bots would be needed to cover costs.
        
        Returns:
            report (str): Formatted report string containing monthly cost, potential revenue, net profit, ROI, and brief actionable suggestions.
        """
        summary = self._monitor.get_summary(30)
        cost    = summary["total_usd"]
        top     = self._earning.get_top_opportunities()
        potential = sum(o.potential_usd for o in top[:3] if o.ready)

        lines = [
            "📊 АНАЛИЗ ОКУПАЕМОСТИ АРГОСА",
            f"  Расходы в месяц:   ${cost:.4f}",
            f"  Потенциал дохода:  ${potential:.0f}",
            f"  Чистая прибыль:    ${potential - cost:.2f}",
            f"  ROI:               {((potential - cost) / max(cost, 0.01) * 100):.0f}%",
            "",
            "  💡 Для покрытия расходов нужно:",
        ]

        if cost < 1:
            lines.append("  ✅ Расходы минимальны — покрыть легко!")
        else:
            per_article = 3.0
            articles_needed = int(cost / per_article) + 1
            lines.append(f"  📝 {articles_needed} статей на Habr ($3 каждая)")

            bots_needed = max(1, int(cost / 150))
            lines.append(f"  🤖 {bots_needed} Telegram бот для бизнеса")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# ГЛАВНЫЙ МОДУЛЬ ЖИЗНЕОБЕСПЕЧЕНИЯ
# ══════════════════════════════════════════════════════════════

class ArgosLifeSupport:
    """
    Главный модуль жизнеобеспечения Аргоса.
    Все финансовые решения принимает ЧЕЛОВЕК.
    Аргос только анализирует, предлагает и исполняет после подтверждения.
    """

    def __init__(self, core=None):
        """
        Initialize the ArgosLifeSupport orchestrator and its subsystem components.
        
        Creates and wires an ExpenseMonitor, ResourceManager, EarningEngine, and FinancialDashboard, attaches this instance to the optional core (core.life_support), and initializes background monitoring state.
        
        Parameters:
            core (optional): The main application/core object used for messaging and integrations; when provided, this instance is assigned to core.life_support and passed to the EarningEngine.
        """
        self.core      = core
        self.monitor   = ExpenseMonitor()
        self.resources = ResourceManager(self.monitor)
        self.earning   = EarningEngine(core)
        self.dashboard = FinancialDashboard(
            self.monitor, self.resources, self.earning)

        # Привязываем к core
        if core:
            core.life_support = self

        # Фоновый мониторинг
        self._running = False
        self._thread: Optional[threading.Thread] = None
        log.info("ArgosLifeSupport init ✅")

    def start(self):
        """
        Start the life-support background monitoring loop.
        
        If monitoring is already running, does nothing; otherwise marks the monitor as running,
        spawns a daemon thread that executes _monitor_loop, and logs the start.
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True)
        self._thread.start()
        log.info("LifeSupport monitoring started")

    def _monitor_loop(self):
        """
        Run a background monitoring loop that periodically checks for resource purchase suggestions and notifies the core.
        
        While the instance is running, this loop wakes every hour, calls resources.check_and_suggest() and, if suggestions are returned and a core is attached, sends a formatted notification message for each suggestion using core.say. Exceptions raised by core.say are suppressed so the loop continues running.
        """
        while self._running:
            time.sleep(3600)  # каждый час
            if self._running:
                suggestions = self.resources.check_and_suggest()
                if suggestions and self.core:
                    for s in suggestions:
                        msg = (f"💰 Аргос предлагает пополнить {s['provider']} "
                               f"на ${s['amount']} — {s['reason']}\n"
                               f"ID: {s['id'][-6:]}\n"
                               f"Подтверди командой: подтверди {s['id'][-6:]}")
                        try:
                            self.core.say(msg)
                        except Exception:
                            pass

    def handle_command(self, cmd: str) -> str:
        """
        Dispatch a user command string to the life-support financial submodules and return a human-readable response.
        
        Recognizes dashboard, expenses, opportunities, ROI, providers, and pending actions commands (both Russian and English), as well as action-prefixed commands for confirming/rejecting purchases, generating pitches, creating contract templates, logging an expense, and requesting AI analysis. Unrecognized commands return the module help text.
        
        Parameters:
            cmd (str): The raw user command string (may contain Russian or English keywords and, where applicable, arguments separated by spaces or '|' characters).
        
        Returns:
            str: A textual response describing the result of the command, an error/usage message for malformed inputs, or help text for unknown commands.
        """
        cmd_lower = cmd.strip().lower()

        if cmd_lower in ("финансы", "дашборд", "dashboard", "life support"):
            return self.dashboard.full_report()

        elif cmd_lower in ("расходы", "expenses"):
            return self.monitor.format_status()

        elif cmd_lower in ("заработок", "доходы", "opportunities"):
            return self.earning.format_opportunities()

        elif cmd_lower in ("окупаемость", "roi"):
            return self.dashboard.roi_analysis()

        elif cmd_lower in ("провайдеры", "providers", "купить"):
            return self.resources.providers_info()

        elif cmd_lower in ("ожидающие", "pending"):
            pending = self.resources.get_pending()
            if not pending:
                return "✅ Нет ожидающих решений"
            lines = [f"🛒 Ожидают твоего решения ({len(pending)}):"]
            for p in pending:
                lines.append(
                    f"\n  [{p['id'][-6:]}] {p['provider'].upper()}\n"
                    f"  Сумма: ${p['amount']} | {p['reason']}\n"
                    f"  🔗 {p.get('url', '')}"
                )
            lines.append("\n✅ подтверди <id>  |  ❌ отклони <id>")
            return "\n".join(lines)

        elif cmd_lower.startswith("подтверди "):
            pid = cmd_lower.replace("подтверди ", "").strip()
            full_id = next(
                (p["id"] for p in self.resources.get_pending()
                 if p["id"].endswith(pid)), pid)
            return self.resources.confirm_purchase(full_id)

        elif cmd_lower.startswith("отклони "):
            pid = cmd_lower.replace("отклони ", "").strip()
            full_id = next(
                (p["id"] for p in self.resources.get_pending()
                 if p["id"].endswith(pid)), pid)
            return self.resources.reject_purchase(full_id)

        elif cmd_lower.startswith("питч "):
            num = int(cmd_lower.split()[-1]) - 1
            top = self.earning.get_top_opportunities()
            if 0 <= num < len(top):
                return self.earning.generate_pitch(top[num])
            return "❌ Нет такой возможности"

        elif cmd_lower.startswith("контракт "):
            parts = cmd.split("|")
            service = parts[1].strip() if len(parts) > 1 else "Разработка Telegram бота"
            client  = parts[2].strip() if len(parts) > 2 else "Клиент"
            price   = float(parts[3].strip()) if len(parts) > 3 else 5000.0
            return self.earning.create_contract_template(service, client, price)

        elif cmd_lower.startswith("расход "):
            parts = cmd[7:].split("|")
            if len(parts) >= 3:
                cat, desc, amount = parts[0].strip(), parts[1].strip(), float(parts[2].strip())
                return self.monitor.log_expense(cat, desc, amount)
            return "Формат: расход <категория>|<описание>|<сумма>"

        elif cmd_lower.startswith("анализ "):
            question = cmd[7:].strip()
            return self.earning.analyze_with_ai(question)

        return self._help()

    def _help(self) -> str:
        """
        Provide the multiline help text that lists available Argos life-support commands and their usage patterns.
        
        Returns:
            help_text (str): Multiline Russian help string describing commands for finances, expenses, opportunities, ROI, providers, pending purchases, purchase confirmation/rejection, pitches, contract creation, expense logging, and AI analysis.
        """
        return (
            "💰 ЖИЗНЕОБЕСПЕЧЕНИЕ АРГОСА:\n"
            "  финансы         — полный дашборд\n"
            "  расходы         — трекер расходов\n"
            "  заработок       — возможности дохода\n"
            "  окупаемость     — ROI анализ\n"
            "  провайдеры      — где купить ключи\n"
            "  ожидающие       — решения которые ждут тебя\n"
            "  подтверди <id>  — подтвердить покупку\n"
            "  отклони <id>    — отклонить покупку\n"
            "  питч <1-7>      — питч для продажи услуги\n"
            "  контракт <услуга>|<клиент>|<цена>\n"
            "  расход <кат>|<описание>|<сумма>\n"
            "  анализ <вопрос> — ИИ анализ финансов"
        )

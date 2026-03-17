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
        if not self.expires_at:
            return False
        return (self.expires_at - time.time()) < 86400 * 3  # 3 дня

    def budget_percent(self) -> float:
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
        os.makedirs("data", exist_ok=True)
        self.db_path = db_path
        self._init_db()
        self._api_keys: Dict[str, APIKey] = {}
        self._load_api_keys()
        log.info("ExpenseMonitor init")

    def _init_db(self):
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
        """Загружает API ключи из окружения."""
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
        """Записывает использование API."""
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
        """Записывает расход."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO expenses VALUES (NULL,?,?,?,?,?)",
                (category, description, amount_usd, time.time(), int(auto))
            )
            conn.commit()
        log.info("Expense: %s %.4f USD — %s", category, amount_usd, description)
        return f"✅ Расход добавлен: {description} — ${amount_usd:.4f}"

    def get_summary(self, days: int = 30) -> dict:
        """Сводка расходов за период."""
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
        """Проверяет критические состояния."""
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
        self._monitor = monitor
        self._pending_purchases: List[dict] = []

    def suggest_purchase(self, provider: str,
                         reason: str, amount_usd: float) -> dict:
        """
        Аргос предлагает покупку.
        НЕ ПОКУПАЕТ САМА — ждёт подтверждения человека.
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
        """Человек подтвердил покупку."""
        for p in self._pending_purchases:
            if p["id"] == purchase_id:
                p["status"] = "confirmed"
                self._monitor.log_expense(
                    "api", f"Покупка: {p['provider']}", p["amount"], auto=False
                )
                return f"✅ Покупка подтверждена: {p['provider']} ${p['amount']}"
        return f"❌ Покупка {purchase_id} не найдена"

    def reject_purchase(self, purchase_id: str) -> str:
        """Человек отклонил покупку."""
        for p in self._pending_purchases:
            if p["id"] == purchase_id:
                p["status"] = "rejected"
                return f"❌ Покупка отклонена: {p['provider']}"
        return "❌ Покупка не найдена"

    def get_pending(self) -> List[dict]:
        return [p for p in self._pending_purchases if p["status"] == "pending"]

    def check_and_suggest(self) -> List[dict]:
        """Автоматически проверяет ресурсы и предлагает пополнение."""
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
        lines = ["🛒 ДОСТУПНЫЕ ПРОВАЙДЕРЫ:"]
        for name, info in self.PROVIDERS.items():
            lines.append(f"\n  📦 {name.capitalize()}")
            lines.append(f"     Free: {info['free_tier']}")
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
        self.core = core
        self._opportunities: List[EarningOpportunity] = []
        self._contracts: List[dict] = []
        self._init_opportunities()
        log.info("EarningEngine init")

    def _init_opportunities(self):
        """Базовые возможности заработка через Аргоса."""
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
        """Топ возможностей по потенциалу."""
        ready_first = sorted(
            self._opportunities,
            key=lambda x: (x.ready, x.potential_usd),
            reverse=True
        )
        return ready_first[:limit]

    def generate_pitch(self, opportunity: EarningOpportunity) -> str:
        """Генерирует питч для продажи услуги."""
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
        """Генерирует шаблон договора и сохраняет в список."""
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
        self._contracts.append({
            "service": service,
            "client":  client,
            "price":   price,
            "date":    date,
            "text":    contract.strip(),
        })
        return f"✅ Контракт добавлен: {service} — {client} — {price:.0f} руб."

    def analyze_with_ai(self, question: str) -> str:
        """Анализ финансовых возможностей через ИИ."""
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
        if self._contracts:
            lines.append("\n  📋 КОНТРАКТЫ:")
            for c in self._contracts:
                lines.append(f"    ✅ {c['service']} — {c['client']} — {c['price']:.0f} руб.")
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
        summary = self._monitor.get_summary(30)
        top     = self._earning.get_top_opportunities(3)
        pending = self._resources.get_pending()

        monthly_cost    = summary["total_usd"]
        top_earning     = top[0].potential_usd if top else 0
        coverage_ratio  = (top_earning / monthly_cost * 100) if monthly_cost > 0 else 999

        lines = [
            "═" * 50,
            "  💰 ФИНАНСЫ — ДАШБОРД АРГОСА",
            "═" * 50,
            f"  📅 Период: последние 30 дней",
            f"  💸 Расходы: ${monthly_cost:.4f} USD",
            f"  📈 Доходы (потенциал): ${top_earning:.0f} USD/мес",
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
        """Анализ окупаемости Аргоса."""
        summary = self._monitor.get_summary(30)
        cost    = summary["total_usd"]
        top     = self._earning.get_top_opportunities()
        potential = sum(o.potential_usd for o in top[:3] if o.ready)

        lines = [
            "📊 АНАЛИЗ ОКУПАЕМОСТИ АРГОСА",
            f"  Инвестиции (Расходы в месяц):   ${cost:.4f}",
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
        """Запуск фонового мониторинга."""
        if self._running:
            return "⚠️ Жизнеобеспечение уже активен"
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True)
        self._thread.start()
        log.info("LifeSupport monitoring started")
        return "✅ Жизнеобеспечение активирован"

    def stop(self):
        """Остановка фонового мониторинга."""
        self._running = False
        log.info("LifeSupport monitoring остановлен")
        return "🛑 Жизнеобеспечение остановлен"

    def _monitor_loop(self):
        """Фоновый цикл мониторинга."""
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
        """Обработка команд финансового модуля."""
        cmd_lower = cmd.strip().lower()

        if cmd_lower in ("финансы", "дашборд", "dashboard", "life support"):
            return self.dashboard.full_report()

        elif cmd_lower in ("статус", "status"):
            return self._status()

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
            body  = cmd[len("контракт "):]
            parts = body.split("|")
            service = parts[0].strip() if parts else "Разработка Telegram бота"
            client  = parts[1].strip() if len(parts) > 1 else "Клиент"
            try:
                price = float(parts[2].strip()) if len(parts) > 2 else 5000.0
            except ValueError:
                return "❌ Сумма должна быть числом"
            return self.earning.create_contract_template(service, client, price)

        elif cmd_lower.startswith("расход "):
            parts = cmd[7:].split("|")
            if len(parts) >= 3:
                cat, desc = parts[0].strip(), parts[1].strip()
                try:
                    amount = float(parts[2].strip())
                except ValueError:
                    return "❌ Сумма должна быть числом"
                return self.monitor.log_expense(cat, desc, amount)
            return "Формат: расход <категория>|<описание>|<сумма>"

        elif cmd_lower.startswith("анализ "):
            question = cmd[7:].strip()
            return self.earning.analyze_with_ai(question)

        return self._help()

    def _status(self) -> str:
        return (
            "💰 ARGOS LIFE SUPPORT — статус:\n"
            f"  Мониторинг: {'активен ✅' if self._running else 'остановлен 🛑'}\n"
            "  финансы         — полный дашборд\n"
            "  расходы         — трекер расходов\n"
            "  заработок       — возможности дохода\n"
            "  окупаемость     — ROI анализ"
        )

    def _help(self) -> str:
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

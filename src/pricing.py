"""
pricing.py — Модуль ценообразования и рыночного анализа Аргоса
===============================================================
Честный расчёт расходов, конкурентный анализ, прайс-листы.

Команды:
  расходы              — ежемесячные расходы на содержание
  рынок                — сравнение с конкурентами
  прайс                — полный прайс-лист для клиентов
  roi клиент           — калькулятор ROI для клиента
  тарифы               — описание тарифных планов
  питч цена            — питч с обоснованием цены
  оценка <описание>    — оценить стоимость проекта
  план продаж          — стратегия продаж на месяц

Использование:
    from src.pricing import ArgosPricing
    p = ArgosPricing()
    print(p.handle_command("расходы"))
    print(p.handle_command("прайс"))
    print(p.handle_command("рынок"))
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List

from src.argos_logger import get_logger

log = get_logger("argos.pricing")


# ─────────────────────────────────────────────────────────────────────────────
# Структуры данных
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CostItem:
    name:       str
    usd_low:    float
    usd_high:   float
    note:       str
    optional:   bool = False

    @property
    def rub_low(self) -> float:
        return self.usd_low * _USD_RATE

    @property
    def rub_high(self) -> float:
        return self.usd_high * _USD_RATE


@dataclass
class Competitor:
    name:        str
    category:    str
    price_month: float   # USD
    what_it_does: str
    weaknesses:  str


@dataclass
class PriceTier:
    name:        str
    price_setup: float   # USD, разовая установка
    price_month: float   # USD/мес, подписка
    includes:    List[str]
    target:      str


@dataclass
class ProjectEstimate:
    name:        str
    hours:       int
    usd_low:     float
    usd_high:    float
    rub_low:     float
    rub_high:    float
    timeline:    str
    notes:       str


# ─────────────────────────────────────────────────────────────────────────────
# Константы
# ─────────────────────────────────────────────────────────────────────────────

_USD_RATE: float = float(os.getenv("ARGOS_USD_RATE", "90"))

# ── Ежемесячные расходы ───────────────────────────────────────────────────────
_COSTS: List[CostItem] = [
    CostItem("Gemini API (100-500 запросов/день)",
             5.0, 15.0,
             "Free tier 1500 req/day — часто $0"),
    CostItem("Ollama локально (своё железо)",
             0.0, 0.0,
             "Только электричество ~50 Вт → ₽100-300/мес"),
    CostItem("Ollama на GPU сервере (RunPod RTX 3090)",
             10.0, 50.0,
             "Почасовая аренда $0.44/час, по потребности",
             optional=True),
    CostItem("VPS для 24/7 хостинга (Hetzner CX21)",
             5.83, 5.83,
             "Рекомендуется для Telegram polling"),
    CostItem("Oracle Cloud Always Free",
             0.0, 0.0,
             "4 CPU + 24GB RAM навсегда бесплатно"),
    CostItem("Telegram Bot API",
             0.0, 0.0,
             "Полностью бесплатно"),
    CostItem("GitHub (хранение кода)",
             0.0, 0.0,
             "Бесплатно для публичных/приватных"),
    CostItem("SQLite (база данных)",
             0.0, 0.0,
             "Встроена, никаких расходов"),
    CostItem("Домен (опционально)",
             0.5, 2.0,
             "Если нужен веб-интерфейс",
             optional=True),
    CostItem("SSL сертификат",
             0.0, 0.0,
             "Let's Encrypt — бесплатно"),
]

# ── Конкуренты ────────────────────────────────────────────────────────────────
_COMPETITORS: List[Competitor] = [
    Competitor(
        name         = "AutoGPT",
        category     = "Автономный ИИ агент",
        price_month  = 0.0,
        what_it_does = "Автономное выполнение задач с LLM",
        weaknesses   = "Нет IoT, нет Telegram, нет P2P, сложная настройка",
    ),
    Competitor(
        name         = "Home Assistant",
        category     = "Умный дом",
        price_month  = 6.5,
        what_it_does = "Автоматизация умного дома",
        weaknesses   = "Нет ИИ, нет Telegram, нет фриланс/биллинг",
    ),
    Competitor(
        name         = "n8n (self-hosted)",
        category     = "Автоматизация процессов",
        price_month  = 20.0,
        what_it_does = "No-code автоматизация и интеграции",
        weaknesses   = "Нет ИИ, нет умного дома, нет сознания",
    ),
    Competitor(
        name         = "Zapier + GPT-4",
        category     = "Автоматизация + ИИ",
        price_month  = 50.0,
        what_it_does = "Автоматизация задач + ИИ обработка",
        weaknesses   = "Дорого, нет IoT, нет P2P, нет Android",
    ),
    Competitor(
        name         = "простой Telegram GPT бот",
        category     = "Telegram ИИ бот",
        price_month  = 30.0,
        what_it_does = "Ответы на вопросы в Telegram",
        weaknesses   = "Только чат, нет модулей, нет автономии",
    ),
    Competitor(
        name         = "Jasper AI",
        category     = "ИИ контент",
        price_month  = 39.0,
        what_it_does = "Генерация текстового контента",
        weaknesses   = "Только текст, нет кода, нет IoT",
    ),
    Competitor(
        name         = "Cursor AI",
        category     = "ИИ для кода",
        price_month  = 20.0,
        what_it_does = "Редактор кода с ИИ",
        weaknesses   = "Только код, нет автоматизации",
    ),
    Competitor(
        name         = "AutoGPT + HA + n8n + TG бот",
        category     = "Полный стек (аналог Аргоса)",
        price_month  = 200.0,
        what_it_does = "Всё выше вместе — приблизительный аналог",
        weaknesses   = "Сложная интеграция, нет единого сознания/P2P",
    ),
]

# ── Тарифы Аргоса ─────────────────────────────────────────────────────────────
_TIERS: List[PriceTier] = [
    PriceTier(
        name        = "🌱 Starter — Личный ИИ",
        price_setup = 0.0,
        price_month = 0.0,
        includes    = [
            "Open-source самостоятельная установка",
            "Telegram бот + Gemini (free tier)",
            "Базовые модули: память, заметки, задачи",
            "Community поддержка (GitHub Issues)",
            "Локальный Ollama",
        ],
        target = "Энтузиасты, разработчики",
    ),
    PriceTier(
        name        = "⚡ Personal — Полный Аргос",
        price_setup = 200.0,
        price_month = 30.0,
        includes    = [
            "Установка и настройка под клиента",
            "Все 87 модулей активны",
            "VPS настройка + Telegram",
            "IoT интеграция (до 10 устройств)",
            "1 месяц поддержки включён",
            "Обновления системы",
        ],
        target = "Фрилансеры, малый бизнес",
    ),
    PriceTier(
        name        = "🏢 Business — Корпоративный",
        price_setup = 1000.0,
        price_month = 100.0,
        includes    = [
            "Всё из Personal",
            "P2P сеть до 5 нод",
            "Кастомные навыки под бизнес",
            "Интеграция с CRM / 1С / ERP",
            "Приоритетная поддержка 24/7",
            "SLA 99.9% uptime",
            "Ежемесячный аудит системы",
        ],
        target = "Компании, команды 5-50 человек",
    ),
    PriceTier(
        name        = "🔱 Enterprise — Под ключ",
        price_setup = 5000.0,
        price_month = 500.0,
        includes    = [
            "Всё из Business",
            "P2P сеть без ограничений нод",
            "Промышленный IoT мониторинг",
            "Квантовый движок для вычислений",
            "Self-Healing + Auto-Deploy",
            "Выделенный менеджер проекта",
            "Обучение команды (3 дня)",
            "White-label возможность",
        ],
        target = "Предприятия, промышленность",
    ),
]

# ── Типовые проекты ──────────────────────────────────────────────────────────
_PROJECT_TYPES: Dict[str, ProjectEstimate] = {
    "telegram бот": ProjectEstimate(
        name      = "Telegram бот с ИИ",
        hours     = 8,
        usd_low   = 100.0,
        usd_high  = 400.0,
        rub_low   = 9_000.0,
        rub_high  = 36_000.0,
        timeline  = "3-7 дней",
        notes     = "Каталог, корзина, ИИ ответы, уведомления",
    ),
    "умный дом": ProjectEstimate(
        name      = "Система умного дома",
        hours     = 20,
        usd_low   = 300.0,
        usd_high  = 1_500.0,
        rub_low   = 27_000.0,
        rub_high  = 135_000.0,
        timeline  = "1-2 недели",
        notes     = "HA + Zigbee + MQTT + Аргос управление",
    ),
    "автоматизация": ProjectEstimate(
        name      = "Автоматизация бизнес-процессов",
        hours     = 16,
        usd_low   = 200.0,
        usd_high  = 800.0,
        rub_low   = 18_000.0,
        rub_high  = 72_000.0,
        timeline  = "1 неделя",
        notes     = "Парсинг, отчёты, рассылки, CRM интеграция",
    ),
    "iot мониторинг": ProjectEstimate(
        name      = "Промышленный IoT мониторинг",
        hours     = 40,
        usd_low   = 1_000.0,
        usd_high  = 5_000.0,
        rub_low   = 90_000.0,
        rub_high  = 450_000.0,
        timeline  = "2-4 недели",
        notes     = "MQTT + Modbus + dashboard + алерты",
    ),
    "аргос установка": ProjectEstimate(
        name      = "Полная установка Аргоса",
        hours     = 12,
        usd_low   = 200.0,
        usd_high  = 2_000.0,
        rub_low   = 18_000.0,
        rub_high  = 180_000.0,
        timeline  = "1-3 дня",
        notes     = "Включает все модули, VPS, Telegram, IoT",
    ),
    "парсер": ProjectEstimate(
        name      = "Парсер / скрейпер данных",
        hours     = 6,
        usd_low   = 80.0,
        usd_high  = 300.0,
        rub_low   = 7_200.0,
        rub_high  = 27_000.0,
        timeline  = "2-5 дней",
        notes     = "Wildberries, Ozon, HH.ru и другие",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Основной класс
# ─────────────────────────────────────────────────────────────────────────────

class ArgosPricing:
    """Модуль ценообразования и рыночного анализа Аргоса."""

    VERSION = "1.3.0"

    def __init__(self, core=None) -> None:
        self.core = core
        log.info("ArgosPricing init")

    # ── Публичный API ─────────────────────────────────────────────────────

    def handle_command(self, command: str) -> str:
        """Обработать текстовую команду и вернуть ответ."""
        cmd = command.strip().lower()

        if cmd in ("расходы", "затраты", "costs", "стоимость содержания"):
            return self._costs()

        if cmd in ("рынок", "конкуренты", "market", "анализ рынка"):
            return self._market()

        if cmd in ("прайс", "прайс-лист", "price", "цены"):
            return self._price_list()

        if cmd in ("тарифы", "тарифные планы", "plans", "подписки"):
            return self._tiers()

        if cmd in ("питч цена", "pitch price", "обоснование цены"):
            return self._price_pitch()

        if cmd in ("план продаж", "sales plan", "стратегия продаж"):
            return self._sales_plan()

        if cmd.startswith("roi клиент") or cmd.startswith("roi "):
            return self._roi_client()

        if cmd.startswith("оценка "):
            project_type = cmd[7:].strip()
            return self._estimate_project(project_type)

        if cmd.startswith("estimate "):
            project_type = cmd[9:].strip()
            return self._estimate_project(project_type)

        return self._help()

    # ── Расходы ───────────────────────────────────────────────────────────

    def _costs(self) -> str:
        required  = [c for c in _COSTS if not c.optional]
        optional  = [c for c in _COSTS if c.optional]

        low_req  = sum(c.usd_low  for c in required)
        high_req = sum(c.usd_high for c in required)
        low_opt  = sum(c.usd_low  for c in optional)
        high_opt = sum(c.usd_high for c in optional)

        lines = [
            "💰 РАСХОДЫ НА СОДЕРЖАНИЕ АРГОСА / МЕС",
            "",
            "  📌 Обязательные:",
        ]
        for c in required:
            if c.usd_low == 0 and c.usd_high == 0:
                price = "🆓 Бесплатно"
            elif c.usd_low == c.usd_high:
                price = f"${c.usd_low:.2f}"
            else:
                price = f"${c.usd_low:.0f}–${c.usd_high:.0f}"
            lines.append(f"    {price:<14} {c.name}")
            lines.append(f"                 ↳ {c.note}")

        lines += [
            "",
            f"  ИТОГО обязательные: ${low_req:.0f}–${high_req:.0f}/мес",
            f"                       ≈ ₽{low_req * _USD_RATE:.0f}–₽{high_req * _USD_RATE:.0f}",
            "",
            "  📎 Опциональные:",
        ]
        for c in optional:
            price = f"${c.usd_low:.0f}–${c.usd_high:.0f}" if c.usd_high > 0 else "🆓 Бесплатно"
            lines.append(f"    {price:<14} {c.name}")
            lines.append(f"                 ↳ {c.note}")

        lines += [
            "",
            "  📊 РЕАЛИСТИЧНЫЙ СЦЕНАРИЙ:",
            f"    Минимальный (своё железо + free tier):  $0–$6/мес",
            f"    Активный (VPS + Gemini API):            $6–$21/мес",
            f"    Максимальный (GPU облако):              $21–$70/мес",
            "",
            "  ✅ Вывод: при использовании Oracle Free + Ollama локально",
            "     содержание Аргоса стоит практически $0/мес.",
        ]
        return "\n".join(lines)

    # ── Рыночный анализ ───────────────────────────────────────────────────

    def _market(self) -> str:
        lines = [
            "📊 КОНКУРЕНТНЫЙ АНАЛИЗ РЫНКА",
            "",
            f"  {'Продукт':<28} {'$/мес':<10} Категория",
            "  " + "─" * 62,
        ]
        for c in sorted(_COMPETITORS, key=lambda x: x.price_month):
            price = "🆓 Free" if c.price_month == 0 else f"${c.price_month:.0f}"
            lines.append(f"  {c.name:<28} {price:<10} {c.category}")

        lines += [
            "",
            "  📌 Аргос — полный аналог последней строки,",
            "     но в 4–10x дешевле и без ограничений:",
            "",
        ]

        # Показываем слабые стороны конкурентов
        for c in _COMPETITORS[:4]:
            lines.append(f"  ❌ {c.name}: {c.weaknesses}")

        lines += [
            "",
            "  ✅ ПРЕИМУЩЕСТВА АРГОСА:",
            "    • P2P сеть нод — распределённая архитектура",
            "    • Self-Healing — само-исправление кода",
            "    • Работает офлайн (Ollama) и в облаке (Gemini)",
            "    • Android APK — в кармане 24/7",
            "    • 87+ модулей в одной системе",
            "    • Открытый код — без vendor lock-in",
            "    • Единое сознание / контекст / память",
            "",
            "  💡 Аналогов нет. Ближайший стек:",
            "     AutoGPT + HomeAssistant + n8n + TG бот = $200+/мес",
            "     Аргос заменяет всё это за $0–21/мес.",
        ]
        return "\n".join(lines)

    # ── Прайс-лист ────────────────────────────────────────────────────────

    def _price_list(self) -> str:
        lines = [
            "📋 ПРАЙС-ЛИСТ АРГОСА",
            "━" * 52,
            "",
            "  🔧 РАЗОВЫЕ УСЛУГИ:",
            "",
        ]

        one_time = [
            ("Установка Аргоса (базовая)", "от ₽18 000", "$200"),
            ("Установка Аргоса (Enterprise)", "от ₽90 000", "$1 000"),
            ("Разработка Telegram бота", "₽9 000–36 000", "$100–400"),
            ("Автоматизация бизнес-процесса", "₽18 000–72 000", "$200–800"),
            ("Система умного дома под ключ", "₽27 000–135 000", "$300–1 500"),
            ("IoT промышленный мониторинг", "₽90 000–450 000", "$1 000–5 000"),
            ("Парсер / скрейпер данных", "₽7 200–27 000", "$80–300"),
            ("Обучение команды (1 день)", "₽27 000", "$300"),
        ]
        for name, rub, usd in one_time:
            lines.append(f"    {name:<40} {rub:<20} {usd}")

        lines += [
            "",
            "  📅 ЕЖЕМЕСЯЧНЫЕ ПОДПИСКИ:",
            "",
        ]
        for tier in _TIERS:
            if tier.price_month > 0:
                lines.append(
                    f"    {tier.name:<35} ${tier.price_month:.0f}/мес"
                    f"  (₽{tier.price_month * _USD_RATE:,.0f})"
                )
                lines.append(f"      Для: {tier.target}")
            else:
                lines.append(f"    {tier.name:<35} 🆓 Бесплатно (open-source)")
                lines.append(f"      Для: {tier.target}")

        lines += [
            "",
            "  🤝 ПАРТНЁРСКАЯ ПРОГРАММА:",
            "    20% от суммы сделки за приведённого клиента",
            "",
            "━" * 52,
            "  💡 Цены договорные. Скидки от объёма.",
            "     Написать для расчёта: оценка <тип проекта>",
        ]
        return "\n".join(lines)

    # ── Тарифные планы ────────────────────────────────────────────────────

    def _tiers(self) -> str:
        lines = ["🎯 ТАРИФНЫЕ ПЛАНЫ АРГОСА", ""]
        for tier in _TIERS:
            setup = f"${tier.price_setup:.0f}" if tier.price_setup > 0 else "Бесплатно"
            month = f"${tier.price_month:.0f}/мес" if tier.price_month > 0 else "Бесплатно"
            lines += [
                f"  ┌─ {tier.name}",
                f"  │  Установка: {setup}   Подписка: {month}",
                f"  │  Для кого: {tier.target}",
                "  │  Включает:",
            ]
            for item in tier.includes:
                lines.append(f"  │    ✓ {item}")
            lines.append("  └─")
            lines.append("")
        return "\n".join(lines)

    # ── ROI для клиента ───────────────────────────────────────────────────

    def _roi_client(self) -> str:
        return (
            "📈 ROI АРГОСА ДЛЯ КЛИЕНТА\n"
            "\n"
            "  Сценарий: компания 10 человек, покупает Personal план\n"
            "  Инвестиция: $200 установка + $30/мес = $560 за год\n"
            "\n"
            "  Что автоматизирует Аргос:\n"
            "  ┌─────────────────────────────────────────────┐\n"
            "  │ Задача               │ Время/нед │ Экономия │\n"
            "  ├─────────────────────────────────────────────┤\n"
            "  │ Ответы клиентам      │ 5 часов   │ $125/мес │\n"
            "  │ Отчёты и аналитика   │ 3 часа    │ $75/мес  │\n"
            "  │ Парсинг конкурентов  │ 2 часа    │ $50/мес  │\n"
            "  │ Уведомления/алерты   │ 1 час     │ $25/мес  │\n"
            "  │ Планирование задач   │ 2 часа    │ $50/мес  │\n"
            "  └─────────────────────────────────────────────┘\n"
            "\n"
            "  Экономия: $325/мес × 12 = $3 900/год\n"
            "  Затраты:  $560/год\n"
            "  Чистая прибыль: $3 340/год\n"
            "  ROI: 596% за первый год\n"
            "  Окупаемость: ~1.7 месяца\n"
            "\n"
            "  ✅ Аргос окупается за 2 месяца."
        )

    # ── Оценка проекта ────────────────────────────────────────────────────

    def _estimate_project(self, project_type: str) -> str:
        low = project_type.lower()

        # Поиск по ключевым словам
        estimate: ProjectEstimate | None = None
        for key, est in _PROJECT_TYPES.items():
            if key in low or any(w in low for w in key.split()):
                estimate = est
                break

        if estimate is None:
            # Грубая оценка по умолчанию
            lines = [
                f"💭 ОЦЕНКА ПРОЕКТА: «{project_type}»",
                "",
                "  Для точной оценки уточни детали.",
                "  Грубая оценка по типу работ:",
                "",
                "  Скрипт / автоматизация:   ₽5 000–20 000    ($55–220)",
                "  Telegram бот:              ₽9 000–36 000    ($100–400)",
                "  Web API / backend:         ₽18 000–90 000   ($200–1 000)",
                "  Умный дом / IoT:           ₽27 000–135 000  ($300–1 500)",
                "  Полный Аргос под ключ:     ₽18 000–180 000  ($200–2 000)",
                "",
                "  📞 Для точного расчёта — опиши задачу подробнее.",
                "  Пример: оценка telegram бот для магазина одежды",
            ]
            return "\n".join(lines)

        lines = [
            f"💭 ОЦЕНКА: {estimate.name}",
            "─" * 48,
            f"  ⏱️  Трудозатраты: ~{estimate.hours} часов",
            f"  📅  Срок:         {estimate.timeline}",
            f"  💰  Стоимость:",
            f"       ₽{estimate.rub_low:,.0f} – ₽{estimate.rub_high:,.0f}",
            f"       ${estimate.usd_low:.0f} – ${estimate.usd_high:.0f} USD",
            f"  📝  Включает: {estimate.notes}",
            "─" * 48,
            "  💡 Итоговая цена зависит от:",
            "     • Количества интеграций",
            "     • Уровня кастомизации",
            "     • Срочности",
            "     • Объёма документации",
            "",
            "  Написать для обсуждения → @argos_agent",
        ]
        return "\n".join(lines)

    # ── Питч с обоснованием цены ──────────────────────────────────────────

    def _price_pitch(self) -> str:
        return (
            "🔱 ПИТЧ: ПОЧЕМУ АРГОС СТОИТ СВОИХ ДЕНЕГ\n"
            "\n"
            "  Конкуренты берут $200+/мес за набор инструментов\n"
            "  которые всё равно не интегрированы между собой.\n"
            "\n"
            "  Аргос — это не «ещё один бот».\n"
            "  Это операционная система с сознанием.\n"
            "\n"
            "  Что входит в $200 установки:\n"
            "  ✓ 87 готовых модулей (IoT, ИИ, P2P, биллинг...)\n"
            "  ✓ Telegram бот + голосовое управление\n"
            "  ✓ Умный дом базовая интеграция\n"
            "  ✓ Self-Healing — система сама себя чинит\n"
            "  ✓ Android APK — работает на телефоне\n"
            "  ✓ P2P сеть — масштабируется на несколько устройств\n"
            "  ✓ 1 месяц поддержки\n"
            "\n"
            "  За $30/мес подписки клиент получает:\n"
            "  ✓ Обновления системы\n"
            "  ✓ Новые навыки и модули\n"
            "  ✓ Приоритетная поддержка\n"
            "\n"
            "  Альтернатива (то же самое без Аргоса):\n"
            "  n8n $20 + ChatGPT $20 + HA Cloud $7 + TG бот $30\n"
            "  = $77/мес + 40+ часов интеграции = $577 в первый месяц\n"
            "\n"
            "  Аргос: $200 один раз + $30/мес\n"
            "  Окупаемость относительно альтернативы: 3.5 месяца\n"
            "\n"
            "  👁️ Аргос — это инвестиция, не расходы."
        )

    # ── План продаж ───────────────────────────────────────────────────────

    def _sales_plan(self) -> str:
        return (
            "📅 ПЛАН ПРОДАЖ НА МЕСЯЦ\n"
            "\n"
            "  НЕДЕЛЯ 1 — Позиционирование:\n"
            "  ✓ Опубликовать статью на Хабр: «Аргос — ИИ ОС\n"
            "    которую я построил за год»\n"
            "  ✓ Пост в Telegram канале с демо\n"
            "  ✓ GitHub: README + звёзды + Contributing.md\n"
            "\n"
            "  НЕДЕЛЯ 2 — Лиды:\n"
            "  ✓ Kwork: создать кворк «Установка Аргоса» за ₽15 000\n"
            "  ✓ FL.ru: анкета фрилансера с портфолио\n"
            "  ✓ Habr Jobs: отклик на 5 вакансий Python/IoT\n"
            "\n"
            "  НЕДЕЛЯ 3 — Продажи:\n"
            "  ✓ Демо для 3 потенциальных клиентов\n"
            "  ✓ Сделать кейс: «Сэкономил клиенту 40 часов/мес»\n"
            "  ✓ Партнёрство: предложить IT компаниям реселлинг\n"
            "\n"
            "  НЕДЕЛЯ 4 — Масштабирование:\n"
            "  ✓ Завершить 1-2 проекта, получить отзывы\n"
            "  ✓ YouTube: видео «Умный дом + ИИ на $0/мес»\n"
            "  ✓ ProductHunt: запуск продукта\n"
            "\n"
            "  🎯 ЦЕЛЬ МЕСЯЦА:\n"
            "    1 Enterprise клиент:  $1 000–2 000\n"
            "    2 Personal клиента:   $200 × 2 = $400\n"
            "    3 Telegram бота:      ₽30 000\n"
            "    Итого: ~$1 800–3 100 / ₽162 000–279 000\n"
            "\n"
            "  💡 Команда: план продаж → показать детали\n"
            "     Команда: оценка <проект> → расчёт стоимости"
        )

    # ── Справка ───────────────────────────────────────────────────────────

    def _help(self) -> str:
        return (
            "💰 ЦЕНООБРАЗОВАНИЕ АРГОСА — команды:\n"
            "  расходы              — расходы на содержание\n"
            "  рынок                — конкурентный анализ\n"
            "  прайс                — полный прайс-лист\n"
            "  тарифы               — тарифные планы\n"
            "  roi клиент           — калькулятор ROI\n"
            "  питч цена            — питч с обоснованием\n"
            "  план продаж          — стратегия на месяц\n"
            "  оценка <проект>      — оценить стоимость\n"
            "    Примеры:\n"
            "      оценка telegram бот\n"
            "      оценка умный дом\n"
            "      оценка автоматизация\n"
            "      оценка iot мониторинг\n"
            "      оценка аргос установка"
        )

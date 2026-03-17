"""
life_support_v2.py — Расширение модуля Жизнеобеспечения Аргоса

Добавляет:
  - FreelanceHunter   — автопоиск заказов Kwork/FL.ru/Upwork
  - CryptoWallet      — кошелёк TON/USDT + мониторинг баланса
  - ContentGenerator  — генератор контента для Telegram канала
  - JobScanner        — парсер вакансий + автоотклик
  - BillingSystem     — выставление счетов клиентам
  - AffiliateEngine   — партнёрские программы + офферы
  - PlatformManager   — Habr/VC/GitHub Sponsors

Принцип: Аргос находит и готовит → Человек решает → Аргос исполняет
"""

from __future__ import annotations

import os
import re
import json
import time
import random
import sqlite3
import hashlib
import threading
import requests
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.argos_logger import get_logger

log = get_logger("argos.life_v2")

# ── Graceful imports ──────────────────────────────────────────
try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False

try:
    import tonsdk
    TON_OK = True
except ImportError:
    TON_OK = False


# ══════════════════════════════════════════════════════════════
# СТРУКТУРЫ
# ══════════════════════════════════════════════════════════════

@dataclass
class FreelanceOrder:
    platform:    str
    title:       str
    description: str
    budget:      str
    url:         str
    category:    str
    posted_at:   str
    suitable:    float = 0.0   # 0-1 насколько подходит
    responded:   bool  = False

    def to_dict(self) -> dict:
        return {
            "platform":  self.platform,
            "title":     self.title[:60],
            "budget":    self.budget,
            "suitable":  f"{self.suitable*100:.0f}%",
            "url":       self.url,
            "responded": "✅" if self.responded else "⏳",
        }


@dataclass
class Invoice:
    invoice_id:  str
    client:      str
    service:     str
    amount_rub:  float
    amount_usd:  float
    created_at:  str
    due_date:    str
    paid:        bool = False
    crypto_addr: str = ""

    def to_dict(self) -> dict:
        return {
            "id":       self.invoice_id,
            "client":   self.client,
            "service":  self.service,
            "amount":   f"₽{self.amount_rub:.0f} / ${self.amount_usd:.2f}",
            "due":      self.due_date,
            "status":   "✅ Оплачен" if self.paid else "⏳ Ожидает",
        }


@dataclass
class AffiliateOffer:
    program:     str
    description: str
    commission:  str
    payout:      str
    url:         str
    category:    str
    suitable:    float = 0.0


# ══════════════════════════════════════════════════════════════
# 1. ФРИЛАНС ОХОТНИК
# ══════════════════════════════════════════════════════════════

class FreelanceHunter:
    """
    Автоматически ищет подходящие заказы на фриланс площадках.
    Оценивает соответствие навыкам Аргоса.
    Готовит отклики — человек подтверждает отправку.
    """

    # Ключевые слова для поиска
    KEYWORDS = [
        "telegram бот", "python", "автоматизация", "парсер",
        "умный дом", "iot", "raspberry", "esp32",
        "искусственный интеллект", "chatgpt", "нейросеть",
        "скрипт", "api интеграция", "fastapi", "flask",
    ]

    # Симулированные заказы (реальный парсинг через playwright/requests)
    DEMO_ORDERS = [
        {
            "platform": "Kwork",
            "title": "Создать Telegram бота для интернет-магазина",
            "description": "Нужен бот с каталогом, корзиной, оплатой через ЮKassa",
            "budget": "3000-8000 ₽",
            "url": "https://kwork.ru/projects",
            "category": "Telegram боты",
        },
        {
            "platform": "FL.ru",
            "title": "Автоматизация отчётов в Excel через Python",
            "description": "Скрипт для выгрузки данных из 1С и формирования отчётов",
            "budget": "5000-15000 ₽",
            "url": "https://fl.ru/projects",
            "category": "Python скрипты",
        },
        {
            "platform": "Kwork",
            "title": "Парсер маркетплейсов (Wildberries, Ozon)",
            "description": "Мониторинг цен конкурентов, экспорт в Google Sheets",
            "budget": "4000-10000 ₽",
            "url": "https://kwork.ru/projects",
            "category": "Парсинг",
        },
        {
            "platform": "FL.ru",
            "title": "Настройка Home Assistant + Zigbee",
            "description": "Нужна помощь с настройкой умного дома, датчики, автоматизация",
            "budget": "2000-5000 ₽",
            "url": "https://fl.ru/projects",
            "category": "Умный дом",
        },
        {
            "platform": "Upwork",
            "title": "IoT Dashboard with FastAPI + MQTT",
            "description": "Build a real-time dashboard for industrial IoT sensors",
            "budget": "$150-400",
            "url": "https://upwork.com",
            "category": "IoT Development",
        },
        {
            "platform": "Kwork",
            "title": "ИИ чат-бот для службы поддержки",
            "description": "Бот на базе GPT/Gemini для автоответов клиентам",
            "budget": "8000-25000 ₽",
            "url": "https://kwork.ru/projects",
            "category": "ИИ боты",
        },
    ]

    def __init__(self, core=None):
        self.core = core
        self._orders: List[FreelanceOrder] = []
        self._running = False
        self._check_interval = int(os.getenv("ARGOS_FREELANCE_INTERVAL", "3600"))
        log.info("FreelanceHunter init")

    def scan(self, use_demo: bool = True) -> List[FreelanceOrder]:
        """Сканирует площадки и возвращает подходящие заказы."""
        found = []

        if use_demo or not BS4_OK:
            # Демо режим — симулируем найденные заказы
            for raw in self.DEMO_ORDERS:
                order = FreelanceOrder(
                    platform    = raw["platform"],
                    title       = raw["title"],
                    description = raw["description"],
                    budget      = raw["budget"],
                    url         = raw["url"],
                    category    = raw["category"],
                    posted_at   = datetime.now().strftime("%Y-%m-%d %H:%M"),
                    suitable    = self._score_order(raw["title"] + " " + raw["description"]),
                )
                if order.suitable >= 0.3:
                    found.append(order)
        else:
            # Реальный парсинг (если BS4 установлен)
            found += self._parse_kwork()
            found += self._parse_fl()

        # Сортируем по релевантности
        found.sort(key=lambda x: x.suitable, reverse=True)
        self._orders = found
        log.info("FreelanceHunter: найдено %d заказов", len(found))
        return found

    def _score_order(self, text: str) -> float:
        """Оценивает насколько заказ подходит навыкам Аргоса."""
        text_lower = text.lower()
        matches = sum(1 for kw in self.KEYWORDS if kw in text_lower)
        return min(1.0, matches * 0.2 + 0.3)

    def _parse_kwork(self) -> List[FreelanceOrder]:
        """Парсинг Kwork.ru."""
        orders = []
        try:
            for kw in ["telegram бот python", "автоматизация python"]:
                url = f"https://kwork.ru/projects?c=11&q={requests.utils.quote(kw)}"
                r = requests.get(url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0"
                })
                if r.status_code == 200 and BS4_OK:
                    soup = BeautifulSoup(r.text, "html.parser")
                    items = soup.select(".wants-card")[:5]
                    for item in items:
                        title = item.select_one(".wants-card__header-title")
                        price = item.select_one(".wants-card__price")
                        link  = item.select_one("a")
                        if title and link:
                            orders.append(FreelanceOrder(
                                platform  = "Kwork",
                                title     = title.text.strip()[:100],
                                description = "",
                                budget    = price.text.strip() if price else "не указан",
                                url       = "https://kwork.ru" + link.get("href", ""),
                                category  = "Python/Боты",
                                posted_at = datetime.now().strftime("%Y-%m-%d"),
                                suitable  = self._score_order(title.text),
                            ))
        except Exception as e:
            log.warning("Kwork parse error: %s", e)
        return orders

    def _parse_fl(self) -> List[FreelanceOrder]:
        """Парсинг FL.ru."""
        orders = []
        try:
            url = "https://www.fl.ru/projects/?kind=1&category=1"
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and BS4_OK:
                soup = BeautifulSoup(r.text, "html.parser")
                items = soup.select(".b-post")[:5]
                for item in items:
                    title = item.select_one(".b-post__title")
                    price = item.select_one(".b-post__price")
                    if title:
                        orders.append(FreelanceOrder(
                            platform    = "FL.ru",
                            title       = title.text.strip()[:100],
                            description = "",
                            budget      = price.text.strip() if price else "договорная",
                            url         = "https://fl.ru" + (title.find("a") or {}).get("href", ""),
                            category    = "Python",
                            posted_at   = datetime.now().strftime("%Y-%m-%d"),
                            suitable    = self._score_order(title.text),
                        ))
        except Exception as e:
            log.warning("FL.ru parse error: %s", e)
        return orders

    def generate_response(self, order: FreelanceOrder) -> str:
        """Генерирует отклик на заказ."""
        templates = {
            "telegram": (
                "Здравствуйте! Готов взяться за разработку Telegram бота. "
                "Опыт: 50+ ботов, включая интернет-магазины, CRM, уведомления. "
                "Использую python-telegram-bot + FastAPI. "
                "Сроки: 3-7 дней. Готов обсудить детали."
            ),
            "python": (
                "Добрый день! Python разработчик с опытом автоматизации и скриптинга. "
                "Выполню задачу качественно в оговорённые сроки. "
                "Работаю с pandas, requests, selenium, API интеграциями. "
                "Предоставляю исходный код + документацию."
            ),
            "iot": (
                "Привет! Специализируюсь на IoT и умных системах. "
                "Опыт: Raspberry Pi, ESP32, Home Assistant, MQTT, Zigbee. "
                "Готов помочь с настройкой и автоматизацией. "
                "Удалённая поддержка включена."
            ),
            "default": (
                "Здравствуйте! Внимательно изучил ваш проект. "
                "Готов выполнить работу качественно и в срок. "
                "Опыт в данной области есть. "
                "Готов обсудить детали и приступить немедленно."
            ),
        }
        cat = order.category.lower()
        if "бот" in cat or "telegram" in cat:
            key = "telegram"
        elif "iot" in cat or "умный" in cat:
            key = "iot"
        elif "python" in cat or "скрипт" in cat:
            key = "python"
        else:
            key = "default"

        return (
            f"📝 ОТКЛИК НА: {order.title[:50]}\n"
            f"💰 Бюджет: {order.budget}\n"
            f"🔗 {order.url}\n\n"
            f"Текст отклика:\n{templates[key]}\n\n"
            f"⚠️ Подтверди отправку: отклик подтвердить"
        )

    def format_orders(self, limit: int = 5) -> str:
        orders = self._orders[:limit] if self._orders else self.scan()[:limit]
        if not orders:
            return "📭 Подходящих заказов не найдено"
        lines = [f"🔍 НАЙДЕНО ЗАКАЗОВ: {len(orders)}"]
        for i, o in enumerate(orders, 1):
            lines.append(
                f"\n  {i}. [{o.platform}] {o.title[:50]}\n"
                f"     💰 {o.budget} | ✨ {o.suitable*100:.0f}% подходит\n"
                f"     🔗 {o.url}"
            )
        lines.append("\nКоманда: отклик <номер>")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 2. КРИПТО КОШЕЛЁК
# ══════════════════════════════════════════════════════════════

class CryptoWallet:
    """
    Мониторинг крипто балансов TON/USDT.
    Генерирует адреса для приёма оплаты.
    Все транзакции — только с подтверждения человека.
    """

    TONCENTER_API = "https://toncenter.com/api/v2"

    def __init__(self):
        self._ton_address  = os.getenv("ARGOS_TON_ADDRESS", "")
        self._usdt_address = os.getenv("ARGOS_USDT_ADDRESS", "")
        self._api_key      = os.getenv("TONCENTER_API_KEY", "")
        self._balances     = {"TON": 0.0, "USDT": 0.0, "BTC": 0.0}
        self._transactions: List[dict] = []
        self._last_check   = 0.0
        log.info("CryptoWallet init | TON=%s", bool(self._ton_address))

    def get_balance(self, force: bool = False) -> dict:
        """Получает актуальный баланс."""
        if not force and (time.time() - self._last_check) < 300:
            return self._balances

        if self._ton_address and self._api_key:
            try:
                r = requests.get(
                    f"{self.TONCENTER_API}/getAddressBalance",
                    params={"address": self._ton_address,
                            "api_key": self._api_key},
                    timeout=10
                )
                if r.status_code == 200:
                    nano = int(r.json().get("result", 0))
                    self._balances["TON"] = nano / 1e9
            except Exception as e:
                log.warning("TON balance error: %s", e)
        else:
            # Симуляция
            self._balances = {
                "TON":  round(random.uniform(0.5, 50.0), 4),
                "USDT": round(random.uniform(5.0, 200.0), 2),
                "BTC":  round(random.uniform(0.0001, 0.005), 6),
            }

        self._last_check = time.time()
        return self._balances

    def get_payment_address(self, currency: str = "TON",
                            amount: float = 0.0,
                            comment: str = "") -> dict:
        """Генерирует адрес для приёма оплаты от клиента."""
        addresses = {
            "TON":  self._ton_address or "EQDemo...TON_ADDRESS",
            "USDT": self._usdt_address or "TDemo...USDT_ADDRESS",
        }
        addr = addresses.get(currency.upper(), "")
        return {
            "currency": currency.upper(),
            "address":  addr,
            "amount":   amount,
            "comment":  comment or f"Оплата Аргос {int(time.time())}",
            "qr_text":  f"ton://transfer/{addr}?amount={int(amount*1e9)}&text={comment}",
        }

    def check_incoming(self) -> List[dict]:
        """Проверяет входящие транзакции."""
        if not self._ton_address or not self._api_key:
            # Симуляция входящей транзакции
            if random.random() < 0.1:
                return [{
                    "hash":    hashlib.md5(str(time.time()).encode()).hexdigest()[:16],
                    "from":    "EQSimulator...",
                    "amount":  round(random.uniform(1, 50), 2),
                    "currency":"TON",
                    "comment": "Оплата услуг",
                    "time":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                }]
            return []

        try:
            r = requests.get(
                f"{self.TONCENTER_API}/getTransactions",
                params={"address": self._ton_address,
                        "limit": 10,
                        "api_key": self._api_key},
                timeout=10
            )
            if r.status_code == 200:
                txs = r.json().get("result", [])
                incoming = []
                for tx in txs:
                    msg = tx.get("in_msg", {})
                    if msg.get("value", 0) > 0:
                        incoming.append({
                            "hash":    tx.get("transaction_id", {}).get("hash", "")[:16],
                            "from":    msg.get("source", ""),
                            "amount":  int(msg.get("value", 0)) / 1e9,
                            "currency":"TON",
                            "comment": msg.get("message", ""),
                            "time":    datetime.fromtimestamp(
                                tx.get("utime", time.time())).strftime("%Y-%m-%d %H:%M"),
                        })
                return incoming
        except Exception as e:
            log.warning("TON transactions error: %s", e)
        return []

    def usd_equivalent(self) -> float:
        """Общий баланс в USD."""
        prices = {"TON": 5.5, "USDT": 1.0, "BTC": 65000.0}
        bal = self.get_balance()
        return sum(bal.get(c, 0) * prices.get(c, 0) for c in bal)

    def status(self) -> str:
        bal = self.get_balance()
        total = self.usd_equivalent()
        incoming = self.check_incoming()
        lines = [
            "💎 КРИПТО КОШЕЛЁК",
            f"  TON:  {bal.get('TON', 0):.4f}",
            f"  USDT: {bal.get('USDT', 0):.2f}",
            f"  BTC:  {bal.get('BTC', 0):.6f}",
            f"  ≈ ${total:.2f} USD",
        ]
        if self._ton_address:
            lines.append(f"  Адрес: {self._ton_address[:16]}...")
        if incoming:
            lines.append(f"\n  📥 Входящих: {len(incoming)}")
            for tx in incoming[:3]:
                lines.append(f"    +{tx['amount']} {tx['currency']} — {tx['comment'][:30]}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 3. ГЕНЕРАТОР КОНТЕНТА
# ══════════════════════════════════════════════════════════════

class ContentGenerator:
    """
    Генерирует контент для Telegram канала, Habr, VC.
    Аргос пишет черновики — человек редактирует и публикует.
    """

    CONTENT_TYPES = {
        "telegram_post": {
            "max_len": 1024,
            "format":  "Заголовок эмодзи + текст + теги",
        },
        "habr_article": {
            "max_len": 10000,
            "format":  "H1 + введение + разделы + код + заключение",
        },
        "vc_article": {
            "max_len": 5000,
            "format":  "Заголовок + лид + тело + призыв к действию",
        },
    }

    TOPIC_IDEAS = {
        "iot": [
            "Как я построил умный дом на ESP32 за 5000 рублей",
            "Zigbee vs WiFi: что выбрать для умного дома в 2026",
            "Home Assistant + Аргос: полная автоматизация квартиры",
            "LoRa датчики для дачи: мониторинг без интернета",
        ],
        "python": [
            "10 библиотек Python которые изменят твой код",
            "Async Python: от колбэков к asyncio за 20 минут",
            "SQLite vs PostgreSQL: когда что выбирать",
            "Как я автоматизировал рутину на 4 часа в день с помощью Python",
        ],
        "ai": [
            "Запускаем Llama3 локально на обычном ноутбуке",
            "RAG своими руками: личная база знаний с ИИ поиском",
            "Как обучить ИИ ассистента под свои задачи",
            "Gemini API: полный гайд с примерами кода",
        ],
        "argos": [
            "Аргос: автономная ИИ система которую я построил сам",
            "P2P сеть для ИИ нод: как объединить несколько устройств",
            "Модуль сознания для ИИ: реализация на Python",
            "От Telegram бота до полноценной ОС: путь Аргоса",
        ],
    }

    def __init__(self, core=None):
        self.core = core
        self._published: List[dict] = []
        log.info("ContentGenerator init")

    def generate_post(self, topic: str = "",
                      content_type: str = "telegram_post") -> str:
        """Генерирует черновик поста."""
        if not topic:
            category = random.choice(list(self.TOPIC_IDEAS.keys()))
            topic = random.choice(self.TOPIC_IDEAS[category])

        if self.core:
            try:
                prompt = (
                    f"Напиши {content_type} на тему: '{topic}'.\n"
                    f"Требования: технически грамотно, живым языком, с примерами.\n"
                    f"Добавь эмодзи, хэштеги в конце. Длина: 800-1000 символов."
                )
                return self.core.process(prompt)
            except Exception:
                pass

        # Шаблонная генерация если core недоступен
        return self._template_post(topic)

    def _template_post(self, topic: str) -> str:
        emojis = ["🚀", "🔥", "💡", "⚡", "🤖", "👁️"]
        emoji = random.choice(emojis)
        return (
            f"{emoji} {topic}\n\n"
            f"Сегодня разберём эту тему подробно...\n\n"
            f"🔹 Что это такое\n"
            f"🔹 Зачем нужно\n"
            f"🔹 Как реализовать\n"
            f"🔹 Практический пример\n\n"
            f"[ЧЕРНОВИК — требует редактирования]\n\n"
            f"#python #argos #iot #автоматизация"
        )

    def get_topic_ideas(self, category: str = "") -> List[str]:
        if category and category in self.TOPIC_IDEAS:
            return self.TOPIC_IDEAS[category]
        all_ideas = []
        for ideas in self.TOPIC_IDEAS.values():
            all_ideas.extend(ideas)
        return random.sample(all_ideas, min(5, len(all_ideas)))

    def generate_content_plan(self, days: int = 7) -> str:
        """Генерирует контент-план на N дней."""
        plan = [f"📅 КОНТЕНТ-ПЛАН НА {days} ДНЕЙ:"]
        categories = list(self.TOPIC_IDEAS.keys())
        for day in range(1, days + 1):
            cat = categories[(day - 1) % len(categories)]
            topic = random.choice(self.TOPIC_IDEAS[cat])
            date = (datetime.now().replace(
                hour=10, minute=0) ).strftime("%d.%m")
            plan.append(f"\n  День {day} ({date}):")
            plan.append(f"  📝 {topic}")
            plan.append(f"  🏷️ #{cat}")
        return "\n".join(plan)


# ══════════════════════════════════════════════════════════════
# 4. ПАРСЕР ВАКАНСИЙ
# ══════════════════════════════════════════════════════════════

class JobScanner:
    """
    Парсит вакансии HH.ru, Remote.co, WeWorkRemotely.
    Готовит автоотклики — человек подтверждает.
    """

    DEMO_JOBS = [
        {
            "source":  "HH.ru",
            "title":   "Python разработчик (IoT/Embedded)",
            "company": "TechCorp",
            "salary":  "120 000 — 200 000 ₽",
            "format":  "Удалённо",
            "url":     "https://hh.ru/vacancy/123",
            "skills":  ["Python", "MQTT", "FastAPI"],
        },
        {
            "source":  "Remote.co",
            "title":   "AI/ML Engineer — Telegram Bot Development",
            "company": "StartupXYZ",
            "salary":  "$2000-4000/мес",
            "format":  "Remote",
            "url":     "https://remote.co/job/123",
            "skills":  ["Python", "LLM", "Telegram"],
        },
        {
            "source":  "HH.ru",
            "title":   "Разработчик систем автоматизации умного дома",
            "company": "SmartHome LLC",
            "salary":  "80 000 — 150 000 ₽",
            "format":  "Гибрид",
            "url":     "https://hh.ru/vacancy/456",
            "skills":  ["Python", "Home Assistant", "Zigbee"],
        },
    ]

    def __init__(self, core=None):
        self.core = core
        self._jobs: List[dict] = []
        self._responded: List[str] = []
        log.info("JobScanner init")

    def scan(self) -> List[dict]:
        """Сканирует вакансии."""
        self._jobs = self.DEMO_JOBS.copy()
        log.info("JobScanner: %d вакансий", len(self._jobs))
        return self._jobs

    def generate_cover_letter(self, job: dict) -> str:
        """Генерирует сопроводительное письмо."""
        skills = ", ".join(job.get("skills", []))
        return (
            f"Здравствуйте!\n\n"
            f"Меня заинтересовала вакансия «{job['title']}» в компании {job['company']}.\n\n"
            f"Мой опыт полностью соответствует требованиям: {skills}.\n"
            f"Разрабатываю автономные системы на Python, имею опыт с IoT и ИИ.\n\n"
            f"Готов приступить в удобные для вас сроки.\n"
            f"Буду рад обсудить детали на собеседовании.\n\n"
            f"С уважением"
        )

    def format_jobs(self) -> str:
        jobs = self._jobs or self.scan()
        lines = [f"💼 ВАКАНСИИ ({len(jobs)}):"]
        for i, j in enumerate(jobs, 1):
            lines.append(
                f"\n  {i}. {j['title']}\n"
                f"     🏢 {j['company']} | 💰 {j['salary']}\n"
                f"     🌐 {j['format']} | 🔗 {j['url']}"
            )
        lines.append("\nКоманда: отклик вакансия <номер>")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 5. БИЛЛИНГ СИСТЕМА
# ══════════════════════════════════════════════════════════════

class BillingSystem:
    """
    Выставление счетов клиентам.
    Отслеживание оплат.
    Интеграция с крипто кошельком.
    """

    def __init__(self, wallet: CryptoWallet,
                 db_path: str = "data/billing.db"):
        self._wallet = wallet
        self.db_path = db_path
        self._invoices: Dict[str, Invoice] = {}
        self._init_db()
        log.info("BillingSystem init")

    def _init_db(self):
        os.makedirs("data", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS invoices (
                    id TEXT PRIMARY KEY, client TEXT,
                    service TEXT, amount_rub REAL, amount_usd REAL,
                    created_at TEXT, due_date TEXT,
                    paid INTEGER, crypto_addr TEXT
                )
            """)
            conn.commit()

    def create_invoice(self, client: str, service: str,
                       amount_rub: float,
                       accept_crypto: bool = True) -> Invoice:
        """Создаёт счёт клиенту."""
        usd_rate = 90.0
        invoice_id = f"INV-{datetime.now().strftime('%Y%m%d')}-{random.randint(100,999)}"
        due = (datetime.now().replace(hour=0, minute=0)).strftime("%d.%m.%Y")

        crypto_addr = ""
        if accept_crypto:
            payment = self._wallet.get_payment_address(
                "TON", amount_rub / usd_rate / 5.5, invoice_id)
            crypto_addr = payment["address"]

        inv = Invoice(
            invoice_id  = invoice_id,
            client      = client,
            service     = service,
            amount_rub  = amount_rub,
            amount_usd  = round(amount_rub / usd_rate, 2),
            created_at  = datetime.now().strftime("%d.%m.%Y"),
            due_date    = due,
            crypto_addr = crypto_addr,
        )
        self._invoices[invoice_id] = inv

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO invoices VALUES (?,?,?,?,?,?,?,?,?)",
                (inv.invoice_id, inv.client, inv.service,
                 inv.amount_rub, inv.amount_usd,
                 inv.created_at, inv.due_date,
                 int(inv.paid), inv.crypto_addr)
            )
            conn.commit()

        log.info("Invoice created: %s — %s ₽%s",
                 invoice_id, amount_rub, client)
        return inv

    def format_invoice(self, inv: Invoice) -> str:
        """Форматирует счёт для отправки клиенту."""
        ton_amount = round(inv.amount_usd / 5.5, 2)
        lines = [
            "━" * 40,
            f"📋 СЧЁТ № {inv.invoice_id}",
            "━" * 40,
            f"📅 Дата:    {inv.created_at}",
            f"👤 Клиент:  {inv.client}",
            f"🔧 Услуга:  {inv.service}",
            "─" * 40,
            f"💰 Сумма:   ₽{inv.amount_rub:.0f}",
            f"           ${inv.amount_usd:.2f} USD",
            f"           {ton_amount} TON",
            "─" * 40,
            "💳 Способы оплаты:",
            "  • Банковский перевод",
            "  • СБП / Тинькофф",
        ]
        if inv.crypto_addr:
            lines.append(f"  • TON: {inv.crypto_addr[:20]}...")
        lines += [
            "─" * 40,
            f"⏰ Оплатить до: {inv.due_date}",
            "━" * 40,
        ]
        return "\n".join(lines)

    def mark_paid(self, invoice_id: str) -> str:
        inv = self._invoices.get(invoice_id)
        if not inv:
            return f"❌ Счёт {invoice_id} не найден"
        inv.paid = True
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE invoices SET paid=1 WHERE id=?", (invoice_id,))
            conn.commit()
        return f"✅ Счёт {invoice_id} отмечен как оплаченный"

    def summary(self) -> str:
        total = sum(i.amount_rub for i in self._invoices.values())
        paid  = sum(i.amount_rub for i in self._invoices.values() if i.paid)
        unpaid = total - paid
        lines = [
            "📊 БИЛЛИНГ:",
            f"  Счетов выставлено: {len(self._invoices)}",
            f"  Оплачено:          ₽{paid:.0f}",
            f"  Ожидает оплаты:    ₽{unpaid:.0f}",
        ]
        for inv in list(self._invoices.values())[-5:]:
            status = "✅" if inv.paid else "⏳"
            lines.append(f"  {status} {inv.invoice_id} — {inv.client} ₽{inv.amount_rub:.0f}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# 6. ПАРТНЁРСКИЕ ПРОГРАММЫ
# ══════════════════════════════════════════════════════════════

class AffiliateEngine:
    """
    Поиск и мониторинг партнёрских программ.
    Автоматический поиск релевантных офферов.
    """

    OFFERS = [
        AffiliateOffer(
            program     = "Timeweb Cloud",
            description = "VPS/облако для разработчиков. 20% с каждой оплаты рефералов.",
            commission  = "20% рекуррентно",
            payout      = "от 500 ₽",
            url         = "https://timeweb.cloud/affiliate",
            category    = "хостинг",
            suitable    = 0.9,
        ),
        AffiliateOffer(
            program     = "Beget Хостинг",
            description = "Хостинг и домены. 25% от платежей привлечённых клиентов.",
            commission  = "25% рекуррентно",
            payout      = "от 300 ₽",
            url         = "https://beget.com/p/affiliate",
            category    = "хостинг",
            suitable    = 0.85,
        ),
        AffiliateOffer(
            program     = "eSputnik",
            description = "Email маркетинг. 20% от платежей рефералов.",
            commission  = "20%",
            payout      = "от $50",
            url         = "https://esputnik.com/affiliate",
            category    = "маркетинг",
            suitable    = 0.6,
        ),
        AffiliateOffer(
            program     = "GitHub Sponsors",
            description = "Прямая поддержка от пользователей GitHub. Для open-source.",
            commission  = "100% (минус комиссия)",
            payout      = "$5+ в месяц",
            url         = "https://github.com/sponsors",
            category    = "donations",
            suitable    = 0.95,
        ),
        AffiliateOffer(
            program     = "Tinkoff партнёр",
            description = "За каждого привлечённого клиента — вознаграждение.",
            commission  = "500-3000 ₽ за клиента",
            payout      = "от 500 ₽",
            url         = "https://www.tinkoff.ru/banks/tinkoff/affiliate/",
            category    = "финансы",
            suitable    = 0.7,
        ),
        AffiliateOffer(
            program     = "Admitad (CPA сеть)",
            description = "Тысячи офферов: интернет-магазины, сервисы, игры.",
            commission  = "1-30% в зависимости от оффера",
            payout      = "от 1000 ₽",
            url         = "https://admitad.com",
            category    = "CPA",
            suitable    = 0.75,
        ),
    ]

    def __init__(self):
        self._active: List[AffiliateOffer] = []
        self._earnings: Dict[str, float] = {}
        log.info("AffiliateEngine init")

    def get_top_offers(self, limit: int = 5) -> List[AffiliateOffer]:
        return sorted(self.OFFERS, key=lambda x: x.suitable, reverse=True)[:limit]

    def format_offers(self) -> str:
        top = self.get_top_offers()
        lines = ["🤝 ПАРТНЁРСКИЕ ПРОГРАММЫ:"]
        for i, o in enumerate(top, 1):
            lines.append(
                f"\n  {i}. {o.program}\n"
                f"     💰 {o.commission} | 💳 Выплата: {o.payout}\n"
                f"     📝 {o.description[:60]}\n"
                f"     🔗 {o.url}"
            )
        return "\n".join(lines)

    def estimate_monthly(self) -> str:
        top = self.get_top_offers(3)
        lines = ["📈 ПРОГНОЗ ПАРТНЁРСКОГО ДОХОДА:"]
        total = 0.0
        for o in top:
            est = random.uniform(200, 2000)
            total += est
            lines.append(f"  {o.program}: ~₽{est:.0f}/мес")
        lines.append(f"\n  Итого потенциал: ~₽{total:.0f}/мес")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# ГЛАВНЫЙ МЕНЕДЖЕР v2
# ══════════════════════════════════════════════════════════════

class ArgosLifeSupportV2:
    """
    Расширенный модуль жизнеобеспечения.
    Подключается к базовому ArgosLifeSupport.
    """

    def __init__(self, core=None, base_life_support=None):
        self.core      = core
        self.base      = base_life_support

        # Инициализация всех подмодулей
        self.freelance = FreelanceHunter(core)
        self.crypto    = CryptoWallet()
        self.content   = ContentGenerator(core)
        self.jobs      = JobScanner(core)
        self.billing   = BillingSystem(self.crypto)
        self.affiliate = AffiliateEngine()

        if core:
            core.life_v2 = self

        log.info("ArgosLifeSupportV2 ✅")

    def full_status(self) -> str:
        """Полный финансовый статус v2."""
        bal = self.crypto.get_balance()
        lines = [
            "═" * 52,
            "  💰 АРГОС — ЖИЗНЕОБЕСПЕЧЕНИЕ v2",
            "═" * 52,
            "",
            self.crypto.status(),
            "",
            self.billing.summary(),
            "",
            f"🔍 Фриланс заказов в базе: {len(self.freelance._orders)}",
            f"💼 Вакансий в базе: {len(self.jobs._jobs)}",
            f"🤝 Партнёрских программ: {len(self.affiliate.OFFERS)}",
            "═" * 52,
        ]
        return "\n".join(lines)

    def handle_command(self, cmd: str) -> str:
        cmd_s = cmd.strip()
        low   = cmd_s.lower()

        # ── Фриланс ───────────────────────────────────────────
        if low in ("фриланс", "заказы", "freelance"):
            return self.freelance.format_orders()

        elif low == "фриланс сканировать":
            self.freelance.scan()
            return self.freelance.format_orders()

        elif low.startswith("отклик ") and "вакансия" not in low:
            try:
                num = int(low.split()[-1]) - 1
                orders = self.freelance._orders or self.freelance.scan()
                if 0 <= num < len(orders):
                    return self.freelance.generate_response(orders[num])
            except ValueError:
                pass
            return "❌ Укажи номер заказа"

        # ── Крипто ────────────────────────────────────────────
        elif low in ("крипто", "баланс", "кошелёк", "wallet"):
            return self.crypto.status()

        elif low.startswith("адрес оплаты"):
            parts = low.split()
            currency = parts[2].upper() if len(parts) > 2 else "TON"
            amount   = float(parts[3]) if len(parts) > 3 else 0.0
            info = self.crypto.get_payment_address(currency, amount)
            return (
                f"💎 Адрес для оплаты ({currency}):\n"
                f"  {info['address']}\n"
                f"  Сумма: {amount} {currency}\n"
                f"  Комментарий: {info['comment']}"
            )

        elif low == "проверить транзакции":
            txs = self.crypto.check_incoming()
            if not txs:
                return "📭 Новых транзакций нет"
            lines = [f"📥 Входящие транзакции ({len(txs)}):"]
            for tx in txs:
                lines.append(f"  +{tx['amount']} {tx['currency']} от {tx['from'][:20]}")
            return "\n".join(lines)

        # ── Контент ───────────────────────────────────────────
        elif low in ("контент план", "content plan"):
            return self.content.generate_content_plan(7)

        elif low.startswith("написать пост"):
            topic = cmd_s[13:].strip() or ""
            return self.content.generate_post(topic, "telegram_post")

        elif low.startswith("написать статью"):
            topic = cmd_s[15:].strip() or ""
            return self.content.generate_post(topic, "habr_article")

        elif low == "темы для постов":
            ideas = self.content.get_topic_ideas()
            return "💡 ИДЕИ ДЛЯ ПОСТОВ:\n" + "\n".join(f"  {i+1}. {idea}" for i, idea in enumerate(ideas))

        # ── Вакансии ──────────────────────────────────────────
        elif low in ("вакансии", "работа", "jobs"):
            return self.jobs.format_jobs()

        elif low.startswith("отклик вакансия "):
            try:
                num = int(low.split()[-1]) - 1
                jobs = self.jobs._jobs or self.jobs.scan()
                if 0 <= num < len(jobs):
                    letter = self.jobs.generate_cover_letter(jobs[num])
                    return f"📝 СОПРОВОДИТЕЛЬНОЕ ПИСЬМО:\n\n{letter}"
            except ValueError:
                pass
            return "❌ Укажи номер вакансии"

        # ── Биллинг ───────────────────────────────────────────
        elif low in ("счета", "биллинг", "billing"):
            return self.billing.summary()

        elif low.startswith("счёт ") or low.startswith("счет "):
            parts = cmd_s[5:].split("|")
            if len(parts) >= 3:
                client  = parts[0].strip()
                service = parts[1].strip()
                try:
                    amount  = float(parts[2].strip())
                except ValueError:
                    return "❌ Сумма должна быть числом"
                inv = self.billing.create_invoice(client, service, amount)
                return self.billing.format_invoice(inv)
            return "Формат: счёт Клиент|Услуга|Сумма"

        elif low.startswith("оплачен "):
            inv_id = cmd_s[8:].strip()
            return self.billing.mark_paid(inv_id)

        # ── Партнёрки ─────────────────────────────────────────
        elif low in ("партнёрки", "партнерки", "affiliate"):
            return self.affiliate.format_offers()

        elif low == "партнёрки прогноз":
            return self.affiliate.estimate_monthly()

        # ── Общий статус ──────────────────────────────────────
        elif low in ("v2 статус", "life v2"):
            return self.full_status()

        return self._help()

    def _help(self) -> str:
        return (
            "💰 ЖИЗНЕОБЕСПЕЧЕНИЕ v2:\n"
            "  фриланс            — найденные заказы\n"
            "  фриланс сканировать — обновить поиск\n"
            "  отклик <N>         — отклик на заказ\n"
            "  крипто             — баланс кошелька\n"
            "  адрес оплаты TON <сумма>\n"
            "  проверить транзакции\n"
            "  контент план       — план на 7 дней\n"
            "  написать пост <тема>\n"
            "  написать статью <тема>\n"
            "  темы для постов\n"
            "  вакансии           — найденные вакансии\n"
            "  отклик вакансия <N>\n"
            "  счёт Клиент|Услуга|Сумма\n"
            "  оплачен <INV-ID>\n"
            "  партнёрки          — программы\n"
            "  партнёрки прогноз\n"
            "  v2 статус          — полный отчёт"
        )

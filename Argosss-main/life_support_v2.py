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
        """
        Serialize the FreelanceOrder into a compact dictionary suitable for display.
        
        The resulting dictionary contains a shortened, presentation-ready view of the order:
        - "platform": source platform name.
        - "title": order title truncated to 60 characters.
        - "budget": original budget string.
        - "suitable": suitability expressed as a percentage string (e.g., "75%").
        - "url": link to the order.
        - "responded": status indicator — "✅" if a response was sent, "⏳" otherwise.
        
        Returns:
            dict: A dictionary with the keys "platform", "title", "budget", "suitable", "url", and "responded" as described above.
        """
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
        """
        Serialize the invoice into a compact dictionary suitable for display or persistence.
        
        Returns:
            dict: Mapping with keys:
                - "id": invoice identifier.
                - "client": client name.
                - "service": billed service description.
                - "amount": human-readable amount combining RUB and USD (e.g. "₽1000 / $13.37").
                - "due": due date string.
                - "status": payment status text — "✅ Оплачен" if paid, "⏳ Ожидает" otherwise.
        """
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
        """
        Initialize the FreelanceHunter, attaching an optional core and preparing internal state.
        
        Parameters:
            core: Optional reference to the central core (e.g., AI or application controller) used for assisted operations; may be None.
        
        Detailed behavior:
            - Initializes an empty cached orders list.
            - Sets the running flag to False.
            - Reads scan interval from the ARGOS_FREELANCE_INTERVAL environment variable (seconds), defaulting to 3600.
        """
        self.core = core
        self._orders: List[FreelanceOrder] = []
        self._running = False
        self._check_interval = int(os.getenv("ARGOS_FREELANCE_INTERVAL", "3600"))
        log.info("FreelanceHunter init")

    def scan(self, use_demo: bool = True) -> List[FreelanceOrder]:
        """
        Scan freelance platforms and return matching orders.
        
        When `use_demo` is True or the BeautifulSoup-based parsers are unavailable, uses built-in demo orders; otherwise attempts real parsing of supported sites. Results are filtered by a minimum suitability threshold and sorted by suitability descending.
        
        Parameters:
            use_demo (bool): If True, force using demo orders instead of live parsing.
        
        Returns:
            List[FreelanceOrder]: Matching orders sorted by suitability (highest first).
        """
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
        """
        Compute a suitability score for an order text against the agent's keywords.
        
        Returns:
            float: Suitability score between 0.3 and 1.0, where higher values indicate greater relevance to the agent's skills.
        """
        text_lower = text.lower()
        matches = sum(1 for kw in self.KEYWORDS if kw in text_lower)
        return min(1.0, matches * 0.2 + 0.3)

    def _parse_kwork(self) -> List[FreelanceOrder]:
        """
        Parse recent Kwork.ru project search results for Python/Telegram-related queries and build a list of FreelanceOrder objects.
        
        Performs HTTP requests to Kwork search pages for predefined queries and converts found listings into FreelanceOrder entries. Network or parsing failures are logged and result in an empty list.
        
        Returns:
            List[FreelanceOrder]: Parsed orders from Kwork; empty list if none or on error.
        """
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
        """
        Parse recent project listings from FL.ru and produce a list of FreelanceOrder entries.
        
        Attempts to retrieve and convert up to several current FL.ru project posts into FreelanceOrder objects; on network errors, parsing failures, or when parsing prerequisites are unavailable, returns an empty list.
        
        Returns:
            List[FreelanceOrder]: A list of parsed freelance orders (may be empty if none found or on error).
        """
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
        """
        Generate a tailored response message for a freelance order.
        
        The returned text contains a short header with the order title, budget and URL, a suggested reply chosen by the order's category (telegram, python, iot, or a default template), and an explicit confirmation prompt.
        
        Parameters:
            order (FreelanceOrder): The freelance order to generate a reply for.
        
        Returns:
            str: A formatted response string containing the order title, budget, URL, suggested reply text, and a confirmation prompt.
        """
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
        """
        Format cached freelance orders into a human-readable list.
        
        Parameters:
            limit (int): Maximum number of orders to include in the output.
        
        Returns:
            str: Formatted text containing up to `limit` freelance orders with platform, title, budget, suitability percentage, and URL; if no orders are available, a not-found message is returned.
        """
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
        """
        Initialize the CryptoWallet and configure addresses, API key, and internal state.
        
        Reads TON and USDT payment addresses and the TONCenter API key from environment variables and sets up internal caches:
        - _ton_address: TON wallet address (from ARGOS_TON_ADDRESS).
        - _usdt_address: USDT wallet address (from ARGOS_USDT_ADDRESS).
        - _api_key: TONCenter API key (from TONCENTER_API_KEY).
        - _balances: dict holding cached balances for 'TON', 'USDT', and 'BTC'.
        - _transactions: list caching recent incoming transaction records.
        - _last_check: timestamp of the last balance check.
        
        Logs whether a TON address was provided.
        """
        self._ton_address  = os.getenv("ARGOS_TON_ADDRESS", "")
        self._usdt_address = os.getenv("ARGOS_USDT_ADDRESS", "")
        self._api_key      = os.getenv("TONCENTER_API_KEY", "")
        self._balances     = {"TON": 0.0, "USDT": 0.0, "BTC": 0.0}
        self._transactions: List[dict] = []
        self._last_check   = 0.0
        log.info("CryptoWallet init | TON=%s", bool(self._ton_address))

    def get_balance(self, force: bool = False) -> dict:
        """
        Return current cached or freshly fetched wallet balances.
        
        If `force` is False and the last successful check was within 300 seconds, the cached balances are returned. When a TON address and API key are configured the method attempts to query TONCenter for the TON balance; if those are not configured or the call fails, simulated balances for TON, USDT, and BTC are provided and cached.
        
        Parameters:
            force (bool): If True, bypass cached value and attempt to refresh balances.
        
        Returns:
            dict: Mapping of currency codes to numeric balances, e.g. {"TON": 1.234, "USDT": 12.34, "BTC": 0.001234}.
        """
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
        """
                            Create a payment address payload for the specified currency.
                            
                            Parameters:
                                currency (str): Currency code (e.g., "TON", "USDT"). Case-insensitive; defaults to "TON".
                                amount (float): Requested payment amount in the currency's main units (for TON, fractional TONs are allowed).
                                comment (str): Optional comment for the payment; if omitted a timestamped default comment is generated.
                            
                            Returns:
                                dict: A payload containing:
                                    - `currency` (str): Uppercased currency code.
                                    - `address` (str): Payment address (real or demo fallback).
                                    - `amount` (float): The requested amount as passed in.
                                    - `comment` (str): The payment comment actually used.
                                    - `qr_text` (str): A transfer URL suitable for QR encoding (TON scheme uses amount converted to nanos by multiplying amount by 1e9 and includes the `text` query parameter).
                            """
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
        """
        Check for incoming cryptocurrency transactions.
        
        When a TON address and API key are configured, queries the TONCenter API and returns parsed inbound transactions with positive value. If no TON address or API key is available, may occasionally return a single simulated incoming transaction.
        
        Returns:
            List[dict]: A list of transaction records. Each record contains:
                - "hash" (str): Short transaction identifier.
                - "from" (str): Sender address.
                - "amount" (float): Amount in TON.
                - "currency" (str): Currency code (e.g., "TON").
                - "comment" (str): Attached message or comment.
                - "time" (str): Human-readable timestamp in "YYYY-MM-DD HH:MM" format.
        """
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
        """
        Compute the total wallet balance converted to US dollars using fixed exchange rates.
        
        Returns:
            float: Total balance in USD computed by converting TON, USDT, and BTC balances with fixed rates (TON=5.5, USDT=1.0, BTC=65000.0).
        """
        prices = {"TON": 5.5, "USDT": 1.0, "BTC": 65000.0}
        bal = self.get_balance()
        return sum(bal.get(c, 0) * prices.get(c, 0) for c in bal)

    def status(self) -> str:
        """
        Builds a human-readable multiline status summary for the crypto wallet.
        
        The summary includes TON/USDT/BTC balances, an approximate total in USD, the (truncated) TON address when set, and a short list of up to three recent incoming transactions with amount, currency, and comment excerpt.
        
        Returns:
            status (str): Formatted multiline status text ready for display.
        """
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
        """
        Initialize the ContentGenerator and prepare internal state.
        
        Parameters:
            core (optional): Optional processing core used to generate content drafts; may be None.
        """
        self.core = core
        self._published: List[dict] = []
        log.info("ContentGenerator init")

    def generate_post(self, topic: str = "",
                      content_type: str = "telegram_post") -> str:
        """
                      Generate a draft post for a given topic and content type.
                      
                      If no topic is provided, a topic is chosen from predefined ideas. When an AI core is available, the method requests a generated draft tailored to the requested content_type; otherwise it returns a local template-based draft.
                      
                      Parameters:
                          topic (str): Topic or title for the post. If empty, a topic is selected automatically.
                          content_type (str): Target format, e.g., "telegram_post", "habr_article", or "vc_article", which influences prompt length and style.
                      
                      Returns:
                          str: The generated draft text.
                      """
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
        """
        Create a short templated draft for a social post on the given topic.
        
        Parameters:
        	topic (str): Headline or topic phrase to include at the top of the draft.
        
        Returns:
        	draft (str): A ready-to-edit post draft containing an emoji, the topic, a structured outline (what, why, how, example), a draft marker, and tags.
        """
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
        """
        Return topic ideas for content creation.
        
        If `category` matches a key in TOPIC_IDEAS, return that category's full list of ideas.
        If `category` is empty or not found, return up to five random ideas sampled from all categories.
        
        Parameters:
            category (str): Optional category name to filter ideas. If omitted or unknown, ideas are chosen across all categories.
        
        Returns:
            List[str]: A list of topic idea strings (either the full category list or up to five random ideas).
        """
        if category and category in self.TOPIC_IDEAS:
            return self.TOPIC_IDEAS[category]
        all_ideas = []
        for ideas in self.TOPIC_IDEAS.values():
            all_ideas.extend(ideas)
        return random.sample(all_ideas, min(5, len(all_ideas)))

    def generate_content_plan(self, days: int = 7) -> str:
        """
        Create a multi-day content plan with one topic and category assigned to each day.
        
        Parameters:
            days (int): Number of consecutive days to include in the plan.
        
        Returns:
            str: A formatted plain-text plan where each day lists the date, a suggested topic, and a category hashtag.
        """
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
        """
        Initialize the JobScanner with an optional core reference and prepare internal state.
        
        Sets the core reference and initializes internal lists for discovered jobs and responded job IDs.
        """
        self.core = core
        self._jobs: List[dict] = []
        self._responded: List[str] = []
        log.info("JobScanner init")

    def scan(self) -> List[dict]:
        """
        Load demo job postings into the scanner and return the loaded list.
        
        This replaces the scanner's internal job cache with the built-in demo jobs and logs the number of loaded vacancies.
        
        Returns:
            list[dict]: The list of job entries currently stored by the scanner (each entry is a dict with keys like 'source', 'title', 'company', 'salary', 'format', 'url', 'skills').
        """
        self._jobs = self.DEMO_JOBS.copy()
        log.info("JobScanner: %d вакансий", len(self._jobs))
        return self._jobs

    def generate_cover_letter(self, job: dict) -> str:
        """
        Generate a cover letter tailored to a job posting.
        
        Parameters:
            job (dict): Job metadata with expected keys:
                - title (str): Job title.
                - company (str): Company name.
                - skills (List[str]): List of relevant skills to include in the letter.
        
        Returns:
            str: A formatted cover letter mentioning the job title, company, listed skills, and a brief availability statement.
        """
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
        """
        Format the current job list into a numbered, human-readable text block for display.
        
        Returns:
            str: Multiline string with a header showing the total number of jobs, numbered entries containing title, company, salary, format and URL, and a trailing instruction `Команда: отклик вакансия <номер>`.
        """
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
        """
        Ensure the billing database file and the invoices table exist.
        
        Creates the data directory if missing and opens the SQLite database at self.db_path, creating an `invoices` table (columns: id, client, service, amount_rub, amount_usd, created_at, due_date, paid, crypto_addr) if it does not already exist.
        """
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
        """
                       Create and persist an invoice for a client.
                       
                       If `accept_crypto` is True, requests a crypto payment address from the configured wallet and attaches it to the invoice. The invoice is stored in-memory and saved to the SQLite database at self.db_path.
                       
                       Parameters:
                           client (str): Client name or identifier.
                           service (str): Description of the billed service.
                           amount_rub (float): Invoice total in Russian rubles.
                           accept_crypto (bool): If True, generate and attach a crypto payment address.
                       
                       Returns:
                           Invoice: The created Invoice object (also stored in self._invoices and persisted to the DB).
                       """
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
        """
        Render an invoice into a human-readable multiline text block suitable for sending to a client.
        
        Includes amounts in RUB and USD, an approximate TON equivalent, available payment methods (including a truncated TON address when present), and the invoice dates.
        
        Parameters:
            inv (Invoice): The invoice object to format.
        
        Returns:
            str: A formatted multiline string representing the invoice ready for sending.
        """
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
        """
        Mark an invoice as paid and persist the change in the billing database.
        
        If the invoice exists, its paid flag is set and the change is saved; otherwise the invoice is left unchanged.
        
        Returns:
            str: A confirmation message on success (`"✅ Счёт <id> отмечен как оплаченный"`) or an error message if the invoice was not found (`"❌ Счёт <id> не найден"`).
        """
        inv = self._invoices.get(invoice_id)
        if not inv:
            return f"❌ Счёт {invoice_id} не найден"
        inv.paid = True
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE invoices SET paid=1 WHERE id=?", (invoice_id,))
            conn.commit()
        return f"✅ Счёт {invoice_id} отмечен как оплаченный"

    def summary(self) -> str:
        """
        Builds a concise billing summary showing totals and recent invoices.
        
        Returns:
            str: Multiline text with total invoiced amount, paid and unpaid totals, the count of invoices, and up to five most-recent invoices each listed with a status icon, invoice ID, client and amount.
        """
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
        """
        Initialize the AffiliateEngine instance and prepare internal state.
        
        Creates an empty list for active affiliate offers and an empty earnings mapping, and records initialization in the logs.
        """
        self._active: List[AffiliateOffer] = []
        self._earnings: Dict[str, float] = {}
        log.info("AffiliateEngine init")

    def get_top_offers(self, limit: int = 5) -> List[AffiliateOffer]:
        """
        Retrieve the top affiliate offers ranked by suitability.
        
        Parameters:
            limit (int): Maximum number of offers to return (default 5).
        
        Returns:
            List[AffiliateOffer]: Offers sorted by descending `suitable` score, limited to `limit`.
        """
        return sorted(self.OFFERS, key=lambda x: x.suitable, reverse=True)[:limit]

    def format_offers(self) -> str:
        """
        Render the top affiliate offers as a human-readable, multiline message.
        
        Each listed offer includes program name, commission, payout, a short description preview, and a URL.
        
        Returns:
            formatted (str): Multiline string ready for display or sending containing the top affiliate offers.
        """
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
        """
        Generate a simulated monthly earnings forecast for the top affiliate offers.
        
        Produces a multiline text block listing an approximate monthly earning for each of the top 3 offers and a summed total. The per-offer and total amounts are randomly simulated and intended as illustrative estimates, not actual projections.
        
        Returns:
            str: Multiline string containing per-offer approximate earnings and the aggregated monthly potential.
        """
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
        """
        Initialize the ArgosLifeSupportV2 manager and instantiate its subsystem components.
        
        Parameters:
            core: Optional central application core object; if provided, this instance will be attached to core.life_v2.
            base_life_support: Optional reference to an existing base life-support instance for compatibility or delegation.
        
        Notes:
            - Creates and wires subsystems: FreelanceHunter, CryptoWallet, ContentGenerator, JobScanner, BillingSystem (connected to the CryptoWallet), and AffiliateEngine.
            - Attaches this manager to `core.life_v2` when `core` is supplied.
        """
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
        """
        Assemble a consolidated status report for Argos life-support v2.
        
        Includes current crypto wallet summary, billing overview, and counts of cached freelance orders, jobs, and affiliate offers.
        
        Returns:
            status (str): A multiline formatted string with the aggregated status report.
        """
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
        """
        Dispatches a user command to the appropriate life-support subsystem and returns a human-readable response.
        
        Supported command categories include freelance (scan/list/respond), crypto (status, payment address, check transactions), content (generate posts, articles, content plans, topic ideas), job/vacancy browsing and auto-responses, billing (list, create invoice, mark paid), affiliate offers and estimates, and overall v2 status. Unrecognized commands return the module help text.
        
        Parameters:
            cmd (str): The raw user command string (will be trimmed and lowercased for matching).
        
        Returns:
            str: A textual response produced by the targeted subsystem or a help message when the command is not recognized or invalid.
        """
        cmd_s = cmd.strip()
        low   = cmd_s.lower()

        # ── Фриланс ───────────────────────────────────────────
        if low in ("фриланс", "заказы", "freelance"):
            return self.freelance.format_orders()

        elif low == "фриланс сканировать":
            self.freelance.scan()
            return self.freelance.format_orders()

        elif low.startswith("отклик ") and not "вакансия" in low:
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
            parts = cmd_s[6:].split("|")
            if len(parts) >= 3:
                client  = parts[0].strip()
                service = parts[1].strip()
                amount  = float(parts[2].strip())
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
        """
        Provide the multi-line help text describing available ArgosLifeSupportV2 commands and their usage.
        
        Returns:
            help_text (str): A multi-line string (Russian) listing commands, brief descriptions, and example syntaxes for the v2 life-support interface.
        """
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

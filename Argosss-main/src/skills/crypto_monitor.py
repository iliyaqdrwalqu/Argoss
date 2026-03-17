"""
crypto_monitor.py — Крипто-Страж
  Мониторинг BTC/ETH каждый час, алерт в Telegram при изменении > 5%
"""
import requests
import time
import os
import threading
import asyncio

class CryptoSentinel:
    API_URL = "https://api.coingecko.com/api/v3/simple/price"
    COINS   = ["bitcoin", "ethereum"]
    SYMBOLS = {"bitcoin": "BTC", "ethereum": "ETH"}

    def __init__(self, telegram_bot=None):
        self.bot       = telegram_bot   # ArgosTelegram instance (опц.)
        self.prev      = {}
        self.threshold = 5.0            # % изменения для алерта
        self._running  = False

    def get_prices(self) -> dict:
        try:
            params = {"ids": ",".join(self.COINS), "vs_currencies": "usd", "include_24hr_change": "true"}
            r = requests.get(self.API_URL, params=params, timeout=8)
            data = r.json()
            return {
                coin: {
                    "price":  data[coin]["usd"],
                    "change": data[coin].get("usd_24h_change", 0.0),
                }
                for coin in self.COINS
            }
        except Exception as e:
            return {}

    def check(self) -> list[str]:
        """Возвращает список алертов (пустой если всё тихо)."""
        current = self.get_prices()
        alerts  = []

        for coin, info in current.items():
            change = info.get("change", 0.0)
            sym    = self.SYMBOLS[coin]
            price  = info["price"]

            if abs(change) >= self.threshold:
                direction = "📈 РОСТ" if change > 0 else "📉 ПАДЕНИЕ"
                alerts.append(
                    f"🪙 {sym} АЛЕРТ\n"
                    f"{direction}: {change:+.2f}%\n"
                    f"Цена: ${price:,.2f}"
                )
        self.prev = current
        return alerts

    def report(self) -> str:
        """Разовый отчёт по текущим ценам."""
        prices = self.get_prices()
        if not prices:
            return "❌ CoinGecko недоступен."
        lines = ["🪙 КРИПТО-РЫНОК:"]
        for coin, info in prices.items():
            sym = self.SYMBOLS[coin]
            lines.append(f"  {sym}: ${info['price']:,.2f}  ({info['change']:+.2f}% за 24ч)")
        return "\n".join(lines)

    def start_loop(self, interval_sec: int = 3600):
        """Фоновый мониторинг в отдельном потоке."""
        self._running = True

        def _notify_bot(msg: str):
            if not self.bot:
                return
            try:
                send = getattr(self.bot, "send", None)
                if callable(send):
                    send(msg)
                    return
                if getattr(self.bot, "app", None) and getattr(self.bot, "user_id", None):
                    coro = self.bot.app.bot.send_message(chat_id=self.bot.user_id, text=msg)
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        asyncio.run(coro)
                    else:
                        loop.call_soon_threadsafe(asyncio.create_task, coro)
            except Exception as e:
                print(f"[CRYPTO-SENTINEL] Ошибка отправки алерта: {e}")
                return

        def _loop():
            while self._running:
                alerts = self.check()
                for msg in alerts:
                    print(f"[CRYPTO-SENTINEL]: {msg}")
                    _notify_bot(msg)
                time.sleep(interval_sec)
        threading.Thread(target=_loop, daemon=True).start()
        return f"Крипто-Страж запущен. Интервал: {interval_sec//60} мин. Порог: {self.threshold}%"

    def stop(self):
        self._running = False
        return "Крипто-Страж остановлен."

"""
content_gen.py — Медиа-Архитектор
  Сбор AI-новостей + генерация поста + публикация в Telegram
"""
import requests
from bs4 import BeautifulSoup
import time
import threading
import os

class ContentGen:
    SOURCES = [
        {"name": "TechCrunch AI",  "url": "https://techcrunch.com/category/artificial-intelligence/"},
        {"name": "The Verge AI",   "url": "https://www.theverge.com/ai-artificial-intelligence"},
        {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/"},
    ]
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    def __init__(self):
        self._pending = []
        self._running = False
        self._tg_token  = os.getenv("TELEGRAM_BOT_TOKEN")
        self._tg_chatid = os.getenv("USER_ID")

    def fetch_headlines(self) -> list:
        headlines = []
        for source in self.SOURCES:
            try:
                r = requests.get(source["url"], headers=self.HEADERS, timeout=8)
                soup = BeautifulSoup(r.text, "html.parser")
                for tag in soup.find_all(["h2", "h3"], limit=5):
                    text = tag.get_text().strip()
                    if len(text) > 20:
                        headlines.append({"source": source["name"], "title": text})
            except Exception:
                continue
        return headlines[:9]

    def generate_digest(self) -> str:
        headlines = self.fetch_headlines()
        if not headlines:
            return "❌ Источники недоступны. Дайджест не сформирован."
        top3  = headlines[:3]
        date  = time.strftime("%d.%m.%Y")
        lines = [f"📰 AI-ДАЙДЖЕСТ от {date}", "━" * 22]
        for i, item in enumerate(top3, 1):
            lines.append(f"\n{i}. [{item['source']}]\n   {item['title']}")
        lines.append("\n━" * 22)
        lines.append("📡 Подготовлено Аргосом. Жду команды: опубликуй")
        post = "\n".join(lines)
        self._pending.append(post)
        return post

    def publish(self) -> str:
        """Публикует пост через Telegram Bot API."""
        if not self._pending:
            return "📭 Нет постов в очереди. Сначала: дайджест"
        post = self._pending.pop(0)

        if self._tg_token and self._tg_chatid and self._tg_token != "your_token_here":
            try:
                url  = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
                resp = requests.post(url, json={
                    "chat_id":    self._tg_chatid,
                    "text":       post,
                    "parse_mode": "Markdown",
                }, timeout=10)
                if resp.ok:
                    return f"✅ Пост опубликован в Telegram ({len(post)} символов)."
                else:
                    return f"⚠️ Telegram вернул ошибку: {resp.text[:200]}"
            except Exception as e:
                return f"❌ Ошибка публикации: {e}"
        else:
            print(f"[MEDIA-ARCHITECT]:\n{post}")
            return f"✅ Пост выведен в консоль ({len(post)} символов). Настрой TELEGRAM_BOT_TOKEN для публикации."

    def start_morning_loop(self, hour: int = 9):
        self._running = True
        def _loop():
            while self._running:
                if int(time.strftime("%H")) == hour:
                    self.generate_digest()
                    self.publish()
                    time.sleep(3600)
                time.sleep(60)
        threading.Thread(target=_loop, daemon=True).start()
        return f"Медиа-Архитектор активен. Дайджест в {hour:02d}:00 ежедневно."

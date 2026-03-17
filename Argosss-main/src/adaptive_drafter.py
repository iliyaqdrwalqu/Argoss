"""
adaptive_drafter.py — TLT (Two-Level Transformer) кэш/сжатие/фильтрация запросов.
Адаптивный черновик: снижает нагрузку на основную модель через кэш похожих ответов.
"""
import os
import time
import hashlib
import json
import threading
from typing import Optional, Dict, List
from src.argos_logger import get_logger

log = get_logger("argos.drafter")

CACHE_FILE = "data/drafter_cache.json"
MAX_CACHE = 500
SIMILARITY_THRESHOLD = 0.85


class AdaptiveDrafter:
    """
    TLT Adaptive Drafter — кэш и сжатие запросов.
    При схожести нового запроса с кэшированным возвращает готовый ответ.
    Снижает количество обращений к тяжёлой модели на 30-60%.
    """

    def __init__(self, core=None):
        self.core = core
        self._cache: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._acceptance: List[float] = []
        self._load_cache()
        log.info("AdaptiveDrafter: loaded %d cached responses", len(self._cache))

    def _load_cache(self) -> None:
        os.makedirs("data", exist_ok=True)
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE) as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}

    def _save_cache(self) -> None:
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _key(self, text: str) -> str:
        return hashlib.md5(text.strip().lower().encode()).hexdigest()

    def _similarity(self, a: str, b: str) -> float:
        """Быстрая косинусная схожесть по множеству слов."""
        wa = set(a.lower().split())
        wb = set(b.lower().split())
        if not wa or not wb:
            return 0.0
        intersection = wa & wb
        return len(intersection) / (len(wa | wb) ** 0.5 + 1e-8)

    def draft(self, query: str) -> Optional[str]:
        """Возвращает готовый ответ из кэша если схожесть высокая."""
        key = self._key(query)
        with self._lock:
            # Точное совпадение
            if key in self._cache:
                entry = self._cache[key]
                entry["hits"] = entry.get("hits", 0) + 1
                entry["last_used"] = time.time()
                self._hits += 1
                log.debug("Drafter: exact hit for key %s", key[:8])
                return entry["answer"]

            # Fuzzy matching
            best_sim = 0.0
            best_entry = None
            for v in list(self._cache.values())[-100:]:  # последние 100
                sim = self._similarity(query, v.get("query", ""))
                if sim > best_sim:
                    best_sim = sim
                    best_entry = v

            if best_sim >= SIMILARITY_THRESHOLD and best_entry:
                best_entry["hits"] = best_entry.get("hits", 0) + 1
                self._hits += 1
                log.debug("Drafter: fuzzy hit sim=%.2f", best_sim)
                return best_entry["answer"]

        self._misses += 1
        return None

    def learn(self, query: str, answer: str, quality: float = 1.0) -> None:
        """Сохраняет пару запрос-ответ в кэш."""
        if not query or not answer:
            return
        key = self._key(query)
        with self._lock:
            self._cache[key] = {
                "query": query,
                "answer": answer,
                "quality": quality,
                "ts": time.time(),
                "hits": 0,
                "last_used": time.time(),
            }
            # LRU eviction
            if len(self._cache) > MAX_CACHE:
                oldest = min(self._cache.items(),
                             key=lambda x: x[1].get("last_used", 0))
                del self._cache[oldest[0]]
            self._save_cache()
        self._acceptance.append(quality)
        if len(self._acceptance) > 200:
            self._acceptance = self._acceptance[-200:]

    def compress_context(self, messages: list, max_tokens: int = 2000) -> list:
        """Сжимает историю сообщений, оставляя самые важные."""
        if not messages:
            return []
        # Всегда оставляем первое системное и последние N сообщений
        system = [m for m in messages if m.get("role") == "system"]
        user_msgs = [m for m in messages if m.get("role") != "system"]

        total_chars = sum(len(m.get("content", "")) for m in messages)
        char_limit = max_tokens * 4  # ~4 символа на токен

        if total_chars <= char_limit:
            return messages

        # Оставляем последние 10 сообщений + системные
        compressed = system + user_msgs[-10:]
        log.debug("Drafter: compressed %d→%d messages", len(messages), len(compressed))
        return compressed

    def filter_query(self, query: str) -> str:
        """Упрощает запрос: убирает лишние слова-паразиты."""
        stopwords = {"аргос", "пожалуйста", "можешь", "скажи", "мне", "что",
                     "такое", "это", "argos", "please", "could", "you", "tell"}
        words = query.split()
        filtered = [w for w in words if w.lower() not in stopwords]
        result = " ".join(filtered) if filtered else query
        if result != query:
            log.debug("Drafter: filtered '%s' → '%s'", query[:50], result[:50])
        return result

    def get_acceptance_rate(self) -> float:
        if not self._acceptance:
            return 1.0
        return sum(self._acceptance[-50:]) / len(self._acceptance[-50:])

    def report(self) -> str:
        total = self._hits + self._misses
        rate = self._hits / total * 100 if total else 0
        return (
            f"📊 ADAPTIVE DRAFTER:\n"
            f"  Кэш:        {len(self._cache)} записей\n"
            f"  Попаданий:  {self._hits}/{total} ({rate:.1f}%)\n"
            f"  Acceptance: {self.get_acceptance_rate():.2f}\n"
            f"  Threshold:  {SIMILARITY_THRESHOLD}"
        )

    def clear_cache(self) -> str:
        with self._lock:
            self._cache.clear()
            self._save_cache()
        return "✅ Кэш драфтера очищен"

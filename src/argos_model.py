"""
argos_model.py — Собственная модель Аргоса
  Создаёт, обучает, сохраняет и использует локальную нейросеть
  на основе накопленных диалогов из SQLite-памяти.

  Архитектура:
    - Эмбеддинг слой (TF-IDF / sentence-transformers)
    - Классификатор намерений (sklearn / torch)
    - Файн-тюнинг на диалогах из памяти
    - Экспорт в ONNX для использования без зависимостей

  Команды:
    модель статус
    модель обучить
    модель сохранить
    модель загрузить
    модель спросить [вопрос]
    модель экспорт
    модель версия
"""

from __future__ import annotations

import os
import json
import time
import pickle
import hashlib
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

import logging

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

log = get_logger("argos.model")

# Директории
MODEL_DIR = Path("data/argos_model")
MODEL_FILE = MODEL_DIR / "argos_intent_model.pkl"
VECTORIZER_FILE = MODEL_DIR / "argos_vectorizer.pkl"
META_FILE = MODEL_DIR / "model_meta.json"
TRAINING_LOG = MODEL_DIR / "training_history.jsonl"


# ── ПОПЫТКА ИМПОРТА ML-БИБЛИОТЕК ─────────────────────────
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False
    log.warning("sklearn не установлен: pip install scikit-learn")

try:
    import numpy as np
    NUMPY_OK = True
except ImportError:
    NUMPY_OK = False


class ArgosModelMeta:
    """Метаданные модели — версия, дата, точность."""

    def __init__(self):
        self.version = "0.0.0"
        self.trained_at = None
        self.accuracy = 0.0
        self.samples = 0
        self.classes = []
        self.git_hash = ""

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "trained_at": self.trained_at,
            "accuracy": self.accuracy,
            "samples": self.samples,
            "classes": self.classes,
            "git_hash": self.git_hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ArgosModelMeta":
        m = cls()
        m.version = d.get("version", "0.0.0")
        m.trained_at = d.get("trained_at")
        m.accuracy = d.get("accuracy", 0.0)
        m.samples = d.get("samples", 0)
        m.classes = d.get("classes", [])
        m.git_hash = d.get("git_hash", "")
        return m


class ArgosOwnModel:
    """
    Собственная ML-модель Аргоса.
    Обучается на диалогах из памяти SQLite.
    Может отвечать на вопросы автономно, без внешнего API.
    """

    def __init__(self, core=None):
        self.core = core
        self._pipeline: Optional[object] = None
        self._meta = ArgosModelMeta()
        self._lock = threading.Lock()
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self._load_if_exists()

    # ── ЗАГРУЗКА / СОХРАНЕНИЕ ─────────────────────────────

    def _load_if_exists(self):
        """Загружает модель при старте если она уже существует."""
        if MODEL_FILE.exists() and META_FILE.exists():
            try:
                with open(MODEL_FILE, "rb") as f:
                    self._pipeline = pickle.load(f)
                with open(META_FILE, "r", encoding="utf-8") as f:
                    self._meta = ArgosModelMeta.from_dict(json.load(f))
                log.info(
                    "Собственная модель загружена: v%s, точность=%.2f%%, образцов=%d",
                    self._meta.version, self._meta.accuracy * 100, self._meta.samples
                )
            except Exception as e:
                log.warning("Не удалось загрузить модель: %s", e)
                self._pipeline = None

    def save(self) -> str:
        """Сохраняет модель и метаданные на диск."""
        if self._pipeline is None:
            return "❌ Нет обученной модели для сохранения."
        try:
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            with open(MODEL_FILE, "wb") as f:
                pickle.dump(self._pipeline, f)
            with open(META_FILE, "w", encoding="utf-8") as f:
                json.dump(self._meta.to_dict(), f, ensure_ascii=False, indent=2)
            size_kb = MODEL_FILE.stat().st_size // 1024
            log.info("Модель сохранена: %s (%d KB)", MODEL_FILE, size_kb)
            return (
                f"💾 Модель сохранена:\n"
                f"  Файл: {MODEL_FILE}\n"
                f"  Размер: {size_kb} KB\n"
                f"  Версия: {self._meta.version}\n"
                f"  Точность: {self._meta.accuracy * 100:.1f}%"
            )
        except Exception as e:
            return f"❌ Ошибка сохранения модели: {e}"

    # ── СБОР ДАННЫХ ───────────────────────────────────────

    def _collect_training_data(self) -> tuple[list[str], list[str]]:
        """
        Собирает обучающие данные из SQLite-памяти Аргоса.
        Использует историю диалогов: вопрос → категория намерения.
        """
        texts, labels = [], []

        # 1. Встроенный базовый датасет (работает без памяти)
        builtin = {
            "system": [
                "статус системы", "чек-ап", "список процессов", "сколько памяти",
                "загрузка cpu", "температура", "статус дисков", "здоровье системы",
                "мониторинг", "отчёт системы", "использование ram",
            ],
            "file": [
                "покажи файлы", "список файлов", "прочитай файл", "создай файл",
                "удали файл", "найди файл", "открой директорию", "скопируй файл",
                "переименуй", "размер файла", "содержимое папки",
            ],
            "network": [
                "сканируй сеть", "статус сети", "мой ip", "ping", "открытые порты",
                "сетевые подключения", "интернет работает", "скорость интернета",
                "arp таблица", "маршруты", "dns запрос",
            ],
            "ai": [
                "привет", "как дела", "что ты умеешь", "помоги мне", "объясни",
                "расскажи про", "что такое", "кто такой", "как работает",
                "переведи", "напиши текст", "сгенерируй", "придумай",
            ],
            "memory": [
                "запомни", "что ты знаешь", "найди в памяти", "граф знаний",
                "забудь", "мои заметки", "история диалогов", "запиши факт",
                "что я говорил", "предыдущий разговор",
            ],
            "iot": [
                "iot статус", "умный дом", "включи свет", "выключи", "температура датчик",
                "zigbee", "mqtt", "умная система", "добавь устройство", "статус устройств",
            ],
            "build": [
                "собрать апк", "build apk", "собери exe", "компиляция",
                "сборка проекта", "deploy", "выпусти версию", "сборка docker",
            ],
            "git": [
                "git статус", "git коммит", "git пуш", "создай ветку",
                "merge", "pull request", "история коммитов", "отмени коммит",
            ],
        }

        for label, examples in builtin.items():
            for ex in examples:
                texts.append(ex)
                labels.append(label)

        # 2. Данные из SQLite-памяти Аргоса
        if self.core and hasattr(self.core, "db") and self.core.db:
            try:
                history = self.core.db.get_chat_history(limit=500)
                for row in history:
                    role = row.get("role", "")
                    text = row.get("text", "") or ""
                    category = row.get("category", "") or "ai"
                    if role == "user" and len(text) > 3:
                        texts.append(text)
                        labels.append(category if category in builtin else "ai")
                log.info("Загружено %d образцов из SQLite", len(history))
            except Exception as e:
                log.warning("Не удалось загрузить историю из SQLite: %s", e)

        # 3. Данные из файлов навыков (названия → категории)
        skills_dir = Path("src/skills")
        if skills_dir.exists():
            for skill_file in skills_dir.glob("*.py"):
                name = skill_file.stem.replace("_", " ")
                texts.append(f"запусти навык {name}")
                labels.append("skill")

        log.info("Итого обучающих образцов: %d", len(texts))
        return texts, labels

    # ── ОБУЧЕНИЕ ──────────────────────────────────────────

    def train(self) -> str:
        """
        Обучает модель на собранных данных.
        Возвращает отчёт с точностью.
        """
        if not SKLEARN_OK:
            return (
                "❌ Для обучения модели нужен scikit-learn:\n"
                "  pip install scikit-learn numpy"
            )

        log.info("Начинаю обучение собственной модели...")
        start = time.time()

        texts, labels = self._collect_training_data()
        if len(texts) < 10:
            return f"❌ Недостаточно данных для обучения: {len(texts)} образцов (нужно минимум 10)."

        # Разбивка на train/test
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                texts, labels, test_size=0.2, random_state=42, stratify=labels
            )
        except ValueError:
            # Если классов слишком мало для stratify
            X_train, X_test, y_train, y_test = train_test_split(
                texts, labels, test_size=0.2, random_state=42
            )

        # Построение pipeline: TF-IDF + LogisticRegression
        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=5000,
                analyzer="word",
                sublinear_tf=True,
            )),
            ("clf", LogisticRegression(
                max_iter=1000,
                C=5.0,
                solver="lbfgs",
                multi_class="auto",
            )),
        ])

        with self._lock:
            pipeline.fit(X_train, y_train)
            accuracy = pipeline.score(X_test, y_test)
            self._pipeline = pipeline

        elapsed = time.time() - start

        # Автоверсия на основе точности и хэша данных
        data_hash = hashlib.md5("|".join(sorted(set(texts))).encode()).hexdigest()[:8]
        version_major = int(accuracy * 10)
        self._meta.version = f"1.{version_major}.0+{data_hash}"
        self._meta.trained_at = datetime.now().isoformat()
        self._meta.accuracy = accuracy
        self._meta.samples = len(texts)
        self._meta.classes = sorted(set(labels))

        # Логируем в history
        try:
            with open(TRAINING_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(self._meta.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

        report = ""
        try:
            y_pred = pipeline.predict(X_test)
            report = classification_report(y_test, y_pred, zero_division=0)
        except Exception:
            pass

        result = (
            f"🧠 МОДЕЛЬ ОБУЧЕНА:\n"
            f"  Версия:   {self._meta.version}\n"
            f"  Образцов: {len(texts)} (train={len(X_train)}, test={len(X_test)})\n"
            f"  Классов:  {len(self._meta.classes)} → {', '.join(self._meta.classes)}\n"
            f"  Точность: {accuracy * 100:.1f}%\n"
            f"  Время:    {elapsed:.1f}с\n"
        )
        if report:
            result += f"\n📊 Отчёт:\n{report}"

        # Автосохранение
        self.save()
        return result

    # ── ИНФЕРЕНС ──────────────────────────────────────────

    def predict(self, text: str) -> dict:
        """
        Предсказывает намерение по тексту.
        Возвращает: {'intent': str, 'confidence': float, 'source': str}
        """
        if self._pipeline is None:
            return {"intent": "unknown", "confidence": 0.0, "source": "no_model"}
        try:
            with self._lock:
                intent = self._pipeline.predict([text])[0]
                proba = self._pipeline.predict_proba([text])[0]
                confidence = float(max(proba))
            return {
                "intent": intent,
                "confidence": confidence,
                "source": f"argos_model_v{self._meta.version}",
            }
        except Exception as e:
            log.error("predict error: %s", e)
            return {"intent": "unknown", "confidence": 0.0, "source": "error"}

    def ask(self, text: str) -> str:
        """Отвечает на вопрос используя собственную модель."""
        if self._pipeline is None:
            return "❌ Модель не обучена. Выполни: модель обучить"

        result = self.predict(text)
        intent = result["intent"]
        conf = result["confidence"]

        # Маршрутизация на ядро Аргоса
        if self.core and conf > 0.5:
            try:
                routed = self.core.process(f"[model_routed:{intent}] {text}")
                if routed and routed.get("answer"):
                    return (
                        f"🤖 [Модель v{self._meta.version}] Намерение: {intent} ({conf*100:.0f}%)\n"
                        f"{routed['answer']}"
                    )
            except Exception:
                pass

        return (
            f"🤖 [Модель v{self._meta.version}]\n"
            f"Намерение: {intent}\n"
            f"Уверенность: {conf*100:.0f}%\n"
            f"(Для полного ответа нужен Gemini API или Ollama)"
        )

    # ── СТАТУС / ВЕРСИЯ ───────────────────────────────────

    def status(self) -> str:
        if self._pipeline is None:
            return (
                "🤖 Собственная модель: НЕ ОБУЧЕНА\n"
                "  Запусти: модель обучить"
            )
        return (
            f"🤖 СОБСТВЕННАЯ МОДЕЛЬ АРГОСА:\n"
            f"  Версия:    {self._meta.version}\n"
            f"  Обучена:   {self._meta.trained_at}\n"
            f"  Точность:  {self._meta.accuracy * 100:.1f}%\n"
            f"  Образцов:  {self._meta.samples}\n"
            f"  Классов:   {len(self._meta.classes)}\n"
            f"  Классы:    {', '.join(self._meta.classes)}\n"
            f"  Файл:      {MODEL_FILE}\n"
            f"  Размер:    {MODEL_FILE.stat().st_size // 1024 if MODEL_FILE.exists() else 0} KB"
        )

    def version(self) -> str:
        return f"🤖 Модель Аргоса v{self._meta.version} (точность {self._meta.accuracy*100:.1f}%)"

    def history(self) -> str:
        """История всех обучений."""
        if not TRAINING_LOG.exists():
            return "📜 История обучений пуста."
        lines = ["📜 ИСТОРИЯ ОБУЧЕНИЙ:"]
        try:
            with open(TRAINING_LOG, "r", encoding="utf-8") as f:
                for i, line in enumerate(f.readlines()[-10:], 1):
                    m = json.loads(line)
                    lines.append(
                        f"  {i}. v{m['version']} | "
                        f"{m['trained_at'][:16]} | "
                        f"точность={m['accuracy']*100:.1f}% | "
                        f"образцов={m['samples']}"
                    )
        except Exception as e:
            return f"❌ Ошибка чтения истории: {e}"
        return "\n".join(lines)

    def export_onnx(self) -> str:
        """Экспортирует модель в ONNX-формат для портативного использования."""
        return (
            "⚠️ ONNX-экспорт для sklearn-pipeline требует skl2onnx:\n"
            "  pip install skl2onnx\n"
            "  Функция будет доступна в следующей версии."
        )

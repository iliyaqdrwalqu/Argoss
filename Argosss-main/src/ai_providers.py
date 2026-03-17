"""
ai_providers.py — Константы лимитов и квот AI-провайдеров для Аргоса.

Содержит dataclass ProviderLimits и реестр AI_PROVIDERS со всеми
известными бесплатными / freemium AI API, их лимитами и конфигурацией.

Использование:
    from src.ai_providers import AI_PROVIDERS, ProviderLimits, get_provider
    p = get_provider("gemini")
    print(p.rpm, p.context_tokens)

Добавить новый провайдер:
    AI_PROVIDERS["my_model"] = ProviderLimits(name="My Model", ...)
"""
from __future__ import annotations

import os
import time
import threading
from dataclasses import dataclass, field
from typing import Optional

from src.argos_logger import get_logger

log = get_logger("argos.ai_providers")


# ─────────────────────────────────────────────────────────────────────────────
# DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ProviderLimits:
    """
    Параметры и лимиты одного AI-провайдера.

    Атрибуты:
        name            — читаемое название провайдера
        rpm             — максимум запросов в минуту (0 = неизвестно)
        tpm             — максимум токенов в минуту (0 = неизвестно)
        rph             — максимум запросов в час (0 = неизвестно)
        rpd             — максимум запросов в день (0 = неизвестно)
        context_tokens  — размер контекстного окна в токенах
        free_quota      — описание бесплатной квоты (строка)
        env_key         — имя переменной окружения для API-ключа
        base_url        — базовый URL API (пустая строка = N/A)
        model_id        — идентификатор модели по умолчанию
        notes           — дополнительные примечания
    """
    name:           str
    rpm:            int   = 0         # Requests Per Minute
    tpm:            int   = 0         # Tokens Per Minute
    rph:            int   = 0         # Requests Per Hour
    rpd:            int   = 0         # Requests Per Day
    context_tokens: int   = 0         # Context window size in tokens
    free_quota:     str   = ""        # Human-readable free tier description
    env_key:        str   = ""        # Name of the env variable for the API key
    base_url:       str   = ""        # Base URL of the API endpoint
    model_id:       str   = ""        # Default model identifier
    notes:          str   = ""        # Extra notes


# ─────────────────────────────────────────────────────────────────────────────
# РЕЕСТР ПРОВАЙДЕРОВ
# ─────────────────────────────────────────────────────────────────────────────

AI_PROVIDERS: dict[str, ProviderLimits] = {

    # ── DeepSeek (V3 / R1) ───────────────────────────────────────────────────
    "deepseek": ProviderLimits(
        name           = "DeepSeek (V3 / R1)",
        rpm            = 15,
        tpm            = 0,
        rph            = 0,
        rpd            = 0,
        context_tokens = 128_000,
        free_quota     = "~2–5 млн токенов при регистрации (разово)",
        env_key        = "DEEPSEEK_API_KEY",
        base_url       = "https://api.deepseek.com/v1",
        model_id       = "deepseek-chat",
        notes          = "Совместим с OpenAI SDK. R1 — reasoning model.",
    ),

    # ── GigaChat (Сбер) ──────────────────────────────────────────────────────
    "gigachat": ProviderLimits(
        name           = "GigaChat (Сбер)",
        rpm            = 60,
        tpm            = 0,
        rph            = 0,
        rpd            = 0,
        context_tokens = 32_000,
        free_quota     = "1 000 000 токенов (разово при регистрации)",
        env_key        = "GIGACHAT_API_KEY",
        base_url       = "https://gigachat.devices.sberbank.ru/api/v1",
        model_id       = "GigaChat",
        notes          = "Требует авторизацию через OAuth 2.0 (Сбер ID). Доступен только из РФ.",
    ),

    # ── YandexGPT (Lite) ─────────────────────────────────────────────────────
    "yandexgpt": ProviderLimits(
        name           = "YandexGPT (Lite)",
        rpm            = 0,
        tpm            = 0,
        rph            = 300,
        rpd            = 0,
        context_tokens = 32_000,
        free_quota     = "Грант ~4 000 ₽ на 60 дней",
        env_key        = "YANDEX_API_KEY",
        base_url       = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        model_id       = "yandexgpt-lite",
        notes          = "Также требует YANDEX_FOLDER_ID. Запросов в час: 300.",
    ),

    # ── Gemini 2.5 Flash (Google) ────────────────────────────────────────────
    "gemini": ProviderLimits(
        name           = "Gemini 2.5 Flash (Google)",
        rpm            = 15,
        tpm            = 1_000_000,
        rph            = 0,
        rpd            = 1_500,
        context_tokens = 1_000_000,
        free_quota     = "1 500 запросов в день, 1 000 000 TPM",
        env_key        = "GEMINI_API_KEY",
        base_url       = "https://generativelanguage.googleapis.com/v1beta",
        model_id       = "gemini-2.5-flash",
        notes          = "Самый большой контекст среди бесплатных провайдеров.",
    ),

    # ── Groq (Llama 3 / Mixtral) ─────────────────────────────────────────────
    "groq": ProviderLimits(
        name           = "Groq (Llama 3 / Mixtral)",
        rpm            = 30,
        tpm            = 30_000,
        rph            = 0,
        rpd            = 0,
        context_tokens = 128_000,
        free_quota     = "Полностью бесплатно (тестовый период без срока)",
        env_key        = "GROQ_API_KEY",
        base_url       = "https://api.groq.com/openai/v1",
        model_id       = "llama3-70b-8192",
        notes          = "Совместим с OpenAI SDK. Очень высокая скорость инференса (LPU).",
    ),

    # ── IBM Watson (Lite) ────────────────────────────────────────────────────
    "watson": ProviderLimits(
        name           = "IBM WatsonX AI (Lite)",
        rpm            = 120,
        tpm            = 0,
        rph            = 0,
        rpd            = 0,
        context_tokens = 128_000,
        free_quota     = "300 000 токенов в месяц",
        env_key        = "WATSONX_API_KEY",
        base_url       = "https://us-south.ml.cloud.ibm.com",
        model_id       = "meta-llama/llama-3-1-70b-instruct",
        notes          = "Также требует WATSONX_PROJECT_ID. Поддерживает Granite и Llama 3.",
    ),

    # ── OpenAI (GPT-4o) ──────────────────────────────────────────────────────
    "openai": ProviderLimits(
        name           = "OpenAI (GPT-4o)",
        rpm            = 3,
        tpm            = 30_000,
        rph            = 0,
        rpd            = 0,
        context_tokens = 128_000,
        free_quota     = "Стартовый баланс $5 (новым аккаунтам, разово)",
        env_key        = "OPENAI_API_KEY",
        base_url       = "https://api.openai.com/v1",
        model_id       = "gpt-4o",
        notes          = "Самый строгий RPM-лимит на бесплатном уровне.",
    ),

    # ── Ollama (локальный) ───────────────────────────────────────────────────
    "ollama": ProviderLimits(
        name           = "Ollama (локальный)",
        rpm            = 0,
        tpm            = 0,
        rph            = 0,
        rpd            = 0,
        context_tokens = 128_000,
        free_quota     = "Полностью бесплатно — локальный инференс",
        env_key        = "",
        base_url       = "http://localhost:11434",
        model_id       = "llama3",
        notes          = "Локальный LLM без API-ключа. Host: OLLAMA_HOST, модель: OLLAMA_MODEL.",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────────────────────────────────────

def get_provider(key: str) -> Optional[ProviderLimits]:
    """Вернуть ProviderLimits по ключу (регистронезависимо) или None."""
    return AI_PROVIDERS.get(key.lower())


def available_providers() -> list[str]:
    """Список провайдеров, для которых установлен API-ключ или (для Ollama) доступен хост."""
    ready = []
    for key, p in AI_PROVIDERS.items():
        if key == "ollama":
            # Ollama не требует ключа — проверяем доступность по сети
            try:
                import urllib.request
                host = os.getenv("OLLAMA_HOST", p.base_url)
                urllib.request.urlopen(f"{host}/api/tags", timeout=2)
                ready.append(key)
            except Exception:
                pass
        elif p.env_key and os.getenv(p.env_key, "").strip():
            ready.append(key)
    return ready


def best_provider(prefer_rpm: bool = False) -> Optional[str]:
    """
    Выбрать лучший из доступных провайдеров.

    Стратегия:
        1. Если prefer_rpm=True — выбрать по максимальному RPM.
        2. Иначе — выбрать с наибольшим контекстом.
    Возвращает None если ни один ключ не установлен.
    """
    ready = available_providers()
    if not ready:
        return None

    if prefer_rpm:
        return max(ready, key=lambda k: AI_PROVIDERS[k].rpm)
    return max(ready, key=lambda k: AI_PROVIDERS[k].context_tokens)


def providers_status() -> str:
    """Вернуть отчёт о статусе всех провайдеров для отображения в UI."""
    lines = ["🤖 AI-ПРОВАЙДЕРЫ (лимиты бесплатного уровня):", ""]
    ready_set = set(available_providers())
    for key, p in AI_PROVIDERS.items():
        if key == "ollama":
            is_ready = key in ready_set
            status_icon = "✅" if is_ready else "🔴"
            host = os.getenv("OLLAMA_HOST", p.base_url)
            model = os.getenv("OLLAMA_MODEL", p.model_id)
            lines.append(
                f"  {status_icon} {p.name}\n"
                f"     Host: {host} | Модель: {model}\n"
                f"     Квота: {p.free_quota}\n"
                f"     Ключ: не требуется (локальный)"
            )
            continue

        has_key = bool(p.env_key and os.getenv(p.env_key, "").strip())
        status_icon = "✅" if has_key else "🔑"

        rpm_str  = f"RPM={p.rpm}"  if p.rpm  else ""
        tpm_str  = f"TPM={p.tpm:,}" if p.tpm  else ""
        rph_str  = f"RPH={p.rph}"  if p.rph  else ""
        rpd_str  = f"RPD={p.rpd:,}" if p.rpd  else ""
        ctx_str  = (
            f"контекст={p.context_tokens // 1000}k"
            if p.context_tokens < 1_000_000
            else f"контекст={p.context_tokens // 1_000_000}M"
        )
        rate_parts = [x for x in [rpm_str, tpm_str, rph_str, rpd_str, ctx_str] if x]

        lines.append(
            f"  {status_icon} {p.name}\n"
            f"     {' | '.join(rate_parts)}\n"
            f"     Квота: {p.free_quota}\n"
            f"     Ключ: {p.env_key}"
        )
    lines.append("")
    ready = list(ready_set)
    lines.append(
        f"Активных провайдеров: {len(ready)}/{len(AI_PROVIDERS)} "
        f"({', '.join(ready) if ready else 'нет'})"
    )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# SIMPLE RATE LIMITER
# ─────────────────────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Простой in-process rate limiter для соблюдения RPM-лимита провайдера.

    Использование:
        limiter = RateLimiter(provider_key="gemini")
        limiter.wait()          # будет ждать если превышен лимит
        # ... вызов API ...
    """

    def __init__(self, provider_key: str):
        p = AI_PROVIDERS.get(provider_key.lower())
        self._rpm      = p.rpm if (p and p.rpm > 0) else 60
        self._interval = 60.0 / self._rpm          # секунд между запросами
        self._lock     = threading.Lock()
        self._last_ts  = 0.0

    def wait(self) -> float:
        """Ждать до тех пор пока не пройдёт нужный интервал. Возвращает фактическую паузу."""
        with self._lock:
            now     = time.monotonic()
            elapsed = now - self._last_ts
            pause   = max(0.0, self._interval - elapsed)
            if pause > 0:
                time.sleep(pause)
            self._last_ts = time.monotonic()
        return pause

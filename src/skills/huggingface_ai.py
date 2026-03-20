"""
huggingface_ai.py — Интеграция с Hugging Face Inference API.
"""
from __future__ import annotations

import os
from typing import Any

import requests

HF_INFERENCE_BASE = "https://api-inference.huggingface.co/models"


class HuggingFaceAI:
    """Клиент для Hugging Face Inference API."""

    def __init__(
        self,
        token: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ):
        self.token = token or os.getenv("HUGGINGFACE_TOKEN", "")
        self.model = model or os.getenv(
            "HUGGINGFACE_MODEL",
            "mistralai/Mistral-7B-Instruct-v0.2",
        )
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise ValueError("HUGGINGFACE_TOKEN is not configured")
        return {"Authorization": f"Bearer {self.token}"}

    def _post(self, model: str, payload: dict[str, Any]) -> Any:
        resp = requests.post(
            f"{HF_INFERENCE_BASE}/{model}",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def ask(self, prompt: str, model: str | None = None, max_new_tokens: int = 512) -> str:
        """Генерация текста по prompt."""
        result = self._post(
            model or self.model,
            {"inputs": prompt, "parameters": {"max_new_tokens": max_new_tokens}},
        )
        if isinstance(result, list) and result:
            return str(result[0].get("generated_text", result[0]))
        return str(result)

    def embed(
        self,
        text: str,
        model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> list[float]:
        """Получение векторных эмбеддингов текста."""
        result = self._post(model, {"inputs": text})
        if isinstance(result, list) and all(isinstance(x, (int, float)) for x in result):
            return [float(x) for x in result]
        return []

    def classify(
        self,
        text: str,
        candidate_labels: list[str],
        model: str = "facebook/bart-large-mnli",
    ) -> dict[str, Any]:
        """Zero-shot классификация текста."""
        return self._post(  # type: ignore[return-value]
            model,
            {"inputs": text, "parameters": {"candidate_labels": candidate_labels}},
        )

    def is_configured(self) -> bool:
        """Возвращает True если токен задан."""
        return bool(self.token)

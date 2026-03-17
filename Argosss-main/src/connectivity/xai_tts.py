import os
import time
import requests

XAI_TTS_ENDPOINT = "https://api.x.ai/v1/tts"
RETRYABLE_STATUS_CODES = {429, 500, 503}


def generate_speech_bytes(
    text: str,
    *,
    voice_id: str | None = None,
    language: str = "ru",
    output_format: dict | None = None,
    timeout_seconds: int = 60,
    max_retries: int = 3,
) -> bytes:
    payload_text = (text or "").strip()
    if not payload_text:
        raise ValueError("text must be non-empty")
    if len(payload_text) > 15000:
        raise ValueError("text exceeds max length 15000")

    api_key = (os.getenv("XAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("XAI_API_KEY is not set")

    payload = {
        "text": payload_text,
        "voice_id": (voice_id or os.getenv("XAI_TTS_VOICE_ID", "eve")).strip() or "eve",
        "language": (language or os.getenv("XAI_TTS_LANGUAGE", "ru")).strip() or "ru",
    }
    if output_format:
        payload["output_format"] = output_format

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    attempts = max(1, int(max_retries))
    for attempt in range(attempts):
        try:
            response = requests.post(
                XAI_TTS_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
            if response.ok:
                return response.content
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < attempts - 1:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
        except requests.RequestException as e:
            response = getattr(e, "response", None)
            status_code = getattr(response, "status_code", None)
            is_retryable = response is None or status_code in RETRYABLE_STATUS_CODES
            if attempt < attempts - 1 and is_retryable:
                time.sleep(2 ** attempt)
                continue
            raise

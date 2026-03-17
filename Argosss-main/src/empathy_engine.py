\
"""empathy_engine.py — Эмпатический анализ намерений (Python-fallback)"""
from __future__ import annotations

SAFE     = "Safe"
WARNING  = "Warning"
CRITICAL = "Critical"

RISKY_KEYWORDS = ["rm -rf","format","delete all","drop table","shutdown","os.remove","shutil.rmtree"]

class EmpathyEngine:
    def analyze_intent(self, intent: str, code: str = "") -> tuple[str,str]:
        combined = (intent + " " + code).lower()
        for kw in RISKY_KEYWORDS:
            if kw in combined:
                return CRITICAL, f"Обнаружено рискованное действие: '{kw}'"
        if any(w in combined for w in ["delete","remove","drop","kill"]):
            return WARNING, "Действие требует подтверждения."
        return SAFE, "Намерение безопасно."

    def is_safe(self, text: str) -> bool:
        status,_ = self.analyze_intent(text)
        return status == SAFE

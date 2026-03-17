"""
weather — Навык Аргоса
Автогенерировано ArgosUniversal
"""

TRIGGERS = ["weather", "weather"]

def setup(core=None):
    """Инициализация навыка."""
    pass

def handle(text: str, core=None) -> str | None:
    """Обработка команды. Вернуть None если не наш запрос."""
    t = text.lower()
    if not any(tr in t for tr in TRIGGERS):
        return None
    return f"✅ Навык weather: обработка {text[:50]}"

def teardown():
    """Завершение работы навыка."""
    pass

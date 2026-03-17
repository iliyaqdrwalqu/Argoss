"""
tests/test_life_support.py
Тесты модуля ArgosLifeSupport (src/life_support.py)
"""
from types import SimpleNamespace

from src.life_support import ArgosLifeSupport


def _make_core():
    return SimpleNamespace()


def test_life_support_start_stop():
    core = _make_core()
    life = ArgosLifeSupport(core)
    msg = life.start()
    assert "активирован" in msg
    assert life._running is True

    msg2 = life.stop()
    assert "остановлен" in msg2
    assert life._running is False


def test_life_support_double_start():
    life = ArgosLifeSupport(_make_core())
    life.start()
    msg = life.start()
    assert "уже активен" in msg
    life.stop()


def test_finances_empty():
    life = ArgosLifeSupport(_make_core())
    result = life.handle_command("финансы")
    assert "ФИНАНСЫ" in result
    assert "Доходы" in result
    assert "Расходы" in result


def test_add_contract_and_earnings():
    life = ArgosLifeSupport(_make_core())
    msg = life.handle_command("контракт Telegram бот|ООО Ромашка|15000")
    assert "Контракт добавлен" in msg

    earnings = life.handle_command("заработок")
    assert "Telegram бот" in earnings
    assert "15,000" in earnings or "15 000" in earnings or "15000" in earnings


def test_add_expense():
    life = ArgosLifeSupport(_make_core())
    msg = life.handle_command("расход api|Gemini ключ|0.05")
    assert "Расход добавлен" in msg


def test_roi_after_contract_and_expense():
    life = ArgosLifeSupport(_make_core())
    life.handle_command("контракт Проект|Клиент|10000")
    life.handle_command("расход хостинг|VPS|500")
    roi = life.handle_command("окупаемость")
    assert "ROI" in roi
    assert "Инвестиции" in roi


def test_pitches():
    life = ArgosLifeSupport(_make_core())
    for n in range(1, 6):
        result = life.handle_command(f"питч {n}")
        assert len(result) > 50

    # Без номера → питч 1
    result = life.handle_command("питч")
    assert len(result) > 50


def test_providers():
    life = ArgosLifeSupport(_make_core())
    result = life.handle_command("провайдеры")
    assert "Gemini" in result
    assert "Ollama" in result
    assert "Free" in result


def test_status_command():
    life = ArgosLifeSupport(_make_core())
    result = life.handle_command("статус")
    assert "LIFE SUPPORT" in result


def test_help_fallback():
    life = ArgosLifeSupport(_make_core())
    result = life.handle_command("неизвестная_команда")
    assert "ЖИЗНЕОБЕСПЕЧЕНИЕ" in result


def test_bad_amount_contract():
    life = ArgosLifeSupport(_make_core())
    result = life.handle_command("контракт Тест|Клиент|не_число")
    assert "числом" in result.lower() or "число" in result.lower()


def test_bad_amount_expense():
    life = ArgosLifeSupport(_make_core())
    result = life.handle_command("расход Кат|Опис|не_число")
    assert "числом" in result.lower() or "число" in result.lower()

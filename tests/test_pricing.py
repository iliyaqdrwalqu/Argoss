"""tests/test_pricing.py — тесты модуля ArgosPricing"""
from src.pricing import ArgosPricing, _COSTS, _COMPETITORS, _TIERS, _PROJECT_TYPES


def _p():
    return ArgosPricing()


# ── Данные ────────────────────────────────────────────────────

def test_costs_have_entries():
    assert len(_COSTS) >= 5


def test_competitors_have_entries():
    assert len(_COMPETITORS) >= 5


def test_tiers_four_plans():
    assert len(_TIERS) == 4


def test_project_types_have_entries():
    assert len(_PROJECT_TYPES) >= 4


def test_cost_item_rub_conversion():
    from src.pricing import CostItem
    c = CostItem("Test", 10.0, 20.0, "note")
    assert c.rub_low  == 10.0 * 90
    assert c.rub_high == 20.0 * 90


# ── handle_command ────────────────────────────────────────────

def test_расходы():
    p = _p()
    r = p.handle_command("расходы")
    assert "РАСХОДЫ" in r
    assert "Бесплатно" in r
    assert "ИТОГО" in r


def test_рынок():
    p = _p()
    r = p.handle_command("рынок")
    assert "КОНКУРЕНТНЫЙ" in r
    assert "Аргос" in r
    assert "Hetzner" in r or "AutoGPT" in r


def test_прайс():
    p = _p()
    r = p.handle_command("прайс")
    assert "ПРАЙС" in r
    assert "₽" in r or "$" in r


def test_тарифы():
    p = _p()
    r = p.handle_command("тарифы")
    assert "ТАРИФНЫЕ" in r
    assert "Starter" in r
    assert "Enterprise" in r


def test_roi_клиент():
    p = _p()
    r = p.handle_command("roi клиент")
    assert "ROI" in r
    assert "%" in r


def test_питч_цена():
    p = _p()
    r = p.handle_command("питч цена")
    assert "ПИТЧ" in r
    assert "$" in r


def test_план_продаж():
    p = _p()
    r = p.handle_command("план продаж")
    assert "ПЛАН" in r
    assert "НЕДЕЛЯ" in r


def test_оценка_telegram_бот():
    p = _p()
    r = p.handle_command("оценка telegram бот")
    assert "Telegram" in r
    assert "₽" in r or "$" in r


def test_оценка_умный_дом():
    p = _p()
    r = p.handle_command("оценка умный дом")
    assert "умн" in r.lower()   # умного / умный / умном


def test_оценка_unknown():
    p = _p()
    r = p.handle_command("оценка летающая тарелка")
    assert "Грубая оценка" in r or "оценк" in r.lower()


def test_оценка_аргос_установка():
    p = _p()
    r = p.handle_command("оценка аргос установка")
    assert "₽" in r or "$" in r


def test_help_fallback():
    p = _p()
    r = p.handle_command("непонятная команда")
    assert "ЦЕНООБРАЗОВАНИЕ" in r or "команды" in r.lower()


def test_aliases():
    p = _p()
    assert "РАСХОДЫ" in p.handle_command("затраты")
    assert "КОНКУРЕНТНЫЙ" in p.handle_command("конкуренты")
    assert "ПРАЙС" in p.handle_command("прайс-лист")
    assert "ТАРИФНЫЕ" in p.handle_command("тарифные планы")

"""tests/test_life_support_v2.py — тесты ArgosLifeSupportV2"""
from src.life_support_v2 import (
    ArgosLifeSupportV2,
    FreelanceHunter,
    CryptoWallet,
    ContentGenerator,
    JobScanner,
    BillingSystem,
    AffiliateEngine,
)


# ── FreelanceHunter ───────────────────────────────────────────

def test_freelance_scan_demo():
    fh = FreelanceHunter()
    orders = fh.scan(use_demo=True)
    assert len(orders) > 0
    for o in orders:
        assert 0.0 <= o.suitable <= 1.0


def test_freelance_score():
    fh = FreelanceHunter()
    score = fh._score_order("telegram бот python автоматизация")
    assert score >= 0.5


def test_freelance_format():
    fh = FreelanceHunter()
    r = fh.format_orders()
    assert "НАЙДЕНО" in r
    assert "отклик" in r.lower()


def test_freelance_generate_response_telegram():
    fh = FreelanceHunter()
    fh.scan(use_demo=True)
    order = fh._orders[0]
    r = fh.generate_response(order)
    assert "ОТКЛИК" in r
    assert "Бюджет" in r


# ── CryptoWallet ──────────────────────────────────────────────

def test_crypto_balance():
    w = CryptoWallet()
    bal = w.get_balance(force=True)
    assert "TON" in bal
    assert "USDT" in bal
    assert "BTC" in bal


def test_crypto_balance_values():
    w = CryptoWallet()
    bal = w.get_balance(force=True)
    for v in bal.values():
        assert v >= 0


def test_crypto_usd_equivalent():
    w = CryptoWallet()
    total = w.usd_equivalent()
    assert total >= 0


def test_crypto_payment_address():
    w = CryptoWallet()
    info = w.get_payment_address("TON", 5.0, "тест")
    assert info["currency"] == "TON"
    assert info["amount"] == 5.0
    assert "address" in info


def test_crypto_status():
    w = CryptoWallet()
    r = w.status()
    assert "КОШЕЛЁК" in r
    assert "TON" in r


def test_crypto_balance_cached():
    w = CryptoWallet()
    b1 = w.get_balance(force=True)
    b2 = w.get_balance()          # should use cache
    assert b1 == b2


# ── ContentGenerator ──────────────────────────────────────────

def test_content_generate_post():
    c = ContentGenerator()
    r = c.generate_post("Python и IoT")
    assert len(r) > 20
    assert "Python" in r or "IoT" in r or "[ЧЕРНОВИК" in r


def test_content_generate_post_random():
    c = ContentGenerator()
    r = c.generate_post()
    assert len(r) > 20


def test_content_topic_ideas():
    c = ContentGenerator()
    ideas = c.get_topic_ideas()
    assert len(ideas) >= 1
    for idea in ideas:
        assert isinstance(idea, str)


def test_content_topic_ideas_by_category():
    c = ContentGenerator()
    ideas = c.get_topic_ideas("iot")
    assert len(ideas) >= 1


def test_content_plan():
    c = ContentGenerator()
    r = c.generate_content_plan(3)
    assert "ПЛАН" in r
    assert "День 1" in r
    assert "День 3" in r


# ── JobScanner ────────────────────────────────────────────────

def test_job_scan():
    js = JobScanner()
    jobs = js.scan()
    assert len(jobs) > 0


def test_job_cover_letter():
    js = JobScanner()
    jobs = js.scan()
    letter = js.generate_cover_letter(jobs[0])
    assert len(letter) > 50
    assert "Здравствуйте" in letter


def test_job_format():
    js = JobScanner()
    r = js.format_jobs()
    assert "ВАКАНСИИ" in r


# ── BillingSystem ─────────────────────────────────────────────

def test_billing_create_invoice():
    wallet  = CryptoWallet()
    billing = BillingSystem(wallet, db_path="data/test_billing_v2.db")
    inv = billing.create_invoice("Test Client", "Python бот", 15000)
    assert inv.invoice_id.startswith("INV-")
    assert inv.amount_rub == 15000
    assert inv.amount_usd > 0


def test_billing_format_invoice():
    wallet  = CryptoWallet()
    billing = BillingSystem(wallet, db_path="data/test_billing_fmt.db")
    inv = billing.create_invoice("ООО Тест", "Разработка", 10000)
    r = billing.format_invoice(inv)
    assert "СЧЁТ" in r
    assert "ООО Тест" in r
    assert "10000" in r or "10 000" in r


def test_billing_mark_paid():
    wallet  = CryptoWallet()
    billing = BillingSystem(wallet, db_path="data/test_billing_paid.db")
    inv = billing.create_invoice("Client", "Service", 5000)
    r = billing.mark_paid(inv.invoice_id)
    assert "оплачен" in r.lower()


def test_billing_mark_paid_unknown():
    wallet  = CryptoWallet()
    billing = BillingSystem(wallet, db_path="data/test_billing_unk.db")
    r = billing.mark_paid("INV-99999999-000")
    assert "не найден" in r


def test_billing_summary():
    wallet  = CryptoWallet()
    billing = BillingSystem(wallet, db_path="data/test_billing_sum.db")
    billing.create_invoice("A", "S1", 1000)
    billing.create_invoice("B", "S2", 2000)
    r = billing.summary()
    assert "БИЛЛИНГ" in r
    assert "2" in r   # 2 счёта


# ── AffiliateEngine ───────────────────────────────────────────

def test_affiliate_top_offers():
    ae = AffiliateEngine()
    top = ae.get_top_offers(3)
    assert len(top) == 3
    # Отсортированы по suitable убыванию
    for i in range(len(top) - 1):
        assert top[i].suitable >= top[i + 1].suitable


def test_affiliate_format():
    ae = AffiliateEngine()
    r = ae.format_offers()
    assert "ПАРТНЁРСКИЕ" in r


def test_affiliate_estimate():
    ae = AffiliateEngine()
    r = ae.estimate_monthly()
    assert "ПРОГНОЗ" in r
    assert "₽" in r


# ── ArgosLifeSupportV2 (handle_command) ───────────────────────

def _v2():
    return ArgosLifeSupportV2()


def test_v2_full_status():
    v = _v2()
    r = v.full_status()
    assert "ЖИЗНЕОБЕСПЕЧЕНИЕ v2" in r


def test_v2_фриланс():
    v = _v2()
    r = v.handle_command("фриланс")
    assert "НАЙДЕНО" in r


def test_v2_фриланс_scan():
    v = _v2()
    r = v.handle_command("фриланс сканировать")
    assert "НАЙДЕНО" in r


def test_v2_отклик():
    v = _v2()
    v.handle_command("фриланс")   # populate orders
    r = v.handle_command("отклик 1")
    assert "ОТКЛИК" in r


def test_v2_крипто():
    v = _v2()
    r = v.handle_command("крипто")
    assert "КОШЕЛЁК" in r


def test_v2_контент_план():
    v = _v2()
    r = v.handle_command("контент план")
    assert "ПЛАН" in r


def test_v2_написать_пост():
    v = _v2()
    r = v.handle_command("написать пост Python для начинающих")
    assert len(r) > 20


def test_v2_написать_статью():
    v = _v2()
    r = v.handle_command("написать статью IoT")
    assert len(r) > 20


def test_v2_темы_для_постов():
    v = _v2()
    r = v.handle_command("темы для постов")
    assert "ИДЕИ" in r


def test_v2_вакансии():
    v = _v2()
    r = v.handle_command("вакансии")
    assert "ВАКАНСИИ" in r


def test_v2_отклик_вакансия():
    v = _v2()
    v.handle_command("вакансии")  # populate
    r = v.handle_command("отклик вакансия 1")
    assert "ПИСЬМО" in r


def test_v2_счёт():
    v = _v2()
    r = v.handle_command("счёт ООО Тест|Разработка|5000")
    assert "СЧЁТ" in r
    assert "ООО Тест" in r


def test_v2_счёт_bad_amount():
    v = _v2()
    r = v.handle_command("счёт A|B|не_число")
    assert "числом" in r.lower() or "число" in r.lower()


def test_v2_биллинг():
    v = _v2()
    r = v.handle_command("биллинг")
    assert "БИЛЛИНГ" in r


def test_v2_партнёрки():
    v = _v2()
    r = v.handle_command("партнёрки")
    assert "ПАРТНЁРСКИЕ" in r


def test_v2_партнёрки_прогноз():
    v = _v2()
    r = v.handle_command("партнёрки прогноз")
    assert "ПРОГНОЗ" in r


def test_v2_v2_статус():
    v = _v2()
    r = v.handle_command("v2 статус")
    assert "ЖИЗНЕОБЕСПЕЧЕНИЕ v2" in r


def test_v2_help_fallback():
    v = _v2()
    r = v.handle_command("непонятная команда")
    assert "v2" in r.lower()


def test_v2_адрес_оплаты():
    v = _v2()
    r = v.handle_command("адрес оплаты TON 5.5")
    assert "TON" in r
    assert "Адрес" in r


def test_v2_проверить_транзакции():
    v = _v2()
    r = v.handle_command("проверить транзакции")
    # Either "нет" or actual list
    assert isinstance(r, str) and len(r) > 0

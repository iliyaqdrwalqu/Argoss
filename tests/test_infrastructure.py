"""tests/test_infrastructure.py — тесты ArgosInfrastructure"""
from src.infrastructure import (
    ArgosInfrastructure,
    MailServerManager,
    VPNManager,
    VPNClient,
    QuantumMarketplace,
)


# ── MailServerManager ─────────────────────────────────────────

def test_mail_status():
    m = MailServerManager()
    r = m.status()
    assert "ПОЧТОВЫЙ" in r


def test_mail_setup_guide_default_domain():
    m = MailServerManager()
    r = m.setup_guide()
    assert "УСТАНОВКА" in r
    assert "MX" in r
    assert "spf1" in r or "SPF" in r


def test_mail_setup_guide_custom_domain():
    m = MailServerManager()
    r = m.setup_guide("argos.example.com")
    assert "argos.example.com" in r


def test_mail_add_account_valid():
    m = MailServerManager()
    r = m.add_account("test@argos.io")
    assert "создан" in r
    assert len(m._accounts) == 1


def test_mail_add_account_duplicate():
    m = MailServerManager()
    m.add_account("dup@argos.io")
    r = m.add_account("dup@argos.io")
    assert "уже существует" in r


def test_mail_add_account_invalid():
    m = MailServerManager()
    r = m.add_account("not-an-email")
    assert "Некорректный" in r


def test_mail_check_mx():
    m = MailServerManager()
    r = m.check_mx("example.com")
    assert "DNS" in r or "MX" in r
    assert "example.com" in r


# ── VPNManager ────────────────────────────────────────────────

def test_vpn_status_empty():
    v = VPNManager()
    r = v.status()
    assert "VPN" in r
    assert "Клиентов: 0" in r


def test_vpn_setup_guide():
    v = VPNManager()
    r = v.setup_guide("1.2.3.4")
    assert "WIREGUARD" in r.upper()
    assert "1.2.3.4" in r


def test_vpn_add_client():
    v = VPNManager()
    c = v.add_client("my_phone")
    assert c.name == "my_phone"
    assert c.ip.startswith("10.8.0.")
    assert c.public_key
    assert len(v._clients) == 1


def test_vpn_add_multiple_clients():
    v = VPNManager()
    c1 = v.add_client("phone")
    c2 = v.add_client("laptop")
    assert c1.ip != c2.ip
    assert len(v._clients) == 2


def test_vpn_client_config():
    v = VPNManager()
    v.add_client("laptop")
    r = v.get_client_config("laptop")
    assert "[Interface]" in r
    assert "PrivateKey" in r
    assert "[Peer]" in r


def test_vpn_client_config_not_found():
    v = VPNManager()
    r = v.get_client_config("nonexistent")
    assert "не найден" in r


def test_vpn_sell_vpn_access():
    v = VPNManager()
    r = v.sell_vpn_access()
    assert "БИЗНЕС" in r
    assert "₽" in r


def test_vpn_client_ips_sequential():
    v = VPNManager()
    clients = [v.add_client(f"c{i}") for i in range(5)]
    ips = [int(c.ip.split(".")[-1]) for c in clients]
    assert ips == list(range(2, 7))


# ── QuantumMarketplace ────────────────────────────────────────

def test_quantum_catalog():
    q = QuantumMarketplace()
    r = q.list_catalog()
    assert "КВАНТОВЫЙ" in r
    assert "random_numbers" in r
    assert "$" in r


def test_quantum_submit_random_numbers():
    q = QuantumMarketplace()
    job = q.submit_job("random_numbers", {"count": 10})
    assert job.status == "done"
    assert job.result is not None
    assert "numbers" in job.result or "note" in job.result


def test_quantum_submit_portfolio():
    q = QuantumMarketplace()
    job = q.submit_job("portfolio_optimization", {"assets": ["BTC", "ETH"]})
    assert job.status == "done"
    assert job.result is not None


def test_quantum_submit_route():
    q = QuantumMarketplace()
    job = q.submit_job("route_optimization", {"points": 5})
    assert job.status == "done"


def test_quantum_submit_unknown():
    q = QuantumMarketplace()
    job = q.submit_job("super_custom_job", {})
    assert job.status == "done"
    assert job.price_usd == 1.0


def test_quantum_sell_result():
    q = QuantumMarketplace()
    r = q.sell_result("random_numbers", {"count": 5})
    assert "ПРОДАН" in r
    assert "$" in r
    assert q._total_earned > 0


def test_quantum_status():
    q = QuantumMarketplace()
    q.sell_result("random_numbers")
    r = q.status()
    assert "КВАНТОВЫЙ" in r
    assert "Задач продано" in r


def test_quantum_market_overview():
    q = QuantumMarketplace()
    r = q.market_overview()
    assert "IBM" in r
    assert "AWS" in r
    assert "$" in r


def test_quantum_earning_accumulation():
    q = QuantumMarketplace()
    q.sell_result("random_numbers")
    q.sell_result("random_numbers")
    assert q._total_earned >= 1.0


# ── ArgosInfrastructure (handle_command) ──────────────────────

def _infra():
    return ArgosInfrastructure(core=None)


def test_handle_почта_статус():
    r = _infra().handle_command("почта статус")
    assert "ПОЧТОВЫЙ" in r


def test_handle_почта_настроить():
    r = _infra().handle_command("почта настроить")
    assert "УСТАНОВКА" in r


def test_handle_почта_аккаунт():
    r = _infra().handle_command("почта аккаунт info@test.io")
    assert "создан" in r or "Некорректный" in r


def test_handle_почта_mx():
    r = _infra().handle_command("почта mx example.com")
    assert "MX" in r


def test_handle_vpn_статус():
    r = _infra().handle_command("vpn статус")
    assert "VPN" in r


def test_handle_vpn_настроить():
    r = _infra().handle_command("vpn настроить")
    assert "WIREGUARD" in r.upper()


def test_handle_vpn_клиент():
    infra = _infra()
    r = infra.handle_command("vpn клиент my_laptop")
    assert "добавлен" in r
    assert "my_laptop" in r


def test_handle_vpn_конфиг():
    infra = _infra()
    infra.handle_command("vpn клиент conf_test")
    r = infra.handle_command("vpn конфиг conf_test")
    assert "[Interface]" in r


def test_handle_vpn_бизнес():
    r = _infra().handle_command("vpn бизнес")
    assert "БИЗНЕС" in r


def test_handle_квант_задачи():
    r = _infra().handle_command("квант задачи")
    assert "КАТАЛОГ" in r


def test_handle_квант_рынок():
    r = _infra().handle_command("квант рынок")
    assert "IBM" in r


def test_handle_квант_продать():
    r = _infra().handle_command("квант продать random_numbers")
    assert "ПРОДАН" in r


def test_handle_квант_статус():
    infra = _infra()
    infra.handle_command("квант продать random_numbers")
    r = infra.handle_command("квант статус")
    assert "КВАНТОВЫЙ" in r


def test_handle_инфра():
    r = _infra().handle_command("инфра")
    assert "ИНФРАСТРУКТУРА" in r


def test_handle_unknown():
    r = _infra().handle_command("что-то странное")
    assert "ИНФРАСТРУКТУРА" in r or "команды" in r.lower()

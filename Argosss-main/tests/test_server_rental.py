"""
tests/test_server_rental.py
Тесты модуля ArgosServerRental (src/server_rental.py)
"""
from src.server_rental import (
    ArgosServerRental,
    ServerCatalog,
    AccountManager,
    DeployManager,
    ServerPlan,
)


# ── ServerCatalog ─────────────────────────────────────────────

def test_catalog_has_plans():
    cat = ServerCatalog()
    assert len(cat.PLANS) >= 10


def test_catalog_free_options():
    cat = ServerCatalog()
    free = cat.free_options()
    assert len(free) > 0
    for p in free:
        assert p.price_month == 0.0


def test_catalog_gpu_options():
    cat = ServerCatalog()
    gpu = cat.gpu_options()
    assert len(gpu) > 0
    for p in gpu:
        assert p.gpu


def test_catalog_best_for_argos():
    cat = ServerCatalog()
    best = cat.best_for_argos()
    assert 1 <= len(best) <= 5
    for p in best:
        assert p.price_month < 10


def test_catalog_recommendation_budget():
    cat = ServerCatalog()
    result = cat.recommendation(6.0)
    assert "$" in result or "мес" in result


def test_catalog_recommendation_free():
    cat = ServerCatalog()
    result = cat.recommendation(0.0)
    assert "Бесплатные" in result or "бесплатн" in result.lower()


def test_catalog_recommendation_gpu():
    cat = ServerCatalog()
    result = cat.recommendation(need_gpu=True)
    assert "GPU" in result


def test_catalog_compare_found():
    cat = ServerCatalog()
    result = cat.compare(["Hetzner"])
    assert "Hetzner" in result


def test_catalog_compare_not_found():
    cat = ServerCatalog()
    result = cat.compare(["НесуществующийПровайдер"])
    assert "не найден" in result


def test_server_plan_score():
    plan = ServerPlan("Test", "S1", "2vCPU", 4, 40, "1TB", 5.0, 0.01, "EU")
    score = plan.score()
    assert isinstance(score, float)
    assert score >= 0


def test_server_plan_to_dict():
    plan = ServerPlan("Test", "S1", "2vCPU", 4, 40, "1TB", 5.0, 0.01, "EU")
    d = plan.to_dict()
    assert d["provider"] == "Test"
    assert "RAM" in d["ram"] or "GB" in d["ram"]


# ── AccountManager ────────────────────────────────────────────

def test_account_request_creates_pending():
    am = AccountManager()
    req = am.request_account("hetzner", "argos@test.com", "нода")
    assert req.status == "pending"
    assert req.platform == "hetzner"
    assert len(am.pending_requests()) == 1


def test_account_confirm_shows_steps():
    am = AccountManager()
    req = am.request_account("hetzner", "a@b.com", "тест")
    result = am.confirm_account(req.id[-8:])
    assert "ПОДТВЕРЖДЕНО" in result
    assert "1." in result   # шаги пронумерованы


def test_account_confirm_unknown_id():
    am = AccountManager()
    result = am.confirm_account("xxxxxxxx")
    assert "не найден" in result


def test_account_register_created():
    am = AccountManager()
    req = am.request_account("github", "a@b.com", "ci")
    am.confirm_account(req.id[-8:])
    result = am.register_created("github", {"token": "ghp_xxx"})
    assert "зарегистрирован" in result
    assert "github" in am.all_accounts().lower()


def test_account_all_empty():
    am = AccountManager()
    assert "пока нет" in am.all_accounts()


def test_account_show_platform_found():
    am = AccountManager()
    result = am.show_platform("hetzner")
    assert "Hetzner" in result


def test_account_show_platform_not_found():
    am = AccountManager()
    result = am.show_platform("несуществующий")
    assert "не найдена" in result


# ── DeployManager ─────────────────────────────────────────────

def test_deploy_register_server():
    dm = DeployManager()
    srv = dm.register_server("Hetzner", "1.2.3.4", "cx21", "CX21", 5.83)
    assert srv.ip == "1.2.3.4"
    assert srv.status == "active"


def test_deploy_request_and_confirm():
    dm = DeployManager()
    srv = dm.register_server("Hetzner", "1.2.3.4", "cx21", "CX21", 5.83)
    req = dm.request_deploy(srv.id)
    assert req["status"] == "pending"
    assert req["server_ip"] == "1.2.3.4"

    result = dm.confirm_deploy(req["id"][-8:])
    assert "ПОДТВЕРЖДЁН" in result
    assert "ssh root@" in result


def test_deploy_request_missing_server():
    dm = DeployManager()
    result = dm.request_deploy("nonexistent_id")
    assert "error" in result


def test_deploy_confirm_missing():
    dm = DeployManager()
    result = dm.confirm_deploy("zzzzzzzz")
    assert "не найден" in result


def test_deploy_list_servers_empty():
    dm = DeployManager()
    result = dm.list_servers()
    assert "нет" in result


def test_deploy_list_servers_with_entries():
    dm = DeployManager()
    dm.register_server("DigitalOcean", "10.0.0.1", "basic", "Basic", 6.0)
    result = dm.list_servers()
    assert "DigitalOcean" in result
    assert "10.0.0.1" in result


def test_check_server_not_found():
    dm = DeployManager()
    result = dm.check_server("nonexistent")
    assert "error" in result
    assert result["online"] is False


# ── ArgosServerRental (handle_command) ────────────────────────

def _rental():
    return ArgosServerRental(core=None)


def test_handle_серверы():
    r = _rental()
    result = r.handle_command("серверы")
    assert "$" in result or "мес" in result


def test_handle_бесплатные():
    r = _rental()
    result = r.handle_command("бесплатные")
    assert "Бесплатные" in result or "бесплатн" in result.lower()


def test_handle_gpu():
    r = _rental()
    result = r.handle_command("gpu")
    assert "GPU" in result


def test_handle_топ():
    r = _rental()
    result = r.handle_command("топ")
    assert "ЛУЧШИЕ" in result


def test_handle_бюджет():
    r = _rental()
    result = r.handle_command("бюджет 5")
    assert "$" in result


def test_handle_бюджет_bad():
    r = _rental()
    result = r.handle_command("бюджет не_число")
    assert "числом" in result or "бюджет" in result.lower()


def test_handle_сравни():
    r = _rental()
    result = r.handle_command("сравни hetzner")
    assert "Hetzner" in result


def test_handle_аккаунты_empty():
    r = _rental()
    result = r.handle_command("аккаунты")
    assert "пока нет" in result


def test_handle_платформа():
    r = _rental()
    result = r.handle_command("платформа hetzner")
    assert "Hetzner" in result


def test_handle_создай_и_подтверди_аккаунт():
    r = _rental()
    create_result = r.handle_command("создай аккаунт oracle|me@test.com|моя нода")
    assert "ЗАПРОС" in create_result
    # Извлекаем ID
    for part in create_result.split():
        if len(part) == 8 and part.isalnum():
            confirm_result = r.handle_command(f"подтверди аккаунт {part}")
            assert "ПОДТВЕРЖДЕНО" in confirm_result
            break


def test_handle_мои_серверы_empty():
    r = _rental()
    result = r.handle_command("мои серверы")
    assert "нет" in result


def test_handle_добавь_и_деплой_сервер():
    r = _rental()
    add_result = r.handle_command("добавь сервер Hetzner|5.6.7.8|CX21|5.83")
    assert "добавлен" in add_result
    # Извлекаем ID сервера: ищем токен после "деплой" в последней строке подсказки
    srv_id = None
    for line in add_result.splitlines():
        if "деплой" in line:
            parts = line.split()
            if parts:
                candidate = parts[-1]
                if candidate.isascii() and candidate.isalnum():
                    srv_id = candidate
                    break
    assert srv_id is not None, f"ID сервера не найден в:\n{add_result}"
    deploy_result = r.handle_command(f"деплой {srv_id}")
    assert "ЗАПРОС" in deploy_result


def test_handle_добавь_сервер_bad_cost():
    r = _rental()
    result = r.handle_command("добавь сервер X|1.2.3.4|Plan|не_число")
    assert "числом" in result or "Формат" in result


def test_handle_ожидающие_empty():
    r = _rental()
    result = r.handle_command("ожидающие")
    assert "Нет ожидающих" in result


def test_handle_ожидающие_with_pending():
    r = _rental()
    r.handle_command("создай аккаунт hetzner|x@y.com|тест")
    result = r.handle_command("ожидающие")
    assert "Аккаунты" in result or "hetzner" in result


def test_handle_unknown_command():
    r = _rental()
    result = r.handle_command("непонятная команда xyz")
    assert "АРЕНДА" in result or "серверы" in result.lower()

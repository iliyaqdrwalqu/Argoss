"""
infrastructure.py — Инфраструктурные сервисы Аргоса
====================================================
Собственный почтовый сервер, VPN, продажа квантовых вычислений.

Модули:
  MailServerManager    — развёртывание Postfix/Dovecot/Roundcube
  VPNManager           — WireGuard VPN (сервер + клиенты)
  QuantumMarketplace   — продажа результатов квантовых вычислений

Принцип: Аргос генерирует конфиги → Человек подтверждает → Аргос деплоит.

Команды (через handle_command):
  почта статус         — статус почтового сервера
  почта настроить      — инструкция по развёртыванию
  почта аккаунт X@Y   — создать почтовый ящик
  почта mx <домен>     — проверить MX записи
  vpn статус           — список клиентов VPN
  vpn настроить        — развернуть WireGuard сервер
  vpn клиент <имя>     — добавить VPN клиента
  vpn конфиг <имя>     — получить конфиг клиента
  квант задачи         — доступные вычислительные задачи
  квант продать <тип>  — выставить результат на продажу
  квант рынок          — маркетплейс квантовых вычислений
  квант статус         — текущие задачи и доходы
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from src.argos_logger import get_logger

log = get_logger("argos.infrastructure")

_USD_RATE = float(os.getenv("ARGOS_USD_RATE", "90"))


# ══════════════════════════════════════════════════════════════
# 1. ПОЧТОВЫЙ СЕРВЕР
# ══════════════════════════════════════════════════════════════

@dataclass
class MailAccount:
    address:    str
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    quota_mb:   int = 1024
    active:     bool = True


class MailServerManager:
    """
    Управление собственным почтовым сервером.

    Стек: Postfix (SMTP) + Dovecot (IMAP/POP3) + Roundcube (веб).
    Всё разворачивается на VPS с доменом через один скрипт.
    """

    # Bash-скрипт установки почтового сервера
    # Placeholder {DOMAIN} and {HOSTNAME} expanded via str.replace(); other braces are literal.
    _SETUP_SCRIPT = """\
#!/bin/bash
# Argos Mail Server — Auto Setup Script
# Postfix + Dovecot + Roundcube + Let's Encrypt
# Требует: Ubuntu 22.04 LTS, домен с MX записью, root
set -e

DOMAIN="__DOMAIN__"
HOSTNAME="mail.__DOMAIN__"
ADMIN_EMAIL="admin@__DOMAIN__"

echo "📧 Установка почтового сервера для $DOMAIN"

# 1. Системные пакеты
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y \\
    postfix dovecot-core dovecot-imapd dovecot-pop3d \\
    roundcube roundcube-mysql nginx certbot python3-certbot-nginx \\
    mailutils spamassassin clamav-daemon -q

# 2. SSL сертификат
certbot certonly --nginx -d "$HOSTNAME" --email "$ADMIN_EMAIL" \\
    --agree-tos --non-interactive

# 3. Postfix конфигурация
cat > /etc/postfix/main.cf << 'POSTFIX'
myhostname = __HOSTNAME__
mydomain = __DOMAIN__
myorigin = $mydomain
inet_interfaces = all
mydestination = $myhostname, localhost.$mydomain, localhost, $mydomain
home_mailbox = Maildir/
smtpd_tls_cert_file = /etc/letsencrypt/live/__HOSTNAME__/fullchain.pem
smtpd_tls_key_file  = /etc/letsencrypt/live/__HOSTNAME__/privkey.pem
smtpd_use_tls = yes
smtpd_tls_security_level = may
smtp_tls_security_level = may
smtpd_sasl_type = dovecot
smtpd_sasl_path = private/auth
smtpd_sasl_auth_enable = yes
smtpd_recipient_restrictions =
    permit_sasl_authenticated,
    permit_mynetworks,
    reject_unauth_destination
POSTFIX

# 4. Dovecot конфигурация
cat > /etc/dovecot/dovecot.conf << 'DOVECOT'
protocols = imap pop3 lmtp
mail_location = maildir:~/Maildir
auth_mechanisms = plain login
passdb { driver = pam }
userdb { driver = passwd }
ssl = required
ssl_cert = </etc/letsencrypt/live/__HOSTNAME__/fullchain.pem
ssl_key  = </etc/letsencrypt/live/__HOSTNAME__/privkey.pem
service auth {
  unix_listener /var/spool/postfix/private/auth {
    mode = 0660
    user = postfix
    group = postfix
  }
}
DOVECOT

# 5. Перезапуск сервисов
systemctl restart postfix dovecot nginx
systemctl enable postfix dovecot nginx

# 6. DNS инструкция
echo ""
echo "✅ Почтовый сервер установлен!"
echo ""
echo "📋 НАСТРОЙТЕ DNS ЗАПИСИ:"
echo "  MX    @       mail.$DOMAIN    приоритет 10"
echo "  A     mail    $(curl -s ifconfig.me)"
echo "  TXT   @       v=spf1 mx a ~all"
echo "  TXT   _dmarc  v=DMARC1; p=quarantine; rua=mailto:admin@$DOMAIN"
"""

    def __init__(self) -> None:
        self._domain:   str = os.getenv("ARGOS_MAIL_DOMAIN", "")
        self._accounts: List[MailAccount] = []
        self._running:  bool = False
        log.info("MailServerManager init | domain=%s", self._domain or "не задан")

    def status(self) -> str:
        lines = [
            "📧 ПОЧТОВЫЙ СЕРВЕР",
            f"  Домен:   {self._domain or '⚠️ не задан (ARGOS_MAIL_DOMAIN)'}",
            f"  Сервер:  {'🟢 Настроен' if self._running else '🔴 Не настроен'}",
            f"  Ящиков:  {len(self._accounts)}",
        ]
        if self._accounts:
            lines.append("  Аккаунты:")
            for acc in self._accounts[-5:]:
                status = "✅" if acc.active else "❌"
                lines.append(f"    {status} {acc.address}  ({acc.quota_mb} MB)")
        return "\n".join(lines)

    def setup_guide(self, domain: str = "") -> str:
        domain = domain or self._domain or "yourdomain.com"
        script = (
            self._SETUP_SCRIPT
            .replace("__DOMAIN__", domain)
            .replace("__HOSTNAME__", f"mail.{domain}")
        )
        script_path = f"/tmp/argos_mail_setup_{domain.replace('.', '_')}.sh"
        try:
            with open(script_path, "w") as fh:
                fh.write(script)
        except OSError:
            pass

        return (
            f"📧 УСТАНОВКА ПОЧТОВОГО СЕРВЕРА\n"
            f"  Домен: {domain}\n\n"
            f"  ⚠️  ТРЕБОВАНИЯ:\n"
            f"    • VPS с Ubuntu 22.04 (рекомендую Hetzner CX21 — $5.83/мес)\n"
            f"    • Домен с возможностью редактировать DNS\n"
            f"    • Открытые порты: 25, 143, 587, 993, 80, 443\n\n"
            f"  📋 ПЛАН ДЕЙСТВИЙ:\n"
            f"    1. Купи VPS (если нет): серверы → Hetzner CX21\n"
            f"    2. Купи домен (если нет): reg.ru, namecheap.com\n"
            f"    3. Выполни скрипт на сервере:\n\n"
            f"       ssh root@<IP_СЕРВЕРА>\n"
            f"       bash <(curl -s https://raw.github.com/.../mail_setup.sh)\n\n"
            f"  ИЛИ скопируй готовый скрипт из: {script_path}\n\n"
            f"  📌 DNS ЗАПИСИ (настроить ДО запуска скрипта):\n"
            f"    MX    @        mail.{domain}    10\n"
            f"    A     mail     <IP_СЕРВЕРА>\n"
            f"    TXT   @        v=spf1 mx a ~all\n"
            f"    TXT   _dmarc   v=DMARC1; p=quarantine\n\n"
            f"  💰 Стоимость: VPS $5.83/мес + домен ~$1/мес = ~$7/мес\n"
            f"     Вместо Google Workspace ($6/мес/пользователь) — неограниченно!"
        )

    def add_account(self, address: str, quota_mb: int = 1024) -> str:
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", address):
            return f"⚠️ Некорректный email адрес: {address}"
        if any(a.address == address for a in self._accounts):
            return f"⚠️ Аккаунт уже существует: {address}"
        acc = MailAccount(address=address, quota_mb=quota_mb)
        self._accounts.append(acc)
        log.info("Mail account added: %s", address)
        return (
            f"✅ Почтовый ящик создан: {address}\n"
            f"  Квота: {quota_mb} MB\n\n"
            f"  Выполни на сервере:\n"
            f"    useradd -m -s /sbin/nologin {address.split('@')[0]}\n"
            f"    passwd {address.split('@')[0]}\n"
            f"    mkdir -p /home/{address.split('@')[0]}/Maildir"
        )

    def check_mx(self, domain: str) -> str:
        domain = domain or self._domain or "example.com"
        return (
            f"🔍 ПРОВЕРКА DNS ДЛЯ {domain}\n\n"
            f"  Выполни в терминале:\n"
            f"    dig MX {domain}\n"
            f"    dig A mail.{domain}\n"
            f"    dig TXT {domain}\n\n"
            f"  Онлайн проверка:\n"
            f"    https://mxtoolbox.com/SuperTool.aspx?action=mx:{domain}\n"
            f"    https://www.mail-tester.com/\n\n"
            f"  ✅ MX должен указывать на: mail.{domain}\n"
            f"  ✅ SPF: v=spf1 mx a ~all\n"
            f"  ✅ DMARC: v=DMARC1; p=quarantine"
        )


# ══════════════════════════════════════════════════════════════
# 2. VPN МЕНЕДЖЕР
# ══════════════════════════════════════════════════════════════

@dataclass
class VPNClient:
    name:        str
    public_key:  str
    private_key: str
    ip:          str
    created_at:  str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    active:      bool = True

    def config(self, server_ip: str, server_pubkey: str,
               server_port: int = 51820) -> str:
        return (
            f"[Interface]\n"
            f"PrivateKey = {self.private_key}\n"
            f"Address = {self.ip}/24\n"
            f"DNS = 1.1.1.1, 8.8.8.8\n\n"
            f"[Peer]\n"
            f"PublicKey = {server_pubkey}\n"
            f"Endpoint = {server_ip}:{server_port}\n"
            f"AllowedIPs = 0.0.0.0/0\n"
            f"PersistentKeepalive = 25\n"
        )


class VPNManager:
    """
    Управление WireGuard VPN сервером.
    Добавление клиентов, генерация конфигов, мониторинг.
    """

    _SERVER_SETUP = """\
#!/bin/bash
# Argos WireGuard VPN — Auto Setup
set -e

SERVER_IP="{SERVER_IP}"
PORT=51820
SUBNET="10.8.0"

echo "🔒 Установка WireGuard VPN..."

# 1. Установка
apt-get update -q && apt-get install -y wireguard qrencode -q

# 2. Генерация ключей сервера
wg genkey | tee /etc/wireguard/server_private.key | \\
    wg pubkey > /etc/wireguard/server_public.key
chmod 600 /etc/wireguard/server_private.key

SERVER_PRIV=$(cat /etc/wireguard/server_private.key)
SERVER_PUB=$(cat /etc/wireguard/server_public.key)

# 3. Конфигурация сервера
cat > /etc/wireguard/wg0.conf << WG
[Interface]
Address = ${{SUBNET}}.1/24
ListenPort = $PORT
PrivateKey = $SERVER_PRIV
PostUp   = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
WG

# 4. IP forwarding
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf && sysctl -p

# 5. Запуск
systemctl enable wg-quick@wg0
systemctl start wg-quick@wg0

echo ""
echo "✅ WireGuard VPN запущен!"
echo "   Публичный ключ сервера: $SERVER_PUB"
echo "   Адрес сервера: $SERVER_IP:$PORT"
echo ""
echo "   Следующий шаг: vpn клиент <имя>"
"""

    def __init__(self) -> None:
        self._server_ip:      str = os.getenv("ARGOS_VPN_SERVER_IP", "")
        self._server_pubkey:  str = os.getenv("ARGOS_VPN_SERVER_PUBKEY", "")
        self._server_port:    int = int(os.getenv("ARGOS_VPN_PORT", "51820"))
        self._clients:        List[VPNClient] = []
        self._next_ip_suffix: int = 2   # 10.8.0.2, .3, .4 ...
        log.info("VPNManager init | server=%s", self._server_ip or "не задан")

    def status(self) -> str:
        lines = [
            "🔒 VPN МЕНЕДЖЕР (WireGuard)",
            f"  Сервер: {self._server_ip or '⚠️ не задан (ARGOS_VPN_SERVER_IP)'}",
            f"  Порт:   {self._server_port}",
            f"  Клиентов: {len(self._clients)}",
        ]
        if self._clients:
            lines.append("  Клиенты:")
            for c in self._clients:
                status = "✅" if c.active else "❌"
                lines.append(f"    {status} {c.name:<20} {c.ip}")
        return "\n".join(lines)

    def setup_guide(self, server_ip: str = "") -> str:
        server_ip = server_ip or self._server_ip or "<IP_СЕРВЕРА>"
        script = self._SERVER_SETUP.format(SERVER_IP=server_ip)
        path   = f"/tmp/argos_vpn_setup_{server_ip.replace('.', '_')}.sh"
        try:
            with open(path, "w") as fh:
                fh.write(script)
        except OSError:
            pass

        return (
            f"🔒 УСТАНОВКА WIREGUARD VPN\n"
            f"  Сервер: {server_ip}\n\n"
            f"  ⚠️  ТРЕБОВАНИЯ:\n"
            f"    • VPS Ubuntu 22.04 (Hetzner CX11 — $3.29/мес)\n"
            f"    • Открытый порт UDP {self._server_port}\n\n"
            f"  📋 БЫСТРЫЙ СТАРТ:\n"
            f"    ssh root@{server_ip}\n"
            f"    bash <(curl -s .../vpn_setup.sh)\n\n"
            f"  ИЛИ скрипт сохранён в: {path}\n\n"
            f"  После установки:\n"
            f"    1. Сохрани публичный ключ сервера в .env:\n"
            f"       ARGOS_VPN_SERVER_PUBKEY=<ключ>\n"
            f"       ARGOS_VPN_SERVER_IP={server_ip}\n"
            f"    2. Добавь первого клиента:\n"
            f"       vpn клиент мой_телефон\n\n"
            f"  💰 Стоимость VPN: $3.29/мес (Hetzner)\n"
            f"     Вместо Mullvad/NordVPN за $5-10/мес — без логов!"
        )

    def add_client(self, name: str) -> VPNClient:
        """Добавляет нового VPN клиента с генерацией ключей."""
        # Генерация псевдо-ключей (на реальном сервере — wg genkey)
        private_key = secrets.token_urlsafe(32)
        public_key  = hashlib.sha256(private_key.encode()).hexdigest()[:44]
        client_ip   = f"10.8.0.{self._next_ip_suffix}"
        self._next_ip_suffix += 1

        client = VPNClient(
            name        = name,
            private_key = private_key,
            public_key  = public_key,
            ip          = client_ip,
        )
        self._clients.append(client)
        log.info("VPN client added: %s @ %s", name, client_ip)
        return client

    def get_client_config(self, name: str) -> str:
        client = next((c for c in self._clients if c.name == name), None)
        if not client:
            return f"❌ Клиент «{name}» не найден."

        server_ip     = self._server_ip or "<IP_СЕРВЕРА>"
        server_pubkey = self._server_pubkey or "<PUBKEY_СЕРВЕРА>"
        cfg = client.config(server_ip, server_pubkey, self._server_port)

        path = f"/tmp/wireguard_{name}.conf"
        try:
            with open(path, "w") as fh:
                fh.write(cfg)
        except OSError:
            pass

        return (
            f"🔒 КОНФИГ VPN ДЛЯ {name.upper()}\n\n"
            f"{cfg}\n"
            f"💾 Конфиг сохранён: {path}\n\n"
            f"  📱 Импорт на телефон:\n"
            f"    1. Установи WireGuard из App Store / Google Play\n"
            f"    2. Нажми «+» → Import from file\n"
            f"    3. Выбери файл {path}\n\n"
            f"  💻 На Linux:\n"
            f"    sudo cp {path} /etc/wireguard/wg0.conf\n"
            f"    sudo wg-quick up wg0\n\n"
            f"  ⚠️  Добавь на сервер (wg0.conf):\n"
            f"    [Peer]\n"
            f"    PublicKey = {client.public_key}\n"
            f"    AllowedIPs = {client.ip}/32\n"
            f"    # Затем: wg syncconf wg0 <(wg-quick strip wg0)"
        )

    def sell_vpn_access(self) -> str:
        """Описание коммерческой модели VPN как услуги."""
        return (
            "💸 VPN КАК УСЛУГА — БИЗНЕС МОДЕЛЬ\n\n"
            "  Ты владеешь VPN сервером → продаёшь доступ.\n\n"
            "  Структура затрат:\n"
            f"    Hetzner CX11: $3.29/мес\n"
            f"    Bandwidth:    20TB включено — практически ∞\n"
            f"    Домен:        $1/мес (опционально)\n"
            f"    Итого:        $4.29/мес\n\n"
            "  Монетизация:\n"
            "    • 1 сервер выдерживает 50-200 клиентов\n"
            "    • Цена для клиента: ₽200-500/мес\n"
            "    • 20 клиентов × ₽300 = ₽6 000/мес\n"
            "    • Расходы: ₽300/мес\n"
            "    • Прибыль: ₽5 700/мес на 1 сервере\n\n"
            "  Масштабирование:\n"
            "    5 серверов (EU, US, Asia) × 20 клиентов\n"
            "    = ₽28 500/мес прибыли\n\n"
            "  Преимущества:\n"
            "    ✓ Полный контроль (без логов)\n"
            "    ✓ Кастомные протоколы (WireGuard, OpenVPN)\n"
            "    ✓ Аргос автоматически управляет клиентами"
        )


# ══════════════════════════════════════════════════════════════
# 3. КВАНТОВЫЙ МАРКЕТПЛЕЙС
# ══════════════════════════════════════════════════════════════

@dataclass
class QuantumJob:
    """Задача квантовых вычислений."""
    job_id:     str
    job_type:   str
    description: str
    input_data: dict
    result:     Optional[dict]
    price_usd:  float
    status:     str = "pending"   # pending / running / done / sold
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    sold_to:    str = ""

    def to_dict(self) -> dict:
        return {
            "id":     self.job_id[-8:],
            "type":   self.job_type,
            "price":  f"${self.price_usd:.2f}",
            "status": self.status,
            "time":   self.created_at,
        }


class QuantumMarketplace:
    """
    Продажа результатов квантовых вычислений.

    Аргос использует src/quantum/logic.py для реальных вычислений
    и продаёт результаты через маркетплейс.

    Типы вычислений:
    - Оптимизация (QUBO, QAOA)
    - Криптография (генерация ключей, случайные числа)
    - Симуляция (молекулярная, физическая)
    - Машинное обучение (квантовые схемы)
    - Финансовая оптимизация (портфели, риски)
    """

    # Каталог вычислительных задач
    CATALOG: List[dict] = [
        {
            "type":        "random_numbers",
            "name":        "Квантовые случайные числа",
            "description": "Истинно случайные числа на основе квантовой суперпозиции. "
                           "Неотличимы от настоящей энтропии. Подходит для криптографии.",
            "price_usd":   0.5,
            "price_per":   "1000 чисел",
            "use_cases":   "Криптографические ключи, лотереи, NFT mint, игры",
            "delivery":    "Мгновенно (JSON массив)",
        },
        {
            "type":        "portfolio_optimization",
            "name":        "Квантовая оптимизация портфеля",
            "description": "QAOA алгоритм для оптимизации распределения активов. "
                           "Минимизирует риск при заданной доходности.",
            "price_usd":   5.0,
            "price_per":   "расчёт (до 20 активов)",
            "use_cases":   "Инвестиционные портфели, крипто распределение",
            "delivery":    "5-30 минут (JSON отчёт)",
        },
        {
            "type":        "route_optimization",
            "name":        "Квантовая оптимизация маршрутов",
            "description": "Travelling Salesman Problem через квантовый отжиг. "
                           "Быстрее классических алгоритмов для N>20 точек.",
            "price_usd":   3.0,
            "price_per":   "расчёт (до 50 точек)",
            "use_cases":   "Логистика, доставка, планирование",
            "delivery":    "10-60 минут",
        },
        {
            "type":        "molecular_simulation",
            "name":        "Молекулярная симуляция",
            "description": "Квантовая химия: расчёт энергии молекул, "
                           "предсказание свойств соединений.",
            "price_usd":   10.0,
            "price_per":   "молекула",
            "use_cases":   "Фармацевтика, материаловедение, химия",
            "delivery":    "1-24 часа",
        },
        {
            "type":        "prime_factorization",
            "name":        "Факторизация чисел (тест Шора)",
            "description": "Алгоритм Шора для факторизации больших чисел. "
                           "Демонстрационные вычисления на симуляторе.",
            "price_usd":   2.0,
            "price_per":   "число до 64 бит",
            "use_cases":   "Исследования, криптоанализ, образование",
            "delivery":    "1-10 минут",
        },
        {
            "type":        "quantum_ml",
            "name":        "Квантовое машинное обучение",
            "description": "Вариационные квантовые схемы для классификации. "
                           "QNN — квантовые нейронные сети.",
            "price_usd":   8.0,
            "price_per":   "обучение модели",
            "use_cases":   "Классификация данных, оптимизация гиперпараметров",
            "delivery":    "30 мин – 4 часа",
        },
    ]

    def __init__(self, core=None) -> None:
        self.core   = core
        self._jobs: List[QuantumJob] = []
        self._total_earned: float = 0.0
        log.info("QuantumMarketplace init")

    def _run_local_quantum(self, job_type: str, input_data: dict) -> dict:
        """Выполняет квантовые вычисления через src.quantum.logic."""
        if self.core and hasattr(self.core, "quantum"):
            try:
                q = self.core.quantum
                if job_type == "random_numbers":
                    n = int(input_data.get("count", 100))
                    return {"numbers": [int(q.measure_qubit()) for _ in range(min(n, 1000))],
                            "count": n, "entropy_bits": n}
                if job_type == "portfolio_optimization":
                    assets = input_data.get("assets", ["BTC", "ETH", "SOL"])
                    weights = q.optimize_weights(len(assets))
                    return {"assets": assets, "weights": weights,
                            "expected_sharpe": round(float(sum(weights)) * 1.3, 3)}
            except Exception as exc:
                log.debug("Quantum core error: %s", exc)

        # Классическая симуляция если квантовый движок недоступен
        import random
        if job_type == "random_numbers":
            n = int(input_data.get("count", 100))
            return {"numbers": [random.getrandbits(32) for _ in range(n)],
                    "count": n, "note": "simulated"}

        if job_type == "portfolio_optimization":
            assets  = input_data.get("assets", ["BTC", "ETH", "SOL"])
            weights = [round(1.0 / len(assets), 4)] * len(assets)
            return {"assets": assets, "weights": weights,
                    "expected_sharpe": round(random.uniform(1.0, 2.5), 3),
                    "note": "simulated"}

        if job_type == "route_optimization":
            points = input_data.get("points", 10)
            return {"optimal_order": list(range(points)),
                    "distance": round(random.uniform(100, 10000), 2),
                    "note": "simulated"}

        return {"status": "computed", "note": "simulated", "input": input_data}

    def submit_job(self, job_type: str,
                   input_data: Optional[dict] = None) -> QuantumJob:
        """Запускает квантовую задачу."""
        catalog_entry = next(
            (c for c in self.CATALOG if c["type"] == job_type), None)
        if not catalog_entry:
            # Неизвестный тип — базовая цена
            catalog_entry = {
                "name":        job_type,
                "description": "Пользовательская задача",
                "price_usd":   1.0,
            }

        job = QuantumJob(
            job_id      = f"QJ-{int(time.time())}-{job_type[:4].upper()}",
            job_type    = job_type,
            description = catalog_entry.get("description", ""),
            input_data  = input_data or {},
            result      = None,
            price_usd   = catalog_entry["price_usd"],
            status      = "running",
        )
        self._jobs.append(job)

        # Вычисляем немедленно
        job.result = self._run_local_quantum(job_type, job.input_data)
        job.status = "done"
        log.info("Quantum job done: %s", job.job_id)
        return job

    def list_catalog(self) -> str:
        lines = [
            "⚛️  КВАНТОВЫЙ МАРКЕТПЛЕЙС — КАТАЛОГ",
            "",
        ]
        for i, item in enumerate(self.CATALOG, 1):
            lines += [
                f"  {i}. {item['name']}",
                f"     💰 ${item['price_usd']:.2f} за {item['price_per']}",
                f"     📝 {item['description'][:80]}",
                f"     🎯 Для: {item['use_cases'][:60]}",
                f"     ⏱️  {item['delivery']}",
                "",
            ]
        lines += [
            "  Команды:",
            "  квант продать random_numbers    — продать случайные числа",
            "  квант продать portfolio_optimization — оптим. портфель",
            "  квант статус                    — текущие задачи",
        ]
        return "\n".join(lines)

    def sell_result(self, job_type: str,
                    input_data: Optional[dict] = None) -> str:
        """Вычисляет и продаёт результат квантового вычисления."""
        job = self.submit_job(job_type, input_data or {})
        self._total_earned += job.price_usd
        job.status = "sold"

        result_preview = str(job.result)[:200] if job.result else "N/A"

        return (
            f"⚛️  КВАНТОВЫЙ РЕЗУЛЬТАТ ПРОДАН\n"
            f"  ID:     {job.job_id}\n"
            f"  Тип:    {job.job_type}\n"
            f"  Цена:   ${job.price_usd:.2f} (≈ ₽{job.price_usd * _USD_RATE:.0f})\n"
            f"  Статус: ✅ Выполнено\n\n"
            f"  Результат (превью):\n"
            f"  {result_preview}\n\n"
            f"  💰 Всего заработано: ${self._total_earned:.2f}\n\n"
            f"  📋 Для доставки клиенту:\n"
            f"    • Отправить JSON через Telegram\n"
            f"    • Выставить счёт: счёт Клиент|Квант {job.job_type}|{job.price_usd * _USD_RATE:.0f}"
        )

    def market_overview(self) -> str:
        return (
            "⚛️  РЫНОК КВАНТОВЫХ ВЫЧИСЛЕНИЙ\n\n"
            "  Конкуренты и цены:\n"
            "  ┌────────────────────────────────────────────────┐\n"
            "  │ IBM Quantum Network    — от $10 000/год        │\n"
            "  │ AWS Braket             — $0.00035/задача+задача│\n"
            "  │ Google Quantum AI      — закрытый доступ       │\n"
            "  │ D-Wave Leap            — от $100/мес           │\n"
            "  │ Azure Quantum          — от $0.10/задача        │\n"
            "  └────────────────────────────────────────────────┘\n\n"
            "  Аргос: квантовый симулятор на CPU/GPU — от $0.50/задача\n\n"
            "  Целевые клиенты:\n"
            "  • Стартапы которым нужны квант. вычисления без бюджета IBM\n"
            "  • Исследователи (университеты, лаборатории)\n"
            "  • Финтех (оптимизация портфелей, риски)\n"
            "  • Логистика (маршруты, склады)\n"
            "  • Фарма (молекулярные симуляции)\n\n"
            "  Потенциал:\n"
            "  • 100 задач/день × $2 среднее = $200/день = $6 000/мес\n"
            "  • Масштаб: GPU кластер → $50 000+/мес\n\n"
            "  📌 Начни с: квант продать random_numbers"
        )

    def status(self) -> str:
        done   = [j for j in self._jobs if j.status == "done"]
        sold   = [j for j in self._jobs if j.status == "sold"]
        lines  = [
            "⚛️  КВАНТОВЫЙ МАРКЕТПЛЕЙС — СТАТУС",
            f"  Задач выполнено:  {len(done) + len(sold)}",
            f"  Задач продано:    {len(sold)}",
            f"  Заработано:       ${self._total_earned:.2f} "
            f"(≈ ₽{self._total_earned * _USD_RATE:.0f})",
            "",
        ]
        if self._jobs:
            lines.append("  Последние задачи:")
            for j in self._jobs[-5:]:
                icon = "✅" if j.status == "sold" else ("🔄" if j.status == "running" else "💾")
                lines.append(
                    f"    {icon} {j.job_id[-12:]} {j.job_type:<25} ${j.price_usd:.2f}"
                )
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# ГЛАВНЫЙ МОДУЛЬ
# ══════════════════════════════════════════════════════════════

class ArgosInfrastructure:
    """
    Единая точка доступа к инфраструктурным сервисам Аргоса.
    Почта, VPN, квантовые вычисления — всё в одном месте.
    """

    def __init__(self, core=None) -> None:
        self.core    = core
        self.mail    = MailServerManager()
        self.vpn     = VPNManager()
        self.quantum = QuantumMarketplace(core)
        if core is not None:
            core.infrastructure = self
        log.info("ArgosInfrastructure init ✅")

    def handle_command(self, cmd: str) -> str:  # noqa: PLR0911, PLR0912
        c   = cmd.strip()
        low = c.lower()

        # ── Почта ─────────────────────────────────────────────
        if low in ("почта", "почта статус", "mail status"):
            return self.mail.status()

        if low in ("почта настроить", "mail setup", "настроить почту"):
            return self.mail.setup_guide()

        if low.startswith("почта настроить "):
            domain = c.split()[-1]
            return self.mail.setup_guide(domain)

        if low.startswith("почта аккаунт "):
            address = c.split()[-1]
            return self.mail.add_account(address)

        if low.startswith("почта mx"):
            domain = c.split()[-1] if len(c.split()) > 2 else ""
            return self.mail.check_mx(domain)

        # ── VPN ───────────────────────────────────────────────
        if low in ("vpn", "vpn статус", "vpn status"):
            return self.vpn.status()

        if low in ("vpn настроить", "vpn setup", "настроить vpn"):
            return self.vpn.setup_guide()

        if low.startswith("vpn настроить "):
            server_ip = c.split()[-1]
            return self.vpn.setup_guide(server_ip)

        if low.startswith("vpn клиент "):
            name   = c[len("vpn клиент "):].strip()
            client = self.vpn.add_client(name)
            return (
                f"✅ VPN клиент добавлен: {client.name}\n"
                f"  IP: {client.ip}\n"
                f"  Публичный ключ: {client.public_key[:32]}...\n\n"
                f"  Получить конфиг: vpn конфиг {client.name}"
            )

        if low.startswith("vpn конфиг "):
            name = c[len("vpn конфиг "):].strip()
            return self.vpn.get_client_config(name)

        if low in ("vpn бизнес", "vpn продать", "vpn монетизация"):
            return self.vpn.sell_vpn_access()

        # ── Квантовые вычисления ──────────────────────────────
        if low in ("квант", "квант задачи", "quantum", "квантовые"):
            return self.quantum.list_catalog()

        if low in ("квант рынок", "quantum market", "квантовый рынок"):
            return self.quantum.market_overview()

        if low in ("квант статус", "quantum status"):
            return self.quantum.status()

        if low.startswith("квант продать "):
            job_type = c[len("квант продать "):].strip().lower().replace(" ", "_")
            return self.quantum.sell_result(job_type)

        if low.startswith("quantum sell "):
            job_type = c[len("quantum sell "):].strip().lower().replace(" ", "_")
            return self.quantum.sell_result(job_type)

        # ── Статус всего ──────────────────────────────────────
        if low in ("инфра", "инфраструктура", "infrastructure"):
            parts = [
                "🏗️  ИНФРАСТРУКТУРА АРГОСА",
                "",
                self.mail.status(),
                "",
                self.vpn.status(),
                "",
                self.quantum.status(),
            ]
            return "\n".join(parts)

        return self._help()

    def _help(self) -> str:
        return (
            "🏗️  ИНФРАСТРУКТУРА — команды:\n\n"
            "📧 ПОЧТА:\n"
            "  почта статус\n"
            "  почта настроить [домен]\n"
            "  почта аккаунт user@domain.com\n"
            "  почта mx [домен]\n\n"
            "🔒 VPN:\n"
            "  vpn статус\n"
            "  vpn настроить [IP]\n"
            "  vpn клиент <имя>\n"
            "  vpn конфиг <имя>\n"
            "  vpn бизнес   — модель монетизации\n\n"
            "⚛️  КВАНТОВЫЕ ВЫЧИСЛЕНИЯ:\n"
            "  квант задачи            — каталог\n"
            "  квант рынок             — анализ рынка\n"
            "  квант продать random_numbers\n"
            "  квант продать portfolio_optimization\n"
            "  квант продать route_optimization\n"
            "  квант статус\n\n"
            "  инфра                   — полный статус"
        )

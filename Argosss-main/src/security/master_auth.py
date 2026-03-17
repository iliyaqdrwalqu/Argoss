"""
master_auth.py — SHA-256 авторизация администратора Argos.
Защита от несанкционированного доступа к командам с привилегиями.
"""
import os
import hashlib
import hmac
import time
from typing import Optional
from src.argos_logger import get_logger

log = get_logger("argos.master_auth")

MAX_ATTEMPTS = 5
COOLDOWN_SEC = 60


class MasterKeyAuth:
    def __init__(self):
        self._key_hash: Optional[str] = self._load_key_hash()
        self._attempts = 0
        self._lockout_ts = 0.0
        self.is_configured = bool(self._key_hash)
        self._session_verified = False
        log.info("Master Auth: %s", "configured" if self.is_configured else "pass-through")

    def _load_key_hash(self) -> Optional[str]:
        raw = (os.getenv("ARGOS_MASTER_KEY", "") or "").strip()
        if raw:
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()
        # Проверяем файл
        key_file = "config/master_auth.hash"
        if os.path.exists(key_file):
            try:
                with open(key_file) as f:
                    return f.read().strip()
            except Exception:
                pass
        return None

    def verify(self, provided_key: str) -> bool:
        """Проверяет ключ. Thread-safe constant-time comparison."""
        if not self.is_configured:
            self._session_verified = True
            return True
        now = time.time()
        if self._attempts >= MAX_ATTEMPTS and (now - self._lockout_ts) < COOLDOWN_SEC:
            remaining = int(COOLDOWN_SEC - (now - self._lockout_ts))
            log.warning("Master Auth: lockout (%ds remaining)", remaining)
            return False

        provided_hash = hashlib.sha256(
            (provided_key or "").strip().encode("utf-8")
        ).hexdigest()
        ok = hmac.compare_digest(provided_hash, self._key_hash or "")
        if ok:
            self._attempts = 0
            self._session_verified = True
            log.info("Master Auth: verified OK")
        else:
            self._attempts += 1
            self._lockout_ts = now
            log.warning("Master Auth: failed attempt %d/%d", self._attempts, MAX_ATTEMPTS)
        return ok

    def revoke_session(self) -> None:
        self._session_verified = False

    def is_session_valid(self) -> bool:
        return self._session_verified or not self.is_configured

    def set_key(self, new_key: str) -> str:
        if len(new_key) < 16:
            return "❌ Ключ должен быть не менее 16 символов"
        h = hashlib.sha256(new_key.encode()).hexdigest()
        os.makedirs("config", exist_ok=True)
        with open("config/master_auth.hash", "w") as f:
            f.write(h)
        os.chmod("config/master_auth.hash", 0o600)
        self._key_hash = h
        self.is_configured = True
        return "✅ Master Key обновлён"

    def status(self) -> str:
        locked = (self._attempts >= MAX_ATTEMPTS and
                  (time.time() - self._lockout_ts) < COOLDOWN_SEC)
        return (
            f"🔐 MASTER AUTH:\n"
            f"  Настроен:    {'✅' if self.is_configured else '❌ (pass-through)'}\n"
            f"  Сессия:      {'✅ активна' if self._session_verified else '❌ не верифицирована'}\n"
            f"  Попыток:     {self._attempts}/{MAX_ATTEMPTS}\n"
            f"  Блокировка:  {'🔒 ДА' if locked else 'нет'}"
        )


_auth: Optional[MasterKeyAuth] = None

def get_auth() -> MasterKeyAuth:
    global _auth
    if _auth is None:
        _auth = MasterKeyAuth()
    return _auth

# Alias для совместимости
MasterAuth = MasterKeyAuth

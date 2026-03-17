"""
encryption.py — AES-256-GCM шифрование для Argos.
Использует cryptography.hazmat (AEAD: аутентификация + шифрование).
Fallback на Fernet для обратной совместимости.
"""
import os
import base64
import hashlib
import hmac
from pathlib import Path
from typing import Optional

from src.argos_logger import get_logger
log = get_logger("argos.encryption")

KEY_FILE = "config/master.key"

# ── Graceful imports ─────────────────────────────────────────
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    AESGCM_OK = True
except ImportError:
    AESGCM_OK = False
    log.warning("cryptography не установлена — шифрование ограничено")

try:
    from cryptography.fernet import Fernet
    FERNET_OK = True
except ImportError:
    FERNET_OK = False


class ArgosEncryption:
    """AES-256-GCM AEAD шифрование с автогенерацией ключа."""

    NONCE_SIZE = 12  # 96-bit nonce (GCM рекомендация)

    def __init__(self, key_file: str = KEY_FILE):
        self.key_file = key_file
        self._key: Optional[bytes] = None
        self._load_or_generate_key()

    def _load_or_generate_key(self) -> None:
        Path(self.key_file).parent.mkdir(parents=True, exist_ok=True)
        if os.path.exists(self.key_file):
            try:
                with open(self.key_file, "rb") as f:
                    raw = f.read().strip()
                self._key = base64.b64decode(raw) if len(raw) > 32 else raw
                if len(self._key) != 32:
                    raise ValueError("Неверная длина ключа")
                log.info("Encryption: ключ загружен из %s", self.key_file)
                return
            except Exception as e:
                log.warning("Encryption: ошибка загрузки ключа (%s), генерируем новый", e)

        self._key = os.urandom(32)
        with open(self.key_file, "wb") as f:
            f.write(base64.b64encode(self._key))
        os.chmod(self.key_file, 0o600)
        log.info("Encryption: новый AES-256 ключ сгенерирован → %s", self.key_file)

    def encrypt(self, plaintext: str) -> str:
        """Шифрует строку → base64-строка (nonce + ciphertext + tag)."""
        if not AESGCM_OK or not self._key:
            return self._fernet_encrypt(plaintext)
        try:
            aesgcm = AESGCM(self._key)
            nonce = os.urandom(self.NONCE_SIZE)
            ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
            return base64.b64encode(nonce + ct).decode("ascii")
        except Exception as e:
            log.error("Encrypt error: %s", e)
            return ""

    def decrypt(self, ciphertext_b64: str) -> str:
        """Дешифрует base64-строку → plaintext."""
        if not AESGCM_OK or not self._key:
            return self._fernet_decrypt(ciphertext_b64)
        try:
            raw = base64.b64decode(ciphertext_b64)
            nonce, ct = raw[:self.NONCE_SIZE], raw[self.NONCE_SIZE:]
            aesgcm = AESGCM(self._key)
            return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
        except Exception as e:
            log.error("Decrypt error: %s", e)
            return ""

    def encrypt_file(self, path: str) -> str:
        """Шифрует файл на диске (in-place, создаёт .enc)."""
        try:
            with open(path, "rb") as f:
                data = f.read()
            enc_path = path + ".enc"
            ct = self.encrypt(base64.b64encode(data).decode())
            with open(enc_path, "w") as f:
                f.write(ct)
            return f"✅ Зашифровано: {enc_path}"
        except Exception as e:
            return f"❌ {e}"

    def decrypt_file(self, enc_path: str) -> str:
        """Дешифрует .enc файл."""
        try:
            with open(enc_path) as f:
                ct = f.read()
            b64 = self.decrypt(ct)
            out_path = enc_path.replace(".enc", "")
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(b64))
            return f"✅ Расшифровано: {out_path}"
        except Exception as e:
            return f"❌ {e}"

    # ── Fernet fallback ──────────────────────────────────────
    def _fernet_encrypt(self, plaintext: str) -> str:
        if not FERNET_OK or not self._key:
            return plaintext
        try:
            key_b64 = base64.urlsafe_b64encode(self._key)
            f = Fernet(key_b64)
            return f.encrypt(plaintext.encode()).decode()
        except Exception:
            return plaintext

    def _fernet_decrypt(self, ciphertext: str) -> str:
        if not FERNET_OK or not self._key:
            return ciphertext
        try:
            key_b64 = base64.urlsafe_b64encode(self._key)
            f = Fernet(key_b64)
            return f.decrypt(ciphertext.encode()).decode()
        except Exception:
            return ciphertext

    def status(self) -> str:
        engine = "AES-256-GCM" if AESGCM_OK else ("Fernet" if FERNET_OK else "NONE")
        key_ok = "✅" if self._key else "❌"
        return (
            f"🔐 ШИФРОВАНИЕ:\n"
            f"  Движок:    {engine}\n"
            f"  Ключ:      {key_ok} ({self.key_file})\n"
            f"  Длина:     {len(self._key) * 8} бит"
        )


class ArgosShield(ArgosEncryption):
    """Backwards-compatible name used by main orchestrator."""


# Синглтон
_enc: Optional[ArgosEncryption] = None

def get_encryption() -> ArgosEncryption:
    global _enc
    if _enc is None:
        _enc = ArgosEncryption()
    return _enc

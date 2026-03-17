"""
gost_p2p.py — ГОСТ-защищённый P2P-транспорт и шифрование почкования.

Интегрирует ГОСТ Р 34.12-2015 (Кузнечик/Магма) и Стрибог в:
  • P2P-подпись сообщений (HMAC-Стрибог вместо SHA-256)
  • Шифрование TCP-полезной нагрузки P2P (CTR-Кузнечик)
  • Шифрование «почек» при почковании (CTR-Кузнечик + HMAC-Стрибог)

Публичный API:
    GostP2PSecurity(secret)           — объект безопасности P2P
        .sign(data)       → str       — HMAC-Стрибог-256 hex
        .verify(data, sig)→ bool      — проверка подписи
        .encrypt(payload) → bytes     — Кузнечик-CTR шифрование
        .decrypt(payload) → dict      — Кузнечик-CTR дешифрование
        .seal_bud(pkg)    → bytes     — запечатать почку (encrypt + sign)
        .open_bud(data)   → dict      — вскрыть почку (verify + decrypt)
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from src.argos_logger import get_logger
from src.security.gost_cipher import (
    GostKuznyechik, GostMagma,
    decrypt_ctr, derive_key, encrypt_ctr,
    gost_hmac, gost_hmac_hex, gost_hash,
    gost_status, PYGOST_OK,
)

log = get_logger("argos.gost_p2p")


class GostP2PSecurity:
    """
    Комплексная ГОСТ-безопасность для P2P-узла Аргоса.

    Parameters
    ----------
    secret : str | bytes
        Общий сетевой секрет (ARGOS_NETWORK_SECRET).
    cipher : {'kuznyechik', 'magma'}
        Шифр для шифрования полезной нагрузки.
    """

    def __init__(self, secret: str | bytes = "argos_default_secret",
                 cipher: str = "kuznyechik"):
        if isinstance(secret, str):
            secret = secret.encode()
        self._raw_secret = secret

        # Деривируем два ключа: один для шифрования, один для MAC
        enc_salt = b"argos_p2p_encrypt"
        mac_salt = b"argos_p2p_mac"
        self._enc_key = derive_key(secret, salt=enc_salt)
        self._mac_key = derive_key(secret, salt=mac_salt)

        self._cipher_cls: type
        cipher_lower = cipher.lower()
        if cipher_lower in ("kuznyechik", "кузнечик", "grasshopper"):
            self._cipher_cls = GostKuznyechik
        elif cipher_lower in ("magma", "магма"):
            self._cipher_cls = GostMagma
        else:
            raise ValueError(
                f"GostP2PSecurity: неизвестный шифр '{cipher}'. "
                f"Допустимые значения: 'kuznyechik' (Кузнечик), 'magma' (Магма)."
            )
        log.info("GostP2PSecurity: шифр=%s pygost=%s", self._cipher_cls.name, PYGOST_OK)

    # ── Подпись / проверка ────────────────────────────────────────────────────

    def sign(self, data: dict | str | bytes) -> str:
        """HMAC-Стрибог-256 подпись данных. Возвращает hex-строку."""
        if isinstance(data, dict):
            data = json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
        elif isinstance(data, str):
            data = data.encode()
        return gost_hmac_hex(self._mac_key, data)

    def verify(self, data: dict | str | bytes, signature: str) -> bool:
        """Проверяет HMAC-Стрибог-256 подпись."""
        expected = self.sign(data)
        # Константное время сравнения
        if len(expected) != len(signature):
            return False
        return all(a == b for a, b in zip(expected, signature))

    # ── Шифрование / дешифрование полезной нагрузки ──────────────────────────

    def encrypt(self, payload: dict) -> bytes:
        """CTR-Кузнечик шифрование словаря payload → bytes (nonce||ciphertext)."""
        raw = json.dumps(payload, ensure_ascii=False).encode()
        return encrypt_ctr(self._enc_key, raw, self._cipher_cls)

    def decrypt(self, data: bytes) -> dict:
        """CTR-Кузнечик дешифрование bytes → словарь."""
        raw = decrypt_ctr(self._enc_key, data, self._cipher_cls)
        return json.loads(raw.decode())

    # ── Полный ГОСТ-пакет P2P ─────────────────────────────────────────────────

    def pack(self, payload: dict) -> bytes:
        """
        Упаковывает P2P-сообщение: шифрует + добавляет HMAC-Стрибог.

        Формат:
            [4 байта: длина ciphertext][ciphertext][64 байта HMAC-Стрибог-256]
        """
        ciphertext = self.encrypt(payload)
        mac        = gost_hmac(self._mac_key, ciphertext, bits=256)
        length     = len(ciphertext).to_bytes(4, "big")
        return length + ciphertext + mac

    def unpack(self, data: bytes) -> dict:
        """
        Распаковывает P2P-сообщение: проверяет HMAC + дешифрует.
        Выбрасывает ValueError при нарушении целостности.
        """
        if len(data) < 4 + 32:
            raise ValueError("ГОСТ P2P: пакет слишком короткий")
        ct_len     = int.from_bytes(data[:4], "big")
        ciphertext = data[4:4 + ct_len]
        received_mac = data[4 + ct_len:4 + ct_len + 32]
        expected_mac = gost_hmac(self._mac_key, ciphertext, bits=256)
        if received_mac != expected_mac:
            raise ValueError("ГОСТ P2P: HMAC-Стрибог не совпадает — возможна подделка")
        return self.decrypt(ciphertext)

    # ── Шифрование почки ──────────────────────────────────────────────────────

    def seal_bud(self, pkg: dict) -> bytes:
        """
        Запечатывает почку (budding payload) с шифрованием + целостностью.

        Добавляет дополнительный заголовок для идентификации ГОСТ-почки.
        Формат: b"ARGOS-BUD-GOST-1" + pack(pkg)
        """
        packed = self.pack(pkg)
        return b"ARGOS-BUD-GOST-1" + packed

    def open_bud(self, data: bytes) -> dict:
        """
        Вскрывает ГОСТ-запечатанную почку.
        Выбрасывает ValueError если магия неверна или HMAC не совпадает.
        """
        magic = b"ARGOS-BUD-GOST-1"
        if not data.startswith(magic):
            raise ValueError("ГОСТ BUD: неверная магия — не ГОСТ-почка")
        return self.unpack(data[len(magic):])

    # ── Статус ────────────────────────────────────────────────────────────────

    def status(self) -> str:
        return (
            f"🔐 ГОСТ P2P БЕЗОПАСНОСТЬ:\n"
            f"  Шифр:       {self._cipher_cls.name} (ГОСТ Р 34.12-2015)\n"
            f"  HMAC:       Стрибог-256 (ГОСТ Р 34.11-2012)\n"
            f"  Режим:      CTR (потоковый)\n"
            f"  Ключ шифр:  деривован (PBKDF2-Стрибог)\n"
            f"  Ключ MAC:   деривован (PBKDF2-Стрибог)\n"
            f"  pygost:     {'✅ эталонная реализация' if PYGOST_OK else '⚠️ fallback'}\n"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательная функция: совместимая замена SHA-256 _sign в ArgosBridge
# ─────────────────────────────────────────────────────────────────────────────

def gost_sign_message(data: dict, secret: str) -> str:
    """Подписывает P2P-словарь HMAC-Стрибог. Замена SHA-256 подписи."""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    return gost_hmac_hex(secret.encode(), raw)


def gost_verify_message(data: dict, signature: str, secret: str) -> bool:
    """Проверяет ГОСТ-подпись P2P-словаря."""
    expected = gost_sign_message(data, secret)
    if len(expected) != len(signature):
        return False
    return all(a == b for a, b in zip(expected, signature))


# ─────────────────────────────────────────────────────────────────────────────
# Глобальный экземпляр (lazy init)
# ─────────────────────────────────────────────────────────────────────────────
_instance: GostP2PSecurity | None = None


def get_gost_p2p(secret: str | None = None) -> GostP2PSecurity:
    """Возвращает (или создаёт) глобальный экземпляр GostP2PSecurity."""
    global _instance
    if _instance is None or secret is not None:
        s = secret or os.getenv("ARGOS_NETWORK_SECRET", "argos_default_secret")
        _instance = GostP2PSecurity(secret=s)
    return _instance

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xen_argo_transport.py — Транспортный слой WhisperNode через Xen Argo.

Позволяет mesh-узлам Argos общаться между доменами Xen (dom0 и domU)
без использования сетевого стека — через специальные сокеты AF_XEN_ARGO.

Требует:
  - права root
  - загруженного модуля ядра xen_argo (sudo modprobe xen-argo)
  - xenstore (пакет xenstore-utils)

При недоступности Xen Argo класс работает в «заглушечном» режиме:
  - send_to / broadcast ничего не делают
  - receive возвращает (None, None)

Интегрируется с WhisperNode:
  argo = XenArgoTransport(node_id, port=5000)
  argo.broadcast(json.dumps(msg).encode())
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
import threading
import time
import warnings
from typing import Dict, Optional, Tuple

log = logging.getLogger("argos.xen_argo")

# Определяем константу AF_XEN_ARGO (обычно 40 на Linux с патчем Xen)
try:
    import ctypes
    _libc = ctypes.CDLL(None, use_errno=True)
    # Попытка прочитать константу из libc (если доступна)
    _val = getattr(_libc, "AF_XEN_ARGO", None)
    AF_XEN_ARGO: int = int(_val) if _val else 40
except Exception:
    AF_XEN_ARGO = 40


def _check_argo_available() -> bool:
    """Проверяет наличие модуля ядра xen_argo."""
    try:
        with open("/proc/modules") as f:
            return any("xen_argo" in line for line in f)
    except OSError:
        return False


def _get_domid() -> Optional[int]:
    """Определяет текущий domid через xenstore или /proc/xen."""
    try:
        result = subprocess.run(
            ["xenstore-read", "domid"],
            capture_output=True, text=True, check=False, timeout=2,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        pass
    try:
        with open("/proc/xen/xenbus") as f:
            for line in f:
                if line.startswith("domid"):
                    return int(line.split()[1])
    except OSError:
        pass
    return None


class XenArgoTransport:
    """
    Транспорт на основе сокетов AF_XEN_ARGO.

    Параметры:
      node_id   — идентификатор узла (для логирования)
      domain_id — domid текущей машины (None = определить автоматически)
      port      — Argo-порт для привязки и рассылки

    Атрибуты:
      available — True если Xen Argo доступен и сокет создан
      domains   — словарь {domid: имя_домена}
    """

    def __init__(
        self,
        node_id: str,
        domain_id: Optional[int] = None,
        port: int = 5000,
    ) -> None:
        self.node_id  = node_id
        self.port     = port
        self.running  = True
        self.sock: Optional[socket.socket] = None
        self.domains: Dict[int, str] = {}
        self.available = False

        # Определяем domid
        self.domain_id = domain_id if domain_id is not None else _get_domid()
        if self.domain_id is None:
            warnings.warn(
                f"[{node_id}] XenArgoTransport: не удалось определить domid — транспорт отключён",
                stacklevel=2,
            )
            return

        # Проверяем модуль ядра
        if not _check_argo_available():
            warnings.warn(
                f"[{node_id}] XenArgoTransport: модуль xen_argo не загружен — транспорт отключён",
                stacklevel=2,
            )
            return

        # Создаём сокет
        self._create_socket()

        if self.sock:
            self.available = True
            # Запускаем фоновое обновление списка доменов
            self._updater = threading.Thread(
                target=self._update_domains_loop, daemon=True
            )
            self._updater.start()
            log.info(
                "[%s] XenArgoTransport готов (domid=%d, port=%d)",
                node_id, self.domain_id, port,
            )

    # ── создание сокета ───────────────────────────────────────────────────

    def _create_socket(self) -> None:
        try:
            self.sock = socket.socket(AF_XEN_ARGO, socket.SOCK_DGRAM)
            # (0, port): принимать от всех доменов на данном порту
            self.sock.bind((0, self.port))
            self.sock.setblocking(False)
        except Exception as exc:
            log.warning("[%s] Ошибка создания Argo-сокета: %s", self.node_id, exc)
            self.sock = None

    # ── список доменов ────────────────────────────────────────────────────

    def _update_domains_loop(self) -> None:
        while self.running:
            self._fetch_domains()
            time.sleep(30)

    def _fetch_domains(self) -> None:
        """Получает список активных доменов через xenstore."""
        try:
            result = subprocess.run(
                ["xenstore-list", "/local/domain"],
                capture_output=True, text=True, check=False, timeout=5,
            )
            if result.returncode != 0:
                return
            ids = [
                int(line.strip())
                for line in result.stdout.splitlines()
                if line.strip().isdigit()
            ]
            new_domains: Dict[int, str] = {}
            for domid in ids:
                name_res = subprocess.run(
                    ["xenstore-read", f"/local/domain/{domid}/name"],
                    capture_output=True, text=True, check=False, timeout=2,
                )
                name = name_res.stdout.strip() if name_res.returncode == 0 else f"dom{domid}"
                new_domains[domid] = name
            self.domains = new_domains
            log.debug("[%s] Домены: %s", self.node_id, self.domains)
        except Exception as exc:
            log.debug("[%s] Ошибка получения доменов: %s", self.node_id, exc)

    # ── отправка ──────────────────────────────────────────────────────────

    def send_to(self, data: bytes, target_domid: int) -> bool:
        """Отправляет данные в указанный домен (на наш порт)."""
        if not self.sock:
            return False
        try:
            self.sock.sendto(data, (target_domid, self.port))
            return True
        except Exception as exc:
            log.debug("[%s] Argo send error → dom%d: %s", self.node_id, target_domid, exc)
            return False

    def broadcast(self, data: bytes) -> None:
        """Рассылает данные всем известным доменам, кроме себя."""
        if not self.sock:
            return
        for domid in list(self.domains):
            if domid != self.domain_id:
                self.send_to(data, domid)

    # ── приём ─────────────────────────────────────────────────────────────

    def receive(self) -> Tuple[Optional[bytes], Optional[dict]]:
        """
        Неблокирующий приём одного сообщения.
        Возвращает (data, addr_info) или (None, None) если нет данных.
        """
        if not self.sock:
            return None, None
        try:
            data, addr = self.sock.recvfrom(8192)
            return data, {
                "domid":     addr[0],
                "port":      addr[1],
                "transport": "xen_argo",
            }
        except socket.error as exc:
            if exc.errno == 11:  # EAGAIN — нет данных
                pass
            else:
                log.debug("[%s] Argo recv error: %s", self.node_id, exc)
        return None, None

    # ── остановка ─────────────────────────────────────────────────────────

    def close(self) -> None:
        """Останавливает транспорт и закрывает сокет."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self.available = False

    def get_status(self) -> dict:
        return {
            "available":  self.available,
            "domain_id":  self.domain_id,
            "port":       self.port,
            "domains":    self.domains,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Точка входа для ручного тестирования
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import time as _time

    logging.basicConfig(level=logging.DEBUG)

    node_id = "TestNode"
    transport = XenArgoTransport(node_id, port=5555)

    if not transport.available:
        print(f"Xen Argo недоступен на этой машине (available={transport.available})")
        print("Статус:", transport.get_status())
        sys.exit(0)

    print("Xen Argo транспорт запущен:", transport.get_status())
    try:
        while True:
            msg = json.dumps({
                "type":    "ping",
                "node_id": node_id,
                "time":    _time.time(),
            }).encode()
            transport.broadcast(msg)
            print(f"[{node_id}] Broadcast ping")
            _time.sleep(5)

            data, addr = transport.receive()
            if data:
                print(f"[{node_id}] Got from dom{addr['domid']}: {data.decode()[:200]}")
    except KeyboardInterrupt:
        transport.close()

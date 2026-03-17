#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xen_argo_transport.py — Транспортный слой для WhisperNode через Xen Argo.

Позволяет узлам Аргоса общаться между доменами Xen (dom0 ↔ domU) без
использования сетевого стека. Требует загруженного модуля ядра xen_argo
и прав root.

Если Xen Argo недоступен — транспорт отключается с предупреждением,
остальные части системы продолжают работать.
"""
from __future__ import annotations

import socket
import subprocess
import threading
import time
import warnings
from typing import Optional, Tuple

# Константа AF_XEN_ARGO (обычно 40 или 42, зависит от сборки ядра)
try:
    import ctypes
    _libc = ctypes.CDLL(None)
    AF_XEN_ARGO = int(_libc.AF_XEN_ARGO)
except Exception:
    AF_XEN_ARGO = 40   # значение по умолчанию


class XenArgoTransport:
    """
    Транспорт через сокеты AF_XEN_ARGO.

    Автоматически:
      - определяет текущий domid через xenstore
      - проверяет наличие модуля ядра xen_argo
      - периодически обновляет список активных доменов
      - поддерживает unicast send_to() и broadcast()

    Параметры
    ---------
    node_id : str
        Идентификатор узла (для логов).
    domain_id : int | None
        Xen-домен. Если None — определяется автоматически.
    port : int
        Порт Argo (аналог UDP-порта).
    """

    def __init__(self, node_id: str, domain_id: Optional[int] = None, port: int = 5000):
        self.node_id   = node_id
        self.port      = port
        self.running   = True
        self.sock: Optional[socket.socket] = None
        self.domains: dict = {}   # domid → имя

        self.domain_id = domain_id if domain_id is not None else self._get_domid()

        if self.domain_id is None:
            warnings.warn(f"[{node_id}] XenArgoTransport: domid не определён — транспорт отключён.")
            return

        if not self._check_argo_available():
            warnings.warn(f"[{node_id}] XenArgoTransport: модуль xen_argo не найден — транспорт отключён.")
            return

        self._create_socket()

        if self.sock is not None:
            self._update_thread = threading.Thread(
                target=self._update_domains_loop, daemon=True
            )
            self._update_thread.start()
            print(f"[{node_id}] XenArgoTransport: domid={self.domain_id}, port={self.port}")

    # ── Служебные методы ─────────────────────────────
    def _get_domid(self) -> Optional[int]:
        """Определяет domid через xenstore-read или /proc/xen/xenbus."""
        try:
            result = subprocess.run(
                ["xenstore-read", "domid"],
                capture_output=True, text=True, check=False, timeout=3,
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        except FileNotFoundError:
            pass

        try:
            with open("/proc/xen/xenbus") as f:
                for line in f:
                    if line.startswith("domid"):
                        return int(line.split()[1])
        except Exception:
            pass

        return None

    def _check_argo_available(self) -> bool:
        """Проверяет, загружен ли модуль xen_argo."""
        try:
            with open("/proc/modules") as f:
                for line in f:
                    if "xen_argo" in line:
                        return True
        except Exception:
            pass
        return False

    def _create_socket(self):
        try:
            self.sock = socket.socket(AF_XEN_ARGO, socket.SOCK_DGRAM)
            self.sock.bind((0, self.port))   # 0 = принимать от всех доменов
            self.sock.setblocking(False)
        except Exception as e:
            print(f"[{self.node_id}] Argo socket error: {e}")
            self.sock = None

    # ── Управление доменами ──────────────────────────
    def _update_domains_loop(self):
        while self.running:
            self._fetch_domains()
            time.sleep(30)

    def _fetch_domains(self):
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
            new_domains = {}
            for domid in ids:
                nr = subprocess.run(
                    ["xenstore-read", f"/local/domain/{domid}/name"],
                    capture_output=True, text=True, check=False, timeout=2,
                )
                new_domains[domid] = nr.stdout.strip() if nr.returncode == 0 else f"dom{domid}"
            self.domains = new_domains
        except Exception as e:
            print(f"[{self.node_id}] Argo domain fetch error: {e}")

    # ── Отправка / приём ─────────────────────────────
    def send_to(self, data: bytes, target_domid: int) -> bool:
        """Отправляет данные в указанный домен (на тот же порт)."""
        if not self.sock:
            return False
        try:
            self.sock.sendto(data, (target_domid, self.port))
            return True
        except Exception as e:
            print(f"[{self.node_id}] Argo send error: {e}")
            return False

    def broadcast(self, data: bytes):
        """Рассылает данные всем известным доменам, кроме своего."""
        if not self.sock:
            return
        for domid in list(self.domains):
            if domid != self.domain_id:
                self.send_to(data, domid)

    def receive(self) -> Tuple[Optional[bytes], Optional[dict]]:
        """
        Неблокирующий приём одного сообщения.
        Возвращает (data, addr_info) или (None, None).
        """
        if not self.sock:
            return None, None
        try:
            data, addr = self.sock.recvfrom(8192)
            return data, {"domid": addr[0], "port": addr[1], "transport": "xen_argo"}
        except socket.error as e:
            if e.errno == 11:   # EAGAIN — нет данных
                pass
            else:
                print(f"[{self.node_id}] Argo recv error: {e}")
        return None, None

    def close(self):
        """Останавливает транспорт."""
        self.running = False
        if self.sock:
            self.sock.close()
            self.sock = None


# ─────────────────────────────────────────────────
# Пример использования (запуск: python xen_argo_transport.py --dom0)
# ─────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys

    def test_node(domid: Optional[int] = None):
        import time
        label = f"TestNode-dom{domid}" if domid is not None else "TestNode"
        transport = XenArgoTransport(label, domain_id=domid, port=5555)
        try:
            while True:
                msg = json.dumps({"type": "ping", "node": label, "ts": time.time()}).encode()
                transport.broadcast(msg)
                print(f"[{label}] ping sent")
                time.sleep(5)
                data, addr = transport.receive()
                if data:
                    print(f"[{label}] got from dom{addr['domid']}: {data.decode()}")
        except KeyboardInterrupt:
            transport.close()

    if "--dom0" in sys.argv:
        test_node(0)
    elif "--domU" in sys.argv:
        test_node()
    else:
        print("Запустите с --dom0 или --domU")

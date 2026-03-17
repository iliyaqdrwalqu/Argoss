#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
budding_manager.py — Менеджер почкования узлов Аргоса.

Отвечает за создание дочерних узлов (почек) на удалённых хостах в LAN.
Алгоритм:
  1. Периодически сканирует ARP-таблицу, собирая активные хосты.
  2. Для каждого нового хоста проверяет «плодородность»:
     - открыт ли порт для приёма почек (parent.port + 1000)
     - нет ли там уже узла Argos (parent.port)
  3. Если хост подходит — сериализует код и состояние и отправляет TCP-посылку.
  4. На принимающей стороне другой BuddingManager распаковывает почку
     и запускает новый процесс WhisperNode.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from typing import Optional

log = logging.getLogger("argos.budding")

import numpy as np


class BuddingManager:
    """
    Менеджер почкования узлов.

    Параметры
    ---------
    parent_node : WhisperNode
        Родительский узел (должен иметь атрибуты: node_id, port, host,
        hidden_size, hidden_state, light_mode, rnn).
    soil_search_interval : int
        Интервал в секундах между циклами поиска «плодородной земли».
    """

    def __init__(self, parent_node, soil_search_interval: int = 60):
        self.parent   = parent_node
        self.bud_port = parent_node.port + 1000
        self.soil_search_interval = soil_search_interval
        self.running  = True
        self.known_hosts: set = set()
        self.sent_buds: dict  = defaultdict(float)   # host -> timestamp

        # ГОСТ-безопасность для шифрования почек
        self._gost = None
        try:
            from src.connectivity.gost_p2p import GostP2PSecurity
            import os as _os
            secret = _os.getenv("ARGOS_NETWORK_SECRET", "argos_default_secret")
            self._gost = GostP2PSecurity(secret=secret)
        except Exception:
            pass

        self._start_bud_listener()
        self._start_soil_search()

    # ── TCP-сервер для приёма почек ──────────────────
    def _start_bud_listener(self):
        def listener():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Привязка ко всем интерфейсам необходима для приёма почек из LAN
            sock.bind(("0.0.0.0", self.bud_port))
            sock.listen(5)
            sock.settimeout(0.5)
            while self.running:
                try:
                    conn, addr = sock.accept()
                    threading.Thread(
                        target=self._handle_incoming_bud,
                        args=(conn, addr),
                        daemon=True,
                    ).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        log.warning("%s BudListener: %s", self.parent.node_id, e)
            sock.close()

        t = threading.Thread(target=listener, daemon=True)
        t.start()
        self._listener_thread = t

    def _handle_incoming_bud(self, conn, addr):
        """Получает TCP-посылку с кодом и состоянием, запускает новый узел.
        Поддерживает ГОСТ-зашифрованные почки (ARGOS-BUD-GOST-1) и plain pickle.
        """
        try:
            chunks = []
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            data = b"".join(chunks)

            # Определяем формат: ГОСТ или plain pickle
            if data.startswith(b"ARGOS-BUD-GOST-1") and self._gost:
                try:
                    pkg = self._gost.open_bud(data)
                    log.info("%s ГОСТ-почка принята от %s", self.parent.node_id, addr[0])
                except Exception as e:
                    log.warning("%s ГОСТ проверка почки: %s", self.parent.node_id, e)
                    conn.close()
                    return
            else:
                pkg = pickle.loads(data)

            code  = pkg["code"]
            state = pkg["state"]
            target_port = pkg.get("target_port", self.parent.port + 1)

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                script_path = f.name

            new_id = f"{self.parent.node_id}_bud_{hashlib.md5(code.encode()).hexdigest()[:4]}"
            cmd = [
                sys.executable, script_path,
                "--node-id",       new_id,
                "--port",          str(target_port),
                "--hidden-size",   str(state["hidden_size"]),
            ]
            if state.get("light_mode"):
                cmd.append("--light-mode")

            hidden = state["hidden_state"]
            if isinstance(hidden, np.ndarray):
                hidden = hidden.tolist()
            cmd += [
                "--initial-state",
                json.dumps(hidden),
                "--initial-weights",
                json.dumps({
                    "W_h": state["W_h"],
                    "W_i": state["W_i"],
                    "b":   state["b"],
                }),
            ]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log.info("%s Bud launched: %s from %s", self.parent.node_id, new_id, addr[0])
        except Exception as e:
            log.error("%s Bud handle: %s", self.parent.node_id, e)
        finally:
            conn.close()

    # ── Отправка почки ───────────────────────────────
    def send_bud(
        self,
        target_ip: str,
        target_port: Optional[int] = None,
        target_bud_port: Optional[int] = None,
    ) -> bool:
        """
        Сериализует код родителя и отправляет его TCP-посылкой на
        target_ip:target_bud_port. Новый узел будет слушать на target_port.
        """
        if target_bud_port is None:
            target_bud_port = self.bud_port

        # Не отправляем на один хост чаще чем раз в 5 минут
        if time.time() - self.sent_buds.get(target_ip, 0) < 300:
            return False

        # Код для самовоспроизведения
        try:
            script = os.path.join(os.path.dirname(__file__), "whisper_node.py")
            if os.path.exists(script):
                with open(script, encoding="utf-8") as f:
                    code = f.read()
            else:
                import inspect
                from src.connectivity import whisper_node as _wm
                code = inspect.getsource(_wm)
        except Exception as e:
            log.error("%s Cannot get source: %s", self.parent.node_id, e)
            return False

        # Состояние родителя
        state = {
            "hidden_size":  self.parent.hidden_size,
            "hidden_state": self.parent.hidden_state.tolist(),
            "W_h": self.parent.rnn.W_h.tolist(),
            "W_i": self.parent.rnn.W_i.tolist(),
            "b":   self.parent.rnn.b.tolist(),
            "light_mode":   self.parent.light_mode,
        }
        bud_pkg = {
            "code":        code,
            "state":       state,
            "target_port": target_port or (self.parent.port + 1),
        }

        # Сериализация: ГОСТ-шифрование если доступно, иначе plain pickle
        if self._gost:
            pkg = self._gost.seal_bud(bud_pkg)
            log.info("%s Почка зашифрована ГОСТ Кузнечик-CTR + HMAC-Стрибог", self.parent.node_id)
        else:
            pkg = pickle.dumps(bud_pkg)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((target_ip, target_bud_port))
            sock.sendall(pkg)
            sock.close()
            self.sent_buds[target_ip] = time.time()
            log.info("%s Bud sent → %s:%s", self.parent.node_id, target_ip, target_bud_port)
            return True
        except Exception as e:
            log.warning("%s Bud send failed: %s", self.parent.node_id, e)
            return False

    # ── Поиск «плодородной земли» ────────────────────
    def _start_soil_search(self):
        def loop():
            while self.running:
                try:
                    self.find_soil()
                except Exception as e:
                    log.warning("%s Soil search: %s", self.parent.node_id, e)
                time.sleep(self.soil_search_interval)

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        self._search_thread = t

    def find_soil(self):
        """Ищет хосты в LAN, подходящие для почкования."""
        for host in self._get_local_hosts():
            if host in self.known_hosts:
                continue
            if self._is_soil_suitable(host):
                log.info("%s Suitable soil at %s", self.parent.node_id, host)
                free_port = self._find_free_port(host, start=5001)
                if free_port:
                    self.send_bud(host, target_port=free_port)
                self.known_hosts.add(host)
                break   # по одной почке за цикл

    def _get_local_hosts(self) -> set:
        """Возвращает активные IPv4-хосты из ARP-таблицы."""
        hosts = set()
        try:
            output = subprocess.check_output(["arp", "-a"], text=True, timeout=5)
            for ip in re.findall(r"(\d+\.\d+\.\d+\.\d+)", output):
                if ip != self.parent.host and not ip.endswith(".255"):
                    hosts.add(ip)
        except Exception as e:
            log.warning("%s ARP error: %s", self.parent.node_id, e)
        return hosts

    def _is_soil_suitable(self, ip: str) -> bool:
        """Хост подходит, если принимает почки, но ещё не запустил Argos."""
        if not self._is_port_open(ip, self.bud_port, timeout=1):
            return False
        if self._is_port_open(ip, self.parent.port, timeout=1):
            self.known_hosts.add(ip)
            return False
        return True

    def _is_port_open(self, ip: str, port: int, timeout: float = 1) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0

    def _find_free_port(self, ip: str, start: int = 5001, max_try: int = 10) -> Optional[int]:
        for port in range(start, start + max_try):
            if not self._is_port_open(ip, port):
                return port
        return None

    def stop(self):
        self.running = False

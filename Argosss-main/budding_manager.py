#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
budding_manager.py — Менеджер почкования узлов Argos.

BuddingManager отвечает за:
  - автоматический поиск «плодородных» хостов в локальной сети (ARP-таблица)
  - TCP-отправку «почек» (code + state) на найденные хосты
  - приём и запуск входящих почек

Интегрируется с WhisperNode: передаётся в конструктор enable_budding=True.
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
from typing import Optional, Set

import numpy as np

log = logging.getLogger("argos.budding")


class BuddingManager:
    """
    Управляет самовоспроизведением узла Argos в локальной сети.

    Алгоритм:
      1. Каждые soil_search_interval секунд сканирует ARP-таблицу.
      2. Для каждого нового хоста проверяет, можно ли туда отправить почку.
      3. Если подходит — отправляет TCP-пакет с кодом и состоянием узла.
      4. Принимает входящие почки и запускает их как новые процессы.
    """

    BUD_PORT_OFFSET = 1000  # порт для приёма почек = parent.port + 1000
    MIN_BUD_INTERVAL = 300  # минимум секунд между повторными попытками на один хост

    def __init__(self, parent_node, soil_search_interval: int = 60) -> None:
        self.parent = parent_node
        self.bud_port = parent_node.port + self.BUD_PORT_OFFSET
        self.soil_search_interval = soil_search_interval
        self.running = True
        self.known_hosts: Set[str] = set()
        self.sent_buds: dict = defaultdict(float)  # ip -> timestamp

        self._start_bud_listener()
        self._start_soil_search()

    # ── TCP-сервер приёма почек ───────────────────────────────────────────

    def _start_bud_listener(self) -> None:
        def _listen() -> None:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Привязка к 0.0.0.0: TCP-сервер должен принимать подключения
            # от любого хоста в сети для получения «почек» с соседних узлов.
            # В изолированной сети это безопасно; при необходимости ограничьте
            # конкретным IP, передав host в конструктор WhisperNode.
            srv.bind(("0.0.0.0", self.bud_port))
            srv.listen(5)
            srv.settimeout(0.5)
            log.info("[%s] BudListener on port %d", self.parent.node_id, self.bud_port)
            while self.running:
                try:
                    conn, addr = srv.accept()
                    threading.Thread(
                        target=self._handle_incoming_bud,
                        args=(conn, addr),
                        daemon=True,
                    ).start()
                except socket.timeout:
                    continue
                except Exception as exc:
                    if self.running:
                        log.warning("[%s] BudListener error: %s", self.parent.node_id, exc)
            srv.close()

        self._listener_thread = threading.Thread(target=_listen, daemon=True)
        self._listener_thread.start()

    def _handle_incoming_bud(self, conn: socket.socket, addr) -> None:
        """Принимает почку и запускает новый узел как отдельный процесс."""
        try:
            chunks = []
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            bud_package = pickle.loads(b"".join(chunks))

            code        = bud_package["code"]
            state       = bud_package["state"]
            target_port = bud_package.get("target_port", self.parent.port + 1)

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                script_path = f.name

            new_id = f"{self.parent.node_id}_bud_{hashlib.md5(code.encode()).hexdigest()[:4]}"
            h_state = state["hidden_state"]
            if isinstance(h_state, np.ndarray):
                h_state = h_state.tolist()

            cmd = [
                sys.executable, script_path,
                "--node-id",        new_id,
                "--port",           str(target_port),
                "--hidden-size",    str(state["hidden_size"]),
                "--initial-state",  json.dumps(h_state),
                "--initial-weights", json.dumps({
                    "W_h": state["W_h"],
                    "W_i": state["W_i"],
                    "b":   state["b"],
                }),
            ]
            if state.get("light_mode"):
                cmd.append("--light-mode")

            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log.info("[%s] Launched bud %s from %s", self.parent.node_id, new_id, addr[0])
        except Exception as exc:
            log.warning("[%s] Error handling bud from %s: %s", self.parent.node_id, addr, exc)
        finally:
            conn.close()

    # ── отправка почек ────────────────────────────────────────────────────

    def send_bud(
        self,
        target_ip: str,
        target_port: Optional[int] = None,
        target_bud_port: Optional[int] = None,
    ) -> bool:
        """Отправляет почку (код + состояние) на указанный хост."""
        if target_bud_port is None:
            target_bud_port = self.bud_port
        if time.time() - self.sent_buds.get(target_ip, 0) < self.MIN_BUD_INTERVAL:
            return False

        # Собираем код для передачи
        code = self._get_node_code()

        # Состояние родительского узла
        state = {
            "hidden_size":  self.parent.hidden_size,
            "hidden_state": self.parent.hidden_state.copy(),
            "W_h":          self.parent.rnn.W_h.tolist(),
            "W_i":          self.parent.rnn.W_i.tolist(),
            "b":            self.parent.rnn.b.tolist(),
            "light_mode":   self.parent.light_mode,
        }
        target_port = target_port or (self.parent.port + 1)
        bud_package = {"code": code, "state": state, "target_port": target_port}
        data = pickle.dumps(bud_package)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((target_ip, target_bud_port))
            sock.sendall(data)
            sock.close()
            self.sent_buds[target_ip] = time.time()
            log.info("[%s] Bud sent to %s:%d", self.parent.node_id, target_ip, target_bud_port)
            return True
        except Exception as exc:
            log.warning("[%s] Failed to send bud to %s: %s", self.parent.node_id, target_ip, exc)
            return False

    def _get_node_code(self) -> str:
        """Читает исходный код whisper_node.py для самовоспроизведения."""
        # Ищем whisper_node.py рядом с этим файлом
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "whisper_node.py"),
        ]
        for path in candidates:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    return f.read()
        # Последний вариант: возвращаем минимальный заглушечный скрипт
        return (
            "import time\n"
            "print('Bud node started')\n"
            "try:\n"
            "    while True: time.sleep(1)\n"
            "except KeyboardInterrupt: pass\n"
        )

    # ── поиск «земли» ─────────────────────────────────────────────────────

    def _start_soil_search(self) -> None:
        def _loop() -> None:
            while self.running:
                try:
                    self.find_soil()
                except Exception as exc:
                    log.debug("[%s] Soil search error: %s", self.parent.node_id, exc)
                time.sleep(self.soil_search_interval)

        self._search_thread = threading.Thread(target=_loop, daemon=True)
        self._search_thread.start()

    def find_soil(self) -> None:
        """Ищет хосты в локальной сети, подходящие для почкования."""
        hosts = self._get_local_hosts()
        for host in hosts:
            if host in self.known_hosts:
                continue
            if self._is_soil_suitable(host):
                log.info("[%s] Suitable soil found at %s", self.parent.node_id, host)
                free_port = self._find_free_port(host)
                if free_port:
                    self.send_bud(host, target_port=free_port)
                self.known_hosts.add(host)
                break  # одна почка за цикл

    def _get_local_hosts(self) -> set:
        """Получает активные хосты из ARP-таблицы."""
        hosts: set = set()
        try:
            output = subprocess.check_output(
                ["arp", "-a"], universal_newlines=True, stderr=subprocess.DEVNULL
            )
            ips = re.findall(r"(\d+\.\d+\.\d+\.\d+)", output)
            for ip in ips:
                if not ip.endswith(".255") and ip != self.parent.host:
                    hosts.add(ip)
        except Exception as exc:
            log.debug("[%s] ARP error: %s", self.parent.node_id, exc)
        return hosts

    def _is_soil_suitable(self, ip: str) -> bool:
        """Проверяет, подходит ли хост для посадки почки."""
        # Порт для приёма почек должен быть доступен
        if not self._is_port_open(ip, self.bud_port):
            return False
        # Если там уже есть Argos-узел — не нужна ещё одна копия
        if self._is_port_open(ip, self.parent.port):
            self.known_hosts.add(ip)
            return False
        return True

    def _is_port_open(self, ip: str, port: int, timeout: float = 1.0) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        result = s.connect_ex((ip, port))
        s.close()
        return result == 0

    def _find_free_port(self, ip: str, start: int = 5001, attempts: int = 10) -> Optional[int]:
        """Находит свободный порт на удалённом хосте."""
        for port in range(start, start + attempts):
            if not self._is_port_open(ip, port):
                return port
        return None

    def stop(self) -> None:
        self.running = False

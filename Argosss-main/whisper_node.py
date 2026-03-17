#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
whisper_node.py — Распределённый mesh-узел Argos.

WhisperNode общается с другими узлами через UDP, обмениваясь:
  - состояниями RNN (шёпот)
  - весами для мимикрии
  - кластерной информацией
  - скомпилированным кодом (если доступен keystone)

Запуск:
  python whisper_node.py --node-id NodeA --port 5001
  python whisper_node.py --node-id NodeB --port 5002 --light-mode

Интегрируется с main.py через команды: mesh start / mesh stop / mesh status
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import pickle
import socket
import threading
import time
import warnings
from collections import deque
from typing import Any, Dict, List, Optional

import numpy as np

try:
    from keystone import Ks, KS_ARCH_X86, KS_MODE_64
    HAVE_KS = True
except ImportError:
    HAVE_KS = False
    warnings.warn("keystone не установлен — ассемблирование отключено", stacklevel=1)

log = logging.getLogger("argos.whisper")


# ─────────────────────────────────────────────────────────────────────────────
# RNN-ячейка (внутренний процессор состояния)
# ─────────────────────────────────────────────────────────────────────────────

class RNNCell:
    """
    Простая ячейка RNN с фиксированными случайными весами.
      h_new = tanh(W_h @ h_old + W_i @ x + b)
    """

    def __init__(self, input_size: int, hidden_size: int) -> None:
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.W_h = np.random.randn(hidden_size, hidden_size) * 0.1
        self.W_i = np.random.randn(hidden_size, input_size) * 0.1
        self.b = np.zeros(hidden_size)

    def forward(self, x: np.ndarray, h_prev: np.ndarray) -> np.ndarray:
        return np.tanh(self.W_h @ h_prev + self.W_i @ x + self.b)


# ─────────────────────────────────────────────────────────────────────────────
# Основной класс узла
# ─────────────────────────────────────────────────────────────────────────────

class WhisperNode:
    """
    Mesh-узел Argos, работающий через UDP.

    Типы сообщений:
      MT_STATE        — вектор скрытого состояния RNN
      MT_CODE         — скомпилированная функция (hex-байты)
      MT_MIMIC_REQUEST — запрос на копирование весов
      MT_MIMIC_DATA   — передача весов (pickle)
      MT_CLUSTER_INFO — информация о кластере (роль, участники)
      MT_PING         — проверка присутствия
      MT_SOIL_INFO    — информация о найденном хосте-«почве»
    """

    PROTOCOL_VERSION = 1

    MT_STATE         = 1
    MT_CODE          = 2
    MT_MIMIC_REQUEST = 3
    MT_MIMIC_DATA    = 4
    MT_CLUSTER_INFO  = 5
    MT_PING          = 6
    MT_SOIL_INFO     = 7

    def __init__(
        self,
        node_id: str,
        host: str = "0.0.0.0",
        port: int = 5000,
        hidden_size: int = 5,
        light_mode: bool = False,
        enable_budding: bool = False,
        soil_search_interval: int = 60,
    ) -> None:
        self.node_id = node_id
        self.host = host
        self.port = port
        self.hidden_size = hidden_size
        self.light_mode = light_mode
        self.running = False

        # RNN
        self.rnn = RNNCell(input_size=1, hidden_size=hidden_size)
        self.hidden_state = np.zeros(hidden_size)
        self.last_silence = 0.0

        # Буферы входящих сообщений
        self.inbox_states: deque = deque(maxlen=20)
        self.inbox_codes: Dict[str, Any] = {}
        self.inbox_mimic_requests: set = set()
        self.inbox_mimic_data: Dict[str, Any] = {}
        self.cluster_info: Dict[str, Any] = {}

        # UDP-сокет (широковещательный).
        # Привязка к 0.0.0.0 необходима для получения UDP-broadcast-пакетов
        # от других узлов mesh-сети на всех сетевых интерфейсах — это
        # основная функция WhisperNode. Для ограничения используйте host=<конкретный IP>.
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(0.1)

        # История
        self.silence_history: List[float] = []

        # Ассемблированные функции
        self.compiled_functions: Dict[str, bytes] = {}

        # Почкование
        self.budding = None
        if enable_budding:
            try:
                from budding_manager import BuddingManager
                self.budding = BuddingManager(self, soil_search_interval=soil_search_interval)
            except ImportError:
                log.warning("budding_manager.py не найден — почкование отключено")

    # ── запуск / остановка ────────────────────────────────────────────────

    def start(self) -> None:
        """Запускает узел (поток слушателя + цикл наблюдения)."""
        if self.running:
            return
        self.running = True
        self._listener_thread = threading.Thread(target=self._listen, daemon=True)
        self._listener_thread.start()
        if not self.light_mode:
            self._schedule_observe()
        log.info("[%s] WhisperNode запущен на порту %d", self.node_id, self.port)

    def stop(self) -> None:
        """Останавливает узел."""
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
        if self.budding:
            self.budding.stop()
        log.info("[%s] WhisperNode остановлен", self.node_id)

    # ── приём сообщений ───────────────────────────────────────────────────

    def _listen(self) -> None:
        while self.running:
            try:
                data, _ = self.sock.recvfrom(8192)
                msg = json.loads(data.decode())
                if msg.get("proto") != self.PROTOCOL_VERSION:
                    continue
                if msg.get("node_id") == self.node_id:
                    continue

                mtype = msg["type"]
                if mtype == self.MT_STATE:
                    self.inbox_states.append((msg["node_id"], np.array(msg["state"])))
                elif mtype == self.MT_CODE:
                    self.inbox_codes[msg["node_id"]] = (
                        msg.get("func_name", "unknown"),
                        bytes.fromhex(msg["code_hex"]),
                    )
                elif mtype == self.MT_MIMIC_REQUEST:
                    self.inbox_mimic_requests.add(msg["node_id"])
                elif mtype == self.MT_MIMIC_DATA:
                    weights = pickle.loads(bytes.fromhex(msg["data_hex"]))
                    self.inbox_mimic_data[msg["node_id"]] = weights
                elif mtype == self.MT_CLUSTER_INFO:
                    self.cluster_info[msg["node_id"]] = {
                        "role": msg["role"],
                        "members": msg["members"],
                    }
                elif mtype == self.MT_SOIL_INFO:
                    log.info("[%s] Soil info from %s: %s", self.node_id, msg["node_id"], msg.get("host"))
                # MT_PING — ничего не делаем
            except socket.timeout:
                continue
            except Exception as exc:
                if self.running:
                    log.debug("[%s] recv error: %s", self.node_id, exc)

    # ── рассылка ──────────────────────────────────────────────────────────

    def _broadcast(self, msg_dict: dict) -> None:
        msg_dict["proto"] = self.PROTOCOL_VERSION
        msg_dict["node_id"] = self.node_id
        try:
            self.sock.sendto(
                json.dumps(msg_dict).encode(),
                ("255.255.255.255", self.port),
            )
        except Exception as exc:
            log.debug("[%s] send error: %s", self.node_id, exc)

    # ── основной цикл ─────────────────────────────────────────────────────

    def _schedule_observe(self) -> None:
        threading.Timer(0.2, self._observe_step).start()

    def _observe_step(self) -> None:
        if not self.running:
            return
        self.observe()
        if self.running and not self.light_mode:
            self._schedule_observe()

    def observe(self) -> None:
        """Один шаг наблюдения: обновляет RNN, рассылает состояние."""
        # 1. Вход из сети
        if self.inbox_states:
            avg_vec = np.mean([s for _, s in self.inbox_states], axis=0)
            self.inbox_states.clear()
            input_val = float(np.linalg.norm(avg_vec))
        else:
            input_val = 0.0

        noise = np.random.randn() * 0.05
        x = np.array([input_val + noise])

        # 2. Обновление RNN
        self.hidden_state = self.rnn.forward(x, self.hidden_state)
        self.last_silence = float(np.linalg.norm(self.hidden_state))
        self.silence_history.append(self.last_silence)

        # 3. Рассылка состояния
        self._broadcast({"type": self.MT_STATE, "state": self.hidden_state.tolist()})

        # 4. Мимикрия — ответ на запросы
        for req_node in list(self.inbox_mimic_requests):
            weights = {
                "W_h": self.rnn.W_h.tolist(),
                "W_i": self.rnn.W_i.tolist(),
                "b":   self.rnn.b.tolist(),
            }
            self._broadcast({
                "type":     self.MT_MIMIC_DATA,
                "target":   req_node,
                "data_hex": pickle.dumps(weights).hex(),
            })
        self.inbox_mimic_requests.clear()

        # 5. Мимикрия — принятие чужих весов
        if self.inbox_mimic_data:
            src_node, wdata = next(iter(self.inbox_mimic_data.items()))
            self.rnn.W_h = np.array(wdata["W_h"])
            self.rnn.W_i = np.array(wdata["W_i"])
            self.rnn.b   = np.array(wdata["b"])
            log.info("[%s] Mimicked %s", self.node_id, src_node)
            self.inbox_mimic_data.clear()

        # 6. Ассемблирование (редко)
        if HAVE_KS and np.random.rand() < 0.05:
            self._assemble_and_send()

        # 7. Кластерный beacon
        if len(self.cluster_info) < 3:
            self._broadcast({
                "type":    self.MT_CLUSTER_INFO,
                "role":    "master",
                "members": [self.node_id],
            })

    # ── ассемблирование ───────────────────────────────────────────────────

    def _assemble_and_send(self) -> None:
        """Компилирует тестовую x86-64 функцию и рассылает её байты."""
        if not HAVE_KS:
            return
        asm_code = """
            push rbp
            mov rbp, rsp
            mov eax, edi
            add eax, esi
            pop rbp
            ret
        """
        try:
            ks = Ks(KS_ARCH_X86, KS_MODE_64)
            encoding, _ = ks.asm(asm_code)
            code_bytes = bytes(encoding)
            func_name = f"add_{hashlib.md5(code_bytes).hexdigest()[:8]}"
            self.compiled_functions[func_name] = code_bytes
            self._broadcast({
                "type":      self.MT_CODE,
                "func_name": func_name,
                "code_hex":  code_bytes.hex(),
            })
            log.debug("[%s] Assembled and sent %s", self.node_id, func_name)
        except Exception as exc:
            log.debug("[%s] Assembly failed: %s", self.node_id, exc)

    # ── управляющие методы ────────────────────────────────────────────────

    def request_mimic(self, target_node_id: str) -> None:
        """Запрашивает мимикрию у конкретного узла."""
        self._broadcast({"type": self.MT_MIMIC_REQUEST, "target": target_node_id})

    def send_ping(self) -> None:
        self._broadcast({"type": self.MT_PING})

    def get_status(self) -> Dict[str, Any]:
        return {
            "node_id":     self.node_id,
            "port":        self.port,
            "running":     self.running,
            "light_mode":  self.light_mode,
            "hidden_norm": float(np.linalg.norm(self.hidden_state)),
            "last_silence": self.last_silence,
            "cluster_info": self.cluster_info,
            "compiled_functions": list(self.compiled_functions.keys()),
            "inbox": {
                "states":         len(self.inbox_states),
                "codes":          len(self.inbox_codes),
                "mimic_requests": len(self.inbox_mimic_requests),
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# Глобальный менеджер (для main.py)
# ─────────────────────────────────────────────────────────────────────────────

_active_node: Optional[WhisperNode] = None


def mesh_start(node_id: str = "ARGOS_MESH", port: int = 5000, light_mode: bool = False) -> str:
    """Запускает mesh-узел (команда из main.py)."""
    global _active_node
    if _active_node and _active_node.running:
        return f"🌐 MESH: узел {_active_node.node_id} уже запущен на порту {_active_node.port}"
    try:
        _active_node = WhisperNode(
            node_id=node_id,
            port=port,
            light_mode=light_mode,
            enable_budding=True,
        )
        _active_node.start()
        return f"🌐 MESH: узел {node_id} запущен на порту {port}"
    except Exception as exc:
        return f"❌ MESH: ошибка запуска: {exc}"


def mesh_stop() -> str:
    global _active_node
    if not _active_node or not _active_node.running:
        return "🌐 MESH: узел не запущен"
    _active_node.stop()
    return f"🌐 MESH: узел {_active_node.node_id} остановлен"


def mesh_status() -> str:
    global _active_node
    if not _active_node:
        return "🌐 MESH: узел не создан. Команда: mesh start"
    import json as _json
    return "🌐 MESH:\n" + _json.dumps(_active_node.get_status(), indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Точка входа при прямом запуске
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Argos WhisperNode")
    parser.add_argument("--node-id",     default="NodeA")
    parser.add_argument("--port",        type=int, default=5001)
    parser.add_argument("--hidden-size", type=int, default=5)
    parser.add_argument("--light-mode",  action="store_true")
    parser.add_argument("--budding",     action="store_true")
    args = parser.parse_args()

    node = WhisperNode(
        node_id=args.node_id,
        port=args.port,
        hidden_size=args.hidden_size,
        light_mode=args.light_mode,
        enable_budding=args.budding,
    )
    node.start()

    try:
        while True:
            time.sleep(5)
            log.info("[%s] status: %s", args.node_id, json.dumps(node.get_status()))
    except KeyboardInterrupt:
        node.stop()

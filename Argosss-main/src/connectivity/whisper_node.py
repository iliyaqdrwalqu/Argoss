#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
whisper_node.py — Шепчущий узел Аргоса.
P2P-узел на основе RNN, обменивающийся состояниями, весами и скомпилированным
кодом с другими узлами через UDP-broadcast.

Функции:
  - Обмен скрытыми состояниями RNN («шепот»)
  - Мимикрия: копирование весов у других узлов
  - Кластеризация: выбор лидера и рассылка карты сети
  - Ассемблирование и рассылка машинного кода (если установлен keystone)
  - Лёгкий режим «колибри»: только слушать, не генерировать
  - Почкование (budding): создание дочерних узлов в сети (через BuddingManager)
  - Поддержка Xen Argo транспорта (между доменами Xen)
"""
from __future__ import annotations

import hashlib
import json
import pickle
import socket
import struct
import threading
import time
import warnings
from collections import deque

import numpy as np

try:
    from keystone import Ks, KS_ARCH_X86, KS_MODE_64
    HAVE_KS = True
except ImportError:
    HAVE_KS = False
    warnings.warn("Keystone not installed, assembly disabled")


# ─────────────────────────────────────────────────
# RNN-ячейка внутреннего состояния
# ─────────────────────────────────────────────────
class RNNCell:
    """
    Простая ячейка RNN с Tanh-активацией.
    h_new = tanh(W_h @ h_old + W_i @ x + b)
    """

    def __init__(self, input_size: int, hidden_size: int):
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.W_h = np.random.randn(hidden_size, hidden_size) * 0.1
        self.W_i = np.random.randn(hidden_size, input_size) * 0.1
        self.b = np.zeros(hidden_size)

    def forward(self, x: np.ndarray, h_prev: np.ndarray) -> np.ndarray:
        return np.tanh(self.W_h @ h_prev + self.W_i @ x + self.b)


# ─────────────────────────────────────────────────
# Основной узел
# ─────────────────────────────────────────────────
class WhisperNode:
    """
    Узел, обменивающийся через UDP:
      - состояниями RNN (MT_STATE)
      - скомпилированным машинным кодом (MT_CODE)
      - запросами/данными мимикрии (MT_MIMIC_REQUEST / MT_MIMIC_DATA)
      - информацией о кластере (MT_CLUSTER_INFO)
      - пингами (MT_PING)
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
        use_xen_argo: bool = False,
    ):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.hidden_size = hidden_size
        self.light_mode = light_mode
        self.running = True

        # RNN-ядро
        self.rnn = RNNCell(input_size=1, hidden_size=hidden_size)
        self.hidden_state = np.zeros(hidden_size)
        self.last_silence = 0.0
        self.history: list = []

        # Буферы сообщений
        self.inbox_states: deque = deque(maxlen=20)
        self.inbox_codes: dict = {}
        self.inbox_mimic_requests: set = set()
        self.inbox_mimic_data: dict = {}
        self.cluster_info: dict = {}
        self.compiled_functions: dict = {}

        # UDP-сокет (широковещательный); host='0.0.0.0' необходим для LAN P2P
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(0.1)

        self.listener_thread = threading.Thread(target=self._listen, daemon=True)
        self.listener_thread.start()

        # Xen Argo (опционально)
        self.argo_transport = None
        if use_xen_argo:
            try:
                from src.connectivity.xen_argo_transport import XenArgoTransport
                self.argo_transport = XenArgoTransport(self.node_id, port=self.port)
            except Exception as e:
                warnings.warn(f"WhisperNode: XenArgo недоступен: {e}")

        # Почкование (опционально)
        self.budding = None
        if enable_budding:
            try:
                from src.connectivity.budding_manager import BuddingManager
                self.budding = BuddingManager(self, soil_search_interval=soil_search_interval)
            except Exception as e:
                warnings.warn(f"WhisperNode: BuddingManager недоступен: {e}")

        # В «полном» режиме запускаем observe
        if not self.light_mode:
            self.observe()

    # ── Приём ────────────────────────────────────────
    def _listen(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(8192)
                msg = json.loads(data.decode())
                if msg.get("proto") != self.PROTOCOL_VERSION:
                    continue
                if msg.get("node_id") == self.node_id:
                    continue
                self._dispatch(msg)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[{self.node_id}] recv error: {e}")

    def _dispatch(self, msg: dict):
        t = msg.get("type")
        if t == self.MT_STATE:
            self.inbox_states.append((msg["node_id"], np.array(msg["state"])))
        elif t == self.MT_CODE:
            self.inbox_codes[msg["node_id"]] = (
                msg.get("func_name", "unknown"),
                bytes.fromhex(msg["code_hex"]),
            )
        elif t == self.MT_MIMIC_REQUEST:
            self.inbox_mimic_requests.add(msg["node_id"])
        elif t == self.MT_MIMIC_DATA:
            weights = pickle.loads(bytes.fromhex(msg["data_hex"]))
            self.inbox_mimic_data[msg["node_id"]] = weights
        elif t == self.MT_CLUSTER_INFO:
            self.cluster_info[msg["node_id"]] = {
                "role": msg.get("role"),
                "members": msg.get("members", []),
            }

    # ── Отправка ─────────────────────────────────────
    def _broadcast(self, msg_dict: dict):
        msg_dict["proto"] = self.PROTOCOL_VERSION
        msg_dict["node_id"] = self.node_id
        try:
            self.sock.sendto(
                json.dumps(msg_dict).encode(),
                ("255.255.255.255", self.port),
            )
        except Exception as e:
            print(f"[{self.node_id}] send error: {e}")

    # ── Основной цикл ────────────────────────────────
    def observe(self):
        """Один шаг самонаблюдения и обмена."""
        if not self.running:
            return

        # 1. Вход из сети
        if self.inbox_states:
            avg_vec = np.mean([s for _, s in self.inbox_states], axis=0)
            self.inbox_states.clear()
            input_val = float(np.linalg.norm(avg_vec))
        else:
            input_val = 0.0

        noise = np.random.randn() * 0.05
        x = np.array([input_val + noise])

        # 2. Обновляем RNN
        self.hidden_state = self.rnn.forward(x, self.hidden_state)
        self.last_silence = float(np.linalg.norm(self.hidden_state))

        # 3. Рассылаем своё состояние
        self._broadcast({"type": self.MT_STATE, "state": self.hidden_state.tolist()})

        # 4. Мимикрия: отвечаем на запросы
        if self.inbox_mimic_requests:
            weights = {
                "W_h": self.rnn.W_h.tolist(),
                "W_i": self.rnn.W_i.tolist(),
                "b":   self.rnn.b.tolist(),
            }
            data_hex = pickle.dumps(weights).hex()
            for req_node in list(self.inbox_mimic_requests):
                self._broadcast({
                    "type": self.MT_MIMIC_DATA,
                    "target": req_node,
                    "data_hex": data_hex,
                })
            self.inbox_mimic_requests.clear()

        # 5. Мимикрия: применяем чужие веса
        if self.inbox_mimic_data:
            src_node, wdata = next(iter(self.inbox_mimic_data.items()))
            self.rnn.W_h = np.array(wdata["W_h"])
            self.rnn.W_i = np.array(wdata["W_i"])
            self.rnn.b   = np.array(wdata["b"])
            print(f"[{self.node_id}] Mimicked {src_node}")
            self.inbox_mimic_data.clear()

        # 6. Ассемблирование (10% шанс, если доступен keystone)
        if HAVE_KS and np.random.rand() < 0.1:
            self._assemble_and_send()

        # 7. Кластеризация
        if len(self.cluster_info) < 3:
            self._broadcast({
                "type": self.MT_CLUSTER_INFO,
                "role": "master",
                "members": [self.node_id],
            })

        # 8. Следующий шаг
        if self.running and not self.light_mode:
            threading.Timer(0.2, self.observe).start()

    # ── Ассемблирование ──────────────────────────────
    def _assemble_and_send(self):
        """
        Компилирует простую функцию x86-64 и рассылает её байт-код узлам.

        ⚠️  БЕЗОПАСНОСТЬ: распространение и выполнение машинного кода от
        сетевых узлов несёт значительные риски. Эта функция включена
        исключительно для исследовательских целей. В продакшен-окружении
        убедитесь, что:
          - входящий код проходит строгую валидацию и sandbox-запуск;
          - только доверенные узлы (с проверкой ARGOS_NETWORK_SECRET) могут
            присылать MT_CODE-сообщения;
          - функциональность задействована через явный opt-in (HAVE_KS=True).
        В текущей реализации только ОТПРАВКА кода — приём без выполнения.
        """
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
                "type": self.MT_CODE,
                "func_name": func_name,
                "code_hex": code_bytes.hex(),
            })
        except Exception as e:
            print(f"[{self.node_id}] Assembly failed: {e}")

    # ── Внешнее управление ───────────────────────────
    def request_mimic(self, target_node_id: str):
        """Послать запрос на мимикрию другому узлу."""
        self._broadcast({"type": self.MT_MIMIC_REQUEST, "target": target_node_id})

    def send_ping(self):
        self._broadcast({"type": self.MT_PING})

    def stop(self):
        self.running = False
        if self.budding:
            self.budding.stop()
        if self.argo_transport:
            self.argo_transport.close()
        try:
            self.sock.close()
        except Exception:
            pass
        print(f"[{self.node_id}] Stopped.")

    def get_status(self) -> dict:
        return {
            "node_id":     self.node_id,
            "port":        self.port,
            "hidden_norm": float(np.linalg.norm(self.hidden_state)),
            "last_silence": self.last_silence,
            "light_mode":  self.light_mode,
            "budding":     self.budding is not None,
            "xen_argo":    self.argo_transport is not None,
            "inbox_sizes": {
                "states":         len(self.inbox_states),
                "codes":          len(self.inbox_codes),
                "mimic_requests": len(self.inbox_mimic_requests),
                "mimic_data":     len(self.inbox_mimic_data),
            },
            "cluster_info":      self.cluster_info,
            "compiled_functions": list(self.compiled_functions.keys()),
        }


# ─────────────────────────────────────────────────
# Точка входа для дочернего узла (почки)
# ─────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="WhisperNode — дочерний узел Аргоса")
    parser.add_argument("--node-id", default="BudNode")
    parser.add_argument("--port",        type=int,   default=6000)
    parser.add_argument("--hidden-size", type=int,   default=5)
    parser.add_argument("--light-mode",  action="store_true")
    parser.add_argument("--initial-state",   default=None)
    parser.add_argument("--initial-weights", default=None)
    args = parser.parse_args()

    node = WhisperNode(
        args.node_id,
        port=args.port,
        hidden_size=args.hidden_size,
        light_mode=args.light_mode,
        enable_budding=True,
    )

    if args.initial_state:
        node.hidden_state = np.array(json.loads(args.initial_state))
    if args.initial_weights:
        w = json.loads(args.initial_weights)
        node.rnn.W_h = np.array(w["W_h"])
        node.rnn.W_i = np.array(w["W_i"])
        node.rnn.b   = np.array(w["b"])

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        node.stop()

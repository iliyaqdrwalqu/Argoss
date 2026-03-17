#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
colibri_daemon.py — Демон Колибри для Аргоса.

Запускает и управляет узлом WhisperNode как фоновым сервисом.
Поддерживает:
  - запуск в foreground-режиме (для отладки)
  - запуск как настоящий Unix-демон (через python-daemon, опционально)
  - корректную обработку сигналов SIGINT / SIGTERM

Использование:
    python colibri_daemon.py [--daemon] [--node-id NAME] [--port PORT] ...
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time

# Добавляем корень проекта в путь (если запущен напрямую)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from src.connectivity.whisper_node import WhisperNode
except ImportError:
    try:
        from whisper_node import WhisperNode      # noqa: F401
    except ImportError as e:
        raise ImportError(f"Не удалось импортировать WhisperNode: {e}") from e

log = logging.getLogger("colibri_daemon")


def _setup_logging(work_dir: str) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    h_console = logging.StreamHandler()
    h_console.setFormatter(fmt)
    log.addHandler(h_console)

    os.makedirs(work_dir, exist_ok=True)
    h_file = logging.FileHandler(os.path.join(work_dir, "colibri.log"))
    h_file.setFormatter(fmt)
    log.addHandler(h_file)
    log.setLevel(logging.INFO)


class ColibriDaemon:
    """
    Демон, управляющий жизнью узла WhisperNode.

    Параметры
    ---------
    node_id : str
        Уникальный идентификатор узла.
    port : int
        UDP-порт для WhisperNode.
    hidden_size : int
        Размер скрытого состояния RNN.
    light_mode : bool
        Если True — узел только слушает (лёгкий режим «колибри»).
    enable_budding : bool
        Включить почкование (создание дочерних узлов).
    work_dir : str
        Рабочая директория для логов и PID-файла.
    """

    def __init__(
        self,
        node_id: str | None = None,
        port: int = 5000,
        hidden_size: int = 5,
        light_mode: bool = False,
        enable_budding: bool = True,
        work_dir: str = "/var/lib/colibri",
    ):
        self.node_id = node_id or f"Colibri-{os.uname().nodename}"
        self.port = port
        self.hidden_size = hidden_size
        self.light_mode = light_mode
        self.enable_budding = enable_budding
        self.work_dir = work_dir

        _setup_logging(work_dir)

        self.node: WhisperNode | None = None
        self.running = False
        self._thread: threading.Thread | None = None

    # ── Запуск / остановка ───────────────────────────
    def start(self) -> None:
        if self.running:
            log.warning("Демон уже запущен.")
            return
        log.info("Запуск Колибри: node_id=%s port=%d light=%s", self.node_id, self.port, self.light_mode)
        self.running = True
        self._thread = threading.Thread(target=self._run_node, daemon=True)
        self._thread.start()

    def _run_node(self) -> None:
        try:
            self.node = WhisperNode(
                node_id=self.node_id,
                port=self.port,
                hidden_size=self.hidden_size,
                light_mode=self.light_mode,
                enable_budding=self.enable_budding,
            )
            log.info("WhisperNode запущен.")
            while self.running:
                time.sleep(1)
        except Exception:
            log.exception("Ошибка в WhisperNode")
        finally:
            if self.node:
                self.node.stop()
                log.info("WhisperNode остановлен.")

    def stop(self) -> None:
        log.info("Остановка демона...")
        self.running = False
        if self.node:
            self.node.stop()
        if self._thread:
            self._thread.join(timeout=5)
        log.info("Демон остановлен.")

    def status(self) -> dict:
        if self.running and self.node:
            s = self.node.get_status()
            s["daemon_running"] = True
            return s
        return {"daemon_running": False}


# ─────────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Демон Колибри для Аргоса")
    p.add_argument("--node-id",      help="Идентификатор узла")
    p.add_argument("--port",         type=int, default=5000)
    p.add_argument("--hidden-size",  type=int, default=5)
    p.add_argument("--light-mode",   action="store_true")
    p.add_argument("--no-budding",   action="store_true", help="Отключить почкование")
    p.add_argument("--work-dir",     default="/var/lib/colibri")
    p.add_argument("--pid-file",     default="/var/run/colibri.pid")
    p.add_argument("--daemon",       action="store_true", help="Запустить как Unix-демон")
    return p.parse_args()


def _run_foreground(args: argparse.Namespace) -> None:
    d = ColibriDaemon(
        node_id=args.node_id,
        port=args.port,
        hidden_size=args.hidden_size,
        light_mode=args.light_mode,
        enable_budding=not args.no_budding,
        work_dir=args.work_dir,
    )
    d.start()

    def _handler(sig, frame):
        log.info("Сигнал %d — завершение.", sig)
        d.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _handler)
    signal.signal(signal.SIGTERM, _handler)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        d.stop()


def _run_daemon(args: argparse.Namespace) -> None:
    try:
        import daemon as _daemon
        from daemon import pidfile as _pidfile
    except ImportError:
        print("python-daemon не установлен. Установи: pip install python-daemon")
        sys.exit(1)

    ctx = _daemon.DaemonContext(
        working_directory=args.work_dir,
        pidfile=_pidfile.PIDLockFile(args.pid_file),
        umask=0o002,
        detach_process=True,
    )
    with ctx:
        d = ColibriDaemon(
            node_id=args.node_id,
            port=args.port,
            hidden_size=args.hidden_size,
            light_mode=args.light_mode,
            enable_budding=not args.no_budding,
            work_dir=args.work_dir,
        )
        d.start()
        signal.pause()


if __name__ == "__main__":
    args = _parse_args()
    if args.daemon:
        _run_daemon(args)
    else:
        _run_foreground(args)

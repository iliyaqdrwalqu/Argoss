"""
container_isolation.py — Docker/LXD изоляция модулей Argos.
Запускает тяжёлые/небезопасные модули в изолированных контейнерах.
"""
import os
import json
import subprocess
import threading
import time
from enum import Enum
from typing import Optional
from src.argos_logger import get_logger

log = get_logger("argos.containers")


class ContainerRuntime(Enum):
    DOCKER = "docker"
    LXD    = "lxd"
    NONE   = "none"


def _detect_runtime() -> ContainerRuntime:
    for rt in ("docker", "lxc"):
        try:
            r = subprocess.run([rt, "--version"], capture_output=True, timeout=3)
            if r.returncode == 0:
                return ContainerRuntime.DOCKER if rt == "docker" else ContainerRuntime.LXD
        except Exception:
            pass
    return ContainerRuntime.NONE


class ContainerIsolation:
    IMAGE = "python:3.11-slim"
    PREFIX = "argos_module_"

    def __init__(self):
        self.runtime = _detect_runtime()
        self._containers: dict = {}
        self._watchdog_running = False
        log.info("Container Isolation: runtime=%s", self.runtime.value)

    def launch(self, module_name: str, env: dict = None) -> str:
        """Запускает модуль в изолированном контейнере."""
        if self.runtime == ContainerRuntime.NONE:
            return "⚠️ Container Isolation: Docker/LXD недоступны"
        cname = f"{self.PREFIX}{module_name}_{int(time.time())}"
        env_args = []
        for k, v in (env or {}).items():
            env_args += ["-e", f"{k}={v}"]
        try:
            cmd = [
                "docker", "run", "-d", "--rm",
                "--name", cname,
                "--memory", "512m",
                "--cpus", "0.5",
                "--network", "none",
                *env_args,
                self.IMAGE,
                "python", "-c",
                f"import importlib; m = importlib.import_module('src.{module_name}'); print('OK')"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                cid = result.stdout.strip()[:12]
                self._containers[cname] = {"id": cid, "module": module_name, "ts": time.time()}
                return f"✅ Container {cname} запущен (id={cid})"
            return f"❌ Docker launch: {result.stderr[:200]}"
        except Exception as e:
            return f"❌ Container launch: {e}"

    def stop(self, container_name: str) -> str:
        try:
            subprocess.run(["docker", "stop", container_name],
                           capture_output=True, timeout=15)
            self._containers.pop(container_name, None)
            return f"✅ Container {container_name} остановлен"
        except Exception as e:
            return f"❌ {e}"

    def logs(self, container_name: str, lines: int = 50) -> str:
        try:
            r = subprocess.run(["docker", "logs", "--tail", str(lines), container_name],
                                capture_output=True, text=True, timeout=10)
            return r.stdout or r.stderr or "(пусто)"
        except Exception as e:
            return f"❌ {e}"

    def list_containers(self) -> str:
        try:
            r = subprocess.run(
                ["docker", "ps", "--filter", f"name={self.PREFIX}", "--format",
                 "table {{.Names}}\t{{.Status}}\t{{.Image}}"],
                capture_output=True, text=True, timeout=10
            )
            return r.stdout or "Контейнеров нет"
        except Exception as e:
            return f"❌ {e}"

    def cleanup(self) -> str:
        try:
            r = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={self.PREFIX}", "-q"],
                capture_output=True, text=True, timeout=10
            )
            ids = r.stdout.strip().split()
            if ids:
                subprocess.run(["docker", "rm", "-f"] + ids, capture_output=True, timeout=30)
            self._containers.clear()
            return f"✅ Очищено {len(ids)} контейнеров"
        except Exception as e:
            return f"❌ {e}"

    def start_watchdog(self) -> str:
        if self._watchdog_running:
            return "ℹ️ Watchdog уже запущен"
        self._watchdog_running = True
        threading.Thread(target=self._watchdog_loop, daemon=True).start()
        return "✅ Container watchdog запущен"

    def _watchdog_loop(self):
        while self._watchdog_running:
            for name, info in list(self._containers.items()):
                try:
                    r = subprocess.run(["docker", "inspect", "--format", "{{.State.Status}}", name],
                                       capture_output=True, text=True, timeout=5)
                    if r.returncode != 0:
                        self._containers.pop(name, None)
                except Exception:
                    pass
            time.sleep(30)

    def status(self) -> str:
        return (
            f"🐳 CONTAINER ISOLATION:\n"
            f"  Runtime:    {self.runtime.value}\n"
            f"  Активных:   {len(self._containers)}\n"
            f"  Watchdog:   {'✅' if self._watchdog_running else '❌'}"
        )

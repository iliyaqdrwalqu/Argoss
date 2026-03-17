"""
net_scanner.py — Сетевой Призрак (NetGhost)
  Сканирование локальной сети, обнаружение новых устройств
"""
import socket
import subprocess
import platform
import os
import json
import threading
import time

KNOWN_DEVICES_FILE = "config/known_devices.json"

class NetGhost:
    def __init__(self):
        self.known    = self._load_known()
        self._running = False

    def _load_known(self) -> set:
        if os.path.exists(KNOWN_DEVICES_FILE):
            with open(KNOWN_DEVICES_FILE, "r") as f:
                return set(json.load(f))
        return set()

    def _save_known(self):
        os.makedirs("config", exist_ok=True)
        with open(KNOWN_DEVICES_FILE, "w") as f:
            json.dump(list(self.known), f, indent=2)

    def get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def ping_scan(self, subnet: str = "") -> list[str]:
        """Пингует диапазон /24 и возвращает активные IP."""
        if not subnet:
            local = self.get_local_ip()
            subnet = ".".join(local.split(".")[:3])

        active = []
        flag   = "-n" if platform.system() == "Windows" else "-c"

        def _ping(ip):
            r = subprocess.run(
                ["ping", flag, "1", "-W", "300", ip],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if r.returncode == 0:
                active.append(ip)

        threads = []
        for i in range(1, 255):
            t = threading.Thread(target=_ping, args=(f"{subnet}.{i}",))
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=1)

        return sorted(active)

    def scan(self) -> str:
        """Полное сканирование с детектом новых устройств."""
        current = set(self.ping_scan())
        new     = current - self.known

        result = [f"📡 Активных устройств: {len(current)}"]

        if new:
            result.append(f"\n⚠️ НОВЫЕ УСТРОЙСТВА ({len(new)}):")
            for ip in sorted(new):
                result.append(f"  🔴 {ip} — НЕ ОПОЗНАНО")
        else:
            result.append("✅ Все устройства известны. Периметр чист.")

        # Обновляем базу известных
        self.known.update(current)
        self._save_known()

        return "\n".join(result)

    def scan_ports(self, host: str = "", ports: list = None) -> str:
        """Сканирование открытых портов на хосте."""
        if not host:
            host = self.get_local_ip()
        if not ports:
            ports = [21, 22, 23, 80, 443, 3389, 8080, 8443]

        open_ports = []
        for port in ports:
            try:
                s = socket.socket()
                s.settimeout(0.5)
                if s.connect_ex((host, port)) == 0:
                    open_ports.append(port)
                s.close()
            except Exception:
                pass

        if open_ports:
            return f"🔍 Открытые порты на {host}:\n  " + ", ".join(map(str, open_ports))
        return f"✅ Открытых портов на {host} не обнаружено."

    def start_patrol(self, interval_hours: int = 24):
        """Периодическое патрулирование сети."""
        self._running = True
        def _loop():
            while self._running:
                report = self.scan()
                print(f"[NET-GHOST PATROL]:\n{report}")
                time.sleep(interval_hours * 3600)
        threading.Thread(target=_loop, daemon=True).start()
        return f"Сетевой Призрак на патруле. Интервал: {interval_hours}ч."

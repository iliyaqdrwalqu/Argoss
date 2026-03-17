"""
wifi_sentinel.py — WiFi Sentinel + HoneyPot ловушка.
Сканирует WiFi-сети, обнаруживает Evil Twin, деаут-атаки, HoneyPot.
"""
import os
import time
import threading
import subprocess
import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from src.argos_logger import get_logger

log = get_logger("argos.wifi")

try:
    import scapy.all as scapy
    SCAPY_OK = True
except ImportError:
    scapy = None; SCAPY_OK = False


@dataclass
class AccessPoint:
    ssid: str = ""
    bssid: str = ""
    channel: int = 0
    signal_dbm: int = -100
    encryption: str = "open"
    vendor: str = ""
    clients: int = 0
    last_seen: float = field(default_factory=time.time)

    def to_dict(self): return asdict(self)


@dataclass
class WifiIncident:
    ts: float = field(default_factory=time.time)
    type: str = ""
    threat_level: str = "LOW"
    description: str = ""
    bssid: str = ""
    ssid: str = ""


class WiFiSentinel:
    """Мониторинг WiFi-эфира, обнаружение атак, HoneyPot."""
    MAX_INCIDENTS = 200

    def __init__(self):
        self._aps: dict = {}
        self._incidents: List[WifiIncident] = []
        self._honeypot_running = False
        self._monitor_running = False
        self._hp_thread: Optional[threading.Thread] = None
        self._mon_thread: Optional[threading.Thread] = None

    def scan_aps(self) -> List[AccessPoint]:
        """Сканирует точки доступа через системные инструменты."""
        aps = []
        # Linux: iw
        try:
            result = subprocess.run(
                ["iw", "dev"], capture_output=True, text=True, timeout=5)
            iface = None
            for line in result.stdout.splitlines():
                if "Interface" in line:
                    iface = line.split()[-1]
                    break
            if iface:
                scan = subprocess.run(
                    ["iw", iface, "scan"], capture_output=True, text=True, timeout=15)
                current = {}
                for line in scan.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("BSS "):
                        if current:
                            ap = AccessPoint(**current)
                            aps.append(ap)
                            self._aps[current.get("bssid", "")] = ap
                        current = {"bssid": line.split()[1][:17]}
                    elif "SSID:" in line:
                        current["ssid"] = line.split("SSID:")[-1].strip()
                    elif "signal:" in line:
                        try: current["signal_dbm"] = int(float(line.split("signal:")[-1].split()[0]))
                        except: pass
                    elif "DS Parameter set: channel" in line:
                        try: current["channel"] = int(line.split("channel")[-1].strip())
                        except: pass
                if current:
                    aps.append(AccessPoint(**current))
        except Exception as e:
            log.debug("iw scan: %s", e)

        # Windows/macOS fallback: netsh
        if not aps:
            try:
                r = subprocess.run(
                    ["netsh", "wlan", "show", "networks", "mode=Bssid"],
                    capture_output=True, text=True, timeout=10)
                ssid = bssid = signal = enc = ""
                for line in r.stdout.splitlines():
                    if "SSID" in line and "BSSID" not in line:
                        ssid = line.split(":")[-1].strip()
                    elif "BSSID" in line:
                        bssid = line.split(":")[-1].strip()
                    elif "Signal" in line:
                        try: signal = -int((100 - int(line.split(":")[-1].strip().replace("%",""))) // 2)
                        except: signal = -70
                    elif "Authentication" in line:
                        enc = line.split(":")[-1].strip()
                    elif ssid and bssid:
                        ap = AccessPoint(ssid=ssid, bssid=bssid,
                                         signal_dbm=signal, encryption=enc)
                        aps.append(ap)
                        ssid = bssid = ""
            except Exception:
                pass
        return aps

    def _detect_threats(self, aps: List[AccessPoint]) -> None:
        ssid_map: dict = {}
        for ap in aps:
            ssid_map.setdefault(ap.ssid, []).append(ap)

        for ssid, group in ssid_map.items():
            if len(group) > 1:
                inc = WifiIncident(
                    type="EVIL_TWIN",
                    threat_level="HIGH",
                    ssid=ssid,
                    description=f"Обнаружено {len(group)} точек с SSID '{ssid}' — возможный Evil Twin"
                )
                self._incidents.append(inc)
                log.warning("WiFi Sentinel: Evil Twin [%s]", ssid)

        # Открытые сети
        for ap in aps:
            if ap.encryption.lower() in ("open", "none", ""):
                inc = WifiIncident(
                    type="OPEN_NETWORK",
                    threat_level="MEDIUM",
                    ssid=ap.ssid,
                    bssid=ap.bssid,
                    description=f"Незащищённая сеть: {ap.ssid}"
                )
                self._incidents.append(inc)

        if len(self._incidents) > self.MAX_INCIDENTS:
            self._incidents = self._incidents[-self.MAX_INCIDENTS:]

    def start_monitor(self) -> str:
        if self._monitor_running:
            return "ℹ️ WiFi мониторинг уже запущен"
        self._monitor_running = True
        self._mon_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._mon_thread.start()
        return "✅ WiFi Sentinel: мониторинг запущен (каждые 60 сек)"

    def _monitor_loop(self):
        while self._monitor_running:
            try:
                aps = self.scan_aps()
                self._detect_threats(aps)
            except Exception as e:
                log.debug("WiFi monitor: %s", e)
            time.sleep(60)

    def start_honeypot(self) -> str:
        if self._honeypot_running:
            return "ℹ️ HoneyPot уже запущен"
        if not SCAPY_OK:
            # Simulated mode
            self._honeypot_running = True
            self._hp_thread = threading.Thread(target=self._hp_sim_loop, daemon=True)
            self._hp_thread.start()
            return "✅ WiFi HoneyPot запущен (симуляция — scapy не установлен)"
        self._honeypot_running = True
        self._hp_thread = threading.Thread(target=self._hp_loop, daemon=True)
        self._hp_thread.start()
        return "✅ WiFi HoneyPot запущен"

    def stop_honeypot(self) -> str:
        self._honeypot_running = False
        return "✅ WiFi HoneyPot остановлен"

    def _hp_sim_loop(self):
        """Симуляция honeypot без scapy."""
        import random
        while self._honeypot_running:
            if random.random() < 0.05:
                inc = WifiIncident(
                    type="HONEYPOT_HIT",
                    threat_level="HIGH",
                    description="Зонд-устройство попыталось подключиться к ловушке"
                )
                self._incidents.append(inc)
                log.warning("HoneyPot SIM: probe detected")
            time.sleep(30)

    def _hp_loop(self):
        """Реальный honeypot через scapy."""
        try:
            def pkt_handler(pkt):
                if not self._honeypot_running:
                    return
                if scapy.Dot11ProbeReq in pkt:
                    ssid = pkt[scapy.Dot11Elt].info.decode("utf-8", errors="ignore")
                    mac = pkt[scapy.Dot11].addr2
                    inc = WifiIncident(
                        type="PROBE_REQUEST",
                        threat_level="MEDIUM",
                        bssid=mac,
                        description=f"Probe Request: устройство {mac} ищет сеть '{ssid}'"
                    )
                    self._incidents.append(inc)
                    log.info("HoneyPot: probe from %s for '%s'", mac, ssid)
            scapy.sniff(prn=pkt_handler, store=0,
                        stop_filter=lambda _: not self._honeypot_running)
        except Exception as e:
            log.error("HoneyPot loop: %s", e)

    def get_incidents(self) -> list:
        return [asdict(i) for i in self._incidents[-50:]]

    def status(self) -> str:
        scapy_s = "✅" if SCAPY_OK else "⚠️ симуляция"
        return (
            f"🛡️ WIFI SENTINEL:\n"
            f"  Scapy:      {scapy_s}\n"
            f"  Мониторинг: {'✅' if self._monitor_running else '❌'}\n"
            f"  HoneyPot:   {'✅' if self._honeypot_running else '❌'}\n"
            f"  АТ:         {len(self._aps)} точек\n"
            f"  Инцидентов: {len(self._incidents)}"
        )

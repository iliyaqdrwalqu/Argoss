"""
air_snitch.py — AirSnitch (SDR / Sub-GHz Radio Scanner)
Пассивный мониторинг эфира 433/868/915 МГц.
⚠ Только RX. Передача запрещена.
"""
import os
import time
import json
import threading
from enum import Enum
from typing import List, Optional
from collections import deque
from dataclasses import dataclass, field, asdict
from src.argos_logger import get_logger

log = get_logger("argos.airsnitch")

try:
    from rtlsdr import RtlSdr
    RTLSDR_OK = True
except ImportError:
    RtlSdr = None; RTLSDR_OK = False

try:
    import numpy as np
    NP_OK = True
except ImportError:
    np = None; NP_OK = False

try:
    import serial
    SERIAL_OK = True
except ImportError:
    serial = None; SERIAL_OK = False


class Modulation(Enum):
    OOK = "OOK"; FSK = "FSK"; GFSK = "GFSK"; LORA = "LoRa"; UNKNOWN = "unknown"

class Band(Enum):
    SUB_433 = 433.92e6; SUB_868 = 868.0e6; SUB_915 = 915.0e6


@dataclass
class RFPacket:
    ts: float = field(default_factory=time.time)
    freq_hz: float = 0.0
    modulation: str = "unknown"
    rssi_dbm: float = -120.0
    raw_hex: str = ""
    decoded: str = ""
    protocol: str = ""
    device_id: str = ""
    repeated: int = 1
    summary: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["freq_mhz"] = round(self.freq_hz / 1e6, 3)
        return d


class AirSnitch:
    """SDR/Sub-GHz сканер эфира (RX only)."""
    MAX_LOG = 500

    def __init__(self):
        self._packets: deque = deque(maxlen=self.MAX_LOG)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._serial_port = None

    def start_rtlsdr(self, band: str = "433", gain: float = 40.0) -> str:
        if not RTLSDR_OK:
            return "❌ AirSnitch: pyrtlsdr не установлен (pip install pyrtlsdr)"
        freq_map = {"433": Band.SUB_433.value, "868": Band.SUB_868.value, "915": Band.SUB_915.value}
        freq = freq_map.get(str(band), Band.SUB_433.value)
        self._running = True
        self._thread = threading.Thread(target=self._rtl_loop, args=(freq, gain), daemon=True)
        self._thread.start()
        return f"✅ AirSnitch RTL-SDR запущен [{band} МГц]"

    def start_serial(self, port: str = "/dev/ttyUSB0", baud: int = 115200) -> str:
        if not SERIAL_OK:
            return "❌ AirSnitch: pyserial не установлен"
        try:
            import serial as pyserial
            self._serial_port = pyserial.Serial(port, baud, timeout=1)
            self._running = True
            self._thread = threading.Thread(target=self._serial_loop, daemon=True)
            self._thread.start()
            return f"✅ AirSnitch serial запущен ({port} @{baud})"
        except Exception as e:
            return f"❌ AirSnitch serial: {e}"

    def stop(self) -> str:
        self._running = False
        if self._serial_port:
            try: self._serial_port.close()
            except Exception: pass
        return "✅ AirSnitch остановлен"

    def _rtl_loop(self, freq: float, gain: float):
        try:
            sdr = RtlSdr()
            sdr.sample_rate = 2.048e6
            sdr.center_freq = freq
            sdr.gain = gain
            while self._running:
                if NP_OK:
                    samples = sdr.read_samples(256 * 1024)
                    power = float(np.mean(np.abs(samples) ** 2))
                    rssi = 10 * np.log10(max(power, 1e-12))
                    pkt = RFPacket(freq_hz=freq, rssi_dbm=float(rssi),
                                   modulation="OOK", summary=f"power={rssi:.1f}dBm")
                    self._packets.append(pkt)
                time.sleep(0.5)
            sdr.close()
        except Exception as e:
            log.error("RTL-SDR loop: %s", e)

    def _serial_loop(self):
        while self._running and self._serial_port:
            try:
                line = self._serial_port.readline().decode("ascii", errors="ignore").strip()
                if line.startswith("RF:"):
                    parts = dict(p.split("=") for p in line[3:].split(",") if "=" in p)
                    pkt = RFPacket(
                        freq_hz=float(parts.get("f", 433.92)) * 1e6,
                        rssi_dbm=float(parts.get("rssi", -100)),
                        modulation=parts.get("mod", "OOK"),
                        raw_hex=parts.get("data", ""),
                        protocol=parts.get("proto", ""),
                        summary=line
                    )
                    self._packets.append(pkt)
            except Exception:
                time.sleep(0.1)

    def get_packets(self, limit: int = 50) -> list:
        return [p.to_dict() for p in list(self._packets)[-limit:]]

    def spectrum_summary(self) -> str:
        if not self._packets:
            return "📻 AirSnitch: пакетов нет (запусти сканирование)"
        recent = list(self._packets)[-20:]
        freqs = set(round(p.freq_hz / 1e6, 1) for p in recent)
        avg_rssi = sum(p.rssi_dbm for p in recent) / len(recent)
        return (
            f"📻 AIRSNITCH — {len(self._packets)} пакетов:\n"
            f"  Частоты: {', '.join(str(f)+' МГц' for f in sorted(freqs))}\n"
            f"  Ср. RSSI: {avg_rssi:.1f} dBm\n"
            f"  Активен: {'✅' if self._running else '❌'}"
        )

    def status(self) -> str:
        rtl = "✅" if RTLSDR_OK else "❌"
        serial_ok = "✅" if SERIAL_OK else "❌"
        return (
            f"📻 AIRSNITCH:\n"
            f"  RTL-SDR:  {rtl}\n"
            f"  Serial:   {serial_ok}\n"
            f"  Запущен:  {'✅' if self._running else '❌'}\n"
            f"  Пакетов:  {len(self._packets)}"
        )

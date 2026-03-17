"""
spatial.py -- IP-based geolocation for ARGOS nodes.
Uses ip-api.com (free) with ipinfo.io fallback.
"""
import os, time
from typing import Any, Dict, Optional
from src.argos_logger import get_logger
log = get_logger("argos.spatial")

try:
    import requests as _req
    REQUESTS_OK = True
except ImportError:
    _req = None
    REQUESTS_OK = False


class ArgosGeolocator:
    API1 = "http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp,query,lat,lon,timezone"
    API2 = "https://ipinfo.io/{ip}/json"

    def __init__(self, db=None):
        self.db = db
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_ts = 0.0
        self._ttl = float(os.getenv("ARGOS_GEO_TTL", "3600"))

    def get_location(self, ip: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        now = time.time()
        if not force and self._cache and (now - self._cache_ts) < self._ttl:
            return self._cache
        target = ip or self._ext_ip()
        result = self._query(target)
        if result:
            self._cache = result
            self._cache_ts = now
        return result or {}

    def _ext_ip(self) -> str:
        if not REQUESTS_OK:
            return "127.0.0.1"
        for url in ["https://api.ipify.org", "https://ifconfig.me/ip"]:
            try:
                r = _req.get(url, timeout=5)
                if r.ok:
                    return r.text.strip()
            except Exception:
                pass
        return "127.0.0.1"

    def _query(self, ip: str) -> Optional[Dict[str, Any]]:
        if ip in ("127.0.0.1", "localhost"):
            return {"ip": ip, "city": "Local", "country": "Local",
                    "isp": "localhost", "lat": 0.0, "lon": 0.0, "timezone": "UTC"}
        if not REQUESTS_OK:
            return {"ip": ip, "city": "Unknown", "country": "Unknown",
                    "isp": "N/A", "lat": 0.0, "lon": 0.0}
        try:
            r = _req.get(self.API1.format(ip=ip), timeout=5)
            if r.ok:
                d = r.json()
                if d.get("status") == "success":
                    return {"ip": d.get("query", ip), "country": d.get("country","?"),
                            "region": d.get("regionName","?"), "city": d.get("city","?"),
                            "isp": d.get("isp","?"), "lat": d.get("lat",0.0),
                            "lon": d.get("lon",0.0), "timezone": d.get("timezone","UTC")}
        except Exception as e:
            log.debug("ip-api: %s", e)
        try:
            r2 = _req.get(self.API2.format(ip=ip), timeout=5)
            if r2.ok:
                d2 = r2.json()
                loc = d2.get("loc","0,0").split(",")
                return {"ip": d2.get("ip",ip), "country": d2.get("country","?"),
                        "region": d2.get("region","?"), "city": d2.get("city","?"),
                        "isp": d2.get("org","?"),
                        "lat": float(loc[0]) if len(loc)==2 else 0.0,
                        "lon": float(loc[1]) if len(loc)==2 else 0.0,
                        "timezone": d2.get("timezone","UTC")}
        except Exception as e:
            log.debug("ipinfo: %s", e)
        return None

    def format_location(self) -> str:
        loc = self.get_location()
        if not loc:
            return "Геолокация: недоступна"
        return (
            f"Геолокация:\n"
            f"  IP: {loc.get('ip','?')}\n"
            f"  {loc.get('city','?')}, {loc.get('region','?')}, {loc.get('country','?')}\n"
            f"  Провайдер: {loc.get('isp','?')}\n"
            f"  Координаты: {loc.get('lat',0)}, {loc.get('lon',0)}\n"
            f"  Часовой пояс: {loc.get('timezone','UTC')}"
        )

    def get_ip(self) -> str:
        return self.get_location().get("ip", "?")

    def status(self) -> str:
        loc = self._cache
        if not loc:
            return "Spatial: кэш пуст"
        return (f"Spatial: IP={loc.get('ip','?')}  "
                f"city={loc.get('city','?')}  country={loc.get('country','?')}")

    def get_full_report(self) -> str:
        return self.format_location()


GeoLocator = ArgosGeolocator
SpatialBridge = ArgosGeolocator
SpatialAwareness = ArgosGeolocator

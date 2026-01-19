import time
import random
from dataclasses import dataclass
from typing import Optional, Dict, Any

import httpx

@dataclass
class CuveReading:
    distance_cm: int
    timestamp: str
    ip: str
    fetched_at_epoch: float

class CuveClient:
    async def get_reading(self, force_refresh: bool = False) -> CuveReading:
        raise NotImplementedError

class RealCuveClient(CuveClient):
    def __init__(self, sensor_url: str, cache_ttl_seconds: int, http_timeout_seconds: float):
        self.sensor_url = sensor_url
        self.cache_ttl_seconds = cache_ttl_seconds
        self.http_timeout_seconds = http_timeout_seconds
        self._cache: Optional[CuveReading] = None

    def _cache_valid(self) -> bool:
        if not self._cache:
            return False
        return (time.time() - self._cache.fetched_at_epoch) < self.cache_ttl_seconds

    async def get_reading(self, force_refresh: bool = False) -> CuveReading:
        if (not force_refresh) and self._cache_valid():
            return self._cache

        async with httpx.AsyncClient(timeout=self.http_timeout_seconds) as client:
            resp = await client.get(self.sensor_url)
            resp.raise_for_status()
            data: Dict[str, Any] = resp.json()

        distance_cm = int(data.get("distance_cm", -1))
        timestamp = str(data.get("timestamp", ""))
        ip = str(data.get("ip", ""))

        reading = CuveReading(
            distance_cm=distance_cm,
            timestamp=timestamp,
            ip=ip,
            fetched_at_epoch=time.time(),
        )
        self._cache = reading
        return reading

class SimCuveClient(CuveClient):
    """
    Simulation simple :
    - distance qui varie doucement autour d'une valeur de base
    - timestamp "maintenant"
    - ip factice
    """
    def __init__(self, base_distance_cm: int = 30):
        self.base = base_distance_cm
        self._last = base_distance_cm

    async def get_reading(self, force_refresh: bool = False) -> CuveReading:
        # petit drift + bruit
        drift = random.choice([-1, 0, 0, 0, 1])          # drift lent
        noise = random.randint(-2, 2)                    # bruit
        self._last = max(0, self._last + drift + noise)

        # timestamp ISO-like (simple)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())

        return CuveReading(
            distance_cm=int(self._last),
            timestamp=ts,
            ip="simulated",
            fetched_at_epoch=time.time(),
        )

import asyncio
import time
import logging
from typing import Optional, Dict, List

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import settings
from app.cuve import RealCuveClient, SimCuveClient
from app import db as cuve_db
from app.db import Period, Order
from app.volume import volume_liters_from_distance_cm

app = FastAPI(title="Cuve API", version="0.3.0")
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


class LastResponse(BaseModel):
    has_data: bool
    distance_cm: Optional[int] = None
    sensor_timestamp: Optional[str] = None
    sensor_ip: Optional[str] = None
    fetched_at_epoch: Optional[float] = None
    age_seconds: Optional[int] = None
    volume_liters: Optional[float] = None
    fill_percent: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "has_data": True,
                "distance_cm": 48,
                "sensor_timestamp": "2026-01-19T08:30:00+0100",
                "sensor_ip": "192.168.1.50",
                "fetched_at_epoch": 1768801800.0,
                "age_seconds": 12,
                "volume_liters": 7420.5,
                "fill_percent": 74.2,
            }
        }


class HealthResponse(BaseModel):
    status: str
    mode: str
    db_path: str
    collect_interval_seconds: int
    has_data: bool

    class Config:
        json_schema_extra = {
            "example": {
                "status": "ok",
                "mode": "real",
                "db_path": "cuve.sqlite3",
                "collect_interval_seconds": 60,
                "has_data": True,
            }
        }


class ExtremeItem(BaseModel):
    distance_cm: int
    sensor_timestamp: str
    sensor_ip: Optional[str] = None
    fetched_at_epoch: float
    volume_liters: Optional[float] = None
    fill_percent: Optional[float] = None


class ExtremesResponse(BaseModel):
    period: Period
    order: Order
    count: int
    items: List[ExtremeItem]

    class Config:
        json_schema_extra = {
            "example": {
                "period": "day",
                "order": "max",
                "count": 2,
                "items": [
                    {
                        "distance_cm": 40,
                        "sensor_timestamp": "2026-01-19T07:45:00+0100",
                        "sensor_ip": "192.168.1.50",
                        "fetched_at_epoch": 1768799100.0,
                        "volume_liters": 8200.0,
                        "fill_percent": 82.0,
                    },
                    {
                        "distance_cm": 42,
                        "sensor_timestamp": "2026-01-19T06:45:00+0100",
                        "sensor_ip": "192.168.1.50",
                        "fetched_at_epoch": 1768795500.0,
                        "volume_liters": 7900.0,
                        "fill_percent": 79.0,
                    },
                ],
            }
        }


class TankInfo(BaseModel):
    total_liters: float
    diameter_cm: float
    length_cm: float
    full_air_gap_cm: float


class ExtremesByOrder(BaseModel):
    max: List[ExtremeItem]
    min: List[ExtremeItem]


class DashboardResponse(BaseModel):
    tank: TankInfo
    mode: str
    has_data: bool
    last: Optional[LastResponse]
    extremes: Dict[Period, ExtremesByOrder]

    class Config:
        json_schema_extra = {
            "example": {
                "tank": {
                    "total_liters": 10000.0,
                    "diameter_cm": 184.5,
                    "length_cm": 436.4,
                    "full_air_gap_cm": 20.0,
                },
                "mode": "real",
                "has_data": True,
                "last": {
                    "has_data": True,
                    "distance_cm": 48,
                    "sensor_timestamp": "2026-01-19T08:30:00+0100",
                    "sensor_ip": "192.168.1.50",
                    "fetched_at_epoch": 1768801800.0,
                    "age_seconds": 12,
                    "volume_liters": 7420.5,
                    "fill_percent": 74.2,
                },
                "extremes": {
                    "day": {
                        "max": [
                            {
                                "distance_cm": 40,
                                "sensor_timestamp": "2026-01-19T07:45:00+0100",
                                "sensor_ip": "192.168.1.50",
                                "fetched_at_epoch": 1768799100.0,
                                "volume_liters": 8200.0,
                                "fill_percent": 82.0,
                            }
                        ],
                        "min": [
                            {
                                "distance_cm": 120,
                                "sensor_timestamp": "2026-01-19T01:30:00+0100",
                                "sensor_ip": "192.168.1.50",
                                "fetched_at_epoch": 1768776600.0,
                                "volume_liters": 3100.0,
                                "fill_percent": 31.0,
                            }
                        ],
                    },
                    "week": {"max": [], "min": []},
                    "month": {"max": [], "min": []},
                    "year": {"max": [], "min": []},
                    "all": {"max": [], "min": []},
                },
            }
        }


# -----------------------------------------------------------------------------
# Client capteur (real/sim)
# -----------------------------------------------------------------------------
if settings.mode == "sim":
    cuve = SimCuveClient(base_distance_cm=30)
else:
    cuve = RealCuveClient(
        sensor_url=settings.sensor_url,  # garanti non-null par config.py
        cache_ttl_seconds=settings.cache_ttl_seconds,
        http_timeout_seconds=settings.http_timeout_seconds,
    )

# -----------------------------------------------------------------------------
# DB
# -----------------------------------------------------------------------------
cuve_db.init_db(settings.db_path)

_collect_task: asyncio.Task | None = None


def with_volume_fields(item: dict) -> dict:
    """
    Ajoute volume_liters et fill_percent à partir de distance_cm.
    """
    distance_cm = item.get("distance_cm")
    if distance_cm is None:
        item["volume_liters"] = None
        item["fill_percent"] = None
        return item

    try:
        vol = volume_liters_from_distance_cm(
            float(distance_cm),
            total_volume_liters=settings.tank_total_volume_liters,
            diameter_cm=settings.tank_diameter_cm,
            length_cm=settings.tank_length_cm,
            full_air_gap_cm=settings.tank_full_air_gap_cm,
        )
        item["volume_liters"] = round(vol, 1)
        if settings.tank_total_volume_liters > 0:
            item["fill_percent"] = round((vol / settings.tank_total_volume_liters) * 100.0, 1)
        else:
            item["fill_percent"] = None
    except Exception:
        item["volume_liters"] = None
        item["fill_percent"] = None

    return item


async def collector_loop():
    """
    Collecte en tâche de fond :
    - tente de lire le capteur
    - en cas d’échec : ne plante pas, réessaie plus tard
    - en cas de succès : insert en DB (avec dédoublonnage sur timestamp capteur)
    """
    interval = max(5, settings.collect_interval_seconds)
    while True:
        try:
            reading = await cuve.get_reading(force_refresh=True)

            # Filtre basique : on n'insère que si la mesure semble valide
            if reading.distance_cm >= 0 and reading.timestamp:
                cuve_db.insert_reading(
                    settings.db_path,
                    distance_cm=reading.distance_cm,
                    sensor_timestamp=reading.timestamp,
                    sensor_ip=reading.ip,
                    fetched_at_epoch=reading.fetched_at_epoch,
                    dedupe_by_sensor_ts=True,
                )
            else:
                logger.warning(
                    "Mesure rejetee (distance_cm=%s, timestamp=%s)",
                    reading.distance_cm,
                    reading.timestamp,
                )
        except Exception as exc:
            # On ignore volontairement toute erreur (wifi capricieux, timeout, etc.)
            logger.warning("Erreur collecte capteur", exc_info=exc)

        await asyncio.sleep(interval)


@app.on_event("startup")
async def on_startup():
    global _collect_task
    _collect_task = asyncio.create_task(collector_loop())


@app.on_event("shutdown")
async def on_shutdown():
    global _collect_task
    if _collect_task:
        _collect_task.cancel()


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health():
    last = cuve_db.get_last(settings.db_path)
    return {
        "status": "ok",
        "mode": settings.mode,
        "db_path": settings.db_path,
        "collect_interval_seconds": settings.collect_interval_seconds,
        "has_data": last is not None,
    }


@app.get("/api/last", response_model=LastResponse)
async def api_last():
    last = cuve_db.get_last(settings.db_path)
    if not last:
        return {"has_data": False}

    payload = {
        "has_data": True,
        "distance_cm": last.distance_cm,
        "sensor_timestamp": last.sensor_timestamp,
        "sensor_ip": last.sensor_ip,
        "fetched_at_epoch": last.fetched_at_epoch,
        "age_seconds": int(time.time() - last.fetched_at_epoch),
    }
    return with_volume_fields(payload)


@app.get("/api/extremes", response_model=ExtremesResponse)
async def api_extremes(
        period: Period = Query("day"),
        order: Order = Query("max"),
        n: int = Query(5, ge=1, le=50),
):
    rows = cuve_db.get_extremes(settings.db_path, period=period, n=n, order=order)
    items = []
    for r in rows:
        it = {
            "distance_cm": r.distance_cm,
            "sensor_timestamp": r.sensor_timestamp,
            "sensor_ip": r.sensor_ip,
            "fetched_at_epoch": r.fetched_at_epoch,
        }
        items.append(with_volume_fields(it))

    return {
        "period": period,
        "order": order,
        "count": len(items),
        "items": items,
    }


@app.get("/api/dashboard", response_model=DashboardResponse)
async def api_dashboard(n: int = Query(5, ge=1, le=50)):
    """
    Endpoint “tout-en-un” pratique pour la page web.
    Retourne :
    - dernières infos (last)
    - top/bottom par période (day/week/month/year/all)
    - paramètres cuve (tank)
    """
    last = cuve_db.get_last(settings.db_path)

    def extremes(period: Period, order: Order):
        rows = cuve_db.get_extremes(settings.db_path, period=period, n=n, order=order)
        return [
            with_volume_fields({
                "distance_cm": r.distance_cm,
                "sensor_timestamp": r.sensor_timestamp,
                "fetched_at_epoch": r.fetched_at_epoch,
            })
            for r in rows
        ]

    periods: list[Period] = ["day", "week", "month", "year", "all"]

    return {
        "tank": {
            "total_liters": settings.tank_total_volume_liters,
            "diameter_cm": settings.tank_diameter_cm,
            "length_cm": settings.tank_length_cm,
            "full_air_gap_cm": settings.tank_full_air_gap_cm,
        },
        "mode": settings.mode,
        "has_data": last is not None,
        "last": None if not last else with_volume_fields({
            "has_data": True,
            "distance_cm": last.distance_cm,
            "sensor_timestamp": last.sensor_timestamp,
            "sensor_ip": last.sensor_ip,
            "fetched_at_epoch": last.fetched_at_epoch,
            "age_seconds": int(time.time() - last.fetched_at_epoch),
        }),
        "extremes": {
            p: {
                "max": extremes(p, "max"),
                "min": extremes(p, "min"),
            }
            for p in periods
        },
    }


# Alias compat (si tu veux garder /api/current pour Jeedom)
@app.get("/api/current", response_model=LastResponse)
async def api_current():
    return await api_last()


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # La page consomme /api/dashboard en JS (pas d'appel direct capteur ici)
    version = time.strftime("%d.%m.%Y %Hh%M")
    return templates.TemplateResponse("index.html", {"request": request, "version": version})

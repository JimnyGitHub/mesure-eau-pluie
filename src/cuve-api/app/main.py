import asyncio
import time

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.cuve import RealCuveClient, SimCuveClient
from app import db as cuve_db
from app.db import Period, Order
from app.volume import volume_liters_from_distance_cm

app = FastAPI(title="Cuve API", version="0.3.0")
templates = Jinja2Templates(directory="app/templates")

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
        except Exception:
            # On ignore volontairement toute erreur (wifi capricieux, timeout, etc.)
            pass

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
@app.get("/health")
async def health():
    last = cuve_db.get_last(settings.db_path)
    return {
        "status": "ok",
        "mode": settings.mode,
        "db_path": settings.db_path,
        "collect_interval_seconds": settings.collect_interval_seconds,
        "has_data": last is not None,
    }


@app.get("/api/last")
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


@app.get("/api/extremes")
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


@app.get("/api/dashboard")
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
@app.get("/api/current")
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

from dataclasses import dataclass
import os
from dotenv import load_dotenv

# Charge .env si présent (local), sinon pas grave (prod via variables d'env)
load_dotenv()

@dataclass(frozen=True)
class Settings:
    # real = appelle le capteur ESP ; sim = capteur simulé
    mode: str = os.getenv("CUVE_MODE", "real").strip().lower()

    # URL du capteur (uniquement nécessaire en mode real)
    sensor_url: str | None = os.getenv("CUVE_SENSOR_URL")

    # paramètres relatifs au client réel
    cache_ttl_seconds: int = int(os.getenv("CUVE_CACHE_TTL_SECONDS", "10"))
    http_timeout_seconds: float = float(os.getenv("CUVE_HTTP_TIMEOUT_SECONDS", "2.0"))
    # paramètres relatifs à la collecte et à la DB
    db_path: str = os.getenv("CUVE_DB_PATH", "cuve.sqlite3")
    collect_interval_seconds: int = int(os.getenv("CUVE_COLLECT_INTERVAL_SECONDS", "60"))

    # Paramètres cuve (pour calcul volume / %)
    tank_total_volume_liters: float = float(os.getenv("CUVE_TANK_TOTAL_LITERS", "10000"))
    tank_diameter_cm: float = float(os.getenv("CUVE_TANK_DIAMETER_CM", "184.5"))
    tank_length_cm: float = float(os.getenv("CUVE_TANK_LENGTH_CM", "436.4"))
    tank_full_air_gap_cm: float = float(os.getenv("CUVE_TANK_FULL_AIR_GAP_CM", "20"))


settings = Settings()

if settings.mode not in ("real", "sim"):
    raise RuntimeError(f"CUVE_MODE invalide: {settings.mode} (attendu: real ou sim)")

if settings.mode == "real" and not settings.sensor_url:
    raise RuntimeError("CUVE_SENSOR_URL est requis quand CUVE_MODE=real")

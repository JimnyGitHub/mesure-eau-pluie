import sqlite3
import time
from dataclasses import dataclass
from typing import Optional, List, Literal

Order = Literal["max", "min"]
Period = Literal["day", "week", "month", "year", "all"]

@dataclass(frozen=True)
class DbReading:
    id: int
    distance_cm: int
    sensor_timestamp: str
    sensor_ip: str
    fetched_at_epoch: float

def init_db(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("""
                    CREATE TABLE IF NOT EXISTS readings (
                                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                            distance_cm INTEGER NOT NULL,
                                                            sensor_timestamp TEXT NOT NULL,
                                                            sensor_ip TEXT NOT NULL,
                                                            fetched_at_epoch REAL NOT NULL
                    )
                    """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_readings_fetched_at ON readings(fetched_at_epoch)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_readings_distance ON readings(distance_cm)")
        con.commit()
    finally:
        con.close()

def _connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con

def get_last(db_path: str) -> Optional[DbReading]:
    con = _connect(db_path)
    try:
        row = con.execute("""
                          SELECT id, distance_cm, sensor_timestamp, sensor_ip, fetched_at_epoch
                          FROM readings
                          ORDER BY fetched_at_epoch DESC, id DESC
                              LIMIT 1
                          """).fetchone()
        if not row:
            return None
        return DbReading(**dict(row))
    finally:
        con.close()

def get_last_n(db_path: str, n: int) -> List[DbReading]:
    con = _connect(db_path)
    try:
        rows = con.execute("""
                           SELECT id, distance_cm, sensor_timestamp, sensor_ip, fetched_at_epoch
                           FROM readings
                           ORDER BY fetched_at_epoch DESC, id DESC
                               LIMIT ?
                           """, (n,)).fetchall()
        return [DbReading(**dict(r)) for r in rows]
    finally:
        con.close()

def _since_epoch(period: Period) -> Optional[float]:
    now = time.time()
    if period == "all":
        return None
    if period == "day":
        return now - 24 * 3600
    if period == "week":
        return now - 7 * 24 * 3600
    if period == "month":
        return now - 30 * 24 * 3600
    if period == "year":
        return now - 365 * 24 * 3600
    raise ValueError(f"Unknown period: {period}")

def get_extremes(db_path: str, period: Period, n: int, order: Order) -> List[DbReading]:
    since = _since_epoch(period)
    con = _connect(db_path)
    try:
        where = ""
        params = []
        if since is not None:
            where = "WHERE fetched_at_epoch >= ?"
            params.append(since)

        if order == "max":
            sql = f"""
                SELECT id, distance_cm, sensor_timestamp, sensor_ip, fetched_at_epoch
                FROM readings
                {where}
                ORDER BY distance_cm DESC, fetched_at_epoch DESC, id DESC
                LIMIT ?
            """
        else:
            sql = f"""
                SELECT id, distance_cm, sensor_timestamp, sensor_ip, fetched_at_epoch
                FROM readings
                {where}
                ORDER BY distance_cm ASC, fetched_at_epoch DESC, id DESC
                LIMIT ?
            """

        params.append(n)
        rows = con.execute(sql, tuple(params)).fetchall()
        return [DbReading(**dict(r)) for r in rows]
    finally:
        con.close()

def insert_reading(
        db_path: str,
        distance_cm: int,
        sensor_timestamp: str,
        sensor_ip: str,
        fetched_at_epoch: float,
        dedupe_by_sensor_ts: bool = True,
) -> bool:
    """
    Retourne True si inséré, False si ignoré (doublon).
    """
    con = _connect(db_path)
    try:
        if dedupe_by_sensor_ts:
            row = con.execute("""
                              SELECT sensor_timestamp
                              FROM readings
                              ORDER BY fetched_at_epoch DESC, id DESC
                                  LIMIT 1
                              """).fetchone()
            if row and row["sensor_timestamp"] == sensor_timestamp and sensor_timestamp:
                return False

        con.execute("""
                    INSERT INTO readings(distance_cm, sensor_timestamp, sensor_ip, fetched_at_epoch)
                    VALUES(?, ?, ?, ?)
                    """, (distance_cm, sensor_timestamp, sensor_ip, fetched_at_epoch))
        con.commit()
        return True
    finally:
        con.close()

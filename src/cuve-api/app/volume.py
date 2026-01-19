import math

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def distance_cm_to_height_cm(
        distance_cm: float,
        *,
        full_air_gap_cm: float,
        diameter_cm: float,
) -> float:
    d_empty = full_air_gap_cm + diameter_cm
    h = d_empty - distance_cm
    return clamp(h, 0.0, diameter_cm)

def _cylinder_full_liters(diameter_cm: float, length_cm: float) -> float:
    r = (diameter_cm / 100.0) / 2.0
    L = length_cm / 100.0
    return math.pi * r * r * L * 1000.0

def volume_liters_from_distance_cm(
        distance_cm: float,
        *,
        total_volume_liters: float = 10_000.0,  # volume nominal constructeur
        diameter_cm: float = 184.5,             # STP = 1845 mm
        length_cm: float = 436.4,               # L = 4364 mm
        full_air_gap_cm: float = 20.0,
) -> float:
    # 1) hauteur d'eau
    h_cm = distance_cm_to_height_cm(
        distance_cm,
        full_air_gap_cm=full_air_gap_cm,
        diameter_cm=diameter_cm,
    )

    # 2) géométrie en mètres
    r = (diameter_cm / 100.0) / 2.0
    h = h_cm / 100.0
    L = length_cm / 100.0
    h = clamp(h, 0.0, 2.0 * r)

    if h == 0.0:
        return 0.0

    # 3) aire du segment rempli
    if h == 2.0 * r:
        v_raw = _cylinder_full_liters(diameter_cm, length_cm)
    else:
        A = (r * r) * math.acos((r - h) / r) - (r - h) * math.sqrt(2.0 * r * h - h * h)
        v_raw = (A * L) * 1000.0

    # 4) scaling vers volume nominal
    v_full_raw = _cylinder_full_liters(diameter_cm, length_cm)
    if v_full_raw <= 0:
        return 0.0

    k = total_volume_liters / v_full_raw
    v = v_raw * k

    return float(clamp(v, 0.0, total_volume_liters))

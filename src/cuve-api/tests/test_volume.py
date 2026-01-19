from app.volume import volume_liters_from_distance_cm

def test_full_is_10000L():
    v = volume_liters_from_distance_cm(20.0)
    assert abs(v - 10_000.0) < 1e-6

def test_empty_is_0L():
    v = volume_liters_from_distance_cm(204.5)
    assert abs(v - 0.0) < 1e-6

def test_half_height_is_about_half_volume():
    v = volume_liters_from_distance_cm(112.25)
    assert abs(v - 5_000.0) < 5.0

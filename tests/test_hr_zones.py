"""HR-zone resolution: Karvonen math + me.json overrides (hr_max / hr_zones)."""
import pytest

from generate import resolve_zone_bounds, zone_bounds

# A fixed "current year" so the age-based fallback is deterministic in tests.
YEAR = 2026


def test_zone_bounds_karvonen_math():
    # HRR = 190 - 44 = 146; thresholds at 60/70/80/90% of reserve above resting.
    assert zone_bounds(190, 44) == pytest.approx([131.6, 146.2, 160.8, 175.4])


def test_zone_bounds_never_divides_by_zero():
    # max <= rest must not blow up (hrr floored at 1.0).
    assert zone_bounds(40, 40) == pytest.approx([40.6, 40.7, 40.8, 40.9])


def test_custom_zones_used_verbatim():
    cfg = {"hr_zones": [138, 152, 164, 173]}
    max_hr, bounds, mode = resolve_zone_bounds(cfg, obs_max=181, birth_year=1990,
                                               rest_hr=44, today_year=YEAR)
    assert mode == "custom"
    assert bounds == [138.0, 152.0, 164.0, 173.0]
    assert all(isinstance(b, float) for b in bounds)
    # with no hr_max pinned, max still comes from observed/age (max(181, 184) = 184)
    assert max_hr == 184


def test_custom_zones_win_over_karvonen_and_use_pinned_max():
    cfg = {"hr_max": 190, "hr_zones": [138, 152, 164, 173]}
    max_hr, bounds, mode = resolve_zone_bounds(cfg, obs_max=170, birth_year=1990,
                                               rest_hr=44, today_year=YEAR)
    assert mode == "custom"
    assert bounds == [138.0, 152.0, 164.0, 173.0]
    assert max_hr == 190


def test_pinned_hr_max_uses_karvonen_on_that_max():
    cfg = {"hr_max": 190}
    max_hr, bounds, mode = resolve_zone_bounds(cfg, obs_max=170, birth_year=1990,
                                               rest_hr=44, today_year=YEAR)
    assert mode == "pinned"
    assert max_hr == 190
    assert bounds == zone_bounds(190, 44)


def test_fallback_uses_observed_max_when_it_dominates():
    max_hr, bounds, mode = resolve_zone_bounds({}, obs_max=192, birth_year=1990,
                                               rest_hr=48, today_year=YEAR)
    assert mode == "auto"
    assert max_hr == 192  # observed beats the age estimate (184)
    assert bounds == zone_bounds(192, 48)


def test_fallback_uses_age_estimate_when_observed_is_low():
    # obs low (e.g. wrist data / no HR) → age estimate 220 - (2026 - 1990) = 184.
    max_hr, bounds, mode = resolve_zone_bounds({}, obs_max=120, birth_year=1990,
                                               rest_hr=48, today_year=YEAR)
    assert mode == "auto"
    assert max_hr == 184
    assert bounds == zone_bounds(184, 48)

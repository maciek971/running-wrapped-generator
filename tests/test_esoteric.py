"""Checks for the esoteric maths.

The astronomy is pinned against independently published Mercury retrograde dates;
the numerology and biorhythm against values derivable by hand. If a change here
moves a station date by more than a day, the elements or Kepler solver broke.
"""
from datetime import date, timedelta

import pytest

from lib_esoteric import (biorhythm, biorhythm_percent, digit_sum, digital_root,
                          is_critical, is_mercury_retrograde, julian_day,
                          mercury_geocentric_longitude, next_retrograde,
                          personal_number, retrograde_periods, to_base_digit)


# ---------------------------------------------------------------- numerology

@pytest.mark.parametrize("n,base,expected", [
    (19900827, 10, 1 + 9 + 9 + 0 + 0 + 8 + 2 + 7),
    (0, 10, 0),
    (255, 16, 15 + 15),          # 0xFF
    (4096, 16, 1),               # 0x1000
])
def test_digit_sum(n, base, expected):
    assert digit_sum(n, base) == expected


@pytest.mark.parametrize("n,base,expected", [
    (0, 10, 0),
    (9, 10, 9),
    (10, 10, 1),
    (19900827, 10, 9),           # 36 -> 9
    (255, 16, 15),               # 30 = 0x1E -> 1+14 = 15 = F
    (31, 16, 1),                 # 0x1F -> 16 -> 0x10 -> 1
])
def test_digital_root(n, base, expected):
    assert digital_root(n, base) == expected


def test_digital_root_stays_in_range_for_both_bases():
    for n in range(1, 3000):
        assert 1 <= digital_root(n, 10) <= 9
        assert 1 <= digital_root(n, 16) <= 15


def test_personal_number_differs_between_bases():
    """The whole point of the hex tab: same dates, same procedure, other answer."""
    birth, day = date(1990, 8, 27), date(2026, 7, 26)
    d10 = personal_number(birth, day, 10)
    d16 = personal_number(birth, day, 16)
    assert 1 <= d10 <= 9
    assert 1 <= d16 <= 15
    assert d10 != d16 or d16 > 9      # if they coincide the joke needs no hex digit


def test_personal_number_base10_is_hand_checkable():
    # 19900827 -> 36; 20260726 -> 25; 36+25 = 61 -> 7
    assert personal_number(date(1990, 8, 27), date(2026, 7, 26), 10) == 7


def test_to_base_digit():
    assert to_base_digit(7, 10) == "7"
    assert to_base_digit(11, 16) == "B"
    assert to_base_digit(15, 16) == "F"


# ----------------------------------------------------------------- biorhythm

def test_biorhythm_is_zero_on_birthday():
    b = date(1990, 8, 27)
    assert all(abs(v) < 1e-9 for v in biorhythm(b, b).values())


def test_biorhythm_peaks_at_quarter_cycle():
    b = date(1990, 8, 27)
    assert biorhythm(b, b + timedelta(days=23 // 4 + 1))["physical"] > 0.9
    assert biorhythm(b, b + timedelta(days=7))["emotional"] == pytest.approx(1.0, abs=1e-9)


def test_biorhythm_returns_to_zero_after_full_cycle():
    b = date(1990, 8, 27)
    assert abs(biorhythm(b, b + timedelta(days=23))["physical"]) < 1e-9
    assert abs(biorhythm(b, b + timedelta(days=28))["emotional"]) < 1e-9
    assert abs(biorhythm(b, b + timedelta(days=33))["intellectual"]) < 1e-9


def test_biorhythm_percent_is_whole_numbers_in_range():
    b = date(1990, 8, 27)
    for i in range(0, 400, 7):
        for v in biorhythm_percent(b, b + timedelta(days=i)).values():
            assert isinstance(v, int) and -100 <= v <= 100


def test_critical_day_detected_at_cycle_boundary():
    b = date(1990, 8, 27)
    assert is_critical(b, b + timedelta(days=23), "physical")
    assert is_critical(b, b + timedelta(days=28), "emotional")


def test_non_critical_day_at_peak():
    b = date(1990, 8, 27)
    assert not is_critical(b, b + timedelta(days=7), "emotional")


# ------------------------------------------------------------------- astronomy

def test_julian_day_known_epoch():
    # 2000-01-01 12:00 UT is JD 2451545.0 by definition
    assert julian_day(date(2000, 1, 1), 12.0) == pytest.approx(2451545.0, abs=1e-6)
    assert julian_day(date(1957, 10, 4), 19.4667) == pytest.approx(2436116.31, abs=0.01)


def test_mercury_longitude_is_a_bearing():
    for d in (date(2014, 1, 1), date(2020, 6, 15), date(2026, 8, 1)):
        assert 0.0 <= mercury_geocentric_longitude(d) < 360.0


@pytest.mark.parametrize("start,end", [
    (date(2026, 2, 26), date(2026, 3, 20)),
    (date(2026, 6, 29), date(2026, 7, 23)),
    (date(2026, 10, 24), date(2026, 11, 13)),
    (date(2025, 3, 15), date(2025, 4, 7)),
    (date(2024, 8, 5), date(2024, 8, 28)),
])
def test_retrograde_matches_published_dates(start, end):
    """Published station dates; allow one day of slack for the daily grid."""
    assert is_mercury_retrograde(start + timedelta(days=2))
    assert is_mercury_retrograde(end - timedelta(days=2))
    assert not is_mercury_retrograde(start - timedelta(days=3))
    assert not is_mercury_retrograde(end + timedelta(days=3))


def test_retrograde_happens_about_three_times_a_year():
    spans = retrograde_periods(date(2020, 1, 15), date(2024, 12, 15))
    per_year = len(spans) / 5
    assert 2.8 <= per_year <= 3.4
    for a, b in spans:
        assert 17 <= (b - a).days + 1 <= 26      # Mercury retrogrades run ~3 weeks


def test_next_retrograde_is_in_the_future():
    span = next_retrograde(date(2026, 8, 3))
    assert span is not None
    assert span[0] > date(2026, 8, 3)
    assert span[0] == date(2026, 10, 24)


def test_retrograde_is_deterministic():
    a = retrograde_periods(date(2026, 1, 1), date(2026, 12, 31))
    b = retrograde_periods(date(2026, 1, 1), date(2026, 12, 31))
    assert a == b

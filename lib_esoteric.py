"""Deterministic, dependency-free maths for the esoteric chapter.

Three unrelated bits of folklore, each reduced to arithmetic:

* Mercury retrograde — computed from Keplerian elements rather than a hardcoded
  table of dates, so it stays correct past whatever year someone runs this in.
  Elements are Standish's (JPL) mean values, good for 1800-2050 to well under a
  degree; station dates land within a day, which is all a daily grid can resolve.
* Biorhythms — the 23/28/33-day sine curves from the 1970s craze.
* Numerology — digital roots, in any base, which is the joke: the "universe"
  turns out to count in whichever base you hand it.

No network, no ephemeris files, no randomness: two builds on the same data and
date produce byte-identical output.
"""
import math
from datetime import date, timedelta

# ---------------------------------------------------------------- numerology

def digit_sum(n, base=10):
    """Sum of the digits of n written in the given base."""
    n = abs(int(n))
    total = 0
    while n:
        total += n % base
        n //= base
    return total


def digital_root(n, base=10):
    """Repeatedly sum digits until one digit remains. Returns 1..base-1 (0 only for 0).

    The closed form (n-1) % (base-1) + 1 is deliberately avoided: the iterative
    version is what the folklore actually describes, and it makes the base-16
    variant obviously the same procedure rather than a different trick.
    """
    n = abs(int(n))
    if n == 0:
        return 0
    while n >= base:
        n = digit_sum(n, base)
    return n


def personal_number(birth: date, day: date, base=10):
    """The 'personal day number' — birth date plus target date, reduced.

    base=10 uses the decimal digits of YYYYMMDD, which is how numerology defines
    it. base=16 applies the identical procedure to the same two dates written in
    hex; nothing else changes, and the answer does.
    """
    if base == 10:
        a = digit_sum(int(f"{birth.year}{birth.month:02d}{birth.day:02d}"), 10)
        b = digit_sum(int(f"{day.year}{day.month:02d}{day.day:02d}"), 10)
    else:
        a = digit_sum(int(f"{birth.year}{birth.month:02d}{birth.day:02d}"), base)
        b = digit_sum(int(f"{day.year}{day.month:02d}{day.day:02d}"), base)
    return digital_root(a + b, base)


def to_base_digit(value, base=16):
    """Render a single digit in the given base: 11 -> 'B' for hex."""
    return "0123456789ABCDEF"[value] if base == 16 else str(value)


# ----------------------------------------------------------------- biorhythm

CYCLES = {"physical": 23, "emotional": 28, "intellectual": 33}


def biorhythm(birth: date, day: date):
    """Return {name: value in -1..1} for the three classic cycles."""
    d = (day - birth).days
    return {k: math.sin(2 * math.pi * d / p) for k, p in CYCLES.items()}


def biorhythm_percent(birth: date, day: date):
    """Same, rounded to whole percent — what the page displays."""
    return {k: round(100 * v) for k, v in biorhythm(birth, day).items()}


def is_critical(birth: date, day: date, name: str):
    """A 'critical day': the curve crosses zero, i.e. changes sign vs yesterday.

    Also treats a near-zero value as critical, matching how the folklore is
    normally stated (the crossing is not observed to the minute).
    """
    today = biorhythm(birth, day)[name]
    yesterday = biorhythm(birth, day - timedelta(days=1))[name]
    return (today == 0) or (today * yesterday < 0) or (abs(100 * today) < 5)


# ------------------------------------------------------------------- astronomy

def julian_day(d: date, hour=12.0):
    """Julian Day for a civil date at the given UT hour."""
    y, m = d.year, d.month
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return (int(365.25 * (y + 4716)) + int(30.6001 * (m + 1))
            + d.day + b - 1524.5 + hour / 24.0)


# a, e, I, L, longitude of perihelion, longitude of ascending node
# and their per-Julian-century rates (Standish, JPL, 1800-2050)
_ELEMENTS = {
    "mercury": ((0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593),
                (0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081)),
    "earth":   ((1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
                (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0)),
}


def _heliocentric_xyz(body, jd):
    """Ecliptic rectangular coordinates (AU) of a planet at Julian Day jd."""
    base, rate = _ELEMENTS[body]
    t = (jd - 2451545.0) / 36525.0
    a, e, inc, ml, peri, node = (b + r * t for b, r in zip(base, rate))
    arg_peri = peri - node
    m = math.radians((ml - peri) % 360.0)
    e_anom = m
    for _ in range(60):                      # Kepler, Newton-Raphson
        delta = (e_anom - e * math.sin(e_anom) - m) / (1 - e * math.cos(e_anom))
        e_anom -= delta
        if abs(delta) < 1e-12:
            break
    xp = a * (math.cos(e_anom) - e)
    yp = a * math.sqrt(1 - e * e) * math.sin(e_anom)
    ap, nd, ic = map(math.radians, (arg_peri, node, inc))
    cw, sw = math.cos(ap), math.sin(ap)
    co, so = math.cos(nd), math.sin(nd)
    ci, si = math.cos(ic), math.sin(ic)
    x = (cw * co - sw * so * ci) * xp + (-sw * co - cw * so * ci) * yp
    y = (cw * so + sw * co * ci) * xp + (-sw * so + cw * co * ci) * yp
    z = (sw * si) * xp + (cw * si) * yp
    return x, y, z


def mercury_geocentric_longitude(d: date):
    """Apparent ecliptic longitude of Mercury as seen from Earth, in degrees."""
    jd = julian_day(d)
    mx, my, mz = _heliocentric_xyz("mercury", jd)
    ex, ey, ez = _heliocentric_xyz("earth", jd)
    return math.degrees(math.atan2(my - ey, mx - ex)) % 360.0


def is_mercury_retrograde(d: date):
    """True when apparent longitude is decreasing, i.e. Mercury appears to reverse.

    Sampled on a one-day grid at noon; shadow periods are deliberately ignored,
    which the page says out loud.
    """
    a = mercury_geocentric_longitude(d - timedelta(days=1))
    b = mercury_geocentric_longitude(d + timedelta(days=1))
    return ((b - a + 540.0) % 360.0) - 180.0 < 0


def retrograde_periods(start: date, end: date):
    """Contiguous [from, to] spans of retrograde motion within the range."""
    spans, run_start, prev = [], None, False
    d = start
    while d <= end:
        now = is_mercury_retrograde(d)
        if now and not prev:
            run_start = d
        elif prev and not now:
            spans.append((run_start, d - timedelta(days=1)))
        prev = now
        d += timedelta(days=1)
    if prev and run_start:
        spans.append((run_start, end))
    return spans


def next_retrograde(after: date, horizon_days=400):
    """First retrograde span starting strictly after the given date, or None."""
    for span in retrograde_periods(after + timedelta(days=1),
                                   after + timedelta(days=horizon_days)):
        return span
    return None

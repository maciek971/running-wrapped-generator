#!/usr/bin/env python3
"""Offline geography: which country a GPS point is in, and a country's outline —
all from a bundled low-res world-borders file. Replaces the old hardcoded
Poland boxes so the Wrapped works for any country."""
from __future__ import annotations

import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

_WORLD = Path(__file__).resolve().parent / "assets" / "world_countries.geo.json"


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(radians, [a[0], a[1], b[0], b[1]])
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def _polys(geom):
    """Yield each polygon (list of rings) from a Polygon/MultiPolygon geometry."""
    if geom["type"] == "Polygon":
        yield geom["coordinates"]
    elif geom["type"] == "MultiPolygon":
        yield from geom["coordinates"]


def _pt_in_ring(lon, lat, ring) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _pt_in_poly(lon, lat, poly) -> bool:
    if not poly or not _pt_in_ring(lon, lat, poly[0]):
        return False
    return not any(_pt_in_ring(lon, lat, hole) for hole in poly[1:])  # outside holes


class World:
    def __init__(self, path: Path = _WORLD, lang: str = "pl"):
        data = json.loads(Path(path).read_text())
        key = f"NAME_{lang.upper()}"
        self.feats = []
        for ft in data["features"]:
            p = ft["properties"]
            name = p.get(key) or p.get("NAME_EN") or p.get("ADMIN") or p.get("NAME") or "?"
            iso2 = p.get("ISO_A2") or p.get("ISO3166-1-Alpha-2") or ""
            bbox = self._bbox(ft["geometry"])
            self.feats.append({"name": name, "iso2": iso2, "geom": ft["geometry"], "bbox": bbox})

    @staticmethod
    def _bbox(geom):
        xs, ys = [], []
        for poly in _polys(geom):
            for x, y in poly[0]:
                xs.append(x); ys.append(y)
        return (min(xs), min(ys), max(xs), max(ys))

    def country_of(self, lat: float, lon: float):
        """Return (name, iso2) for a point, or None."""
        for f in self.feats:
            x0, y0, x1, y1 = f["bbox"]
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            if any(_pt_in_poly(lon, lat, poly) for poly in _polys(f["geom"])):
                return f["name"], f["iso2"]
        return None

    def nearest_country(self, lat: float, lon: float, max_km: float = 30.0):
        """Fallback for coastal points that fall just outside a simplified polygon:
        the country with the closest border vertex (within max_km)."""
        best, best_d = None, 1e9
        for f in self.feats:
            x0, y0, x1, y1 = f["bbox"]
            if lon < x0 - 1 or lon > x1 + 1 or lat < y0 - 1 or lat > y1 + 1:
                continue
            for poly in _polys(f["geom"]):
                for x, y in poly[0]:
                    d = haversine_km((lat, lon), (y, x))
                    if d < best_d:
                        best_d, best = d, (f["name"], f["iso2"])
        return best if best_d <= max_km else None

    def locate(self, lat: float, lon: float):
        """Country for a point: exact polygon test, else nearest coast within 30 km."""
        return self.country_of(lat, lon) or self.nearest_country(lat, lon)

    def outline(self, name: str):
        """Largest polygon's outer ring [[lon,lat],...] for the given country name."""
        for f in self.feats:
            if f["name"] == name:
                best = max(_polys(f["geom"]), key=lambda poly: len(poly[0]))
                return best[0]
        return None

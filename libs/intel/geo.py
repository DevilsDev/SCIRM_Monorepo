"""
Supplier sites and site-level disaster exposure.

A site is a place a supplier operates: {"label", "city", "country", "lat", "lon",
"source", "precision"}. Its coordinates come either from the person who entered it, or
from an offline gazetteer (GeoNames cities with population > 15,000, CC BY 4.0) looked
up by city and country. No address is sent to any outside geocoding service.

A GDACS disaster alert reports one point: an earthquake's epicentre, a cyclone's or
flood's reported position. A site is treated as exposed when it lies within a radius of
that point that depends on the event type and alert level (EXPOSURE_RADIUS_KM). The
radii are deliberately generous approximations, not impact footprints: cyclone tracks
and flood extents are not used, so they are published with every match.
"""

import gzip
import math
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GAZETTEER = Path(__file__).resolve().parent / "data" / "cities.tsv.gz"

# Kilometres from the reported point, by GDACS event type and alert level. Droughts
# affect whole regions and have no meaningful point, so they stay country-level.
EXPOSURE_RADIUS_KM = {
    "EQ": {"Orange": 150, "Red": 300},
    "TC": {"Orange": 300, "Red": 500},
    "FL": {"Orange": 200, "Red": 300},
    "VO": {"Orange": 50, "Red": 100},
    "WF": {"Orange": 50, "Red": 100},
}


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().replace("-", " ").split())


@lru_cache(maxsize=1)
def _index() -> Dict[Tuple[str, str], List[Tuple[float, float, int, str]]]:
    index: Dict[Tuple[str, str], List[Tuple[float, float, int, str]]] = {}
    with gzip.open(GAZETTEER, "rt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            country, name, ascii_name, alternates, lat, lon, population = line.rstrip("\n").split("\t")
            entry = (float(lat), float(lon), int(population), name)
            for n in {name, ascii_name, *(a for a in alternates.split("|") if a)}:
                index.setdefault((country, _fold(n)), []).append(entry)
    return index


def locate(city: Optional[str], country: Optional[str]) -> Optional[Dict[str, Any]]:
    """City-level coordinates for a city in a country (ISO-2), or None if not found.
    Several places of the same name: the most populous, marked ambiguous."""
    if not city or not country:
        return None
    matches = _index().get((country.upper(), _fold(city)))
    if not matches:
        return None
    unique = sorted(set(matches), key=lambda m: m[2], reverse=True)
    lat, lon, _, name = unique[0]
    return {"lat": lat, "lon": lon, "matched": name,
            "precision": "city" if len(unique) == 1 else "city_ambiguous", "candidates": len(unique)}


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def event_point(signal: Dict[str, Any]) -> Optional[Tuple[float, float, float]]:
    """(lat, lon, radius_km) for a disaster with a usable point, else None."""
    raw = signal.get("raw") or {}
    radius = EXPOSURE_RADIUS_KM.get(raw.get("eventtype") or "", {}).get(raw.get("alertlevel") or "")
    lat, lon = raw.get("lat"), raw.get("lon")
    if radius is None or lat is None or lon is None:
        return None
    return float(lat), float(lon), float(radius)


def located_sites(supplier: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in (supplier.get("sites") or [])
            if isinstance(s, dict) and s.get("lat") is not None and s.get("lon") is not None][:50]


def nearest_site(supplier: Dict[str, Any], signal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The supplier's closest site within the event's radius, with the distance."""
    point = event_point(signal)
    if point is None:
        return None
    lat, lon, radius = point
    best = None
    for site in located_sites(supplier):
        d = distance_km(lat, lon, float(site["lat"]), float(site["lon"]))
        if d <= radius and (best is None or d < best["distance_km"]):
            best = {"site": site.get("label") or site.get("city") or "site", "city": site.get("city"),
                    "country": site.get("country"), "distance_km": round(d), "radius_km": int(radius),
                    "precision": site.get("precision")}
    return best


def site_from_address(label: str, city: Optional[str], country: Optional[str], source: str) -> Optional[Dict[str, Any]]:
    found = locate(city, country)
    if not found:
        return None
    return {"label": label, "city": city, "country": (country or "").upper(), "lat": found["lat"], "lon": found["lon"],
            "source": source, "precision": found["precision"], "matched": found["matched"]}

"""
Water risk by site, from WRI Aqueduct 4.0 (CC BY 4.0).

Aqueduct divides the world into about 68,500 units, each the union of a level 6 river
basin, a province and an aquifer, and publishes 13 baseline indicators per unit with its
own categories and labels (for example "Extremely High (>80%)"). SCIRM places a site in
its unit using an offline 0.02 degree grid (about 2 km) built by
scripts/build_water_risk.py, so no coordinates leave SCIRM, and shows WRI's indicators
one by one. There is no SCIRM water
score and no combined index: WRI's weighted "overall water risk" is left out on purpose.

A site's unit is only as good as its coordinates. A city-level site is placed at the city
centre, which can sit in a different basin from the plant itself; the precision is
returned with every result. A point on the coast can fall just outside every unit at this
grid size, so the nearest unit within NEAREST_KM is used and marked as such. Close to a
unit boundary the grid can pick the neighbouring unit (checked against WRI's polygons:
97% of random land points got the same unit and 98% the same categories), so a site whose
neighbouring cells hold a unit with different categories is marked near_boundary.
"""

import gzip
import math
import struct
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA = Path(__file__).resolve().parent / "data"
UNITS = DATA / "water_risk_units.tsv.gz"
GRID = DATA / "water_risk_grid.bin.gz"

SOURCE = {
    "name": "WRI Aqueduct 4.0",
    "url": "https://www.wri.org/aqueduct",
    "licence": "CC BY 4.0",
    "licence_url": "https://creativecommons.org/licenses/by/4.0/",
    "citation": ("Kuzma, S. et al. 2023. “Aqueduct 4.0: Updated decision-relevant global water risk "
                 "indicators.” Technical Note. Washington, DC: World Resources Institute. "
                 "doi.org/10.46830/writn.23.00061"),
    "baseline": "1979–2019",
    "modified": "SCIRM shows the indicators per site; it does not change WRI's values or categories.",
}

GROUPS = {"quantity": "Physical risk: quantity", "quality": "Physical risk: quality",
          "regulatory": "Regulatory and reputational risk"}

# Short names follow WRI's data dictionary. "updated" means recalculated for Aqueduct 4.0;
# the others are carried over from Aqueduct 3.0.
INDICATORS = {
    "bws": {"name": "Baseline water stress", "group": "quantity", "updated": True,
            "about": "Total water withdrawals as a share of available renewable supply."},
    "bwd": {"name": "Baseline water depletion", "group": "quantity", "updated": True,
            "about": "Total water consumption as a share of available renewable supply."},
    "iav": {"name": "Interannual variability", "group": "quantity", "updated": True,
            "about": "How much the water supply varies from year to year."},
    "sev": {"name": "Seasonal variability", "group": "quantity", "updated": True,
            "about": "How much the water supply varies between months of the year."},
    "gtd": {"name": "Groundwater table decline", "group": "quantity", "updated": False,
            "about": "The average yearly fall of the groundwater table."},
    "rfr": {"name": "Riverine flood risk", "group": "quantity", "updated": False,
            "about": "The share of the population expected to be affected by river floods each year."},
    "cfr": {"name": "Coastal flood risk", "group": "quantity", "updated": False,
            "about": "The share of the population expected to be affected by coastal floods each year."},
    "drr": {"name": "Drought risk", "group": "quantity", "updated": False,
            "about": "How likely droughts are and how much harm they would do."},
    "ucw": {"name": "Untreated connected wastewater", "group": "quality", "updated": False,
            "about": "The share of piped wastewater returned without treatment."},
    "cep": {"name": "Coastal eutrophication potential", "group": "quality", "updated": False,
            "about": "The potential for nutrient run-off to cause algal blooms along the coast."},
    "udw": {"name": "Unimproved or no drinking water", "group": "regulatory", "updated": False,
            "about": "The share of the population without improved drinking water."},
    "usa": {"name": "Unimproved or no sanitation", "group": "regulatory", "updated": False,
            "about": "The share of the population without improved sanitation."},
}

SCENARIOS = {
    "opt": "Optimistic (SSP1 RCP2.6)",
    "bau": "Business as usual (SSP3 RCP7.0)",
    "pes": "Pessimistic (SSP5 RCP8.5)",
}
YEARS = {"30": "2030 (2015–2045)", "50": "2050 (2035–2065)"}

# WRI's categories: 0 Low to 4 Extremely high; -1 a special class such as "Arid and Low
# Water Use" or "No Risk"; -9999 no data.
CATEGORY_NO_DATA = -9999
NEAREST_KM = 15
_SENTINELS = {-9999.0, 9999.0}


def _int(text: str) -> Optional[int]:
    return int(text) if text not in ("", "nan") else None


def _raw(text: str) -> Optional[float]:
    if not text:
        return None
    value = float(text)
    return None if value in _SENTINELS else value


@lru_cache(maxsize=1)
def _units() -> Tuple[List[str], List[List[str]]]:
    with gzip.open(UNITS, "rt", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f if not line.startswith("#")]
    return lines[0].split("\t"), [line.split("\t") for line in lines[1:]]


@lru_cache(maxsize=1)
def _grid() -> Tuple[float, int, int, bytes, List[int]]:
    with gzip.open(GRID, "rb") as f:
        data = f.read()
    magic, res, cols, rows = struct.unpack_from("<4sdII", data, 0)
    if magic != b"AQG1":
        raise ValueError("Unexpected water risk grid format")
    offsets, pos = [], struct.calcsize("<4sdII")
    for _ in range(rows):
        offsets.append(pos)
        (count,) = struct.unpack_from("<I", data, pos)
        pos += 4 + 8 * count
    return res, cols, rows, data, offsets


@lru_cache(maxsize=4096)
def _row(r: int) -> Tuple[List[int], List[int]]:
    """Run starts and unit indexes for one grid row."""
    _, _, _, data, offsets = _grid()
    pos = offsets[r]
    (count,) = struct.unpack_from("<I", data, pos)
    pairs = struct.unpack_from(f"<{2 * count}I", data, pos + 4)
    starts, values, col = [], [], 0
    for i in range(count):
        starts.append(col)
        values.append(pairs[2 * i + 1])
        col += pairs[2 * i]
    return starts, values


def _cell_unit(r: int, c: int) -> int:
    starts, values = _row(r)
    return values[bisect_right(starts, c) - 1]


def _cell(lat: float, lon: float) -> Tuple[int, int]:
    res, cols, rows, _, _ = _grid()
    r = min(rows - 1, max(0, int((90 - lat) / res)))
    c = int(((lon + 180) % 360) / res) % cols
    return r, c


def _cell_centre(r: int, c: int) -> Tuple[float, float]:
    res = _grid()[0]
    return 90 - (r + 0.5) * res, -180 + (c + 0.5) * res


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def unit_at(lat: float, lon: float) -> Optional[Tuple[int, Optional[float]]]:
    """The Aqueduct unit (row index into the units table, from 1) at a point, and the
    distance in km to it when the point itself falls outside every unit. None if no unit
    lies within NEAREST_KM."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    res, cols, rows, _, _ = _grid()
    r, c = _cell(lat, lon)
    found = _cell_unit(r, c)
    if found:
        return found, None
    reach = int(math.ceil(NEAREST_KM / (111.0 * res))) + 1
    best: Optional[Tuple[float, int]] = None
    for dr in range(-reach, reach + 1):
        rr = r + dr
        if not 0 <= rr < rows:
            continue
        for dc in range(-reach, reach + 1):
            unit = _cell_unit(rr, (c + dc) % cols)
            if unit:
                km = _distance_km(lat, lon, *_cell_centre(rr, (c + dc) % cols))
                if km <= NEAREST_KM and (best is None or km < best[0]):
                    best = (km, unit)
    return (best[1], round(best[0], 1)) if best else None


def _categories(index: int) -> Tuple[Optional[int], ...]:
    head, rows = _units()
    f = dict(zip(head, rows[index - 1]))
    return tuple(_int(f[f"{k}_cat"]) for k in INDICATORS)


def near_boundary(lat: float, lon: float, index: int) -> bool:
    """True when a cell next to the point's cell holds a unit with different categories."""
    _, cols, rows, _, _ = _grid()
    r, c = _cell(lat, lon)
    own = _categories(index)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if 0 <= r + dr < rows:
                other = _cell_unit(r + dr, (c + dc) % cols)
                if other and other != index and _categories(other) != own:
                    return True
    return False


def unit_record(index: int) -> Dict[str, Any]:
    head, rows = _units()
    f = dict(zip(head, rows[index - 1]))
    indicators = []
    for key, meta in INDICATORS.items():
        indicators.append({"key": key, "name": meta["name"], "group": meta["group"],
                           "category": _int(f[f"{key}_cat"]), "label": f[f"{key}_label"] or "No data",
                           "raw": _raw(f[f"{key}_raw"])})
    future = [{"scenario": s, "scenario_label": SCENARIOS[s], "year": "20" + y, "period": YEARS[y],
               "category": _int(f[f"{s}{y}_ws_cat"]), "label": f[f"{s}{y}_ws_label"] or "No data"}
              for s in SCENARIOS for y in YEARS]
    # Prefixed so they never overwrite the site's own fields (its country is ISO-2).
    return {"aq30_id": int(f["aq30_id"]), "basin": f["pfaf_id"], "unit_country": f["gid_0"],
            "province": f["name_1"], "indicators": indicators, "future_water_stress": future}


def site_water_risk(site: Dict[str, Any]) -> Dict[str, Any]:
    """Aqueduct's indicators for one supplier site, or why there are none."""
    base = {k: site.get(k) for k in ("id", "label", "city", "country", "precision", "source")}
    lat, lon = site.get("lat"), site.get("lon")
    if lat is None or lon is None:
        return {**base, "status": "not_located"}
    hit = unit_at(float(lat), float(lon))
    if hit is None:
        return {**base, "status": "outside", "lat": lat, "lon": lon}
    index, km = hit
    return {**base, "status": "nearest" if km is not None else "inside", "distance_km": km,
            "near_boundary": near_boundary(float(lat), float(lon), index), "lat": lat, "lon": lon,
            **unit_record(index)}


def supplier_water_risk(supplier: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [site_water_risk(s) for s in supplier.get("sites") or [] if isinstance(s, dict)]


def catalog() -> Dict[str, Any]:
    return {"source": SOURCE, "groups": GROUPS, "scenarios": SCENARIOS, "years": YEARS,
            "indicators": [{"key": k, **v} for k, v in INDICATORS.items()], "nearest_km": NEAREST_KM}

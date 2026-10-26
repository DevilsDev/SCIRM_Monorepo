"""Build the offline water risk lookup from WRI Aqueduct 4.0.

    curl -O https://files.wri.org/aqueduct/aqueduct-4-0-water-risk-data.zip
    pip install geopandas pyogrio rasterio    # build only; the app does not need them
    python scripts/build_water_risk.py aqueduct-4-0-water-risk-data.zip

Aqueduct 4.0 (World Resources Institute, https://www.wri.org/aqueduct), licensed CC BY 4.0.
Kuzma, S. et al. 2023. "Aqueduct 4.0: Updated decision-relevant global water risk
indicators." Technical Note. Washington, DC: WRI. doi.org/10.46830/writn.23.00061.

Writes two files used by libs/intel/water.py:

- water_risk_units.tsv.gz: one row per Aqueduct baseline unit (the union of a level 6
  river basin, a province and an aquifer), with each indicator's raw value, category and
  WRI's own label, plus the projected water stress for that basin in 2030 and 2050.
- water_risk_grid.bin.gz: the units rasterised on a 0.02 degree grid (about 2.2 km at the
  equator), run-length encoded per row, so a site's unit is found without any GIS library.

Left out on purpose: WRI's weighted "overall water risk" composites (SCIRM shows each
indicator on its own) and the RepRisk country index (a third party's index).
"""

import gzip
import io
import struct
import sys
import zipfile
from pathlib import Path

ROOT = "Aqueduct40_waterrisk_download_Y2023M07D05"
OUT = Path(__file__).resolve().parents[1] / "libs" / "intel" / "data"
RES = 0.02
COLS, ROWS = int(360 / RES), int(180 / RES)
INDICATORS = ["bws", "bwd", "iav", "sev", "gtd", "rfr", "cfr", "drr", "ucw", "cep", "udw", "usa"]
FUTURE = [f"{s}{y}" for s in ("opt", "bau", "pes") for y in ("30", "50")]


def _num(value) -> str:
    if value is None:
        return ""
    value = float(value)
    if value in (-9999.0, 9999.0) or value != value:
        return str(int(value)) if value == value else ""
    return f"{value:.4g}"


def _text(value) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _cat(value) -> str:
    return "" if value is None or value != value else str(int(value))


def main(path: str) -> None:
    import numpy as np
    import pyogrio
    from rasterio import features
    from rasterio.transform import from_origin

    gdb = f"/vsizip/{Path(path).as_posix()}/{ROOT}/GDB/Aq40_Y2023D07M05.gdb"
    cols = ["aq30_id", "pfaf_id", "gid_0", "name_1"] + [f"{i}_{t}" for i in INDICATORS for t in ("raw", "cat", "label")]
    meta = pyogrio.read_dataframe(gdb, layer="baseline_annual", columns=cols)
    geoms = meta.geometry

    with zipfile.ZipFile(path) as z:
        raw = z.read(f"{ROOT}/CVS/Aqueduct40_future_annual_y2023m07d05.csv").decode("utf-8")
    future = {}
    lines = io.StringIO(raw)
    header = lines.readline().rstrip("\n").split(",")
    for line in lines:
        f = dict(zip(header, line.rstrip("\n").split(",")))
        future[int(float(f["pfaf_id"]))] = [(f[f"{k}_ws_x_c"], f[f"{k}_ws_x_l"]) for k in FUTURE]

    units = []
    for idx, row in enumerate(meta.itertuples(index=False), start=1):
        cells = [str(int(row.aq30_id)), str(int(row.pfaf_id)), _text(row.gid_0), _text(row.name_1)]
        for ind in INDICATORS:
            cells += [_num(getattr(row, f"{ind}_raw")), _cat(getattr(row, f"{ind}_cat")),
                      _text(getattr(row, f"{ind}_label"))]
        for cat, label in future.get(int(row.pfaf_id), [("", "")] * len(FUTURE)):
            cells += [_cat(float(cat)) if cat not in ("", "nan") else "", label.strip()]
        units.append("\t".join(cells))

    shapes = ((geom, idx) for idx, geom in enumerate(geoms, start=1) if geom is not None)
    grid = features.rasterize(shapes, out_shape=(ROWS, COLS), transform=from_origin(-180, 90, RES, RES),
                              fill=0, dtype="uint32")

    OUT.mkdir(parents=True, exist_ok=True)
    head = ["aq30_id", "pfaf_id", "gid_0", "name_1"] + [f"{i}_{t}" for i in INDICATORS for t in ("raw", "cat", "label")] \
        + [f"{k}_ws_{t}" for k in FUTURE for t in ("cat", "label")]
    with gzip.open(OUT / "water_risk_units.tsv.gz", "wt", encoding="utf-8", compresslevel=9) as out:
        out.write("# WRI Aqueduct 4.0 baseline annual (https://www.wri.org/aqueduct), CC BY 4.0. "
                  "Built by scripts/build_water_risk.py\n")
        out.write("\t".join(head) + "\n")
        out.write("\n".join(units) + "\n")

    # Per row: a count of runs, then (run length, unit index) pairs, little-endian uint32.
    buf = io.BytesIO()
    buf.write(struct.pack("<4sdII", b"AQG1", RES, COLS, ROWS))
    runs_total = 0
    for r in range(ROWS):
        row = grid[r]
        change = np.flatnonzero(np.diff(row)) + 1
        starts = np.concatenate(([0], change))
        lengths = np.diff(np.concatenate((starts, [COLS])))
        values = row[starts]
        buf.write(struct.pack("<I", len(starts)))
        buf.write(np.column_stack((lengths, values)).astype("<u4").tobytes())
        runs_total += len(starts)
    with gzip.open(OUT / "water_risk_grid.bin.gz", "wb", compresslevel=9) as out:
        out.write(buf.getvalue())
    for name in ("water_risk_units.tsv.gz", "water_risk_grid.bin.gz"):
        print(f"{name}: {(OUT / name).stat().st_size // 1024} KB")
    print(f"{len(units)} units, {runs_total} runs")


if __name__ == "__main__":
    main(sys.argv[1])

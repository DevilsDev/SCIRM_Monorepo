"""Build libs/intel/data/cities.tsv.gz from GeoNames cities15000.

    curl -O https://download.geonames.org/export/dump/cities15000.zip
    python scripts/build_gazetteer.py cities15000.zip

GeoNames (https://www.geonames.org), licensed CC BY 4.0. Kept per city: country code,
name, ASCII name, up to 8 Latin-script alternate names (so "Cologne" finds Köln),
latitude, longitude and population. Used offline by libs/intel/geo.py to place a
supplier site from its city and country; no address is sent to any geocoding service.
"""

import gzip
import io
import sys
import unicodedata
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "libs" / "intel" / "data" / "cities.tsv.gz"
MAX_ALTERNATES = 8


def _latin(text: str) -> bool:
    return all(ch.isascii() or "LATIN" in unicodedata.name(ch, "") or not ch.isalpha() for ch in text)


def main(path: str) -> None:
    with zipfile.ZipFile(path) as z:
        raw = z.read("cities15000.txt").decode("utf-8")
    rows = []
    for line in io.StringIO(raw):
        f = line.rstrip("\n").split("\t")
        if len(f) < 15:
            continue
        name, ascii_name, alternates = f[1], f[2], f[3]
        seen = {name.lower(), ascii_name.lower()}
        alt = []
        for a in alternates.split(","):
            a = a.strip()
            if a and len(a) <= 40 and _latin(a) and a.lower() not in seen and not any(c.isdigit() for c in a):
                seen.add(a.lower())
                alt.append(a)
            if len(alt) >= MAX_ALTERNATES:
                break
        rows.append("\t".join([f[8], name, ascii_name, "|".join(alt), f"{float(f[4]):.4f}", f"{float(f[5]):.4f}",
                               str(int(f[14] or 0))]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as out:
        out.write("# GeoNames cities15000 (https://www.geonames.org), CC BY 4.0. "
                  "country\tname\tascii\talternates\tlat\tlon\tpopulation\n")
        out.write("\n".join(sorted(rows)) + "\n")
    print(f"{len(rows)} cities -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1])

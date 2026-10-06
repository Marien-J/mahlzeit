"""Build src/mahlzeit/seed/generic_foods.json from the official BLS 4.0 file.

    uv run python scripts/build_bls_seed.py path/to/BLS_4_0_Daten_2025_DE.xlsx

Inputs in backend/seed/: bls_selection.csv (which foods, category, Dutch name, tracking mode,
favourite), servings.csv, extra_foods.json (generic items the BLS does not have).
Data: Max Rubner-Institut (2025), Bundeslebensmittelschlüssel (BLS) 4.0, CC BY 4.0.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed"
OUT = ROOT / "src" / "mahlzeit" / "seed" / "generic_foods.json"
COLUMNS = {
    "kcal": "ENERCC",
    "protein": "PROT625",
    "carbs": "CHO",
    "sugar": "SUGAR",
    "fat": "FAT",
    "sat_fat": "FASAT",
    "fibre": "FIBT",
    "salt": "NACL",
    "alcohol": "ALC",
}


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, str):
        return None
    return round(float(value), 3)


def read_bls(path: Path) -> dict[str, dict[str, Any]]:
    sheet = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = [str(h or "") for h in next(rows)]
    index = {
        name: next(i for i, h in enumerate(header) if h.startswith(code + " "))
        for name, code in COLUMNS.items()
    }
    foods = {}
    for row in rows:
        foods[str(row[0])] = {
            "de": str(row[1]).strip(),
            "en": str(row[2]).strip(),
            "nutrients": {name: _number(row[i]) for name, i in index.items()},
        }
    return foods


def main(xlsx: str) -> None:
    bls = read_bls(Path(xlsx))
    servings: dict[str, list[list[Any]]] = {}
    with (SEED / "servings.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            servings.setdefault(row["key"], []).append([row["label"], float(row["amount"])])

    items = []
    with (SEED / "bls_selection.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            food = bls[row["bls_code"]]
            items.append(
                {
                    "source": "bls",
                    "source_id": row["bls_code"],
                    "names": {"de": food["de"], "en": food["en"], "nl": row["name_nl"]},
                    "category": row["category"],
                    "tracking_mode": row["tracking"],
                    "nutrients": food["nutrients"],
                    "servings": servings.get(f"bls:{row['bls_code']}", []),
                    "favourite": row["favourite"] == "1",
                }
            )
    for extra in json.loads((SEED / "extra_foods.json").read_text(encoding="utf-8")):
        extra = {**extra, "servings": servings.get(f"mahlzeit:{extra['source_id']}", [])}
        items.append(extra)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} items to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1])

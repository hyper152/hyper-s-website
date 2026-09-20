"""Copy anonymized CT QC images into the website and refresh its manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import secrets
import shutil
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUMMARY = Path(
    r"E:\projects\Future-Scholar\Sarcopia\runs\ct_corrected_2026-09-17\summary.csv"
)
DEFAULT_WEB_DIR = ROOT / "pages" / "projects" / "Future-Scholar"
SALT_PATH = ROOT / "data" / "future_scholar_salt.txt"
MANIFEST_PATH = ROOT / "data" / "future_scholar_cases.json"


def salt() -> str:
    SALT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SALT_PATH.is_file():
        SALT_PATH.write_text(secrets.token_hex(32), encoding="ascii")
    return SALT_PATH.read_text(encoding="ascii").strip()


def case_id(row: dict[str, str], secret: str) -> str:
    raw = "|".join(str(row.get(name, "")) for name in ("dataset", "patient_id", "series_id"))
    return hashlib.sha256((secret + "|" + raw).encode("utf-8")).hexdigest()[:20]


def copy_if_present(source: str, destination: Path) -> str:
    if not source:
        return ""
    path = Path(source)
    if not path.is_file():
        return ""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file() or destination.stat().st_mtime_ns < path.stat().st_mtime_ns:
        shutil.copy2(path, destination)
    return "/" + destination.relative_to(ROOT).as_posix()


def sync(summary: Path, web_dir: Path) -> dict:
    if not summary.is_file():
        return {"summary_exists": False, "cases": 0}
    with summary.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    secret = salt()
    assets = web_dir / "assets"
    cases = []
    for row in rows:
        identifier = case_id(row, secret)
        case_assets = assets / identifier
        images = {
            name: copy_if_present(row.get(f"{name}_png", ""), case_assets / f"{name}.png")
            for name in ("l3", "mask", "overlay")
        }
        cases.append(
            {
                "case_id": identifier,
                "status": row.get("status", ""),
                "scan_phase": row.get("scan_phase", ""),
                "phase_confidence": row.get("phase_confidence", ""),
                "slice_thickness_mm": row.get("slice_thickness_mm", ""),
                "kvp": row.get("kvp", ""),
                "ctdi_vol_mgy": row.get("ctdi_vol_mgy", ""),
                "localization_method": row.get("localization_method", ""),
                "sma_cm2": row.get("sma_cm2", ""),
                "muscle_hu_mean": row.get("muscle_hu_mean", ""),
                "muscle_hu_median": row.get("muscle_hu_median", ""),
                "message": row.get("message", ""),
                **images,
            }
        )
    cases.sort(key=lambda item: (item["status"] != "success", item["case_id"]))
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(MANIFEST_PATH)
    return {"summary_exists": True, "cases": len(cases)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--web-dir", default=str(DEFAULT_WEB_DIR))
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    while True:
        result = sync(Path(args.summary), Path(args.web_dir))
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if not args.watch:
            return 0
        time.sleep(max(args.interval, 10))


if __name__ == "__main__":
    raise SystemExit(main())

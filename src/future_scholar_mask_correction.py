"""Persistence and queue management for manual muscle-mask corrections."""

from __future__ import annotations

import base64
import csv
import json
import sqlite3
import struct
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CASES_PATH = DATA_DIR / "future_scholar_cases.json"
REVIEWS_DB = DATA_DIR / "future_scholar_qc.db"
DB_PATH = DATA_DIR / "future_scholar_mask_corrections.db"
EXPORT_PATH = DATA_DIR / "future_scholar_mask_corrections.csv"
MASK_DIR = DATA_DIR / "future_scholar_mask_corrections"


@contextmanager
def connection(write: bool = False):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA journal_mode=WAL")
        if write:
            db.execute("BEGIN IMMEDIATE")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS corrections (
                case_id TEXT PRIMARY KEY,
                corrected_mask_path TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                reviewer_email TEXT NOT NULL,
                corrected_at TEXT NOT NULL
            )
            """
        )
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _cases() -> dict[str, dict]:
    if not CASES_PATH.is_file():
        return {}
    rows = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return {row["case_id"]: row for row in rows if row.get("case_id")}


def _eligible_ids() -> list[str]:
    if not REVIEWS_DB.is_file():
        return []
    db = sqlite3.connect(str(REVIEWS_DB), timeout=30)
    try:
        return [
            row[0]
            for row in db.execute(
                "SELECT case_id FROM reviews "
                "WHERE localization_qc='pass' AND segmentation_qc='fail' "
                "ORDER BY reviewed_at,case_id"
            )
        ]
    finally:
        db.close()


def pending_cases() -> list[dict]:
    cases = _cases()
    with connection() as db:
        done = {row[0] for row in db.execute("SELECT case_id FROM corrections")}
    return [cases[case_id] for case_id in _eligible_ids() if case_id in cases and case_id not in done]


def next_case() -> dict | None:
    rows = pending_cases()
    return rows[0] if rows else None


def stats() -> dict:
    eligible = _eligible_ids()
    with connection() as db:
        corrected = db.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
    return {
        "eligible": len(eligible),
        "corrected": corrected,
        "remaining": max(len(eligible) - corrected, 0),
    }


def corrected_cases() -> list[dict]:
    cases = _cases()
    with connection() as db:
        rows = db.execute(
            "SELECT case_id,reviewer,reviewer_email,corrected_at "
            "FROM corrections ORDER BY corrected_at DESC,case_id"
        ).fetchall()
    result = []
    for row in rows:
        case = cases.get(row["case_id"])
        if case is None:
            continue
        result.append({
            **case,
            "correction": dict(row),
            "corrected_mask": (
                "/api/future-scholar/mask-correction/file?case_id="
                + quote(row["case_id"], safe="")
            ),
        })
    return result


def corrected_mask_bytes(case_id: str) -> bytes | None:
    case_id = str(case_id).strip()
    if not case_id:
        return None
    with connection() as db:
        row = db.execute(
            "SELECT corrected_mask_path FROM corrections WHERE case_id=?",
            (case_id,),
        ).fetchone()
    if row is None:
        return None
    path = Path(row["corrected_mask_path"])
    return path.read_bytes() if path.is_file() else None


def _png_dimensions(payload: bytes) -> tuple[int, int]:
    if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Mask must be a PNG image")
    width, height = struct.unpack(">II", payload[16:24])
    if width < 32 or height < 32 or width > 2048 or height > 2048:
        raise ValueError("Invalid mask dimensions")
    return width, height


def _source_dimensions(case: dict) -> tuple[int, int]:
    source = ROOT.joinpath(*case["mask"].strip("/").split("/"))
    return _png_dimensions(source.read_bytes())


def _export(db) -> None:
    rows = db.execute(
        "SELECT case_id,corrected_mask_path,reviewer,reviewer_email,corrected_at "
        "FROM corrections ORDER BY corrected_at,case_id"
    ).fetchall()
    temporary = EXPORT_PATH.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            rows[0].keys()
            if rows
            else ["case_id", "corrected_mask_path", "reviewer", "reviewer_email", "corrected_at"]
        )
        writer.writerows([tuple(row) for row in rows])
    temporary.replace(EXPORT_PATH)


def save_mask(payload: dict, user: dict) -> dict:
    case_id = str(payload.get("case_id", "")).strip()
    cases = _cases()
    if case_id not in cases or case_id not in set(_eligible_ids()):
        raise ValueError("Case is not eligible for mask correction")
    encoded = str(payload.get("mask_png", ""))
    prefix = "data:image/png;base64,"
    if not encoded.startswith(prefix):
        raise ValueError("mask_png must be a PNG data URL")
    try:
        png = base64.b64decode(encoded[len(prefix):], validate=True)
    except Exception as exc:
        raise ValueError("Invalid base64 mask") from exc
    if len(png) > 2 * 1024 * 1024:
        raise ValueError("Mask PNG is too large")
    if _png_dimensions(png) != _source_dimensions(cases[case_id]):
        raise ValueError("Corrected mask dimensions differ from the source mask")
    case_dir = MASK_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    destination = case_dir / "mask.png"
    temporary = case_dir / "mask.png.tmp"
    temporary.write_bytes(png)
    temporary.replace(destination)
    reviewer = str(user.get("username", "")).strip() or "authenticated_user"
    email = str(user.get("email", "")).strip()
    corrected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connection(write=True) as db:
        db.execute(
            """
            INSERT INTO corrections VALUES (?,?,?,?,?)
            ON CONFLICT(case_id) DO UPDATE SET
                corrected_mask_path=excluded.corrected_mask_path,
                reviewer=excluded.reviewer,
                reviewer_email=excluded.reviewer_email,
                corrected_at=excluded.corrected_at
            """,
            (case_id, str(destination), reviewer, email, corrected_at),
        )
        _export(db)
    return {"case_id": case_id, "reviewer": reviewer, "corrected_at": corrected_at}

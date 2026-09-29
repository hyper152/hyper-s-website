"""Local persistence for the Future Scholar CT quality-control page."""

from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CASES_PATH = DATA_DIR / "future_scholar_cases.json"
DB_PATH = DATA_DIR / "future_scholar_qc.db"
EXPORT_PATH = DATA_DIR / "future_scholar_qc_reviews.csv"

ALLOWED_VALUES = {"pass", "fail", "uncertain"}


def _ensure_reviews_schema(db) -> None:
    expected = [
        "case_id", "localization_qc", "segmentation_qc", "qc_status",
        "reviewer", "reviewer_email", "reviewed_at", "record",
    ]
    columns = [row[1] for row in db.execute("PRAGMA table_info(reviews)")]
    if not columns:
        db.execute(
            """
            CREATE TABLE reviews (
                case_id TEXT PRIMARY KEY,
                localization_qc TEXT NOT NULL,
                segmentation_qc TEXT NOT NULL,
                qc_status TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                reviewer_email TEXT NOT NULL,
                reviewed_at TEXT NOT NULL,
                record TEXT NOT NULL
            )
            """
        )
        return
    if columns == expected:
        return
    rows = db.execute(
        "SELECT case_id,localization_qc,segmentation_qc,qc_status,"
        "reviewer,reviewer_email,reviewed_at FROM reviews"
    ).fetchall()
    db.execute("DROP TABLE IF EXISTS reviews_new")
    db.execute(
        """
        CREATE TABLE reviews_new (
            case_id TEXT PRIMARY KEY,
            localization_qc TEXT NOT NULL,
            segmentation_qc TEXT NOT NULL,
            qc_status TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            reviewer_email TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            record TEXT NOT NULL
        )
        """
    )
    for row in rows:
        record = dict(row)
        db.execute(
            "INSERT INTO reviews_new VALUES (?,?,?,?,?,?,?,?)",
            (*tuple(row), json.dumps(record, ensure_ascii=False, allow_nan=False)),
        )
    db.execute("DROP TABLE reviews")
    db.execute("ALTER TABLE reviews_new RENAME TO reviews")


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
        _ensure_reviews_schema(db)
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def load_cases() -> list[dict]:
    if not CASES_PATH.is_file():
        return []
    value = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Future Scholar case manifest must be a JSON list")
    return [item for item in value if isinstance(item, dict) and item.get("case_id")]


def next_case() -> dict | None:
    cases = next_cases(1)
    return cases[0] if cases else None


def next_cases(limit: int | None = 1000) -> list[dict]:
    cases = load_cases()
    with connection() as db:
        reviewed = {row[0] for row in db.execute("SELECT case_id FROM reviews")}
    remaining = [case for case in cases if case["case_id"] not in reviewed]
    if limit is None or int(limit) <= 0:
        return remaining
    return remaining[:int(limit)]


def stats() -> dict:
    cases = load_cases()
    with connection() as db:
        reviewed = db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        passed = db.execute(
            "SELECT COUNT(*) FROM reviews "
            "WHERE localization_qc='pass' AND segmentation_qc='pass'"
        ).fetchone()[0]
        failed = db.execute(
            "SELECT COUNT(*) FROM reviews "
            "WHERE localization_qc='fail' OR segmentation_qc='fail'"
        ).fetchone()[0]
        uncertain = db.execute(
            "SELECT COUNT(*) FROM reviews "
            "WHERE localization_qc!='fail' AND segmentation_qc!='fail' "
            "AND (localization_qc='uncertain' OR segmentation_qc='uncertain')"
        ).fetchone()[0]
    total = len(cases)
    return {
        "available": total,
        "reviewed": reviewed,
        "remaining": max(total - reviewed, 0),
        "pass": passed,
        "fail": failed,
        "uncertain": uncertain,
    }


def reviewed_cases(status: str) -> list[dict]:
    status = str(status).strip().lower()
    if status not in ALLOWED_VALUES:
        raise ValueError("Invalid review status")
    cases_by_id = {case["case_id"]: case for case in load_cases()}
    condition = {
        "pass": "localization_qc='pass' AND segmentation_qc='pass'",
        "fail": "localization_qc='fail' OR segmentation_qc='fail'",
        "uncertain": (
            "localization_qc!='fail' AND segmentation_qc!='fail' "
            "AND (localization_qc='uncertain' OR segmentation_qc='uncertain')"
        ),
    }[status]
    with connection() as db:
        rows = db.execute(
            "SELECT case_id,localization_qc,segmentation_qc,qc_status,"
            "reviewer,reviewer_email,reviewed_at FROM reviews "
            f"WHERE {condition} ORDER BY reviewed_at DESC,case_id",
        ).fetchall()
    result = []
    for row in rows:
        case = cases_by_id.get(row["case_id"])
        if case is not None:
            result.append({
                **case,
                "review": dict(row),
                "mask_correction_eligible": (
                    row["localization_qc"] == "pass"
                    and row["segmentation_qc"] == "fail"
                ),
            })
    return result


def _export(db) -> None:
    rows = db.execute(
        "SELECT case_id,localization_qc,segmentation_qc,qc_status,"
        "reviewer,reviewer_email,reviewed_at "
        "FROM reviews ORDER BY reviewed_at,case_id"
    ).fetchall()
    temporary = EXPORT_PATH.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(rows[0].keys() if rows else [
            "case_id", "localization_qc", "segmentation_qc", "qc_status",
            "reviewer", "reviewer_email", "reviewed_at",
        ])
        writer.writerows([tuple(row) for row in rows])
    temporary.replace(EXPORT_PATH)


def save_review(payload: dict, user: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    case_id = str(payload.get("case_id", "")).strip()
    available = {case["case_id"] for case in load_cases()}
    if not case_id or case_id not in available:
        raise ValueError("Unknown case_id")
    values = {
        name: str(payload.get(name, "")).strip().lower()
        for name in ("localization_qc", "segmentation_qc", "qc_status")
    }
    for name, value in values.items():
        if value not in ALLOWED_VALUES:
            raise ValueError(f"Invalid {name}")
    reviewer = str(user.get("username", "")).strip() or "authenticated_user"
    reviewer_email = str(user.get("email", "")).strip()
    reviewed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "case_id": case_id,
        **values,
        "reviewer": reviewer,
        "reviewer_email": reviewer_email,
        "reviewed_at": reviewed_at,
    }
    encoded = json.dumps(record, ensure_ascii=False, allow_nan=False)
    with connection(write=True) as db:
        db.execute(
            """
            INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(case_id) DO UPDATE SET
                localization_qc=excluded.localization_qc,
                segmentation_qc=excluded.segmentation_qc,
                qc_status=excluded.qc_status,
                reviewer=excluded.reviewer,
                reviewer_email=excluded.reviewer_email,
                reviewed_at=excluded.reviewed_at,
                record=excluded.record
            """,
            (
                case_id,
                values["localization_qc"],
                values["segmentation_qc"],
                values["qc_status"],
                reviewer,
                reviewer_email,
                reviewed_at,
                encoded,
            ),
        )
        _export(db)
    return record

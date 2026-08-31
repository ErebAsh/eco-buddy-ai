"""Portable, versioned EcoBuddy sustainability profile import/export.

The public API deliberately keeps the persistence layer independent from the
rest of the application so exports can be validated and imported atomically.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

EXPORT_SCHEMA_VERSION = "1.0"
APPLICATION_NAME = "EcoBuddy AI"
SUPPORTED_SCHEMA_VERSIONS = (EXPORT_SCHEMA_VERSION,)
CONFLICT_STRATEGIES = ("skip", "replace", "merge")

USER_COLUMNS = ("id", "username", "email", "anonymous_leaderboard", "created_at")
# Fields that describe an assessment's actual content (used to tell an
# "unchanged" re-import apart from a genuine "updated" record).
ASSESSMENT_CONTENT_FIELDS = ("transport", "distance", "electricity", "diet", "flights", "footprint", "eco_score", "date", "trip_id")
ASSESSMENT_STATUSES = ("new", "unchanged", "updated", "conflicting", "duplicate", "legacy")
TABLES = {
    "assessments": {
        "columns": ("id", "user_id", "date", "created_at", "updated_at", "client_uuid", "source_device", "transport", "distance", "electricity", "diet", "flights", "footprint", "eco_score", "trip_id"),
        "id": "id",
    },    "goals": {
        "table": "reduction_goals",
        "columns": ("id", "user_id", "baseline_kg", "target_kg", "start_date", "target_date", "status", "created_at"),
        "id": "id",
    },
    "habits": {
        "table": "user_habits",
        "columns": ("user_id", "data_json", "updated_at"),
        "id": "user_id",
    },
    "recommendations": {
        "table": "recommendation_feedback",
        "columns": ("id", "user_id", "recommendation_id", "category", "feedback_type", "difficulty", "created_at", "feedback", "recommendation"),
        "id": "id",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO-8601 date/time string")
    candidate = value.strip().replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO-8601 date/time") from exc
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info(\"{table}\")")}


def _rows(conn: sqlite3.Connection, table: str, user_id: int, columns: Iterable[str]) -> list[dict[str, Any]]:
    available = _existing_columns(conn, table)
    selected = [c for c in columns if c in available]
    if "user_id" in available:
        selected = [c for c in selected if c != "user_id"]
        selected = ["user_id", *selected]
    if not selected or "user_id" not in available:
        return []
    query = f'SELECT {", ".join(f"\"{c}\"" for c in selected)} FROM "{table}" WHERE user_id = ?'
    return [{k: _json_safe(v) for k, v in zip(selected, row)} for row in conn.execute(query, (user_id,)).fetchall()]


def export_user_profile(user_id: int, db_name: str | None = None) -> dict[str, Any]:
    db_name = db_name or os.getenv("ECO_BUDDY_DB", "eco_buddy.db")
    with sqlite3.connect(db_name) as conn:
        available = _existing_columns(conn, "users")
        columns = [c for c in USER_COLUMNS if c in available and c != "id"]
        if not columns:
            return {}
        row = conn.execute(
            f'SELECT {", ".join(columns)} FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        if not row:
            return {}
        return {k: _json_safe(v) for k, v in zip(columns, row)}


def export_assessments(user_id: int, db_name: str | None = None) -> list[dict[str, Any]]:
    db_name = db_name or os.getenv("ECO_BUDDY_DB", "eco_buddy.db")
    with sqlite3.connect(db_name) as conn:
        return _rows(conn, "assessments", user_id, TABLES["assessments"]["columns"])


def export_goals(user_id: int, db_name: str | None = None) -> list[dict[str, Any]]:
    db_name = db_name or os.getenv("ECO_BUDDY_DB", "eco_buddy.db")
    with sqlite3.connect(db_name) as conn:
        return _rows(conn, "reduction_goals", user_id, TABLES["goals"]["columns"])


def export_habits(user_id: int, db_name: str | None = None) -> list[dict[str, Any]]:
    db_name = db_name or os.getenv("ECO_BUDDY_DB", "eco_buddy.db")
    with sqlite3.connect(db_name) as conn:
        return _rows(conn, "user_habits", user_id, TABLES["habits"]["columns"])


def export_recommendation_history(user_id: int, db_name: str | None = None) -> list[dict[str, Any]]:
    db_name = db_name or os.getenv("ECO_BUDDY_DB", "eco_buddy.db")
    with sqlite3.connect(db_name) as conn:
        return _rows(conn, "recommendation_feedback", user_id, TABLES["recommendations"]["columns"])


def export_profile(user_id: int, db_name: str | None = None) -> dict[str, Any]:
    """Build the complete v1 profile document without credentials."""
    exported_at = _now()
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": exported_at,
        "application": APPLICATION_NAME,
        "profile": export_user_profile(user_id, db_name),
        "assessments": export_assessments(user_id, db_name),
        "goals": export_goals(user_id, db_name),
        "habits": export_habits(user_id, db_name),
        "recommendations": export_recommendation_history(user_id, db_name),
        "metadata": {"exported_user_id": int(user_id), "credential_fields_excluded": ["password_hash"]},
    }


def export_profile_json(user_id: int, db_name: str | None = None) -> str:
    return json.dumps(export_profile(user_id, db_name), indent=2, ensure_ascii=False, sort_keys=True)


def _validate_record_list(name: str, records: Any, numeric_ranges: dict[str, tuple[float, float]] | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(records, list):
        return [f"{name} must be an array"]
    ids: set[str] = set()
    for index, record in enumerate(records):
        prefix = f"{name}[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if "id" in record:
            rid = str(record["id"])
            if rid in ids:
                errors.append(f"{prefix}.id is duplicated")
            ids.add(rid)
        for key in ("date", "created_at", "updated_at"):
            if key in record and record[key] is not None:
                try:
                    _parse_iso(record[key], f"{prefix}.{key}")
                except ValueError as exc:
                    errors.append(str(exc))
        if numeric_ranges:
            for key, (minimum, maximum) in numeric_ranges.items():
                if key in record and record[key] is not None:
                    if isinstance(record[key], bool) or not isinstance(record[key], (int, float)):
                        errors.append(f"{prefix}.{key} must be numeric")
                    elif not minimum <= record[key] <= maximum:
                        errors.append(f"{prefix}.{key} must be between {minimum} and {maximum}")
    return errors


def validate_export_document(document: Any) -> tuple[bool, list[str]]:
    """Strictly validate the portable document before any database mutation."""
    errors: list[str] = []
    if not isinstance(document, dict):
        return False, ["Export document must be a JSON object"]
    required = ("schema_version", "exported_at", "application", "profile", "assessments", "goals", "habits", "recommendations", "metadata")
    errors.extend(f"Missing required field: {key}" for key in required if key not in document)
    if "schema_version" in document and document["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"Unsupported schema version: {document.get('schema_version')}")
    if "exported_at" in document:
        try:
            _parse_iso(document["exported_at"], "exported_at")
        except ValueError as exc:
            errors.append(str(exc))
    if document.get("application") != APPLICATION_NAME:
        errors.append("application must be 'EcoBuddy AI'")
    if not isinstance(document.get("profile"), dict):
       errors.append("profile must be an object")
    if isinstance(document.get("metadata"), dict) and "exported_user_id" in document["metadata"]:
        uid = document["metadata"]["exported_user_id"]
        if isinstance(uid, bool) or not isinstance(uid, int) or uid < 1:
            errors.append("metadata.exported_user_id must be a positive integer")
    errors.extend(_validate_record_list("assessments", document.get("assessments", []), {
        "distance": (0, 10_000_000), "electricity": (0, 10_000_000), "flights": (0, 10_000), "footprint": (0, 10_000_000), "eco_score": (0, 100),
    }))
    errors.extend(_validate_record_list("goals", document.get("goals", []), {"baseline_kg": (0, 10_000_000), "target_kg": (0, 10_000_000)}))
    errors.extend(_validate_record_list("habits", document.get("habits", [])))
    errors.extend(_validate_record_list("recommendations", document.get("recommendations", [])))
    if not isinstance(document.get("profile", {}), dict):
       errors.append("profile must be an object")
    return not errors, errors


def migrate_v1_to_v2(document: dict[str, Any]) -> dict[str, Any]:
    """Reference migration hook; v2 is intentionally not accepted yet."""
    migrated = copy.deepcopy(document)
    migrated["schema_version"] = "2.0"
    migrated.setdefault("metadata", {})["migrated_from"] = "1.0"
    return migrated


def migrate_export(document: dict[str, Any], target_version: str = EXPORT_SCHEMA_VERSION) -> dict[str, Any]:
    version = document.get("schema_version")
    if version == target_version:
        return copy.deepcopy(document)
    raise ValueError(f"No migration path from {version!r} to {target_version!r}")


def _stable_key(table: str, record: dict[str, Any]) -> str:
    raw = json.dumps(record, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(f"{table}:{raw}".encode()).hexdigest()


def _assessment_content_hash(record: dict[str, Any]) -> str:
    """Hash only the fields that represent the assessment's content, ignoring
    bookkeeping columns (id/created_at/updated_at/client_uuid/source_device)."""
    payload = {k: record.get(k) for k in ASSESSMENT_CONTENT_FIELDS}
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def classify_assessments(document: dict[str, Any], user_id: int, db_name: str | None = None) -> list[str]:
    """Classify each assessment in document['assessments'] using its stable
    client_uuid. Returned list is aligned 1:1 with document['assessments'].

    Statuses:
      - "legacy": no client_uuid on the record; handled by the old id-based path.
      - "new": no local assessment shares this client_uuid.
      - "unchanged": local content is identical (safe to skip; keeps re-imports idempotent).
      - "updated": content differs and the incoming record is not older than local.
      - "conflicting": content differs and the local record is newer than the incoming one.
      - "duplicate": this client_uuid already appeared earlier in the same import.
    """
    db_name = db_name or os.getenv("ECO_BUDDY_DB", "eco_buddy.db")
    records = document.get("assessments", [])
    statuses: list[str] = []
    seen_uuids: set[str] = set()
    with sqlite3.connect(db_name) as conn:
        available = _existing_columns(conn, "assessments")
        for record in records:
            client_uuid = record.get("client_uuid")
            if client_uuid is None:
                statuses.append("legacy")
                continue
            if client_uuid in seen_uuids:
                statuses.append("duplicate")
                continue
            seen_uuids.add(client_uuid)
            local = None
            if "client_uuid" in available:
                columns = [c[0] for c in conn.execute('SELECT * FROM "assessments" WHERE 1=0').description]
                row = conn.execute(
                    'SELECT * FROM "assessments" WHERE client_uuid = ? AND user_id = ?', (client_uuid, user_id)
                ).fetchone()
                if row:
                    local = {k: _json_safe(v) for k, v in zip(columns, row)}
            if local is None:
                statuses.append("new")
                continue
            if _assessment_content_hash(local) == _assessment_content_hash(record):
                statuses.append("unchanged")
                continue
            local_updated = str(local.get("updated_at") or local.get("created_at") or "")
            incoming_updated = str(record.get("updated_at") or record.get("created_at") or "")
            statuses.append("conflicting" if local_updated > incoming_updated else "updated")
    return statuses


def _upsert_assessment(conn: sqlite3.Connection, record: dict[str, Any], user_id: int, replace: bool) -> str:
    """Insert or update an assessment matched by its stable client_uuid (not the
    local autoincrement id, which is not stable across devices)."""
    available = _existing_columns(conn, "assessments")
    payload = {k: v for k, v in record.items() if k in available and k != "id"}
    payload["user_id"] = user_id
    client_uuid = record.get("client_uuid")
    if client_uuid and "client_uuid" in available:
        existing = conn.execute(
            'SELECT id FROM "assessments" WHERE client_uuid = ? AND user_id = ?', (client_uuid, user_id)
        ).fetchone()
        if existing:
            if not replace:
                return "skipped"
            assignments = ", ".join(f'"{k}" = ?' for k in payload if k != "user_id")
            values = [payload[k] for k in payload if k != "user_id"]
            if assignments:
                conn.execute(f'UPDATE "assessments" SET {assignments} WHERE id = ?', (*values, existing[0]))
            return "merged"
    columns = list(payload)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(f'INSERT INTO "assessments" ({", ".join(columns)}) VALUES ({placeholders})', [payload[c] for c in columns])
    return "imported"

def detect_conflicts(document: dict[str, Any], user_id: int, db_name: str | None = None) -> dict[str, list[dict[str, Any]]]:
    db_name = db_name or os.getenv("ECO_BUDDY_DB", "eco_buddy.db")
    result = {name: [] for name in ("assessments", "goals", "habits", "recommendations")}
    with sqlite3.connect(db_name) as conn:
        for name in result:
            spec = TABLES[name]
            table = spec.get("table", name)
            if not _table_exists(conn, table):
                continue
            existing = _rows(conn, table, user_id, spec["columns"])
            existing_keys = {_stable_key(name, row): row for row in existing}
            for record in document.get(name, []):
                if _stable_key(name, record) in existing_keys:
                    result[name].append(record)
                    continue
                rid = record.get(spec["id"])
                if rid is not None and spec["id"] in _existing_columns(conn, table):
                    row = conn.execute(f'SELECT 1 FROM "{table}" WHERE "{spec["id"]}" = ? AND user_id = ?', (rid, user_id)).fetchone()
                    if row:
                        result[name].append(record)
    return result


def create_import_preview(document: dict[str, Any], user_id: int, db_name: str | None = None) -> dict[str, Any]:
    valid, errors = validate_export_document(document)
    if not valid:
        return {"valid": False, "records_found": {}, "new_records": {}, "conflicts": {}, "skipped_records": {}, "invalid_records": len(errors), "errors": errors}
    conflicts = detect_conflicts(document, user_id, db_name)
    counts = {name: len(document.get(name, [])) for name in ("assessments", "goals", "habits", "recommendations")}
    conflict_counts = {name: len(records) for name, records in conflicts.items()}
    new_counts = {name: counts[name] - conflict_counts[name] for name in counts}
    assessment_status_counts = dict.fromkeys(ASSESSMENT_STATUSES, 0)
    for status in classify_assessments(document, user_id, db_name):
        assessment_status_counts[status] += 1
    return {"valid": True, "records_found": counts, "new_records": new_counts, "conflicts": conflict_counts, "skipped_records": {name: 0 for name in counts}, "invalid_records": 0, "errors": [], "assessment_status_counts": assessment_status_counts}

def _validate_user_target(conn: sqlite3.Connection, user_id: int) -> None:
    if not conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone():
        raise ValueError("Target user does not exist")


def _insert_record(conn: sqlite3.Connection, table: str, record: dict[str, Any], user_id: int, strategy: str) -> str:
    available = _existing_columns(conn, table)
    if not available:
        return "skipped"
    payload = {k: v for k, v in record.items() if k in available and k != "id"}
    payload["user_id"] = user_id

    # user_habits is a singleton row per user, so user_id is its conflict key.
    if table == "user_habits":
        existing = conn.execute('SELECT 1 FROM "user_habits" WHERE user_id = ?', (user_id,)).fetchone()
        if existing:
            if strategy == "skip":
                return "skipped"
            if strategy in ("merge", "replace"):
                assignments = ", ".join(f'"{k}" = ?' for k in payload if k != "user_id")
                values = [payload[k] for k in payload if k != "user_id"]
                if assignments:
                    conn.execute(f'UPDATE "user_habits" SET {assignments} WHERE user_id = ?', (*values, user_id))
                return "merged" if strategy == "merge" else "imported"

    # Preserve primary IDs only when safe; otherwise SQLite allocates them.
    if "id" in available and "id" in record and record["id"] is not None:
        existing = conn.execute(f'SELECT 1 FROM "{table}" WHERE id = ? AND user_id = ?', (record["id"], user_id)).fetchone()
        if existing:
            if strategy == "skip":
                return "skipped"
            if strategy == "replace":
                conn.execute(f'DELETE FROM "{table}" WHERE id = ? AND user_id = ?', (record["id"], user_id))
            elif strategy == "merge":
                assignments = ", ".join(f'"{k}" = ?' for k in payload if k != "user_id")
                values = [payload[k] for k in payload if k != "user_id"]
                if assignments:
                    conn.execute(f'UPDATE "{table}" SET {assignments} WHERE id = ? AND user_id = ?', (*values, record["id"], user_id))
                return "merged"
    columns = list(payload)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(f'INSERT INTO "{table}" ({", ".join(columns)}) VALUES ({placeholders})', [payload[c] for c in columns])
    return "imported"


def merge_imported_data(
    document: dict[str, Any],
    user_id: int,
    strategy: str = "skip",
    db_name: str | None = None,
    resolutions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Atomically import a validated document. Any exception rolls back all writes.

    `resolutions` lets the caller pick a winner for individual conflicting
    assessments: map an assessment's `client_uuid` to "keep_incoming" to accept
    the imported version, or leave it out (or "keep_local") to keep the newer
    local copy. Records without a resolution are never silently overwritten.
    """
    if strategy not in CONFLICT_STRATEGIES:
        raise ValueError(f"Unknown conflict strategy: {strategy}")
    valid, errors = validate_export_document(document)
    if not valid:
        raise ValueError("Import validation failed: " + "; ".join(errors))
    document = migrate_export(document)
    db_name = db_name or os.getenv("ECO_BUDDY_DB", "eco_buddy.db")
    resolutions = resolutions or {}
    summary = {"imported": 0, "merged": 0, "skipped": 0, "conflicts": 0, "invalid": 0}
    with sqlite3.connect(db_name) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _validate_user_target(conn, user_id)
        try:
            conn.execute("BEGIN")
            conflicts = detect_conflicts(document, user_id, db_name)
            summary["conflicts"] = sum(len(v) for v in conflicts.values())
            assessment_statuses = classify_assessments(document, user_id, db_name)
            for name in ("assessments", "goals", "habits", "recommendations"):
                table = TABLES[name].get("table", name)
                for index, record in enumerate(document.get(name, [])):
                    if name == "habits" and "data_json" in record:
                        # Never import a second user_habits row; strategy controls update/skip.
                        pass
                    if name == "assessments":
                        status = assessment_statuses[index]
                        if status == "legacy":
                            outcome = _insert_record(conn, table, record, user_id, strategy)
                            summary[outcome] += 1
                            continue
                        if status in ("unchanged", "duplicate"):
                            summary["skipped"] += 1
                            continue
                        if status == "conflicting":
                            choice = resolutions.get(record.get("client_uuid"), "keep_local")
                            if choice != "keep_incoming":
                                summary["skipped"] += 1
                                continue
                            summary[_upsert_assessment(conn, record, user_id, replace=True)] += 1
                            continue
                        # status is "new" or "updated": safe to apply without user input.
                        summary[_upsert_assessment(conn, record, user_id, replace=True)] += 1
                        continue
                    outcome = _insert_record(conn, table, record, user_id, strategy)
                    summary[outcome] += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return summary


def import_user_profile(
    source: str | dict[str, Any],
    user_id: int,
    strategy: str = "skip",
    db_name: str | None = None,
    resolutions: dict[str, str] | None = None,
) -> dict[str, Any]:
    if isinstance(source, str):
        try:
            document = json.loads(source)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc
    else:
        document = source
    valid, errors = validate_export_document(document)
    if not valid:
        raise ValueError("Import validation failed: " + "; ".join(errors))
    return merge_imported_data(document, user_id, strategy=strategy, db_name=db_name, resolutions=resolutions)
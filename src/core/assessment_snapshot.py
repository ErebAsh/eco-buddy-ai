"""
Immutable assessment calculation snapshots.

EcoBuddy AI's emission factors (see carbon/emission_factors.py), eco-score
baseline/sensitivity, and category weights (see core/config.py) can all
change over time. A footprint or Eco Score computed today is only meaningful
alongside the exact calculation context that produced it, so every completed
assessment now freezes that context into a snapshot at calculation time,
instead of letting historical views silently recalculate against whatever
configuration happens to be live later.

This module only builds and (de)serializes snapshots. Persistence lives in
core/database.py, in an append-only table (`assessment_snapshots`, one row
per assessment via a UNIQUE constraint, no update path in application code),
so a stored snapshot can't be modified by ordinary update operations.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.core.config import ECO_SCORE_BASELINE, ECO_SCORE_SENSITIVITY, CATEGORY_WEIGHTS
from src.utils.assessment_explainability import ENGINE_VERSION

# Schema version for the snapshot's own shape, distinct from the
# calculation-engine version. Bump this if fields are added or removed so
# old snapshots can still be told apart from new ones.
SNAPSHOT_SCHEMA_VERSION = "1.0"


def build_assessment_snapshot(
    inputs: dict[str, Any],
    footprint_audit: dict[str, Any],
    contributors: dict[str, Any],
    total: float,
    eco_score: int,
    uncertainty_range: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Freeze everything needed to reproduce an assessment later:

    - the original normalized user inputs
    - the emission-factor dataset/version and its provenance
    - the calculation-engine version
    - the eco-score configuration (baseline, sensitivity, category weights)
      in effect at calculation time
    - the resulting category-level emissions
    - the final total footprint and Eco Score
    - the exact calculation timestamp
    - uncertainty bounds and confidence per category (if available)

    `footprint_audit` is the audit log dict already returned by
    `calculate_footprint(..., return_audit=True)`; `contributors` is the
    per-category emissions dict returned alongside it.
    `uncertainty_range` is the dict returned by `calculate_footprint_range()`
    if available, containing category_bounds and uncertainty_percent.
    """
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": dict(inputs),
        "factor_version": footprint_audit.get("factor_version"),
        "provenance": footprint_audit.get("provenance"),
        "eco_score_config": {
            "baseline": ECO_SCORE_BASELINE,
            "sensitivity": ECO_SCORE_SENSITIVITY,
            "category_weights": dict(CATEGORY_WEIGHTS),
        },
        "category_emissions_kg": dict(contributors),
        "total_kg": total,
        "eco_score": eco_score,
    }
    
    # Add uncertainty metadata if available, so historical assessments
    # remain reproducible even after emission factors change.
    if uncertainty_range:
        snapshot["uncertainty_percent"] = uncertainty_range.get("uncertainty_percent")
        snapshot["category_bounds"] = uncertainty_range.get("category_bounds", {})
        snapshot["uncertainty_range"] = {
            "low_kg": uncertainty_range.get("low_kg"),
            "central_kg": uncertainty_range.get("central_kg"),
            "high_kg": uncertainty_range.get("high_kg"),
        }
    
    return snapshot

def serialize_snapshot(snapshot: dict[str, Any]) -> str:
    """JSON-encode a snapshot for storage."""
    return json.dumps(snapshot, sort_keys=True)


def deserialize_snapshot(snapshot_json: str) -> dict[str, Any]:
    """Decode a stored snapshot back into a plain dict."""
    return json.loads(snapshot_json)
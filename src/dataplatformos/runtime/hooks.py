"""Thin runtime helpers imported by generated Airflow DAGs — not a framework scheduler."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("dataplatformos.runtime")

DEFAULT_POISON_DIR = Path(".dataplatformos/intake_failed")


def intake_guard(
    pipeline_id: str,
    step_id: str,
    max_attempts: int = 3,
    on_failure: str = "poison",
    landing_space: str | None = None,
    poison_root: str | Path | None = None,
    **_: Any,
) -> dict[str, Any]:
    """
    Landing→Bronze intake guard (D16).

    Corrupt delivery units stay in Landing; we record poison markers so the next
    DAG run does not infinitely reprocess the same unit.
    """
    root = Path(poison_root) if poison_root else DEFAULT_POISON_DIR
    root.mkdir(parents=True, exist_ok=True)
    marker = root / f"{pipeline_id}__{step_id}.json"
    state = {"attempts": 0, "status": "ok", "units": []}
    if marker.exists():
        state = json.loads(marker.read_text(encoding="utf-8"))

    poisoned = [u for u in state.get("units", []) if u.get("status") == "poison"]
    terminal = [u for u in poisoned if u.get("attempts", 0) >= max_attempts]

    logger.info(
        "intake_guard pipeline=%s step=%s landing=%s poisoned=%s terminal=%s mode=%s",
        pipeline_id,
        step_id,
        landing_space,
        len(poisoned),
        len(terminal),
        on_failure,
    )

    if terminal and on_failure == "fail_pipeline":
        raise RuntimeError(
            f"intake terminal failures for {pipeline_id}.{step_id}: "
            f"{[u.get('unit_id') for u in terminal]}"
        )

    # Skip terminal poison units; callers should filter landing listings against marker
    return {
        "skip_unit_ids": [u.get("unit_id") for u in terminal],
        "marker": str(marker),
        "max_attempts": max_attempts,
    }


def mark_intake_failure(
    pipeline_id: str,
    step_id: str,
    unit_id: str,
    error: str,
    *,
    poison_root: str | Path | None = None,
) -> dict[str, Any]:
    """Record a poison marker for one delivery unit."""
    root = Path(poison_root) if poison_root else DEFAULT_POISON_DIR
    root.mkdir(parents=True, exist_ok=True)
    marker = root / f"{pipeline_id}__{step_id}.json"
    state: dict[str, Any] = {"attempts": 0, "status": "ok", "units": []}
    if marker.exists():
        state = json.loads(marker.read_text(encoding="utf-8"))

    units = state.setdefault("units", [])
    existing = next((u for u in units if u.get("unit_id") == unit_id), None)
    if existing:
        existing["attempts"] = int(existing.get("attempts", 0)) + 1
        existing["error"] = error
        existing["status"] = "poison"
    else:
        units.append(
            {
                "unit_id": unit_id,
                "attempts": 1,
                "error": error,
                "status": "poison",
            }
        )
    marker.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return existing or units[-1]


def clear_intake_failure(
    pipeline_id: str,
    step_id: str,
    unit_id: str,
    *,
    poison_root: str | Path | None = None,
) -> None:
    """Operator-driven replay: clear a poison marker for one unit."""
    root = Path(poison_root) if poison_root else DEFAULT_POISON_DIR
    marker = root / f"{pipeline_id}__{step_id}.json"
    if not marker.exists():
        return
    state = json.loads(marker.read_text(encoding="utf-8"))
    state["units"] = [u for u in state.get("units", []) if u.get("unit_id") != unit_id]
    marker.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def quality_gate(
    pipeline_id: str,
    step_id: str,
    engine: str,
    contract_ref: str | None,
    on_failure: str,
    zone: str,
    **_: Any,
) -> dict[str, Any]:
    """Placeholder quality gate — real Deequ/GE runs happen in generated job configs."""
    logger.info(
        "quality_gate pipeline=%s step=%s engine=%s contract=%s on_failure=%s zone=%s",
        pipeline_id,
        step_id,
        engine,
        contract_ref,
        on_failure,
        zone,
    )
    if zone in {"landing", "bronze"} and on_failure == "quarantine":
        raise ValueError("quarantine is not allowed for bronze/landing")
    return {"status": "compiled_placeholder", "engine": engine}


def supervise_continuous(
    pipeline_id: str,
    step_id: str,
    engine: str,
    connector: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Airflow supervision stub for continuous (streaming) steps — liveness, not cron."""
    logger.info(
        "supervise_continuous pipeline=%s step=%s engine=%s connector=%s",
        pipeline_id,
        step_id,
        engine,
        connector,
    )
    return {"status": "supervise", "engine": engine, "connector": connector}


def tier1_reconcile(
    pipeline_id: str,
    step_id: str,
    connector: str | None,
    object: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    """
    Tier-1 reconciliation stub (D5): entity-key presence/checksums, not raw row counts.
    Generated jobs should call connector metadata helpers at runtime.
    """
    logger.info(
        "tier1_reconcile pipeline=%s step=%s connector=%s object=%s mode=entity_key",
        pipeline_id,
        step_id,
        connector,
        object,
    )
    return {
        "status": "compiled_placeholder",
        "mode": "entity_key",
        "connector": connector,
        "object": object,
    }

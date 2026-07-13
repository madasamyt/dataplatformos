from __future__ import annotations

import json
from pathlib import Path

from dataplatformos.compiler.compile import compile_project
from dataplatformos.runtime.hooks import clear_intake_failure, intake_guard, mark_intake_failure

REPO = Path(__file__).resolve().parents[1]
COMMERCE = REPO / "examples" / "commerce_orders"
DEVICES = REPO / "examples" / "device_json_stream"


def test_compile_commerce_orders(tmp_path: Path) -> None:
    out = tmp_path / "dist"
    result = compile_project(COMMERCE, out)
    paths = {a.relative_path for a in result.artifacts}
    assert any(p.startswith("airflow/dags/") for p in paths)
    assert any(p.startswith("dbt/") for p in paths)
    assert any(p.startswith("meltano/") for p in paths)
    assert any(p.startswith("debezium/") for p in paths)
    assert any(p.startswith("ml/") for p in paths)
    assert any(p.startswith("semantic/") for p in paths)
    assert any(p.startswith("delivery/") for p in paths)
    assert "openlineage/lineage.json" in paths
    assert "docs/index.md" in paths
    assert (out / "MANIFEST.json").is_file()
    assert (out / "delivery" / "recertification_flags.json").is_file()
    assert (out / "semantic" / "metricflow_project.yml").is_file()
    assert (out / "quality" / "deequ").is_dir()
    assert (out / "quality" / "great_expectations").is_dir()


def test_compile_device_stream_flink(tmp_path: Path) -> None:
    out = tmp_path / "dist"
    result = compile_project(DEVICES, out)
    paths = {a.relative_path for a in result.artifacts}
    assert any(p.startswith("flink/") for p in paths)
    dag = next(p for p in paths if p.startswith("airflow/dags/"))
    text = (out / dag).read_text(encoding="utf-8")
    assert "supervise_continuous" in text or "_supervise_continuous" in text


def test_intake_poison_helpers(tmp_path: Path) -> None:
    root = tmp_path / "poison"
    mark_intake_failure("p", "s", "file-1", "bad gzip", poison_root=root)
    mark_intake_failure("p", "s", "file-1", "bad gzip again", poison_root=root)
    state = json.loads((root / "p__s.json").read_text(encoding="utf-8"))
    unit = state["units"][0]
    assert unit["attempts"] == 2
    assert unit["status"] == "poison"

    guard = intake_guard("p", "s", max_attempts=2, poison_root=root)
    assert "file-1" in guard["skip_unit_ids"]

    clear_intake_failure("p", "s", "file-1", poison_root=root)
    guard2 = intake_guard("p", "s", max_attempts=2, poison_root=root)
    assert guard2["skip_unit_ids"] == []

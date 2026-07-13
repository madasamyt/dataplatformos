# dataplatformos

Design-time compiler for metadata-driven lakehouse pipelines. Validate a **segment project** (multi-pipeline graph) and generate native Airflow / dbt / Meltano / Debezium / Flink / quality / OpenLineage artifacts. Not a runtime.

## Quick start

```bash
python3 -m pip install -e ".[dev]"
pipeline validate examples/commerce_orders
pipeline compile examples/commerce_orders -o /tmp/commerce_dist
pipeline docs generate examples/commerce_orders -o /tmp/commerce_dist
pipeline lineage examples/commerce_orders -o /tmp/commerce_dist
pytest
```

## What `compile` emits

| Path | Source |
|------|--------|
| `airflow/dags/` | One DAG per pipeline (cron + continuous supervision) |
| `dbt/` | dbt projects grouped by `transform.dbt.project` |
| `meltano/` | Meltano projects for `meltano.*` connectors |
| `debezium/` | CDC connector manifests (Bronze-as-log) |
| `flink/` | FlinkDeployment manifests when `engine: flink` |
| `ml/` | Model invocation manifests when `engine: ml` |
| `quality/` | Deequ + Great Expectations suites from contracts |
| `semantic/` | Metric definitions + MetricFlow-style project |
| `delivery/` | Data product catalog, passthrough views, re-cert flags |
| `openlineage/lineage.json` | Design-time lineage graph |
| `docs/index.md` | Human-readable hop docs + mermaid |

## Docs

1. `docs/architecture-spec.md` — six-zone lakehouse
2. `docs/framework-spec.md` — compiler design and roadmap
3. `docs/decisions.md` — why each constraint exists
4. `AGENTS.md` — non-negotiables for coding agents

## Status

v0.8 — validate + compile including Metrics, DataProducts, and `engine: ml` model invocation. See `docs/plugin-sdk.md`.

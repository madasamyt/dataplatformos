# AGENTS.md — read this before touching the repo

This file is the entry point for any coding agent (Claude Code, Cursor, or otherwise) working in this repository. Claude Code reads `CLAUDE.md` by convention and Cursor reads `AGENTS.md` / `.cursor/rules` — keep this file as the single canonical source and symlink or copy it to whichever filename your tool expects, rather than maintaining two diverging copies.

## What this repo is

An open-source, metadata-driven pipeline framework: a design-time compiler that validates a YAML project (Segment + Pipelines) and generates native Airflow DAGs, dbt projects, Meltano configs, and Flink job manifests — then gets out of the way. It is **not** a runtime. Full spec: `docs/framework-spec.md`.

It exists to support a broader lakehouse architecture — six zones (Landing, Bronze, Silver, Gold, Semantic, Delivery), plus cross-cutting concerns (MDM/RDM, Serving Acceleration, ML Sandbox, Archival) and a federated data-mesh model for productizing data across domains. Full spec: `docs/architecture-spec.md`.

## Read in this order

1. `docs/architecture-spec.md` — what the six zones are, why each exists, naming conventions, stage-wise inter-zone processing
2. `docs/framework-spec.md` — the tool this repo builds, and why it's design-time-only
3. `docs/decisions.md` — the compressed "why," in case a design choice looks arbitrary — check here before overriding it

## Non-negotiable constraints (don't relitigate these without flagging it explicitly to a human)

- **Design-time only.** No framework-owned runtime. Compile to native Airflow/dbt/Meltano/Flink artifacts; don't build a custom scheduler or execution engine.
- **One default per category, not a menu.** Kafka, Flink, Airflow, dbt, Meltano, Debezium are the defaults. Don't add a second adapter for a category unless there's a concrete forcing requirement — pluggability is an interface (`adapters/`), not a pile of pre-built options.
- **Estuary and Dremio are optional, commercial, `contrib/`-only.** Never move them into the default dependency set or the core adapter list.
- **Bronze never rejects records.** Quarantine and validation happen in Silver, not Bronze. Corrupt *delivery units* fail at Landing intake (`intake.on_failure: poison`) — they are not Bronze quarantine. Don't reintroduce rejection logic into Bronze ingestion code.
- **Metrics are defined once, in Semantic.** A `contract_attributes.derived_from` entry that needs grain flexibility must point at a Semantic metric (`semantic_ref`), never re-declare the formula. If you find yourself writing the same aggregation logic in two places, that's the bug to fix, not a pattern to copy.
- **A `custom` step is still a governed step.** It must declare `inputs`, `outputs`, `trigger`, and `quality.contract_ref` like any config-driven step — the carve-out is for *logic*, not for escaping lineage/observability.
- **Don't build a second catalog.** Every adapter registers schema/lineage back into the shared Iceberg REST catalog. No framework-local table registry that could drift from what the query engine actually sees.
- **Project compile.** Validate and compile a segment project directory (multi-pipeline graph), not only a single file.
- **ML is a governed step.** Prefer `transform.engine: ml` with `ml.model_ref` for model registry invocation; `custom` remains for non-model containers. Both require inputs/outputs/trigger/contract.
- **Metrics once, products certify in place.** Segment `metrics[]` / `products[]`; KPI products must not skip Semantic (D4).

## When you hit a design question not covered above

Check `docs/decisions.md` first — most edge cases (row-count expectations across zones, job-vs-view-vs-materialized-view, CDC-as-mirror-vs-log, streaming-vs-batch reconciliation, intake vs quarantine) were already reasoned through and the rationale is there, not just the conclusion. If it's genuinely new, make the smallest decision consistent with the constraints above and note it — don't silently pick a direction that contradicts an existing entry.

# Decisions log

Compressed ADR-style record of design decisions and the reasoning behind them. Read this when a choice in the spec docs looks arbitrary — most aren't; they're the surviving option after a specific alternative was tried and rejected. Newest-relevant-first within each topic isn't the ordering here; it's grouped by subject.

---

### D1 — Medallion core is 3 layers (Bronze/Silver/Gold); everything else must earn its place
**Decision:** Landing, Semantic, and Delivery are legitimate additions, but only because each does a transformation nothing else does. Landing = pre-schema staging. Semantic = metric definition decoupled from physical grain. Delivery = packaging/certification, not content.
**Rejected:** An earlier 7-layer draft split "Semantic" into two overlapping boxes (domain products / consumption views) that both duplicated what Databricks' own docs already describe as native Gold behavior (star schemas, business aggregates). Collapsed back to one Semantic layer.
**Why it matters for the framework:** the metadata schema's `zone` enum should stay at six values (landing, bronze, silver, gold, semantic, delivery) — resist pressure to add more without the same "does this do a transformation nothing else does" test.

### D2 — Quarantine and validation happen in Silver, never Bronze
**Decision:** Bronze does structural typing only and never rejects a record. Malformed/unexpected fields are retained loosely-typed. Quarantine, null-handling, and business-rule validation are Silver's job.
**Why:** Bronze's value is being a replayable "insurance policy" — every record that arrived is still there. Rejecting records in Bronze breaks that guarantee and means re-deriving rejection logic on every replay.
**Framework implication:** `quality.on_failure: quarantine` should not be a valid config for a Bronze-zone target in the schema validator — flag it as a validation error if attempted.
**Intake failures are not quarantine:** A fundamentally corrupt *delivery unit* (truncated file, undecryptable object, non-JSON payload) is not a bad Bronze record — the Landing→Bronze job cannot admit it as a row. Corrupt bytes stay in Landing; the job records an intake/poison failure with attempt limits so the next DAG run does not infinitely reprocess the same unit. See D16.

### D3 — Delivery is packaging, not a content tier
**Decision:** Renamed from "Data Products" to "Delivery & Access Layer." A product's *content* is certified in place — Foundation products in Silver, Analytical/360° in Gold, KPI/Dashboard products in Semantic. Delivery is the uniform front door (catalog, entitlement, output-port translation) every certified product passes through regardless of origin tier.
**Why:** the original naming implied products originate at the last layer, which contradicted the taxonomy (Foundation, 360°, Analytical, AI/ML, Dashboard products) that's sourced from earlier tiers.

### D4 — Skipping a layer is fine; reusing its function silently is not
**Decision:** Gold → Delivery direct is fine for content-shaped products (a 360, a foundation extract) with no metric to abstract. Gold → Delivery must NOT skip Semantic when the product carries a governed, reusable metric — that's a silent fork of the metric's definition.
**Mechanism split:** a "governance skip" (no access-control chokepoint enforced upstream) needs nothing extra. An "access-uniformity skip" (RLS/entitlements enforced centrally at the query engine) needs a thin 1:1 passthrough view in Semantic — same content, no new metric, but the enforcement chokepoint stays intact.

### D5 — Row-count parity between a layer and its source is not a valid completeness signal
**Decision:** Verify completeness at the entity-key level (every source `order_id` traceable downstream), not by comparing raw row counts.
**Why:** counts diverge in both directions for legitimate reasons — technical dedup (Bronze) and entity dedup (Silver) shrink counts; SCD2 history and grain changes (nested line items exploding to rows) grow them; Silver→Gold aggregation can shrink or grow depending on target grain.
**Framework implication:** the Tier-1 reconciliation job (`SourceConnector.report_metadata()`) should compare key-level presence/checksums, not row counts, by default.

### D6 — Data products are certified in place; domain tag reflects the owner, not the source
**Decision:** A product's domain association should reflect who owns/consumes it (a "consumption-level domain" like Customer Experience or Finance), not which source systems its inputs came from ("source-level domains" like Commerce or CRM). Most valuable products are cross-domain by design — that's not a modeling failure, it's the point of productization.
**Example anchor:** Customer 360 (cross-domain: Commerce+CRM+Marketing+Loyalty, owned by CX) vs. Order Fulfillment Ops Product (single-domain: Commerce only, owned by Commerce).

### D7 — Measure → Metric → KPI is a real progression, not synonyms
**Decision:** A measure is a number bound to one table's fixed grain (Gold). A metric is that computation decoupled into a governed, reusable definition callable at any grain (Semantic). A KPI is a metric frozen to one formula and certified for one audience (Delivery), sourced from the metric catalog, never recomputed fresh.
**Related:** goals/targets are a separate, third object (a Goal Registry keyed by KPI × consumer × period) — not part of the metric or the KPI record, because the same KPI can carry different targets for different audiences. RAG status and trend are presentation-time comparisons, not new metrics. QoQ/YoY/YTD are the same aggregation over a different window (decoration). Percentiles (P90/P95) are NOT decoration — they require the full distribution, a genuinely different aggregation, and should be their own registered metric.

### D8 — A BI tool's semantic model is a cache, never the source of truth
**Decision:** Metric definitions are authored once in the lakehouse-hosted Semantic layer. Power BI/Tableau/notebook-local calculated fields are legitimate only as a local cache of an already-governed definition.
**Why:** independent authoring in each tool recreates the exact metric-sprawl problem the Semantic layer exists to prevent, one level up.

### D9 — Streaming outputs can be products, but must carry a provisional flag; never silently equal to a certified KPI
**Decision:** Fast/streaming signals may feed operational/tactical products (freshness in seconds, explicit "corrected within Nh" contract). They cannot become certified KPIs until the batch/deep pipeline reconciles them. On reconciliation: either overwrite in place (same product, upgraded confidence) or publish a separate certified product with lineage back to the provisional one.

### D10 — CDC/ODS sourcing: Bronze-as-log is the default, not Bronze-as-mirror
**Decision:** Bronze should be an append-only event log (one row per CDC change event with before/after images), not a continuously-upserted mirror of current source state.
**Why:** Bronze-as-mirror destroys history the moment a row is updated/deleted — SCD2 and status-history tables cannot be accurately built from it afterward without a side-channel back to the raw feed. Bronze-as-log keeps history-building possible downstream (in Silver) without extra plumbing.
**SCD2 timing:** use the CDC event's source-commit timestamp for `_valid_from`/`_valid_to`, not ingestion timestamp, to avoid ingestion-lag skew.

### D11 — Lineage-aware re-certification, not blind trust in "certified"
**Decision:** A certified product built on an uncertified intermediate table (e.g., Regional Sales Performance Product on `orders_daily_agg`) should trigger an automatic re-certification flag when that upstream table changes — even transitively — not just when its direct output changes.
**Why:** without this, "certified" quietly rests on an unreviewed foundation, and the certification stamp stops meaning what a consumer assumes it means.

### D12 — Validation is three tiers; AI/MCP agents belong at tier 3 only
**Decision:** Tier 1 (structural/entity-key completeness) and Tier 2 (business-rule/referential validation) are deterministic, scheduled, no AI involved. Tier 3 (semantic reconciliation, root-cause triage across systems) is where an AI agent with read-only MCP connections adds real value — diagnosing *why* a diff exists, not computing the diff itself. Auto-remediation requires an explicit human approval gate; agents don't get write access by default.

### D13 — Framework is a design-time compiler, not a runtime
**Decision:** The pipeline framework validates metadata and generates native Airflow DAGs / dbt projects / Meltano configs / Flink manifests, then exits. No framework-owned scheduler, no framework-owned execution engine.
**Why:** avoids the single biggest over-engineering risk — a custom orchestration runtime the team now has to operate as a second platform, on top of the AWS+Dremio (or any) platform already in place.
**Compile-first adapters:** Adapter Protocols expose `compile(spec) → GeneratedArtifact`. Native tools (Airflow, dbt, Meltano, Flink, Deequ/GE) are the runtime. Optional thin helper libraries may be *imported by generated jobs* (intake poison markers, Tier-1 reconciliation, quarantine writers) — never a standing framework service.

### D14 — One default tool per category; commercial tools are optional contrib adapters
**Decision:** Kafka (not multiple streaming transports), Flink (not Flink + Kinesis Analytics + Lambda treated as three streaming tiers — Lambda is stateless glue only), Airflow, dbt-core, Meltano, Debezium are the shipped defaults. Estuary and Dremio are supported through the same adapter interface but live in `contrib/commercial/`, excluded from the default install, because the project is open-source-first and shouldn't require a commercial dependency to run.
**Deliberate exception:** data quality uses two tools (Deequ for Bronze/Silver volume + anomaly detection; Great Expectations for Gold/Semantic/Delivery-tier contract readability) — not redundancy, they serve genuinely different volume/audience tiers.

### D15 — Attribute-level contracts, not a full ontology, inside the pipeline framework
**Decision:** Contracts extend to column granularity (type, valid range, accepted values, simple same-table derivations). Anything needing cross-attribute reasoning, grain-flexible calculation, or semantic relationships points at a Semantic-layer metric (`semantic_ref`) instead of re-declaring logic — and stops there.
**Why:** a full ontology (ontology/knowledge graph/RAG) is explicitly out of scope for the data substrate — that's Knowledge Core, living in the Agentic Core dimension. Building attribute-level ontology reasoning into the pipeline framework would blur a boundary that's been deliberately kept clean throughout this design.

### D16 — Landing intake failure ≠ Silver quarantine
**Decision:** Unreadable or fundamentally corrupt delivery units fail at *intake* (Landing→Bronze), not via Bronze `quality.on_failure: quarantine`. Bytes remain in Landing; a poison/control marker (or `_intake_failed/` sidecar) records the error and attempt count. Default: do not re-attempt forever — terminal after `max_attempts` unless an operator clears the marker for deliberate replay.
**Why:** Quarantine is a business-rule outcome on parseable rows. Intake failure is "this unit never became a row." Collapsing them would either force fake Bronze rows or reintroduce Bronze rejection under another name.
**Framework implication:** Landing→Bronze steps may declare `intake.on_failure: poison | fail_pipeline` and `intake.max_attempts`. Bronze `quality.on_failure` may only be `warn` or `fail_pipeline`.

### D17 — Segment = multi-pipeline graph; Pipeline = multi-step DAG
**Decision:** A `Pipeline` is an ordered/DAG of zone-transition *steps*. A `Segment` is the project-level graph that binds landing spaces and multiple pipelines that are not necessarily one chronology (e.g. parallel source ingest + a later conform pipeline).
**Why:** Real platform slices are not linear. Forcing everything into one pipeline file either lies about dependencies or creates god-files.
**Framework implication:** CLI validates/compiles a *project directory* (segment + refs), not only a single YAML file.

### D19 — ML model invocation is a typed custom carve-out (`engine: ml`)
**Decision:** Invoking a registered ML model is still a governed pipeline step (inputs, outputs, trigger, `quality.contract_ref`). Prefer `transform.engine: ml` with required `transform.ml.model_ref` when the step scores/trains against a model registry. `engine: custom` remains valid for arbitrary containers that are not model invocations.
**Why:** The custom carve-out already prevents escaping lineage/observability; a typed `ml` engine makes model provenance explicit in metadata and generated manifests without inventing a second runtime.
**Rejected:** A separate ML orchestration platform inside the compiler, or allowing model steps without contracts.

### D20 — Metric and DataProduct are first-class segment kinds
**Decision:** Segments may declare `metrics[]` and `products[]` refs. Metrics are authored once (`semantic/v1`) and compiled to MetricFlow-style YAML. Data products (`delivery/v1`) certify content in place (Silver/Gold/Semantic/Metric) and emit Delivery packaging + re-certification watch lists (D11).
**Framework implication:** `contract_attributes.derived_from.semantic_ref` must resolve to a Metric id in the same segment. KPI/dashboard products must source from `semantic` or `metric` (D4).

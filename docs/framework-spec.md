# Metadata-Driven Pipeline Framework
### An open-source build specification — for a coding agent, not just a reader

---

## 0. What kind of thing this is

This document is written to be handed to a coding agent (Cursor, Claude Code) to scaffold and build an actual open-source repository. It states defaults where a clear one exists, marks explicit extension points where pluggability genuinely matters, and stays deliberately silent on implementation detail an agent should figure out — the goal is a spec an agent can act on without a hundred follow-up questions, not a prescription for every line of code.

**Scope decision, settled from prior discussion: this is a design-time compiler, not a runtime.** The framework validates a metadata definition and *generates* native artifacts — an Airflow DAG file, a dbt project, a Meltano config — then gets out of the way. Nothing framework-owned executes in production except the compiler itself and a thin metadata/lineage registry. This is the single most important scope boundary in this spec: it is what keeps the project from becoming "a second platform to operate" instead of a governance layer over tools teams already run.

**One strong default per category, not a menu.** Where a category has one clearly solid open-source answer (Kafka for streaming transport, Flink for stream processing, Airflow for orchestration), the framework ships exactly one first-class adapter and doesn't pretend to be neutral about it. Pluggability exists as an architectural seam (an adapter interface), not as five pre-built options nobody asked for. Commercial tools some environments already run (Estuary, Dremio) are supported as clearly-labeled optional adapters, never defaults, so the open-source project stands on its own without requiring them.

---

## 1. Default stack

| Category | Default (OSS, ships in core) | Optional / pluggable (documented, not built-in) |
|---|---|---|
| Orchestration runtime | **Airflow** | — (single target for v1; additional targets are a post-1.0 adapter, not a launch requirement) |
| Batch SQL transform | **dbt-core** | Works against Dremio (dbt-dremio), Snowflake, BigQuery, Postgres, Databricks — warehouse-agnostic by design, not tied to Dremio |
| Batch/API EL | **Meltano** (Singer taps) | Airbyte; **Estuary** (commercial — marked explicitly optional) |
| CDC | **Debezium** | AWS DMS; **Estuary** (also covers CDC, commercial) |
| Streaming transport | **Kafka** | AWS MSK is managed Kafka, so this is not an AWS-exclusion — Kinesis supported as a secondary transport adapter, not default |
| Streaming compute | **Flink** | — (single option; deployment target — self-managed, MSK Connect, Kinesis Data Analytics for Flink — is an adapter *config*, not a second engine choice) |
| Data quality — Bronze/Silver volume | **Deequ** (Spark-native, scales, has anomaly detection on tracked metrics) | — |
| Data quality — Gold/Semantic/Delivery contracts | **Great Expectations** (readable "data docs" for small, business-facing tables) | This is the one deliberate two-tool case — they serve different volume/audience tiers, not a redundant choice |
| Catalog | **Iceberg REST catalog** interface (the emerging open standard) | Glue Catalog, Unity Catalog, Nessie — all speak Iceberg REST or have a thin adapter |
| Query / semantic engine | **Not owned by the framework at all** | Dremio, Trino, anything — the framework writes to the catalog and stops; it has no opinion here |
| Non-SQL custom compute | **Spark** | Arbitrary containers via the custom carve-out (§5) |

If a category above has exactly one entry in both columns, that's deliberate — it means "don't add a second option without a concrete forcing requirement," not "we forgot to research alternatives."

---

## 2. Architecture

```
metadata (YAML, git-versioned)
        │
        ▼
  [ schema validator ]  ──── JSON Schema, versioned (apiVersion)
        │
        ▼
  [ compiler / generators ]
        │
  ┌─────┼─────────┬─────────────┬──────────────┐
  ▼     ▼         ▼             ▼              ▼
Airflow  dbt    Meltano/    Flink job        Quality
DAG    project  Debezium    deployment       gate config
file            config      manifest         (Deequ/GE)
        │
        ▼
[ these run as 100% native Airflow / dbt / Meltano / Flink — no framework runtime ]
        │
        ▼
[ lineage + docs extraction ]  ──── OpenLineage events + dbt docs, written back to
                                     the shared Iceberg REST catalog
```

The compiler is the only thing that needs to be "always available" — it can run in CI (validate + compile on every metadata commit) rather than as a standing service.

---

## 3. Metadata schema (v1)

Validation and compile operate on a **project directory**: a `Segment` plus referenced `Pipeline` (and optional `Contract`) files. A segment is a multi-pipeline graph for one slice of the platform — not necessarily one chronology. A pipeline is a multi-step DAG of zone transitions.

### 3.1 Segment (project root)

```yaml
apiVersion: platform/v1
kind: Segment
metadata:
  id: commerce.orders
  domain: commerce
  owner: team-commerce-eng
  description: "Commerce orders ingest and conformation"

spec:
  landingSpaces:
    - id: shopify_files
      mode: platform_owned          # platform_owned | tool_managed | source_owned
      storageRef: s3://acme-landing/shopify/
    - id: meltano_shopify_internal
      mode: tool_managed            # no storageRef — tool owns raw staging
    - id: netsuite_ods
      mode: source_owned            # source/ODS is the replay baseline

  pipelines:
    - ref: pipelines/shopify_orders.yaml
    - ref: pipelines/netsuite_orders.yaml
    - ref: pipelines/orders_conform.yaml
```

`platform_owned` spaces require `storageRef`. `tool_managed` and `source_owned` must omit it (or the validator warns and ignores it).

### 3.2 Pipeline (multi-step)

```yaml
apiVersion: pipeline/v1
kind: Pipeline
metadata:
  id: commerce.shopify_orders
  domain: commerce
  owner: team-commerce-eng
  description: "Land Shopify orders into Bronze then conform toward Silver inputs"
  tags: [orders, shopify, pii]

spec:
  steps:
    - id: land_to_bronze
      dependsOn: []
      source:
        type: file                  # api | db_cdc | file | stream | custom
        landingSpace: shopify_files # must reference a segment landingSpace when platform_owned
        connector: meltano.tap-shopify
        connection_ref: secrets/shopify_prod
        pattern: incremental        # incremental | full_snapshot | cdc | streaming
        incremental_key: updated_at
      target:
        zone: bronze
        catalog: lakehouse
        schema: bronze.shopify
        object: shopify__orders
        format: iceberg
      transform:
        engine: dbt                 # dbt | flink | spark | custom
        ref: models/bronze/shopify__orders.sql
        dbt:
          project: bronze_project
          select: shopify__orders
      trigger:
        mode: cron                  # cron | event | continuous
        schedule: "cron(0 * * * ? *)"
      intake:                       # Landing→Bronze only — not Silver quarantine
        on_failure: poison          # poison | fail_pipeline
        max_attempts: 3
      quality:
        engine: deequ
        contract_ref: contracts/shopify_orders_bronze.yml
        on_failure: warn            # bronze: warn | fail_pipeline only — never quarantine
      lineage:
        upstream: [landing.shopify.orders]
        downstream: [silver.commerce.orders]
      extensions:
        acme.compliance.pii_fields: [customer_email, customer_phone]
        acme.cost_center: CMX-2201

    - id: bronze_typed_checks
      dependsOn: [land_to_bronze]
      # ... additional steps as needed
```

### 3.3 Contract (standalone — source of truth for attributes)

Contracts live in their own files referenced by `quality.contract_ref`. Do not duplicate `contract_attributes` inline on the pipeline except in documentation examples.

```yaml
apiVersion: contract/v1
kind: Contract
metadata:
  id: shopify_orders_bronze
spec:
  attributes:
    - name: order_id
      type: string
      nullable: false
    - name: status
      type: string
      accepted_values: [placed, shipped, cancelled]
    - name: net_amount
      type: decimal
      valid_range: {min: 0}
      derived_from: "gross_amount - discount_amount"
    - name: net_revenue
      type: decimal
      derived_from: {semantic_ref: semantic.commerce.net_revenue}
```

**Hard validation rules (v0.1):**
- `quality.on_failure: quarantine` is **invalid** when `target.zone` is `bronze` (or `landing`).
- Bronze/Landing quality may only use `warn` or `fail_pipeline`.
- `intake` is only valid on steps whose target zone is `bronze` and whose source uses a landing space / file/CDC ingest path.
- Every `landingSpace` id referenced by a pipeline must exist on the segment.
- Step `dependsOn` and pipeline refs must resolve; IDs must be unique within the project.
- A `custom` transform step must declare inputs/outputs (via source/target), `trigger`, and `quality.contract_ref`.

**What changed from the prior draft, and why:**
- **Segment + multi-step pipelines** replace the single-hop YAML — platform slices are graphs, not one chronology.
- **`intake`** distinguishes corrupt delivery units from Silver quarantine (D16).
- **`landingSpaces`** make Landing ownership explicit (D18).
- **Contracts are files** — `contract_ref` is authoritative; inline attributes in docs are illustrative only.
- `trigger` supports `cron | event | continuous` for mixing batch and streaming steps in one lineage graph.
- `quality.engine` stays per-step so Bronze/Silver can default to `deequ` and Gold+ to `great_expectations`.

---

## 4. Plugin architecture — compile-first seam

Four adapter interfaces, each a small Python `Protocol`/ABC. Adapters **compile** metadata into native artifacts. They do not extract or validate data inside the compiler process.

```python
class SourceConnector(Protocol):
    def compile(self, spec: SourceSpec) -> GeneratedArtifact: ...
    # Generated jobs may call a small helper for Tier-1 reconciliation:
    # report_metadata() → entity-key presence / checksums (not raw row counts)

class TransformEngine(Protocol):
    def compile(self, spec: TransformSpec) -> GeneratedArtifact: ...

class QualityEngine(Protocol):
    def compile(self, contract: Contract, target: TableRef) -> GeneratedArtifact: ...

class CatalogWriter(Protocol):
    def compile_registration(self, schema: TableSchema, lineage: LineageEdge) -> GeneratedArtifact: ...
```

Shipped implementations (later milestones): `MeltanoConnector`, `DebeziumConnector`, `DbtEngine`, `FlinkEngine`, `SparkEngine`, `CustomContainerEngine`, `DeequEngine`, `GreatExpectationsEngine`, `IcebergRestCatalogWriter`. `EstuaryConnector` and `DremioCatalogWriter` live in `contrib/commercial/`.

---

## 5. The custom carve-out

Unchanged in principle: a `transform.engine: custom` step still declares inputs, outputs, `trigger`, and `quality.contract_ref`. The generator emits a container/task definition instead of a dbt/Flink manifest, but lineage, scheduling, and quality-gating stay uniform. Enforced by the schema, not convention.

---

## 6. Repository structure

```
dataplatformos/
├── schema/
│   ├── segment.v1.schema.json
│   ├── pipeline.v1.schema.json
│   └── contract.v1.schema.json
├── src/dataplatformos/
│   ├── cli.py                         # `pipeline validate|compile|lineage|docs`
│   ├── compiler/
│   │   └── validator.py
│   ├── adapters/                      # populated from v0.2+
│   └── lineage/
├── contrib/commercial/
├── examples/
│   └── commerce_orders/               # segment project
├── docs/
├── tests/
└── pyproject.toml
```

CLI surface (v0.1): `pipeline validate <project-dir>`. Later: `pipeline compile <project-dir> --target airflow`, `pipeline lineage`, `pipeline docs generate`.

---

## 7. Lineage and KPI documentation — generated, not hand-maintained

Because every step declares `lineage.upstream`/`downstream`, and (in later milestones) Semantic metrics chain via `semantic_ref`, `pipeline docs generate` can walk the graph automatically. `dbt docs generate` covers dbt hops; OpenLineage fills in connector/Flink hops. KPI provenance reports require `Metric` / `DataProduct` kinds (deferred — see roadmap).

---

## 8. Build roadmap

1. **v0.1** ✅ — Segment/Pipeline/Contract JSON Schema + project validator + `pipeline validate <project-dir>`.
2. **v0.2** ✅ — Airflow DAG generator + dbt project generator for multi-step batch SQL hops.
3. **v0.3** ✅ — Meltano and Debezium source adapters; emit Tier-1 reconciliation task stubs (entity-key / checksum).
4. **v0.4** ✅ — Flink adapter + `continuous` trigger supervision in Airflow.
5. **v0.5** ✅ — Deequ and Great Expectations quality adapters + intake poison helpers in `dataplatformos.runtime.hooks`.
6. **v0.6** ✅ — OpenLineage emission + hop-level `pipeline docs generate`.
7. **v0.7** ✅ — `Metric` kind + MetricFlow-style generator; enforce `semantic_ref` resolution.
8. **v0.8** ✅ — `DataProduct` kind (ports, SLA, consumption domain) + lineage-aware re-certification stubs (D11).
9. **v1.0** ✅ (docs) — Plugin SDK docs in `docs/plugin-sdk.md`; `contrib/commercial/` Estuary + Dremio as reference plugins.

**Also:** `transform.engine: ml` — typed model invocation (D19); `custom` still valid for non-model containers.

**v1 non-goals:** marketplace UI, MDM stewardship apps, Goal Registry service, query-engine ownership, MCP auto-remediation agents, Kinesis as a second streaming transport.

CLI: `pipeline validate|compile|docs generate|lineage <project-dir>`.

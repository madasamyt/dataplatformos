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

## 3. Metadata schema (v1, revised)

```yaml
apiVersion: pipeline/v1
kind: Pipeline
metadata:
  id: commerce.orders.shopify
  domain: commerce
  owner: team-commerce-eng
  description: "Ingest and conform Shopify orders"
  tags: [orders, shopify, pii]

spec:
  source:
    type: api                       # api | db_cdc | file | stream | custom
    connector: meltano.tap-shopify  # namespaced: <adapter>.<specific-connector>
    connection_ref: secrets/shopify_prod
    pattern: incremental            # incremental | full_snapshot | cdc | streaming
    incremental_key: updated_at
    trigger:
      mode: cron                    # cron | event | continuous
      schedule: "cron(0 * * * ? *)" # required if mode: cron
      # continuous mode (e.g. a Flink job): orchestrator supervises liveness
      # instead of scheduling discrete runs — no `schedule` field needed

  target:
    zone: bronze
    catalog: lakehouse
    schema: bronze.shopify
    object: shopify__orders
    format: iceberg

  transform:
    engine: dbt                     # dbt | flink | spark | custom
    ref: models/bronze/shopify__orders.sql
    dbt:
      project: bronze_project
      select: shopify__orders

  quality:
    engine: deequ                   # deequ | great_expectations — pick per tier, see §1
    contract_ref: contracts/shopify_orders_v1.yml
    on_failure: quarantine          # quarantine | fail_pipeline | warn

  # Attribute-level contract extension — lives in contract_ref, shown inline here for clarity.
  # Extends the existing SLA/schema contract down to the column level, WITHOUT duplicating
  # anything Semantic already owns.
  contract_attributes:
    - name: order_id
      type: string
      nullable: false
    - name: status
      type: string
      accepted_values: [placed, shipped, cancelled]
    - name: net_amount
      type: decimal
      valid_range: {min: 0}
      derived_from: "gross_amount - discount_amount"   # simple same-table calc, fine to inline
    - name: net_revenue
      type: decimal
      derived_from: {semantic_ref: semantic.commerce.net_revenue}  # anything needing grain
      # flexibility points at the Semantic metric instead of re-declaring the formula

  lineage:
    upstream: [landing.shopify.orders]
    downstream: [silver.commerce.orders]

  extensions:                       # free-form, namespaced — anything the core schema doesn't model yet
    nuskin.compliance.pii_fields: [customer_email, customer_phone]
    nuskin.cost_center: CMX-2201
```

**What changed from the prior draft, and why:**
- `trigger` is now its own object supporting `cron | event | continuous` — a continuous-mode pipeline (a Flink job) is *supervised for liveness* by the orchestrator, not scheduled as discrete task instances. This is the explicit mechanism for mixing job-based and streaming steps in one lineage graph.
- `contract_attributes` extends the contract to column granularity, but stops short of a full ontology: derived attributes either inline a simple same-table formula or **point at a Semantic metric** rather than re-declaring logic Semantic already owns — deliberately not a parallel knowledge model.
- `quality.engine` is explicit per pipeline, not global, so Bronze/Silver pipelines default to `deequ` and Gold/Semantic/Delivery-facing contract checks default to `great_expectations` without a special case in the schema itself.

---

## 4. Plugin architecture — the seam that keeps this from being a monolith

Four adapter interfaces, each a small Python `Protocol`/ABC. This is deliberately the *only* extension mechanism — a community adapter for Airbyte, Snowflake-as-catalog, or a second orchestrator later is "implement this interface," not "fork the core."

```python
class SourceConnector(Protocol):
    def extract(self, spec: SourceSpec) -> ExtractionResult: ...
    def report_metadata(self) -> dict:  # row count, checksum, max(incremental_key)
        ...  # feeds Tier-1 source-vs-Bronze reconciliation

class TransformEngine(Protocol):
    def compile(self, spec: TransformSpec) -> GeneratedArtifact: ...

class QualityEngine(Protocol):
    def validate(self, contract: Contract, target: TableRef) -> ValidationResult: ...

class CatalogWriter(Protocol):
    def register(self, schema: TableSchema, lineage: LineageEdge) -> None: ...
```

Shipped implementations: `MeltanoConnector`, `DebeziumConnector`, `DbtEngine`, `FlinkEngine`, `SparkEngine`, `CustomContainerEngine`, `DeequEngine`, `GreatExpectationsEngine`, `IcebergRestCatalogWriter`. `EstuaryConnector` and `DremioCatalogWriter` ship as clearly-labeled `contrib/commercial/` adapters — present in the repo, not in the default dependency set, so `pip install pipeline-framework` doesn't pull commercial SDKs.

---

## 5. The custom carve-out

Unchanged in principle from the prior draft: a `transform.engine: custom` step still declares `inputs`, `outputs`, `trigger`, and `quality.contract_ref` like any other step. The generator emits a container/task definition instead of a dbt/Flink manifest, but lineage, scheduling, and quality-gating stay uniform. This is enforced by the schema, not convention — the validator rejects a `custom` block missing those fields exactly as it would reject a malformed `dbt` block.

---

## 6. Repository structure (for the coding agent to scaffold)

```
pipeline-framework/
├── schema/
│   └── pipeline.v1.schema.json          # JSON Schema, versioned
├── compiler/
│   ├── validator.py
│   └── generators/
│       ├── airflow_dag_generator.py
│       ├── dbt_project_generator.py
│       ├── meltano_config_generator.py
│       └── flink_job_manifest.py
├── adapters/
│   ├── source/  { meltano.py, debezium.py }
│   ├── transform/ { dbt.py, flink.py, spark.py, custom.py }
│   ├── quality/ { deequ.py, great_expectations.py }
│   └── catalog/ { iceberg_rest.py }
├── contrib/commercial/
│   ├── estuary.py
│   └── dremio_catalog.py
├── cli/
│   └── pipeline.py                       # `pipeline validate|compile|lineage|docs`
├── lineage/
│   └── openlineage_emitter.py
├── examples/
│   ├── shopify_orders.pipeline.yaml
│   └── device_json_stream.pipeline.yaml
├── docs/
└── tests/
```

CLI surface: `pipeline validate <file>`, `pipeline compile <file> --target airflow`, `pipeline lineage --format openlineage`, `pipeline docs generate` (→ dbt-docs-style site plus a KPI provenance report, per §7).

---

## 7. Lineage and KPI documentation — generated, not hand-maintained

Because every pipeline declares `lineage.upstream`/`downstream`, and a Semantic metric's `contract_attributes.derived_from.semantic_ref` chains back through Gold to Bronze to source, `pipeline docs generate` can walk the full graph automatically: **Q3 Board Revenue KPI → Semantic definition → Gold fact table → Silver entity → Bronze table → source system**, without a hand-maintained wiki page. `dbt docs generate` already produces most of this for the dbt-owned hops; OpenLineage events fill in the rest (source connector runs, Flink jobs) in a compatible format, so nothing framework-specific is needed for the output format.

---

## 8. Build roadmap (milestones for an agent to work through incrementally)

1. **v0.1** — JSON Schema + validator + `pipeline validate` CLI. No generators yet. Get the contract right before generating anything against it.
2. **v0.2** — Airflow DAG generator + dbt project generator. This alone covers the entire batch-SQL happy path (source→Bronze→Silver→Gold via dbt) and is worth shipping on its own.
3. **v0.3** — Meltano and Debezium source adapters, including `report_metadata()` for Tier-1 reconciliation.
4. **v0.4** — Flink adapter + `continuous` trigger mode in the Airflow generator (supervision, not scheduling).
5. **v0.5** — Deequ and Great Expectations quality adapters, wired to `on_failure` handling.
6. **v0.6** — OpenLineage emission + `pipeline docs generate` (§7).
7. **v1.0** — Plugin SDK documentation stabilized; `contrib/commercial/` adapters (Estuary, Dremio) as reference implementations of the plugin interface, proving the seam works for something the core team didn't build.

Each milestone is independently useful — v0.2 alone is a legitimate tool for a team doing only batch SQL work, which is a good sanity check that the design isn't over-built relative to what an early adopter actually needs.

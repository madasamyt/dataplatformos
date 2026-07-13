# Enterprise Data Platform — Architecture Specification

*Plain-text extraction of the canonical architecture document, for agent/LLM context consumption. The styled HTML version (`data_platform_architecture.html`) is the human-facing artifact; this is a content-complete, zero-decoration companion to `docs/framework-spec.md` and `docs/decisions.md`.*

## Overview

Six-zone medallion-plus lakehouse architecture (Landing → Bronze → Silver → Gold → Semantic → Delivery), designed against one rule: each zone must do a transformation nothing else does, or it doesn't earn a place in the pipeline. Data products are a cross-cutting certification pattern, not a seventh layer. See `decisions.md` for the reasoning trail behind each structural choice below.

## The six zones

### Raw / Landing Layer
*Ingestion · Landing Zone*

The immutable record of truth — every byte as it arrived. This layer captures data exactly as emitted by source systems: no transformations, no business logic, no corrections. It functions as the system of record for auditability, re-processing, and lineage tracing. Think of it as your enterprise's "event log" — append-only, timestamped, and forever queryable from any downstream logic.

**Primary users:** Data Engineers, Platform Ops, Data Architects, Audit / Compliance

| Attribute | Rating | Detail |
|---|---|---|
| ✦ Data Quality | 1/5 | Unvalidated Contains duplicates, nulls, schema drift, and format inconsistencies. No quality checks applied — source-faithful by design. |
| ⊕ Grain |  | Event / Record level Full fidelity — every row, every field, every event as received. No aggregation, no deduplication. |
| 🔒 Security & Access |  | Highly restricted Engineering teams only. Typically no BI or analyst access. Service accounts for pipeline processes. |
| 🛡 Privacy & Guardrails |  | PII present / unmasked May contain raw PII, credentials, or sensitive fields from source. Encryption at rest mandatory. RBAC enforced at storage layer. |

### Bronze Layer
*Medallion L1 · Foundation*

The first structured checkpoint. Bronze receives raw data and applies structural typing and basic format standardisation — casting fields to a stable schema so downstream layers have a consistently-shaped foundation to build on. Bronze does not reject records: fields that don't fit cleanly are captured loosely (string/variant-typed) rather than dropped, preserving Bronze's "insurance policy" property — every record that arrived is still here, replayable, even before anyone has decided what "invalid" means. That decision, and the quarantine that follows from it, belongs to Silver. Bronze is the starting point for all traceable transformations and the boundary where data governance begins to take hold.

**Primary users:** Data Engineers, Data Stewards, QA / Data Ops

| Attribute | Rating | Detail |
|---|---|---|
| ✦ Data Quality | 2/5 | Structurally typed, not yet validated Type casting and technical deduplication keys applied. Nothing is rejected here — malformed or unexpected fields are retained loosely-typed so no record is lost before Silver decides what's valid. |
| ⊕ Grain |  | Record level (technical key) Retains source granularity. Surrogate keys and ingestion timestamps added. Some deduplication on natural keys. |
| 🔒 Security & Access |  | Engineering + Data Stewards Read access for validated engineering roles and data stewards. Analysts excluded. |
| 🛡 Privacy & Guardrails |  | PII tagging begins Sensitive columns flagged via data catalogue. Masking rules defined but not yet enforced for downstream. Lineage tracking starts here. |

### Silver Layer
*Medallion L2 · Conformation*

Where data is made enterprise-grade. Silver applies business rules, entity resolution, and cross-source joins to produce a clean, conformed, and enriched representation of real-world entities — customers, orders, products, events. This is the layer where a "customer" means the same thing regardless of which source system originated the record, and where "valid" is first defined and enforced: records failing referential integrity, business-rule, or null-handling checks are quarantined here — with a dead-letter path back to Bronze's replayable history if the rule itself turns out to be wrong. Silver is the canonical enterprise data model — authoritative, reusable, and the foundation for all analytical consumption patterns.

**Primary users:** Data Engineers, Analytics Engineers, Senior Analysts, Data Scientists

| Attribute | Rating | Detail |
|---|---|---|
| ✦ Data Quality | 3/5 | Business-rule validated Referential integrity enforced. Null imputation, value standardisation (e.g. country codes), and SCD patterns applied. Records that fail validation are quarantined with error codes for remediation, since Bronze intentionally never rejects. |
| ⊕ Grain |  | Entity / transaction level One row per entity instance (customer, order, product). Historical versions tracked via SCD Type 2 where required. |
| 🔒 Security & Access |  | Controlled — role-based Analytics engineers and senior analysts with domain approval. Column-level security on sensitive attributes. Row-level filtering by region/domain. |
| 🛡 Privacy & Guardrails |  | PII masked / tokenised Direct identifiers pseudonymised. GDPR/DPDP right-to-erasure hooks applied at entity level. Consent flags joined from consent service. |

### Gold Layer
*Medallion L3 · Business Aggregates*

Purpose-built for business consumption. Gold tables are pre-aggregated, domain-oriented datasets shaped to answer specific analytical questions — revenue by region, customer cohort performance, supply chain KPIs. Each Gold table has an explicit business owner, documented refresh SLA, and a named set of approved consumers. Gold is the primary source feeding dashboards, executive reporting, and the semantic layer. It trades full granularity for query performance and business relevance.

**Primary users:** BI Developers, Analysts, Analytics Engineers, Business Domain Owners

| Attribute | Rating | Detail |
|---|---|---|
| ✦ Data Quality | 4/5 | Business-certified Automated DQ tests on row counts, metric thresholds, and freshness. Business owner sign-off on definitions. Data contracts in place. |
| ⊕ Grain |  | Aggregate / domain grain Pre-grouped at business dimensions (day, region, product category). Not suitable for transaction-level forensics. |
| 🔒 Security & Access |  | Domain-scoped — wider access BI teams and approved analysts. Access governed by domain data contracts. RBAC enforced by domain taxonomy. |
| 🛡 Privacy & Guardrails |  | Aggregated — low PII risk Individual-level PII removed through aggregation. K-anonymity checks on small cohorts. Suppression rules for sub-threshold segments. |

### Semantic Layer
*Semantic Layer · Universal Language*

The single source of metric truth. The semantic layer translates physical data structures into business-language objects — dimensions, measures, KPIs, and hierarchies — that mean the same thing everywhere they are used. By centralising metric definitions (e.g. "Active Customer", "Net Revenue"), the semantic layer eliminates metric sprawl and ensures a dashboard built in Power BI and a query in Tableau always agree. It decouples business logic from tool-specific implementation and is the API between data and decision-making.

**Primary users:** BI Developers, Business Analysts, Product Managers, Finance / Strategy, Self-serve Consumers

| Attribute | Rating | Detail |
|---|---|---|
| ✦ Data Quality | 5/5 | Governed & certified Metric definitions version-controlled, peer-reviewed, and approved by data governance council. Single definition per KPI. |
| ⊕ Grain |  | Metric / dimension grain Exposed as logical objects (measures + dimensions). Physical grain abstracted — consumers query at any level the model permits. |
| 🔒 Security & Access |  | Broad — governed by metric permissions Widest intended access. Row-level security and metric-level entitlements enforced within the semantic engine. SSO-integrated. |
| 🛡 Privacy & Guardrails |  | Privacy by design No PII exposed at model level. Aggregation thresholds built into metric definitions. Sensitive dimensions hidden by default — role-unlocked only. |

### Delivery & Access Layer
*Delivery · Publishing & Access, Not a Content Tier*

The uniform front door every certified product passes through — regardless of which tier actually produced it. This is not where products originate; it's where they're published, catalogued, entitled, and translated into output ports. Certification itself happens in place: a Foundation product is certified Silver output, an Analytical or 360° product is certified Gold output, a Dashboard/KPI product is certified Semantic output. What distinguishes this layer structurally from everything below it is that its units are access surfaces, not persisted schemas — REST API, SQL endpoint, BI live-connect, embedded dashboard, file extract, streaming subscription. A report is a specific presentation binding of already-certified data for one audience — an "experience data product," not new content — and an API is simply one more output-port attachment on a product defined upstream. One product can carry several form factors at once. This is the same protocol-priority idea as the Access Gateway construct elsewhere in the platform (MCP → REST/GraphQL → SQL → Extraction), applied here to product delivery specifically.

**Primary users:** Business Users, Executives, Operations Teams, External Partners, ML / AI Applications

| Attribute | Rating | Detail |
|---|---|---|
| ✦ Data Quality | 5/5 | SLA-certified Contractual quality guarantees: freshness SLA, accuracy thresholds, schema versioning, and incident response. Monitored 24/7. |
| ⊕ Grain |  | Product-purpose grain Tailored to the product's use case — could be atomic (ML feature store) or highly aggregated (exec dashboard). Documented in data catalogue. |
| 🔒 Security & Access |  | Consumer-facing — marketplace governed Published via data marketplace with subscription model. Access request, approval workflow, and usage logging enforced. |
| 🛡 Privacy & Guardrails |  | Highest privacy assurance DPIA completed per product. Retention policies documented. Statutory compliance (GDPR, DPDP) embedded in product contract. Consent-aware. |
## Stage-wise processing — inter-zone vs intra-zone

**Inter-zone transitions — the critical path**

| Transition | Core operations (always happen) | Conditional / source-dependent |
|---|---|---|
| Landing → Bronze | Structural typing, schema application, technical dedup on an idempotency key — no rejection | Semi-structured: nested payload preserved (VARIANT), not flattened. Unstructured: a reference/pointer row (file path, device ID, timestamp) — bytes stay in Landing. Some ELT tools (Meltano, Fivetran, Airbyte) fold Landing into their own internal staging — the tool pulls from source and commits typed data directly, with no separate object-store hop the platform manages. The zone still exists conceptually (raw, replayable, pre-typing) even when it's the tool's internal state rather than a bucket you own; if the tool doesn't expose that internal state for replay, treat the source system itself as the de facto Landing zone of record. |
| Bronze → Silver | Business-rule validation + quarantine, entity resolution / cross-source matching, canonicalization of taxonomies, referential integrity, SCD2 history capture for dimensions | Semi-structured/unstructured: ML-based extraction (object detection, transcription, indicator parsing) turning raw payload into conformed rows, with a confidence score standing in for the pass/fail quarantine trigger |
| Silver → Gold | Business logic, cross-domain joins, denormalization, fact/dimension modeling, aggregation to business grain, derived columns | Grain choice is per-target-table — this hop is most responsible for row-count divergence in either direction (see appendix) |
| Gold → Semantic Optional hop | Metric abstraction — decoupling a measure's formula from its physical grain, dimension/measure registration, glossary binding | Skipped entirely for Foundation and 360°/Analytical products that carry no reusable metric — they promote straight to Delivery |
| Semantic → Delivery Optional hop | Certification (SLA, contract, owner, version), output-port translation, catalog registration, entitlement binding, goal/threshold attachment for KPI-tier products | Also optional as a physical hop — products sourced directly from Silver or Gold certify in place; Delivery packages regardless of origin tier |

Not every product traverses all five hops. A Foundation product goes Silver → Delivery directly. A 360°/Analytical product goes Gold → Delivery. Only a product carrying a governed, reusable metric goes the full distance through Semantic — this is the same rule as the "skipping a layer" principle below, expressed as a path rather than a single exception.

**Intra-zone processing — same zone, no boundary crossed**

| Zone | What happens intra-zone |
|---|---|
| Landing | None by definition — pure capture |
| Bronze | Incremental batch append, file/partition compaction, schema-evolution handling as new source fields appear |
| Silver | Incremental SCD2 updates as changes trickle in continuously; enrichment passes referencing other already-conformed Silver entities |
| Gold | Gold-on-Gold composition — an aggregate built on another aggregate (the Regional Sales Performance Product case; the lineage-risk caveat in the appendix applies here) |
| Semantic | Metric-on-metric composition — e.g. aov = net_revenue / order_count , both already-registered metrics |
| Delivery | Product-on-product bundling — packaging several already-certified products into one subscription/bundle |
## Commerce domain walkthrough — where layer boundaries actually bite

### Source-aligned vs Domain-aligned
*Bronze → Silver Single domain (Commerce) — reconciled across systems*

- **Bronze — source-aligned** — `shopify_orders_raw · netsuite_orders_raw · salesforce_opportunities_raw`: Three tables, three shapes. Shopify's financial_status , NetSuite's tranid , Salesforce's Opportunity_Stage__c — each keeps the source system's own field names, status codes, and ID space. No one has decided yet which fields mean the same thing.
- **Silver — domain-aligned** — `orders`: One row per order, one order_status taxonomy (placed / fulfilled / returned), one resolved customer_id — regardless of which channel or system it originated in.

Why it can't collapse: resolving "which Shopify customer equals which NetSuite customer" requires business rules that don't exist at ingestion time. Doing that resolution inside Bronze would mean re-deriving it on every replay, and if the rule is ever wrong, the immutable source-faithful record is gone with it.

### Simply aggregated vs Data product with derived metrics
*Gold → Data Product (skips Semantic — ships a fixed aggregate, not a flexible metric) Single domain (Commerce/Sales)*

- **Gold — simply aggregated** — `orders_daily_agg`: Total orders, total revenue, total units — grouped by day, region, category. Arithmetic on Silver. Answers "what happened."
- **Data Product — derived-metric bundle** — `Regional Sales Performance Product`: Same underlying numbers, plus computed ratios (AOV, conversion rate, repeat-purchase rate), documentation, a freshness SLA, and a named owner for Merchandising to consume without writing SQL. Answers "what should I do about it."

Why it can't collapse: most Gold tables are intermediate building blocks feeding several downstream tables — they don't need an SLA, an owner, or a support contract. Forcing every Gold table to carry that overhead is waste; reserving it for the tables a business stakeholder actually depends on directly is the entire point of a "product" designation. Caveat: this product is built on top of another Gold table ( orders_daily_agg ), not a certified one — if that upstream table's logic changes, the product inherits the change without triggering re-certification unless lineage-aware change notification is in place. Detail in the appendix.

### Simple dataset vs Productized data
*Gold → Data Product (skips Semantic — this is a discovery/ownership promotion, not a grain problem) Cross-domain (Commerce + CRM + Marketing + Loyalty)*

- **Gold — simple dataset** — `customer_order_summary`: Used internally by three other pipelines. No external documentation, no version pinning, no named owner — it changes whenever the team that built it decides to change it.
- **Data Product — productized** — `Customer 360 Data Product (v2.1)`: The same underlying content, but catalogued with a business-glossary entry, subscribed to via the data marketplace, owned by a named VP, versioned so consumers aren't broken by silent schema drift — consumed by external partner co-marketing teams and the recommendation model.

Why it can't collapse: the distinction isn't the data — it's whether the dataset has external or cross-team dependents who need lifecycle guarantees. Promoting a dataset to "product" status is a governance decision, not a transformation step, which is exactly why it has to be an explicit layer someone opts into rather than a property Gold grants automatically.

### Domain grain vs Metric grain
*Gold → Semantic Layer Single domain (Commerce) — grain, not domain count, is the variable here*

- **Gold — domain grain** — `sales_fact`: One row per (order_line, day, store, product) — a physical fact table, shaped like the business entity it represents. Fixed grain, fixed structure.
- **Semantic — metric grain** — `net_revenue measure`: Defined once as SUM(sales_fact.net_amount) , but callable at any grain a consumer asks for — day, week, region, category, channel — without a new physical table for each combination.

Why it can't collapse: if metric grain only existed in Gold, every new slice a stakeholder wants (revenue by week-by-channel, by month-by-region...) would need its own physical table — combinatorial explosion. The semantic layer decouples the measure's definition from its materialization grain , letting one governed formula serve infinite grains at query time.

### Metric vs Certified KPI
*Semantic Layer → Data Product Single-domain source (Commerce), cross-domain governance (Finance certifies it)*

- **Semantic — metric** — `net_revenue`: Defined, governed, technically correct, available for anyone with entitlement to query at any grain. One of several legitimate ways revenue could be computed (gross vs net, constant vs current currency).
- **Data Product — certified KPI** — `Q3 Board Revenue KPI`: The same metric, but locked to one specific reporting definition (excludes cancelled-but-unshipped orders, constant currency), signed off by Finance, and versioned so historical board decks never silently change when the underlying formula is later revised.

Why it can't collapse: a metric is a technical capability — AOV can legitimately be computed five ways. A certified KPI is a governance decision about which single version is "the" official number for a high-stakes audience. Not every metric needs board-level sign-off weight; reserving certification for the ones that do keeps the semantic catalogue usable instead of bureaucratic.

### Shared view vs Consumer-specific view
*Semantic Layer → Data Product Cross-domain (Finance + Commerce + Marketing + Supply Chain)*

- **Semantic — shared** — `revenue_by_region`: One governed definition. Finance, Merchandising, and the executive dashboard all query the same model and see the same number — that's the point of "write once, reuse everywhere."
- **Data Product — consumer-specific** — `CFO Weekly Flash`: A bespoke, pre-filtered, pre-formatted view combining revenue_by_region with inventory days-on-hand and marketing spend, arranged for one recipient's Monday review. Single named consumer, no obligation to generalize.

Why it can't collapse: shared views have to stay generic or duplicate logic starts forking every time one stakeholder wants a tweak — the exact metric sprawl the semantic layer exists to prevent. Consumer-specific views intentionally trade reusability for fit; mixing that responsibility into the shared model is how "just one more column for the CFO" turns into five divergent copies of net_revenue.

## Concepts, mapped — legacy BI terms to modern zones

| Concept | Maps to | Why here, not elsewhere |
|---|---|---|
| Canonicalized / harmonized data | Silver | This is Silver's job by definition — "canonicalized" and Kimball's "conformed" describe the same activity: one entity, one meaning, regardless of source. |
| Data marts | Gold | Older name for the same thing — domain-specific, business-ready, star-schema datasets. Gold is the mart layer. |
| OLAP cubes | Semantic | Legacy physical implementation of what the Semantic Layer now does virtually — pre-materialized slice-and-dice vs. one governed measure computed at any grain on demand. |
| Facts & dimensions | Gold | Structural components inside Gold's star schema. Conformed dimensions specifically depend on Silver having already resolved that entity canonically — the two layers are linked, not redundant. |
| Customer 360 / Product 360 | Gold → Data Product | Wider than Silver's identity resolution — a 360 view joins behavioral signals across domains (orders, support, marketing), which only Gold-level joins can do. Frequently graduates to Data Product once external teams depend on it. |
| MDM (Master Data Management) | Cross-cutting → feeds Silver | An external, governed system producing golden records via match/merge/survivorship. It's an authority Silver's entity resolution defers to — not a stage in the pipeline itself. |
| RDM (Reference Data Management) | Cross-cutting → Silver, Gold, Semantic | Shared lookup/code tables (country, currency, category taxonomies) referenced at multiple points — value standardisation in Silver, grouping in Gold, labeling in Semantic. One source, several consumers. |
| Measure → Metric → KPI | Gold → Semantic → Delivery | A measure is a number bound to one table's fixed grain (Gold). A metric is that same computation decoupled into a governed, reusable definition callable at any grain (Semantic). A KPI is a metric frozen to one specific formula and signed off for one high-stakes audience (Delivery) — sourced from the metric catalogue, never recomputed fresh. |
| Goal, RAG status, trend, QoQ/YTD, P90/P95 | Semantic / Delivery | A goal/target is a separate object from the metric it's measured against — it varies per consumer and lives in its own registry. RAG and trend are presentation-time comparisons of an existing metric, not new metrics. QoQ/YTD are the same aggregation over a different window — decoration. Percentiles are a genuinely different aggregation and should be their own registered metric, not a decoration. Full breakdown in the appendix. |
## Data products are cross-cutting, not a seventh layer

"Data Product" is a certification and publishing pattern that can attach to Silver, Gold, or Semantic output — not exclusively fed by Gold. The pipeline node is the registry these graduate into, not the only source.

- **Foundation / source-aligned product** — A certified, published domain feed — e.g. an orders extract for a partner. No Gold aggregation needed; the conformed entity is the whole product.
- **Aggregate / analytical product** — A packaged rollup with derived ratios and an SLA — Regional Sales Performance Product is the example above.
- **360° / consumer-aligned product** — Customer 360, Product 360 — wide, denormalized profiles joining several Gold facts into one entity-grain view.
- **AI / ML product** — Point-in-time-correct, versioned feature sets for model training or serving — its own contract (latency, freshness) distinct from BI consumption.
- **Dashboard / certified KPI product** — A governed, owned consumption surface built on certified metric definitions — CFO Weekly Flash is the example above.
## Domain association — source-level vs consumption-level

Every data product has a domain tag. The mistake is assuming it's the domain the source data came from — usually it isn't.

- **Defined by system of record** — Commerce (Shopify/NetSuite), CRM (Salesforce), Support (Zendesk), Marketing (campaign platforms), Loyalty. These map cleanly onto Bronze and Silver, because that's literally how source ownership is drawn — one team, one system, one domain.
- **Defined by business capability** — Merchandising, Customer Experience, Finance/FP&A, Marketing Ops, Executive. These are what data products get organized around — and they frequently span several source-level domains at once.

A data product's domain tag should reflect who owns and consumes it, not where its inputs originated — most of the products worth productizing exist precisely because they synthesize across source domains.

| Product | Source domains touched | Owning / consumption domain | Single or cross-domain |
|---|---|---|---|
| Order Fulfillment Ops Product | Commerce only | Commerce / Fulfillment Ops | Single |
| Regional Sales Performance Product | Commerce only (many regions, one domain) | Merchandising / Sales | Single — more regions isn't more domains |
| Customer 360 | Commerce + CRM + Marketing + Loyalty | Customer Experience | Cross |
| CFO Weekly Flash | Finance + Commerce + Marketing + Supply Chain | Executive / Finance | Cross — executive products almost always are |
| Distributor Compensation & Genealogy Product | Commerce/Orders + Comp Plan + Genealogy (org structure) | Compensation / Field Ops | Cross — PV rolls up through a tree that itself spans domains |

## Advanced patterns — streaming, multimodal, MDM

### Is a Kafka/Kinesis topic Bronze?
No — a raw producer topic is Landing : immutable, source-faithful, replayable, same as a raw file. Bronze is a second, downstream topic or table, schema-registry-validated and typed by a stream job reading the raw topic. Many teams also sink the raw topic to object storage as Landing's durable form once the topic's own retention window expires — same layer, two storage tiers.

### Fast signal vs. deep reprocessing
The fast output can be a real product — but only carrying an explicit provisional flag and completeness SLA (e.g. "corrected within 4h"). It may feed operational/tactical products, but per the metric-vs-KPI rule above, it never becomes a certified KPI until the deep pipeline reconciles it. On reconciliation, either the value is overwritten in place or a separate certified product is published with lineage back to the provisional one — never two identical-looking numbers with different trust levels.

### Worked scenario — order fact + customer dimension, incremental updates

| Day | Event | Bronze | Silver | Gold |
|---|---|---|---|---|
| 1 | order_created | Typed, appended | orders row created; order_status=placed ; customer_id resolved via entity dedup | — |
| 2 | order_status_changed → shipped | Typed, appended | orders.order_status updated in place (Type-1); optionally also appended to order_status_history if SLA/dwell-time tracking has business value | sales_fact reflects current status |
| 5 | customer_updated — address change | Typed, appended | SCD Type 2 on customer : new row inserted ( valid_from=5 ), prior row closed ( valid_to=5 ); customer_id stable, versioned surrogate key changes | sales_fact joins the customer row valid on day 1 — the address the order actually shipped to, not today's |

Dedup happens twice, for different reasons: Bronze does technical dedup on a delivery key ( event_id ) to absorb at-least-once redelivery; Silver does entity dedup — collapsing the same real-world customer appearing under two source IDs. SCD Type 2 history is captured and stored in Silver; Gold decides per-question whether to join point-in-time (SCD2) or expose current-state (Type-1 flattened).

⚠ Row counts diverge from the source at every hop, in both directions — dedup shrinks them, SCD2 history and grain changes (one order payload exploding into several line-item rows) grow them. Row-count parity between a layer and its source is not a valid completeness check; verify at the entity-key level instead. Worked breakdown in the appendix.

### MDM / PIM / 360 — bidirectional, not purely upstream
Correcting the earlier "cross-cutting → feeds Silver" framing: mature MDM is a loop. Silver-conformed entities feed candidate matches into the MDM stewardship tool; a steward's golden-record decision flows back into Silver as the authoritative reference. Customer 360, once built, commonly becomes a source for that same stewardship review. Derived attributes — a churn score, a computed segment — are frequently reverse-ETL'd back into the operational CRM so a rep sees them there. PIM behaves the same way: raw attributes flow in, AI-generated descriptions or computed tags sometimes flow back out to the operational catalog. Reverse ETL is a legitimate delivery pattern, not an exception to route around.

### AI context data (SharePoint / Confluence → vectors, ontology)
Split deliberately. Landing/Bronze are shared with the rest of the lakehouse — documents land untouched, then get parsed/chunked with provenance metadata (doc_id, source, ingestion_ts), under the same governance, PII handling, and lineage as everything else. Embedding and vectorization are owned by the AI/Knowledge Core team , not the medallion ladder — consistent with Knowledge Core (ontology + KG + RAG) sitting in the Agentic Core dimension rather than the data substrate, since similarity-search consumption doesn't progress through Gold→Semantic aggregation the way BI does. The one non-negotiable: the vector store must write its provenance back to the shared catalog, or you get an ungoverned shadow copy of sensitive documents with no retention or access control tied back to the source.
## Auxiliary capabilities — not primary layers

- **⚡ Serving Acceleration** *(Physical technique, attached to Gold / Semantic)* — Reflections, materialized aggregates, extracts, caches — physical speed-ups underneath an already-governed Gold/Semantic definition. Invisible to the consumer, never a second source of truth: if a cache and the definition it accelerates ever disagree, the cache is wrong by construction.
- **🧪 ML Sandbox** *(Permission zone, attached to Silver / Gold)* — Read-only exploratory access into Silver/Gold for data scientists; writes go to isolated scratch space that never re-enters the lineage-tracked stack. Production feature stores are different — those are a real AI Data Product (see above), with their own contract and consumers.
- **🗄 Archival** *(Retention policy, attached to Landing / Bronze)* — Cold-tiering of data past its active-use window — mainly the full-fidelity Landing/Bronze history, sometimes aged Silver/Gold partitions. A lifecycle policy, not a value-adding transformation — so it doesn't get promoted to a pipeline stage, even though it's operationally essential.

## At-a-glance reference

| Layer | Primary Purpose | Typical Users | Quality | Grain | Access Level | PII / Privacy |
|---|---|---|---|---|---|---|
| 🪨 Raw / Landing Ingestion | Immutable source archive; audit & replay baseline | Data Engineers, Platform Ops, Audit |  | Event / record — full fidelity | Engineering only | PII present, unmasked — encryption at rest mandatory |
| 🔶 Bronze L1 | Structural typing and standardisation — no rejection, nothing lost | Data Engineers, Data Stewards |  | Record level with surrogate keys | Engineering + Stewards | PII tagged in catalogue; masking rules defined |
| 🔷 Silver L2 | Conformed entities, business rules, cross-source joins, quarantine | Analytics Engineers, Senior Analysts, Data Scientists |  | Entity / transaction with SCD history | Domain RBAC — role-based columns & rows | PII pseudonymised; consent flags applied; erasure hooks in place |
| ⭐ Gold L3 | Business-domain aggregates; certified reporting datasets | BI Developers, Analysts, Domain Owners |  | Aggregate — day, region, category | Domain-scoped; data contracts govern access | Aggregation removes individual PII; k-anonymity enforced on small cohorts |
| 🔗 Semantic Semantic | Universal metric definitions; decouples logic from BI tools | All BI consumers, Analysts, PMs, Finance, Self-serve |  | Logical (metric + dimension) — any query grain | Broad; metric entitlements + SSO; row-level security in engine | No PII in model; aggregation thresholds built-in; sensitive dims gated by role |
| 📦 Delivery & Access Publishing | SLA-backed, published, versioned datasets for enterprise consumption | Business, Executives, Ops, ML/AI, External Partners |  | Product-purpose (varies by product) | Marketplace subscription; approval workflow; usage audited | DPIA completed; GDPR/DPDP compliant; consent-aware; retention documented |
## Naming conventions

Deliberately engine-agnostic — a generic three-level catalog → schema → object hierarchy that maps onto Dremio, Unity Catalog, Snowflake, or BigQuery equally, so the convention survives a query-engine change even if this document was written with Dremio in front of it today.

| Zone | Storage path (S3/object store) | Catalog · schema | Object naming | Column naming | Notes |
|---|---|---|---|---|---|
| 🪨 Landing | s3://{org}-landing/{source_system}/{entity}/{yyyy}/{mm}/{dd}/ | Usually unregistered — files, not tables. If catalogued: landing.{source_system}.{entity} | Preserve the file name as delivered, or {source_system}_{entity}_{batch_id}_{ts}.{ext} | Untouched — whatever the source calls it | Never rename fields here; that's the entire point of the zone |
| 🔶 Bronze | s3://{org}-lakehouse/bronze/{source_system}/{entity}/ | bronze.{source_system}.{entity} — schema keyed by source , since nothing's conformed yet | {source_system}__{entity} (double underscore avoids collision when two sources name an entity the same) shopify__orders , netsuite__orders | snake_case, source field names normalised in casing only. Technical/system columns get a leading underscore: _ingested_at , _source_system , _batch_id | Leading-underscore convention for system columns is engine-agnostic and instantly reads as "not business data" to anyone |
| 🔷 Silver | s3://{org}-lakehouse/silver/{domain}/{entity}/ | silver.{domain}.{entity} — schema keyed by conformed domain , not source, since Silver is source-agnostic | Plain canonical entity name, no source prefix: orders , customers , products | snake_case business names. SCD2 technical columns get a fixed suffix set: _valid_from , _valid_to , _is_current . Surrogate key: {entity}_sk . Natural/business key stays {entity}_id | Keeping _id (stable) distinct from _sk (versioned) is the single most load-bearing convention for correct SCD2 joins |
| ⭐ Gold | s3://{org}-lakehouse/gold/{domain}/{subject_area}/ | gold.{domain}.{table} | Kimball-style role prefix, recognizable regardless of engine: fct_{subject} , dim_{entity} , agg_{subject}_{grain} fct_sales , dim_customer , agg_orders_daily | Business snake_case. Measures carry a unit/type suffix: _amount , _count , _pct . Foreign keys reference a dimension's surrogate key: customer_sk | Prefix-by-role makes grain and table purpose readable from the name alone in any SQL client or catalog browser |
| 🔗 Semantic | Not physically stored — a metric/model repository, e.g. semantic/{domain}/{metric}.yml | semantic.{domain}.{metric_name} as a logical namespace, however the chosen semantic engine models it | No engineering prefix — this is the one zone consumers see directly, so names should read as plain business language: net_revenue , aov , order_value_p90 | Same as object naming — metrics and dimensions are named for the dropdown a business user sees, not for a DBA | Resist the urge to decorate these with technical prefixes; that defeats the layer's purpose |
| 📦 Delivery | No storage path of its own — a catalog/marketplace registry entry per product | product.{owning_domain}.{product_name} for discoverability in the catalog | Human-friendly product name for the listing ("Customer 360", "Regional Sales Performance Product"), separate from any underlying table name. Prefer stable name + version as metadata over baking version into the name; use {product_name}_v{n} only if the platform forces physical versioning | Pass through whatever Semantic or Gold already named the fields — Delivery should never introduce a third naming variant for the same column | A product's name is a catalog listing, not a schema — don't let it acquire engineering conventions |

Bucket structure: default to one lakehouse bucket, prefixed by zone ( s3://{org}-lakehouse/{zone}/... ) — simpler IAM than bucket-per-zone for most orgs. Bucket-per-zone is worth the extra IAM overhead only when a zone needs materially different lifecycle/replication/compliance settings than its neighbours (e.g. Landing holding unmasked PII needs stricter isolation than Gold).

**Generic hierarchy → engine mapping**

| Generic | Dremio | Databricks (Unity Catalog) | Snowflake | BigQuery |
|---|---|---|---|---|
| Catalog | Space | Catalog | Database | Project |
| Schema | Folder | Schema | Schema | Dataset |
| Object | Dataset (PDS/VDS) | Table / View | Table / View | Table / View |
## Platform principles

- **Write once, reuse everywhere** — Business logic lives in exactly one layer. Metric definitions in the semantic layer are the source — every tool and team reads from the same definition, never forks it.
- **Contracts over conventions** — Each layer boundary is a data contract: explicit schema, quality SLA, freshness guarantee, and named owner. Consumers know what to expect and producers know what they must deliver.
- **Security at every boundary** — Access narrows upward — raw data is most restricted, data products have the broadest reach but the tightest governance. No layer inherits access from the layer below it.
- **Privacy by default** — PII is masked by default, not by request. The further up the stack, the less individual data is visible — not because it was deleted, but because the architecture never exposes it.
- **Full lineage, always** — Every column in every Gold table or data product can be traced back to its raw source record. Lineage is infrastructure, not documentation — automated, queryable, and always current.
- **Data as a product** — Data isn't a pipeline output — it's a product with users, SLAs, documentation, and versioning. Certified data products carry the organisation's trust mark and a named accountable owner.
- **Skipping a layer is fine — reusing its function isn't** — Gold can promote straight to Delivery when there's no grain-flexibility problem to solve (a 360, a foundation extract); it can't skip Semantic when the product carries a governed metric — that's a silent fork of the definition. Mechanically, two different things get called "skipping": a governance skip (no access-control chokepoint enforced upstream — nothing was bypassed) needs nothing extra, while an access-uniformity skip , where RLS/entitlements are enforced centrally at the query engine, needs a thin 1:1 passthrough view in Semantic — same content, no new metric, enforcement chokepoint stays intact. Detail in the appendix.
- **A BI tool's semantic model is a cache, never the source** — If a metric is authored independently in Power BI's DAX, Tableau's calculated fields, and a notebook, the metric-sprawl problem the semantic layer exists to prevent has just re-formed one layer up. Tool-side semantic models are legitimate only as a local cache of an already-governed lakehouse definition — never as where the definition is authored.

## Appendix — reference detail

### A. KPI decoration reference

| Concept | What it is | Zone | Computed fresh or stored? |
|---|---|---|---|
| Goal / target | A threshold set per (KPI, consumer/org-unit, period) — Sales' AOV target ≠ Finance's AOV target for the same metric | Goal Registry (metadata, cross-cutting) | Stored — it's configuration, not a calculation |
| RAG status | Current metric value compared to its goal-registry threshold | Delivery (presentation) | Computed fresh, cheap |
| Trend (up/down) | Current value vs. the same metric at a prior period | Semantic / Delivery | Computed fresh |
| QoQ / YoY / YTD | Same aggregation (SUM/AVG), evaluated over a different window and diffed | Semantic | Computed fresh — native time-comparison capability of the semantic engine |
| P90 / P95 | A genuinely different aggregation function requiring the full distribution, not a window re-evaluation | Semantic (defined) — Gold (if materialized) | Compute fresh for low-cardinality/low-volume; materialize (or use t-digest/HLL approximation) when exact percentiles over high-volume data can't meet dashboard latency |

### B. Why row counts diverge from source, hop by hop

- Landing → Bronze (shrink): Landing captures every delivery including network-retry duplicates. Bronze's technical dedup on a stable idempotency key ( event_id ) collapses them — if the source provides one. If not, duplication survives into Bronze and becomes Silver's problem via business-key dedup instead.
- Source → Silver (shrink): entity resolution merges the same customer appearing under two source-system IDs — Silver can end up with fewer rows than the two sources combined.
- Source → Silver (grow): SCD Type 2 stores history the source discarded. If NetSuite overwrites a customer's address in place (one current row), Silver ends up with two rows for that one customer once history is tracked.
- Source → Silver (grow): grain changes — a source API nesting three line items inside one order payload becomes three rows in a conformed order_lines entity, where the source presented "one order."
- Silver → Gold (shrink or grow): aggregation collapses many rows into few ( orders_daily_agg ), but a finer target grain (exploding to line-item level for margin analysis) can also produce more rows than Silver. Direction depends entirely on the target grain, not on a fixed rule.

Conclusion: row-count parity between a layer and its source is not a valid completeness signal in either direction. Check completeness at the entity-key level (every source order_id traceable somewhere downstream) instead of comparing raw row counts.

### C. KPI Catalog & Goal Registry

Two related but distinct metadata objects, both cross-cutting rather than owned by one layer:

- KPI Catalog — name, formula reference (points to the Semantic definition, never re-implements it), owner, certification status, certifying audience, version history. Write points: Semantic registers the formula; Delivery registers the certification record when a metric is locked to KPI status.
- Goal Registry — (KPI, consumer/org-unit, period) → target value, plus RAG thresholds for that specific consumer. Deliberately separate from the KPI Catalog so the same certified metric can carry different targets for different audiences without touching the metric's definition.

### D. Lineage-aware re-certification — the Regional Sales Performance Product case

The product is certified at Delivery, but its content is built on orders_daily_agg — an ordinary, uncertified Gold table with several other downstream consumers. If that table's logic changes (a new order-status exclusion, a currency-conversion fix), the certified product inherits the change silently, because its certification was reviewed against its own output, not against the stability of everything it transitively depends on.

This isn't a reason to forbid intra-Gold composition — disallowing Gold-on-Gold modeling would break ordinary star-schema practice. The fix is process, not structure: any change to a table with certified products downstream — even transitively — should trigger an automatic re-certification flag on those products, not just direct-consumer review. Without this, "certified" quietly rests on an uncertified, unreviewed foundation, and the certification stamp stops meaning what consumers assume it means.

### E. Worked row-count scenario — 100 rows, +2/−1/~3 in 24h

Source starts at 100 rows; next day gains 2 inserts, loses 1 delete, and 3 rows are updated. The resulting counts depend on two modeling choices, not one fixed answer.

Choice A — Bronze as an append-only event log (recommended; matches "Bronze never rejects"). Every insert/update/delete arrives as its own event.

| Layer | Day 1 | Day 2 events | Running total | Represents |
|---|---|---|---|---|
| Bronze (event log) | 100 | +2 insert, +3 update, +1 delete events | 106 | Cumulative events — never shrinks, never equals source row count by design |
| Silver, history-inclusive (SCD2) | 100 | +2 new, +3 new versions (old versions closed, not deleted) | 105 | 3 old versions get is_current=false — a close-out delete needs no new physical row |
| Silver, is_current=true view | 100 | +2 new, −1 deleted, updates don't change count | 101 | This is the number that should match "source row count as of now" |

For orders + order_status_history (a table that doesn't exist in the source at all): Bronze reaches 106 the same way. Silver orders (current status as a plain attribute) reaches 101 if deletes are physical — but a source-side hard delete on an order should usually be reinterpreted as a status transition (cancelled/voided) rather than a row removal, since Gold/reporting need the order's history intact even when the source doesn't care. Doing this keeps Silver orders at 102, not 101. order_status_history is append-only and never mirrors source cardinality at all — it lands around 105–106 depending on whether the deletion is itself modeled as a transition.

Choice B — Bronze as periodic full-snapshot partitions (when the source only offers daily full extracts, not a change stream). Each day is its own partition: day-1 partition has 100 rows, day-2 partition has 101 (100 + 2 − 1, updates applied in place within the extract). Latest-partition count = 101; cumulative-across-partitions = 201. The real cost of this choice: snapshot-diff SCD2 can only see "changed sometime since yesterday" — if an order went placed→processing→shipped entirely between two extracts, the diff only ever sees the final "shipped" state and silently loses "processing." CDC-based Bronze (Choice A) doesn't have this blind spot (see item H).

### F. Ongoing validation against source — three tiers, not one

Tier 1 — structural completeness (cheap, continuous, deterministic). Reconcile at the entity-key level, not raw row counts (per the row-count-parity principle above) — every source order_id traceable somewhere downstream. Standard tooling: dbt tests, Great Expectations, Monte Carlo/Soda — no AI required.

Tier 2 — business-rule and referential validation (Silver/Gold). Null checks, uniqueness, accepted-value checks, referential integrity. Also deterministic and scheduled.

Tier 3 — semantic reconciliation and root-cause triage. "Recompute sales volume for the last 7 days by product and check" splits into two parts: the diff itself (source-side aggregate vs. Gold-side aggregate) is a deterministic scheduled query needing no AI. What an AI agent with MCP connections genuinely adds is what happens after a mismatch is flagged — querying the source system through one connector and the lakehouse through another, correlating the discrepancy against recent schema changes or a known SCD2 boundary condition, and producing a diagnosis ("the gap is exactly the 3 orders still in processing that Gold's filter excludes — expected lag, not loss") rather than a bare pass/fail. That's interactive root-cause investigation across systems, a genuinely different capability from a static test suite.

Governance line: read-only MCP access by default; auto-remediation needs an explicit human approval gate. This is also a natural implementation of the lineage-aware re-certification idea in item D — the agent flags for re-certification when an upstream dependency changes, rather than a human having to notice.

### G. Job, dbt model, view, or materialized view?

| Transition | Implementation | Why |
|---|---|---|
| Landing → Bronze | Job (Fivetran/Airbyte/Debezium/Glue/Lambda, orchestrated) | Raw extraction and CDC consumption aren't SQL-transform work — dbt assumes data has already landed somewhere queryable |
| Bronze → Silver | dbt model — incremental for Type-1, dbt snapshot for SCD2 — materialized as a table | dbt snapshots are the canonical SCD2 mechanism; Silver needs to be queryable at speed by many consumers, so not a view |
| Silver → Gold | dbt model, materialized as a table | Star-schema fact/dimension tables are meant to be pre-computed, not recomputed per query |
| Gold → Semantic | Not a dbt model — a metric definition (dbt Semantic Layer/MetricFlow, LookML, AtScale, Dremio VDS) evaluated at query time | The whole reason Semantic exists: logic decoupled from physical materialization |
| Semantic → Delivery | View (thin passthrough, VDS-equivalent or API definition) | Delivery owns no storage by design; it packages, it doesn't compute |

Materialized views aren't a new zone — they're one implementation of Serving Acceleration (see auxiliary capabilities). Reach for one when a query is too expensive to recompute per request but doesn't need dbt's full incremental/testing/versioning ceremony, and refresh frequency must run faster than the batch job's cadence. If it needs history, testing, or lineage tracking, it should be a dbt model instead — a materialized view is a performance technique, not a governance unit.

### H. ODS/CDC as a source — Bronze-as-log vs. Bronze-as-mirror, and SCD2 under CDC

Some sources replicate to an ODS for backup/read-replica purposes, and that ODS becomes our extraction point via CDC. Two Bronze patterns follow from this, and they behave very differently.

Bronze-as-log (recommended default). CDC naturally produces this — Debezium-style connectors emit one event per row-level change, with operation type (c/u/d), before/after images, and source commit metadata (LSN, commit timestamp). This is the cleanest realization of the append-only Bronze principle already established.

Bronze-as-mirror (exact row/column parity with the source). The CDC stream is applied as continuous upserts/deletes into a single Bronze table that always reflects current source state. Operationally simpler, but it destroys history the moment a row is updated or deleted — table-format time travel (Iceberg/Delta) is only a partial substitute. If Bronze-as-mirror is chosen, accurate SCD2 or order-status-history cannot be built from Bronze alone — the raw CDC stream must be retained independently (at Landing) to feed Silver's history logic. This is the strongest argument for defaulting to Bronze-as-log: it keeps history-building possible downstream without a side-channel back to the raw feed.

Where composition into a current-state image happens: if Bronze-as-log, that composition is Silver's job — a dbt snapshot (SCD2 entities) or a standard merge (Type-1 entities). If Bronze-as-mirror, the composition already happened in Bronze, and Silver's job shrinks to canonicalization only — but then Silver has nowhere to get history from, which is the trap above.

SCD2/history mechanics under CDC: use the CDC event's source commit timestamp , not ingestion timestamp, as _valid_from / _valid_to — this avoids ingestion-lag skew. For order_status_history : since Debezium gives a before/after image on every update, the history table is built by appending a row whenever before.status != after.status , timestamped at source-commit time. This is strictly more accurate than batch-diff history-building (item E, Choice B) — CDC captures every intermediate transition, where a daily snapshot diff can silently miss a status that changed and moved on again within one extract window. Bronze-as-mirror should still add standard technical columns ( _source_commit_ts , _cdc_operation , _lsn , _ingested_at ) — "same business columns plus system metadata," not byte-identical to the source in either pattern.

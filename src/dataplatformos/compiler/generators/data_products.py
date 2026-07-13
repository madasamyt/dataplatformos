"""DataProduct delivery artifacts + lineage-aware re-certification stubs (D11)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from dataplatformos.compiler.artifacts import GeneratedArtifact
from dataplatformos.compiler.model import Project, safe_name


def generate_data_products(project: Project) -> list[GeneratedArtifact]:
    if not project.products:
        return []

    artifacts: list[GeneratedArtifact] = []
    catalog = []
    recert_flags = []

    # Build upstream index from pipeline lineage + targets
    node_producers: dict[str, list[str]] = {}
    for pipeline in project.pipelines:
        for step in pipeline.steps:
            tgt = step.target
            obj = f"{tgt.get('schema') or tgt.get('zone')}.{tgt.get('object')}"
            node_producers.setdefault(obj, []).append(f"{pipeline.id}.{step.id}")
            for down in step.lineage.get("downstream") or []:
                node_producers.setdefault(down, []).append(f"{pipeline.id}.{step.id}")

    for product in project.products.values():
        spec = product.spec
        pid = product.id
        catalog_entry = {
            "id": pid,
            "name": spec.get("name"),
            "owningDomain": spec.get("owningDomain"),
            "productType": spec.get("productType"),
            "source": spec.get("source"),
            "metricRef": spec.get("metricRef"),
            "certification": spec.get("certification"),
            "sla": spec.get("sla"),
            "outputPorts": spec.get("outputPorts") or [],
        }
        catalog.append(catalog_entry)

        artifacts.append(
            GeneratedArtifact(
                relative_path=f"delivery/products/{safe_name(pid)}.json",
                content=json.dumps(catalog_entry, indent=2) + "\n",
                kind="data_product",
            )
        )

        # Thin Delivery passthrough view stub (no storage — packaging only)
        source = spec.get("source") or {}
        artifacts.append(
            GeneratedArtifact(
                relative_path=f"delivery/views/{safe_name(pid)}.sql",
                content=(
                    f"-- Delivery passthrough for {spec.get('name')} ({pid})\n"
                    f"-- Source kind={source.get('kind')} ref={source.get('ref')}\n"
                    f"-- Packaging only — do not recompute metrics here (D3/D7).\n"
                    f"create or replace view product.{safe_name(spec.get('owningDomain', 'domain'))}."
                    f"{safe_name(str(spec.get('name', pid)).lower())} as\n"
                    f"select * from {source.get('ref')};\n"
                ),
                kind="delivery_view",
            )
        )

        # D11 re-certification: flag when declared deps or source ref change
        deps = list(spec.get("dependsOn") or [])
        if source.get("ref"):
            deps.append(source["ref"])
        if spec.get("metricRef"):
            deps.append(spec["metricRef"])

        producers = []
        for dep in deps:
            producers.extend(node_producers.get(dep, []))

        recert_flags.append(
            {
                "product_id": pid,
                "certification_status": (spec.get("certification") or {}).get("status"),
                "watched_dependencies": deps,
                "producing_steps": sorted(set(producers)),
                "action_on_upstream_change": "flag_recertification",
                "note": (
                    "Any change to watched_dependencies (even transitive Gold tables) "
                    "should flag this product for re-certification (D11)."
                ),
            }
        )

    artifacts.append(
        GeneratedArtifact(
            relative_path="delivery/catalog.json",
            content=json.dumps(
                {
                    "segment": project.segment_id,
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "products": catalog,
                },
                indent=2,
            )
            + "\n",
            kind="product_catalog",
        )
    )
    artifacts.append(
        GeneratedArtifact(
            relative_path="delivery/recertification_flags.json",
            content=json.dumps(
                {
                    "segment": project.segment_id,
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "flags": recert_flags,
                },
                indent=2,
            )
            + "\n",
            kind="recertification",
        )
    )
    return artifacts

"""Metric → MetricFlow-style semantic YAML generator."""

from __future__ import annotations

import json

from dataplatformos.compiler.artifacts import GeneratedArtifact
from dataplatformos.compiler.model import Project, safe_name


def generate_metrics(project: Project) -> list[GeneratedArtifact]:
    if not project.metrics:
        return []

    artifacts: list[GeneratedArtifact] = []
    semantic_models: list[dict] = []
    metrics_block: list[dict] = []

    for metric in project.metrics.values():
        spec = metric.spec
        mid = metric.id
        name = mid.split(".")[-1]
        mtype = spec.get("type", "simple")

        if mtype == "simple":
            measure = spec.get("measure") or {}
            metrics_block.append(
                {
                    "name": name,
                    "label": spec.get("label"),
                    "type": "simple",
                    "type_params": {
                        "measure": {
                            "name": name,
                            "agg": measure.get("agg", "sum"),
                            "expr": measure.get("expr"),
                            "percentile": measure.get("percentile"),
                        }
                    },
                    "filter": spec.get("filter"),
                    "meta": {
                        "id": mid,
                        "model": spec.get("model"),
                        "dimensions": spec.get("dimensions") or [],
                    },
                }
            )
            model_name = safe_name(str(spec.get("model") or "model"))
            semantic_models.append(
                {
                    "name": model_name,
                    "model": spec.get("model"),
                    "defaults": {"agg_time_dimension": "metric_time"},
                    "entities": [],
                    "dimensions": [
                        {"name": d, "type": "categorical"}
                        for d in (spec.get("dimensions") or [])
                    ],
                    "measures": [
                        {
                            "name": name,
                            "agg": measure.get("agg", "sum"),
                            "expr": measure.get("expr") or name,
                        }
                    ],
                }
            )
        else:
            metrics_block.append(
                {
                    "name": name,
                    "label": spec.get("label"),
                    "type": "derived" if mtype == "derived" else "ratio",
                    "type_params": {
                        "expr": " / ".join(
                            d.split(".")[-1] for d in (spec.get("derived_from") or [])
                        )
                        if mtype == "ratio"
                        else None,
                        "metrics": [
                            {"name": d.split(".")[-1]}
                            for d in (spec.get("derived_from") or [])
                        ],
                    },
                    "meta": {
                        "id": mid,
                        "derived_from": spec.get("derived_from") or [],
                    },
                }
            )

        # Per-metric sidecar for non-MetricFlow consumers
        artifacts.append(
            GeneratedArtifact(
                relative_path=f"semantic/metrics/{safe_name(mid)}.json",
                content=json.dumps(
                    {"id": mid, "spec": spec, "metadata": metric.raw.get("metadata")},
                    indent=2,
                )
                + "\n",
                kind="metric",
            )
        )

    # MetricFlow-ish project file
    mf = {
        "semantic_models": semantic_models,
        "metrics": metrics_block,
    }
    artifacts.append(
        GeneratedArtifact(
            relative_path="semantic/metricflow_project.yml",
            content=_to_yamlish(mf),
            kind="metricflow",
        )
    )
    artifacts.append(
        GeneratedArtifact(
            relative_path="semantic/README.md",
            content=(
                f"# Semantic metrics — `{project.segment_id}`\n\n"
                "Generated MetricFlow-compatible definitions. "
                "Author metrics once here; BI tool models are caches only (D8).\n"
            ),
            kind="metric_readme",
        )
    )
    return artifacts


def _to_yamlish(data: dict) -> str:
    """Minimal YAML emitter for MetricFlow project (avoid complex dump deps)."""
    import yaml

    return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)

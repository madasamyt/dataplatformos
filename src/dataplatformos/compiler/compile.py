"""Compile orchestrator — validate project then emit native artifacts."""

from __future__ import annotations

from pathlib import Path

from dataplatformos.adapters.quality.deequ import compile_deequ
from dataplatformos.adapters.quality.great_expectations import compile_great_expectations
from dataplatformos.adapters.source.debezium import compile_debezium
from dataplatformos.adapters.source.meltano import compile_meltano
from dataplatformos.adapters.transform.flink import compile_flink
from dataplatformos.adapters.transform.ml import compile_ml
from dataplatformos.compiler.artifacts import CompileResult, GeneratedArtifact
from dataplatformos.compiler.generators.airflow_dag import generate_all_airflow
from dataplatformos.compiler.generators.data_products import generate_data_products
from dataplatformos.compiler.generators.dbt_project import generate_dbt_projects
from dataplatformos.compiler.generators.docs import generate_docs
from dataplatformos.compiler.generators.metrics import generate_metrics
from dataplatformos.compiler.generators.openlineage_gen import generate_openlineage
from dataplatformos.compiler.model import Project, load_project


def compile_project(
    project_dir: Path | str,
    output_dir: Path | str,
    *,
    targets: set[str] | None = None,
    validate: bool = True,
) -> CompileResult:
    """
    Compile a segment project into an output directory.

    targets: subset of {
      airflow, dbt, meltano, debezium, flink, ml, quality,
      metrics, products, openlineage, docs, all
    }
    """
    all_targets = {
        "airflow",
        "dbt",
        "meltano",
        "debezium",
        "flink",
        "ml",
        "quality",
        "metrics",
        "products",
        "openlineage",
        "docs",
    }
    selected = all_targets if not targets else (all_targets & targets)
    if targets and "all" in targets:
        selected = all_targets

    project: Project = load_project(project_dir, validate=validate)
    result = CompileResult()

    if "airflow" in selected:
        for art in generate_all_airflow(project):
            result.add(art)
    if "dbt" in selected:
        for art in generate_dbt_projects(project):
            result.add(art)
    if "meltano" in selected:
        for art in compile_meltano(project):
            result.add(art)
    if "debezium" in selected:
        for art in compile_debezium(project):
            result.add(art)
    if "flink" in selected:
        for art in compile_flink(project):
            result.add(art)
    if "ml" in selected:
        for art in compile_ml(project):
            result.add(art)
    if "quality" in selected:
        for art in compile_deequ(project):
            result.add(art)
        for art in compile_great_expectations(project):
            result.add(art)
    if "metrics" in selected:
        for art in generate_metrics(project):
            result.add(art)
    if "products" in selected:
        for art in generate_data_products(project):
            result.add(art)
    if "openlineage" in selected:
        for art in generate_openlineage(project):
            result.add(art)
    if "docs" in selected:
        for art in generate_docs(project):
            result.add(art)

    result.add(
        GeneratedArtifact(
            relative_path="MANIFEST.json",
            content=_manifest(project, result),
            kind="manifest",
        )
    )

    out = Path(output_dir)
    result.write_all(out)
    return result


def _manifest(project: Project, result: CompileResult) -> str:
    import json
    from datetime import datetime, timezone

    return (
        json.dumps(
            {
                "segment": project.segment_id,
                "compiledAt": datetime.now(timezone.utc).isoformat(),
                "pipelines": [p.id for p in project.pipelines],
                "metrics": list(project.metrics.keys()),
                "products": list(project.products.keys()),
                "artifacts": [
                    {"path": a.relative_path, "kind": a.kind} for a in result.artifacts
                ],
            },
            indent=2,
        )
        + "\n"
    )

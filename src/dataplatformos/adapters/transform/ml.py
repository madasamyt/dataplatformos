"""ML model invocation adapter — typed custom carve-out (D19)."""

from __future__ import annotations

import json

from dataplatformos.compiler.artifacts import GeneratedArtifact
from dataplatformos.compiler.model import Project, safe_name


def compile_ml(project: Project) -> list[GeneratedArtifact]:
    artifacts: list[GeneratedArtifact] = []
    for pipeline in project.pipelines:
        for step in pipeline.steps:
            if step.engine != "ml":
                continue
            ml = step.transform.get("ml") or {}
            name = safe_name(f"{pipeline.id}__{step.id}")
            manifest = {
                "pipeline_id": pipeline.id,
                "step_id": step.id,
                "model_ref": ml.get("model_ref"),
                "task": ml.get("task") or "batch_score",
                "framework": ml.get("framework"),
                "feature_ref": ml.get("feature_ref"),
                "image": step.transform.get("image"),
                "command": step.transform.get("command"),
                "source": step.source,
                "target": step.target,
                "contract_ref": step.quality.get("contract_ref"),
                "note": (
                    "Governed ML step — same lineage/quality rules as custom; "
                    "model_ref is required. Prefer engine: ml over opaque custom "
                    "when invoking a registered model."
                ),
            }
            artifacts.append(
                GeneratedArtifact(
                    relative_path=f"ml/{name}.json",
                    content=json.dumps(manifest, indent=2) + "\n",
                    kind="ml",
                )
            )
    return artifacts

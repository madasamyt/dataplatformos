"""Flink job manifest generator."""

from __future__ import annotations

import json

from dataplatformos.compiler.artifacts import GeneratedArtifact
from dataplatformos.compiler.model import Project, safe_name


def compile_flink(project: Project) -> list[GeneratedArtifact]:
    artifacts: list[GeneratedArtifact] = []
    for pipeline in project.pipelines:
        for step in pipeline.steps:
            if step.engine != "flink":
                continue

            name = safe_name(f"{pipeline.id}__{step.id}")
            manifest = {
                "apiVersion": "flink.apache.org/v1beta1",
                "kind": "FlinkDeployment",
                "metadata": {"name": name},
                "spec": {
                    "image": "flink:1.18",
                    "flinkVersion": "v1_18",
                    "job": {
                        "jarURI": step.transform.get("ref") or "local:///opt/flink/job.jar",
                        "parallelism": 1,
                        "upgradeMode": "stateless",
                    },
                    "pipeline_id": pipeline.id,
                    "step_id": step.id,
                    "source": step.source,
                    "target": step.target,
                },
            }
            artifacts.append(
                GeneratedArtifact(
                    relative_path=f"flink/{name}.json",
                    content=json.dumps(manifest, indent=2) + "\n",
                    kind="flink",
                )
            )
    return artifacts

"""Dremio catalog writer — contrib/commercial reference (not a default dependency)."""

from __future__ import annotations

import json

from dataplatformos.compiler.artifacts import GeneratedArtifact
from dataplatformos.compiler.model import Project, safe_name


def compile_dremio_catalog(project: Project) -> list[GeneratedArtifact]:
    """Emit Dremio VDS/registration stubs for compiled targets."""
    entries = []
    for pipeline in project.pipelines:
        for step in pipeline.steps:
            tgt = step.target
            entries.append(
                {
                    "path": [
                        tgt.get("catalog") or "lakehouse",
                        tgt.get("schema") or tgt.get("zone"),
                        tgt.get("object"),
                    ],
                    "pipeline_id": pipeline.id,
                    "step_id": step.id,
                    "zone": step.zone,
                }
            )
    return [
        GeneratedArtifact(
            relative_path=f"contrib/dremio/{safe_name(project.segment_id)}_catalog.json",
            content=json.dumps({"spaces": entries}, indent=2) + "\n",
            kind="dremio_catalog",
        )
    ]

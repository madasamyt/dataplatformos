"""Estuary Flow connector — contrib/commercial reference (not a default dependency)."""

from __future__ import annotations

from dataplatformos.compiler.artifacts import GeneratedArtifact
from dataplatformos.compiler.model import Project, safe_name


def compile_estuary(project: Project) -> list[GeneratedArtifact]:
    """Emit placeholder Estuary capture specs for steps tagged connector estuary.*."""
    artifacts: list[GeneratedArtifact] = []
    for pipeline in project.pipelines:
        for step in pipeline.steps:
            connector = (step.source.get("connector") or "")
            if not connector.startswith("estuary."):
                continue
            name = safe_name(f"{pipeline.id}__{step.id}")
            artifacts.append(
                GeneratedArtifact(
                    relative_path=f"contrib/estuary/{name}.yaml",
                    content=(
                        f"# Estuary capture placeholder for {pipeline.id}.{step.id}\n"
                        f"# Requires Estuary credentials — not part of default install.\n"
                        f"connector: {connector}\n"
                        f"target: {step.target.get('object')}\n"
                    ),
                    kind="estuary",
                )
            )
    return artifacts

"""Deequ quality compile artifacts."""

from __future__ import annotations

import json

from dataplatformos.compiler.artifacts import GeneratedArtifact
from dataplatformos.compiler.model import Project, safe_name


def compile_deequ(project: Project) -> list[GeneratedArtifact]:
    artifacts: list[GeneratedArtifact] = []
    for pipeline in project.pipelines:
        for step in pipeline.steps:
            quality = step.quality
            engine = quality.get("engine") or (
                "deequ"
                if step.zone in {"bronze", "silver"}
                else "great_expectations"
            )
            if engine != "deequ":
                continue
            name = safe_name(f"{pipeline.id}__{step.id}")
            checks = []
            cref = quality.get("contract_ref")
            for contract in project.contracts.values():
                if not cref or contract.path.name not in cref:
                    continue
                for attr in (contract.raw.get("spec") or {}).get("attributes") or []:
                    if attr.get("nullable") is False:
                        checks.append(
                            {"type": "isComplete", "column": attr["name"]}
                        )
                    if attr.get("accepted_values"):
                        checks.append(
                            {
                                "type": "isContainedIn",
                                "column": attr["name"],
                                "values": attr["accepted_values"],
                            }
                        )
            payload = {
                "engine": "deequ",
                "pipeline_id": pipeline.id,
                "step_id": step.id,
                "target": step.target,
                "on_failure": quality.get("on_failure"),
                "checks": checks,
            }
            artifacts.append(
                GeneratedArtifact(
                    relative_path=f"quality/deequ/{name}.json",
                    content=json.dumps(payload, indent=2) + "\n",
                    kind="deequ",
                )
            )
    return artifacts

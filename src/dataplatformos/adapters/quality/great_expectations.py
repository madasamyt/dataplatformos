"""Great Expectations quality compile artifacts."""

from __future__ import annotations

import json

from dataplatformos.compiler.artifacts import GeneratedArtifact
from dataplatformos.compiler.model import Project, safe_name


def compile_great_expectations(project: Project) -> list[GeneratedArtifact]:
    artifacts: list[GeneratedArtifact] = []
    for pipeline in project.pipelines:
        for step in pipeline.steps:
            quality = step.quality
            engine = quality.get("engine")
            if engine is None:
                engine = (
                    "great_expectations"
                    if step.zone in {"gold", "semantic", "delivery"}
                    else "deequ"
                )
            if engine != "great_expectations":
                continue

            name = safe_name(f"{pipeline.id}__{step.id}")
            expectations = []
            cref = quality.get("contract_ref")
            for contract in project.contracts.values():
                if not cref or contract.path.name not in cref:
                    continue
                for attr in (contract.raw.get("spec") or {}).get("attributes") or []:
                    col = attr["name"]
                    if attr.get("nullable") is False:
                        expectations.append(
                            {
                                "expectation_type": "expect_column_values_to_not_be_null",
                                "kwargs": {"column": col},
                            }
                        )
                    if attr.get("accepted_values"):
                        expectations.append(
                            {
                                "expectation_type": "expect_column_values_to_be_in_set",
                                "kwargs": {
                                    "column": col,
                                    "value_set": attr["accepted_values"],
                                },
                            }
                        )
                    vr = attr.get("valid_range") or {}
                    if "min" in vr or "max" in vr:
                        expectations.append(
                            {
                                "expectation_type": "expect_column_values_to_be_between",
                                "kwargs": {
                                    "column": col,
                                    "min_value": vr.get("min"),
                                    "max_value": vr.get("max"),
                                },
                            }
                        )

            suite = {
                "expectation_suite_name": name,
                "expectations": expectations,
                "meta": {
                    "pipeline_id": pipeline.id,
                    "step_id": step.id,
                    "on_failure": quality.get("on_failure"),
                    "zone": step.zone,
                },
            }
            artifacts.append(
                GeneratedArtifact(
                    relative_path=f"quality/great_expectations/{name}.json",
                    content=json.dumps(suite, indent=2) + "\n",
                    kind="great_expectations",
                )
            )
    return artifacts

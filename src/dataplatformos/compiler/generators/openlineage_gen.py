"""OpenLineage lineage document generator (design-time graph export)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from dataplatformos.compiler.artifacts import GeneratedArtifact
from dataplatformos.compiler.model import Project


def generate_openlineage(project: Project) -> list[GeneratedArtifact]:
    events = []
    run_id = f"compile-{project.segment_id}"
    now = datetime.now(timezone.utc).isoformat()

    for pipeline in project.pipelines:
        for step in pipeline.steps:
            inputs = []
            outputs = []
            for up in step.lineage.get("upstream") or []:
                inputs.append(
                    {
                        "namespace": project.segment_id,
                        "name": up,
                    }
                )
            for down in step.lineage.get("downstream") or []:
                outputs.append(
                    {
                        "namespace": project.segment_id,
                        "name": down,
                    }
                )
            # Always include physical target as output
            tgt = step.target
            outputs.append(
                {
                    "namespace": tgt.get("catalog") or project.segment_id,
                    "name": f"{tgt.get('schema', tgt.get('zone'))}.{tgt.get('object')}",
                }
            )
            events.append(
                {
                    "eventType": "COMPLETE",
                    "eventTime": now,
                    "run": {"runId": f"{run_id}/{pipeline.id}/{step.id}"},
                    "job": {
                        "namespace": project.segment_id,
                        "name": f"{pipeline.id}.{step.id}",
                    },
                    "inputs": inputs,
                    "outputs": outputs,
                    "producer": "https://github.com/dataplatformos/dataplatformos",
                    "schemaURL": "https://openlineage.io/spec/2-0-2/OpenLineage.json",
                }
            )

    doc = {
        "segment": project.segment_id,
        "producedAt": now,
        "events": events,
    }
    return [
        GeneratedArtifact(
            relative_path="openlineage/lineage.json",
            content=json.dumps(doc, indent=2) + "\n",
            kind="openlineage",
        )
    ]

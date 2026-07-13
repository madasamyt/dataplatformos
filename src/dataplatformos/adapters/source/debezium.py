"""Debezium CDC adapter — compile-time only. Defaults to Bronze-as-log (D10)."""

from __future__ import annotations

import json

from dataplatformos.compiler.artifacts import GeneratedArtifact
from dataplatformos.compiler.model import Project, safe_name


def compile_debezium(project: Project) -> list[GeneratedArtifact]:
    artifacts: list[GeneratedArtifact] = []
    for pipeline in project.pipelines:
        for step in pipeline.steps:
            source = step.source
            connector = source.get("connector") or ""
            if not (
                connector.startswith("debezium.")
                or source.get("pattern") == "cdc"
                or source.get("type") == "db_cdc"
            ):
                continue

            name = safe_name(f"{pipeline.id}__{step.id}")
            target = step.target
            # Bronze-as-log: emit change events, not upserts-to-mirror
            config = {
                "name": name,
                "config": {
                    "connector.class": "io.debezium.connector.jdbc.JdbcConnector",
                    "comment": "Bronze-as-log default (D10): retain c/u/d events with before/after",
                    "transforms": "unwrap",
                    "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
                    "transforms.unwrap.drop.tombstones": "false",
                    "transforms.unwrap.delete.handling.mode": "rewrite",
                    "key.converter.schemas.enable": "false",
                    "value.converter.schemas.enable": "false",
                    "topic.prefix": f"landing.{target.get('schema', 'bronze')}",
                    "table.include.list": source.get("object") or target.get("object"),
                    "connection_ref": source.get("connection_ref"),
                    "bronze_pattern": "log",
                    "system_columns": [
                        "_source_commit_ts",
                        "_cdc_operation",
                        "_lsn",
                        "_ingested_at",
                    ],
                },
            }
            artifacts.append(
                GeneratedArtifact(
                    relative_path=f"debezium/{name}.json",
                    content=json.dumps(config, indent=2) + "\n",
                    kind="debezium",
                )
            )
    return artifacts

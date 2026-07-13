"""Airflow DAG generator."""

from __future__ import annotations

import json
import textwrap

from dataplatformos.compiler.artifacts import GeneratedArtifact
from dataplatformos.compiler.model import Pipeline, Project, Step, safe_name


def _cron_to_airflow(schedule: str | None) -> str:
    if not schedule:
        return "None"
    # Accept "cron(0 * * * ? *)" AWS-style or plain cron
    s = schedule.strip()
    if s.startswith("cron(") and s.endswith(")"):
        inner = s[5:-1].strip()
        # Airflow 2 prefers 5-field; strip AWS '?' day-of-week/month
        parts = inner.split()
        if len(parts) == 6:
            # minute hour dom month dow year -> drop year, replace ?
            parts = [p.replace("?", "*") for p in parts[:5]]
            return repr(" ".join(parts))
        return repr(inner.replace("?", "*"))
    return repr(s)


def _task_id(step: Step) -> str:
    return safe_name(step.id)


def _render_step_task(pipeline: Pipeline, step: Step, project: Project) -> str:
    tid = _task_id(step)
    engine = step.engine
    trigger_mode = step.trigger.get("mode", "cron")
    zone = step.zone
    quality = step.quality
    intake = step.intake
    source = step.source
    transform = step.transform

    lines: list[str] = []

    if trigger_mode == "continuous":
        # Liveness supervision (not cron). Optional CDC apply / intake / quality around it.
        connector = source.get("connector") or ""
        chain: list[str] = []
        if (
            connector.startswith("debezium.")
            or source.get("pattern") == "cdc"
            or source.get("type") == "db_cdc"
        ):
            cdc_tid = f"{tid}__cdc_apply"
            lines.append(
                textwrap.dedent(
                    f"""\
                    {cdc_tid} = BashOperator(
                        task_id="{cdc_tid}",
                        bash_command=(
                            "echo 'Ensure Debezium connector {safe_name(pipeline.id)} is running'"
                        ),
                    )
                    """
                ).rstrip()
            )
            chain.append(cdc_tid)

        if intake and zone == "bronze":
            poison_tid = f"{tid}__intake_guard"
            max_attempts = intake.get("max_attempts", 3)
            lines.append(
                textwrap.dedent(
                    f"""\
                    {poison_tid} = PythonOperator(
                        task_id="{poison_tid}",
                        python_callable=_intake_guard,
                        op_kwargs={{
                            "pipeline_id": "{pipeline.id}",
                            "step_id": "{step.id}",
                            "max_attempts": {max_attempts},
                            "on_failure": "{intake.get("on_failure", "poison")}",
                            "landing_space": {json.dumps(source.get("landingSpace"))},
                        }},
                    )
                    """
                ).rstrip()
            )
            chain.append(poison_tid)

        if engine == "flink":
            flink_tid = f"{tid}__flink_submit"
            lines.append(
                textwrap.dedent(
                    f"""\
                    {flink_tid} = BashOperator(
                        task_id="{flink_tid}",
                        bash_command=(
                            "echo 'Submit Flink job from flink/{safe_name(pipeline.id)}__{tid}.json'"
                        ),
                    )
                    """
                ).rstrip()
            )
            chain.append(flink_tid)

        lines.append(
            textwrap.dedent(
                f"""\
                {tid} = PythonOperator(
                    task_id="{tid}",
                    python_callable=_supervise_continuous,
                    op_kwargs={{
                        "pipeline_id": "{pipeline.id}",
                        "step_id": "{step.id}",
                        "engine": "{engine}",
                        "connector": {json.dumps(source.get("connector"))},
                    }},
                )
                """
            ).rstrip()
        )
        chain.append(tid)

        q_engine = quality.get("engine") or "deequ"
        on_failure = quality.get("on_failure", "warn")
        q_tid = f"{tid}__quality"
        lines.append(
            textwrap.dedent(
                f"""\
                {q_tid} = PythonOperator(
                    task_id="{q_tid}",
                    python_callable=_quality_gate,
                    op_kwargs={{
                        "pipeline_id": "{pipeline.id}",
                        "step_id": "{step.id}",
                        "engine": "{q_engine}",
                        "contract_ref": {json.dumps(quality.get("contract_ref"))},
                        "on_failure": "{on_failure}",
                        "zone": "{zone}",
                    }},
                )
                """
            ).rstrip()
        )
        chain.append(q_tid)
        if len(chain) >= 2:
            lines.append(" >> ".join(chain))
        return "\n\n".join(lines)

    # Source extract (Meltano / Debezium) before transform when connector present
    connector = source.get("connector") or ""
    extract_tid = None
    if connector.startswith("meltano.") or source.get("type") in {"api", "file"}:
        if "meltano" in connector or source.get("type") in {"api", "file"}:
            extract_tid = f"{tid}__extract"
            meltano_project = safe_name(pipeline.id)
            lines.append(
                textwrap.dedent(
                    f"""\
                    {extract_tid} = BashOperator(
                        task_id="{extract_tid}",
                        bash_command=(
                            "meltano --cwd ${{MELTANO_PROJECT_ROOT:-./meltano/{meltano_project}}} run tap target"
                        ),
                    )
                    """
                ).rstrip()
            )
    if connector.startswith("debezium.") or source.get("pattern") == "cdc":
        extract_tid = f"{tid}__cdc"
        lines.append(
            textwrap.dedent(
                f"""\
                {extract_tid} = BashOperator(
                    task_id="{extract_tid}",
                    bash_command=(
                        "echo 'Apply Debezium connector {safe_name(pipeline.id)} "
                        "(manifest under debezium/)'"
                    ),
                )
                """
            ).rstrip()
        )

    if intake and zone == "bronze":
        poison_tid = f"{tid}__intake_guard"
        max_attempts = intake.get("max_attempts", 3)
        lines.append(
            textwrap.dedent(
                f"""\
                {poison_tid} = PythonOperator(
                    task_id="{poison_tid}",
                    python_callable=_intake_guard,
                    op_kwargs={{
                        "pipeline_id": "{pipeline.id}",
                        "step_id": "{step.id}",
                        "max_attempts": {max_attempts},
                        "on_failure": "{intake.get("on_failure", "poison")}",
                        "landing_space": {json.dumps(source.get("landingSpace"))},
                    }},
                )
                """
            ).rstrip()
        )
    else:
        poison_tid = None

    if engine == "dbt":
        dbt = transform.get("dbt") or {}
        project_name = dbt.get("project", "dbt_project")
        select = dbt.get("select") or transform.get("ref") or step.id
        lines.append(
            textwrap.dedent(
                f"""\
                {tid} = BashOperator(
                    task_id="{tid}",
                    bash_command=(
                        "dbt run --project-dir ${{DBT_PROJECT_ROOT:-./dbt/{project_name}}} "
                        "--select {select}"
                    ),
                )
                """
            ).rstrip()
        )
    elif engine == "flink":
        lines.append(
            textwrap.dedent(
                f"""\
                {tid} = BashOperator(
                    task_id="{tid}",
                    bash_command=(
                        "echo 'Submit Flink job from flink/{safe_name(pipeline.id)}__{tid}.json'"
                    ),
                )
                """
            ).rstrip()
        )
    elif engine == "custom":
        image = transform.get("image", "custom:latest")
        cmd = transform.get("command") or ["echo", "custom"]
        lines.append(
            textwrap.dedent(
                f"""\
                {tid} = BashOperator(
                    task_id="{tid}",
                    bash_command={json.dumps(" ".join(str(c) for c in cmd) + f"  # image={image}")},
                )
                """
            ).rstrip()
        )
    elif engine == "ml":
        ml = transform.get("ml") or {}
        image = transform.get("image", "ml-runner:latest")
        model_ref = ml.get("model_ref", "unknown")
        task = ml.get("task") or "batch_score"
        cmd = transform.get("command") or [
            "python",
            "-m",
            "score",
            "--model",
            str(model_ref),
            "--task",
            str(task),
        ]
        lines.append(
            textwrap.dedent(
                f"""\
                {tid} = BashOperator(
                    task_id="{tid}",
                    bash_command={json.dumps(
                        " ".join(str(c) for c in cmd)
                        + f"  # image={image} model_ref={model_ref}"
                    )},
                )
                """
            ).rstrip()
        )
    elif engine == "spark":
        lines.append(
            textwrap.dedent(
                f"""\
                {tid} = BashOperator(
                    task_id="{tid}",
                    bash_command="echo 'Submit Spark job for {pipeline.id}.{step.id}'",
                )
                """
            ).rstrip()
        )
    else:
        lines.append(
            textwrap.dedent(
                f"""\
                {tid} = EmptyOperator(task_id="{tid}")
                """
            ).rstrip()
        )

    # Quality gate
    q_engine = quality.get("engine") or "deequ"
    on_failure = quality.get("on_failure", "fail_pipeline")
    q_tid = f"{tid}__quality"
    lines.append(
        textwrap.dedent(
            f"""\
            {q_tid} = PythonOperator(
                task_id="{q_tid}",
                python_callable=_quality_gate,
                op_kwargs={{
                    "pipeline_id": "{pipeline.id}",
                    "step_id": "{step.id}",
                    "engine": "{q_engine}",
                    "contract_ref": {json.dumps(quality.get("contract_ref"))},
                    "on_failure": "{on_failure}",
                    "zone": "{zone}",
                }},
            )
            """
        ).rstrip()
    )

    # Wiring within step
    chain: list[str] = []
    if extract_tid:
        chain.append(extract_tid)
    if poison_tid:
        chain.append(poison_tid)
    chain.append(tid)
    chain.append(q_tid)
    if len(chain) >= 2:
        lines.append(" >> ".join(chain))

    # Tier-1 reconciliation after bronze extracts
    if zone == "bronze" and source.get("connector"):
        recon_tid = f"{tid}__reconcile"
        lines.append(
            textwrap.dedent(
                f"""\
                {recon_tid} = PythonOperator(
                    task_id="{recon_tid}",
                    python_callable=_tier1_reconcile,
                    op_kwargs={{
                        "pipeline_id": "{pipeline.id}",
                        "step_id": "{step.id}",
                        "connector": {json.dumps(source.get("connector"))},
                        "object": {json.dumps(step.target.get("object"))},
                    }},
                )
                {q_tid} >> {recon_tid}
                """
            ).rstrip()
        )

    return "\n\n".join(lines)


def generate_airflow_dag(project: Project, pipeline: Pipeline) -> GeneratedArtifact:
    dag_id = safe_name(f"{project.segment_id}__{pipeline.id}")
    # schedule from first cron step, else None
    schedule = "None"
    for step in pipeline.steps:
        if step.trigger.get("mode") == "cron" and step.trigger.get("schedule"):
            schedule = _cron_to_airflow(step.trigger.get("schedule"))
            break

    task_blocks = [_render_step_task(pipeline, step, project) for step in pipeline.steps]

    # Cross-step dependsOn
    deps: list[str] = []
    for step in pipeline.steps:
        tid = _task_id(step)
        for dep in step.depends_on:
            deps.append(f"{safe_name(dep)} >> {tid}")

    body = "\n\n".join(task_blocks)
    dep_block = "\n".join(deps)

    content = f'''"""
Auto-generated by dataplatformos — do not edit by hand.
Segment: {project.segment_id}
Pipeline: {pipeline.id}
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator

from dataplatformos.runtime.hooks import (
    intake_guard as _intake_guard,
    quality_gate as _quality_gate,
    supervise_continuous as _supervise_continuous,
    tier1_reconcile as _tier1_reconcile,
)

with DAG(
    dag_id="{dag_id}",
    start_date=datetime(2024, 1, 1),
    schedule={schedule},
    catchup=False,
    tags={json.dumps([project.segment_id, pipeline.id])},
    default_args={{"owner": {json.dumps((pipeline.metadata.get("owner") or "data-platform"))}}},
) as dag:
{textwrap.indent(body, "    ")}
'''
    if dep_block:
        content += "\n" + textwrap.indent(dep_block, "    ") + "\n"

    return GeneratedArtifact(
        relative_path=f"airflow/dags/{dag_id}.py",
        content=content,
        kind="airflow_dag",
    )


def generate_all_airflow(project: Project) -> list[GeneratedArtifact]:
    return [generate_airflow_dag(project, p) for p in project.pipelines]

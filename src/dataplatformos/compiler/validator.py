"""Project validation: Segment + Pipelines + Contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ZONE_NO_QUARANTINE = frozenset({"landing", "bronze"})
INTAKE_ALLOWED_TARGET_ZONES = frozenset({"bronze"})


@dataclass
class Issue:
    path: str
    message: str
    severity: str = "error"

    def __str__(self) -> str:
        return f"[{self.severity}] {self.path}: {self.message}"


@dataclass
class ValidationResult:
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def error(self, path: str, message: str) -> None:
        self.issues.append(Issue(path=path, message=message, severity="error"))

    def warning(self, path: str, message: str) -> None:
        self.issues.append(Issue(path=path, message=message, severity="warning"))


def schema_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "schema",  # installed: dataplatformos/schema
        here.parents[3] / "schema",  # editable: <repo>/schema
        Path.cwd() / "schema",
    ]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "segment.v1.schema.json").exists():
            return candidate
    raise FileNotFoundError(
        "Could not locate schema/. Expected segment.v1.schema.json under "
        + ", ".join(str(c) for c in candidates)
    )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _format_jsonschema_error(err: ValidationError) -> str:
    loc = ".".join(str(p) for p in err.absolute_path) or "(root)"
    return f"{loc}: {err.message}"


def _validator_for(name: str) -> Draft202012Validator:
    schema = _load_json(schema_dir() / name)
    return Draft202012Validator(schema)


def find_segment_file(project_dir: Path) -> Path | None:
    for name in ("segment.yaml", "segment.yml"):
        candidate = project_dir / name
        if candidate.is_file():
            return candidate
    matches = sorted(project_dir.glob("*.segment.yaml")) + sorted(
        project_dir.glob("*.segment.yml")
    )
    return matches[0] if matches else None


def validate_project(project_dir: Path | str) -> ValidationResult:
    """Validate a segment project directory."""
    result = ValidationResult()
    root = Path(project_dir).resolve()

    if not root.is_dir():
        result.error(str(root), "project path is not a directory")
        return result

    segment_path = find_segment_file(root)
    if segment_path is None:
        result.error(
            str(root),
            "no segment.yaml (or *.segment.yaml) found in project directory",
        )
        return result

    try:
        segment = _load_yaml(segment_path)
    except yaml.YAMLError as exc:
        result.error(str(segment_path), f"invalid YAML: {exc}")
        return result

    if not isinstance(segment, dict):
        result.error(str(segment_path), "document must be a mapping")
        return result

    _validate_against_schema(result, segment_path, segment, "segment.v1.schema.json")
    if not result.ok:
        return result

    landing_list = (segment.get("spec") or {}).get("landingSpaces") or []
    landing_spaces: dict[str, dict[str, Any]] = {}
    for space in landing_list:
        sid = space.get("id")
        if not sid:
            continue
        if sid in landing_spaces:
            result.error(str(segment_path), f"duplicate landingSpace id: {sid}")
        landing_spaces[sid] = space

    pipeline_ids: set[str] = set()
    contract_paths_seen: set[Path] = set()
    contract_semantic_refs: list[tuple[str, str]] = []

    for idx, entry in enumerate((segment.get("spec") or {}).get("pipelines") or []):
        ref = entry.get("ref")
        if not ref:
            continue
        pipeline_path = (root / ref).resolve()
        rel = f"{segment_path.name}#spec.pipelines[{idx}].ref"
        if not pipeline_path.is_file():
            result.error(rel, f"pipeline file not found: {ref}")
            continue
        try:
            pipeline = _load_yaml(pipeline_path)
        except yaml.YAMLError as exc:
            result.error(str(pipeline_path), f"invalid YAML: {exc}")
            continue
        if not isinstance(pipeline, dict):
            result.error(str(pipeline_path), "document must be a mapping")
            continue

        _validate_against_schema(
            result, pipeline_path, pipeline, "pipeline.v1.schema.json"
        )
        pid = (pipeline.get("metadata") or {}).get("id")
        if pid:
            if pid in pipeline_ids:
                result.error(str(pipeline_path), f"duplicate pipeline id: {pid}")
            pipeline_ids.add(pid)

        _validate_pipeline_semantics(
            result,
            root=root,
            pipeline_path=pipeline_path,
            pipeline=pipeline,
            landing_spaces=landing_spaces,
            contract_paths_seen=contract_paths_seen,
            contract_semantic_refs=contract_semantic_refs,
        )

    _validate_metrics_and_products(
        result,
        root=root,
        segment_path=segment_path,
        contract_semantic_refs=contract_semantic_refs,
    )

    return result


def _validate_against_schema(
    result: ValidationResult,
    path: Path,
    document: dict[str, Any],
    schema_name: str,
) -> None:
    validator = _validator_for(schema_name)
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    for err in errors:
        result.error(str(path), _format_jsonschema_error(err))


def _validate_pipeline_semantics(
    result: ValidationResult,
    *,
    root: Path,
    pipeline_path: Path,
    pipeline: dict[str, Any],
    landing_spaces: dict[str, dict[str, Any]],
    contract_paths_seen: set[Path],
    contract_semantic_refs: list[tuple[str, str]],
) -> None:
    steps = (pipeline.get("spec") or {}).get("steps") or []
    step_ids = [s.get("id") for s in steps if s.get("id")]
    if len(step_ids) != len(set(step_ids)):
        result.error(str(pipeline_path), "duplicate step ids within pipeline")

    known = set(step_ids)
    for step in steps:
        sid = step.get("id", "?")
        step_path = f"{pipeline_path}#steps.{sid}"

        for dep in step.get("dependsOn") or []:
            if dep not in known:
                result.error(step_path, f"dependsOn references unknown step: {dep}")
            if dep == sid:
                result.error(step_path, "dependsOn cannot reference itself")

        target = step.get("target") or {}
        zone = target.get("zone")
        quality = step.get("quality") or {}
        on_failure = quality.get("on_failure")

        if zone in ZONE_NO_QUARANTINE and on_failure == "quarantine":
            result.error(
                step_path,
                f"quality.on_failure=quarantine is not allowed for zone={zone} "
                "(quarantine is Silver+; use intake.on_failure for corrupt delivery units)",
            )

        intake = step.get("intake")
        if intake is not None:
            if zone not in INTAKE_ALLOWED_TARGET_ZONES:
                result.error(
                    step_path,
                    f"intake is only valid when target.zone is bronze (got {zone})",
                )

        source = step.get("source") or {}
        landing_ref = source.get("landingSpace")
        if landing_ref:
            if landing_ref not in landing_spaces:
                result.error(
                    step_path,
                    f"source.landingSpace '{landing_ref}' is not declared on the segment",
                )

        transform = step.get("transform") or {}
        engine = transform.get("engine")
        if engine in {"custom", "ml"}:
            if not source:
                result.error(
                    step_path,
                    f"{engine} transform requires source (inputs)",
                )
            if not quality.get("contract_ref"):
                result.error(
                    step_path,
                    f"{engine} transform requires quality.contract_ref",
                )
        if engine == "ml":
            ml = transform.get("ml") or {}
            if not ml.get("model_ref"):
                result.error(step_path, "ml transform requires transform.ml.model_ref")

        contract_ref = quality.get("contract_ref")
        if contract_ref:
            contract_path = (root / contract_ref).resolve()
            if not contract_path.is_file():
                alt = (pipeline_path.parent / contract_ref).resolve()
                if alt.is_file():
                    contract_path = alt
                else:
                    result.error(
                        step_path,
                        f"quality.contract_ref not found: {contract_ref}",
                    )
                    continue
            if contract_path not in contract_paths_seen:
                contract_paths_seen.add(contract_path)
                try:
                    contract = _load_yaml(contract_path)
                except yaml.YAMLError as exc:
                    result.error(str(contract_path), f"invalid YAML: {exc}")
                    continue
                if not isinstance(contract, dict):
                    result.error(str(contract_path), "document must be a mapping")
                    continue
                _validate_against_schema(
                    result, contract_path, contract, "contract.v1.schema.json"
                )
                for attr in (contract.get("spec") or {}).get("attributes") or []:
                    derived = attr.get("derived_from")
                    if isinstance(derived, dict) and derived.get("semantic_ref"):
                        contract_semantic_refs.append(
                            (str(contract_path), derived["semantic_ref"])
                        )


def _resolve_ref(root: Path, ref: str) -> Path:
    return (root / ref).resolve()


def _load_and_validate_refs(
    result: ValidationResult,
    *,
    root: Path,
    segment_path: Path,
    key: str,
    schema_name: str,
    kind_label: str,
) -> dict[str, dict]:
    """Load segment.spec.<key> refs; return id -> document."""
    segment = _load_yaml(segment_path)
    loaded: dict[str, dict] = {}
    for idx, entry in enumerate((segment.get("spec") or {}).get(key) or []):
        ref = entry.get("ref")
        if not ref:
            continue
        path = _resolve_ref(root, ref)
        loc = f"{segment_path.name}#spec.{key}[{idx}].ref"
        if not path.is_file():
            result.error(loc, f"{kind_label} file not found: {ref}")
            continue
        try:
            doc = _load_yaml(path)
        except yaml.YAMLError as exc:
            result.error(str(path), f"invalid YAML: {exc}")
            continue
        if not isinstance(doc, dict):
            result.error(str(path), "document must be a mapping")
            continue
        _validate_against_schema(result, path, doc, schema_name)
        doc_id = (doc.get("metadata") or {}).get("id")
        if not doc_id:
            result.error(str(path), f"{kind_label} metadata.id is required")
            continue
        if doc_id in loaded:
            result.error(str(path), f"duplicate {kind_label} id: {doc_id}")
        loaded[doc_id] = doc
    return loaded


def _validate_metrics_and_products(
    result: ValidationResult,
    *,
    root: Path,
    segment_path: Path,
    contract_semantic_refs: list[tuple[str, str]],
) -> None:
    metrics = _load_and_validate_refs(
        result,
        root=root,
        segment_path=segment_path,
        key="metrics",
        schema_name="metric.v1.schema.json",
        kind_label="metric",
    )
    for mid, doc in metrics.items():
        for dep in (doc.get("spec") or {}).get("derived_from") or []:
            if dep not in metrics:
                result.error(
                    mid,
                    f"metric derived_from references unknown metric id: {dep}",
                )

    for path, sref in contract_semantic_refs:
        if sref not in metrics:
            result.error(
                path,
                f"contract semantic_ref '{sref}' does not match a Metric in this segment",
            )

    products = _load_and_validate_refs(
        result,
        root=root,
        segment_path=segment_path,
        key="products",
        schema_name="data_product.v1.schema.json",
        kind_label="data product",
    )
    for pid, doc in products.items():
        spec = doc.get("spec") or {}
        mref = spec.get("metricRef")
        product_type = spec.get("productType")
        source = spec.get("source") or {}

        if mref and mref not in metrics:
            result.error(pid, f"metricRef '{mref}' does not match a Metric in this segment")

        if product_type in {"kpi", "dashboard"} and source.get("kind") not in {
            "semantic",
            "metric",
        }:
            result.error(
                pid,
                "kpi/dashboard products with a governed metric must source from "
                "semantic or metric (D4 — do not skip Semantic)",
            )

        if source.get("kind") == "metric":
            sref = source.get("ref")
            if sref and sref not in metrics:
                result.error(
                    pid,
                    f"source.ref '{sref}' is not a Metric id in this segment",
                )


def validate_project_or_raise(project_dir: Path | str) -> ValidationResult:
    result = validate_project(project_dir)
    if not result.ok:
        messages = "\n".join(str(i) for i in result.issues if i.severity == "error")
        raise ValueError(messages)
    return result

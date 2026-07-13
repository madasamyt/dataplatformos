"""Loaded segment project model used by generators."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from dataplatformos.compiler.validator import find_segment_file, validate_project


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class LandingSpace:
    id: str
    mode: str
    storage_ref: str | None = None


@dataclass
class Step:
    id: str
    raw: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)

    @property
    def source(self) -> dict[str, Any]:
        return self.raw.get("source") or {}

    @property
    def target(self) -> dict[str, Any]:
        return self.raw.get("target") or {}

    @property
    def transform(self) -> dict[str, Any]:
        return self.raw.get("transform") or {}

    @property
    def trigger(self) -> dict[str, Any]:
        return self.raw.get("trigger") or {}

    @property
    def intake(self) -> dict[str, Any] | None:
        return self.raw.get("intake")

    @property
    def quality(self) -> dict[str, Any]:
        return self.raw.get("quality") or {}

    @property
    def lineage(self) -> dict[str, Any]:
        return self.raw.get("lineage") or {}

    @property
    def zone(self) -> str:
        return str(self.target.get("zone", ""))

    @property
    def engine(self) -> str:
        return str(self.transform.get("engine") or "none")


@dataclass
class Pipeline:
    id: str
    path: Path
    raw: dict[str, Any]
    steps: list[Step]

    @property
    def metadata(self) -> dict[str, Any]:
        return self.raw.get("metadata") or {}


@dataclass
class Contract:
    id: str
    path: Path
    raw: dict[str, Any]


@dataclass
class Metric:
    id: str
    path: Path
    raw: dict[str, Any]

    @property
    def spec(self) -> dict[str, Any]:
        return self.raw.get("spec") or {}


@dataclass
class DataProduct:
    id: str
    path: Path
    raw: dict[str, Any]

    @property
    def spec(self) -> dict[str, Any]:
        return self.raw.get("spec") or {}


@dataclass
class Project:
    root: Path
    segment_path: Path
    segment: dict[str, Any]
    landing_spaces: dict[str, LandingSpace]
    pipelines: list[Pipeline]
    contracts: dict[str, Contract] = field(default_factory=dict)
    metrics: dict[str, Metric] = field(default_factory=dict)
    products: dict[str, DataProduct] = field(default_factory=dict)

    @property
    def segment_id(self) -> str:
        return str((self.segment.get("metadata") or {}).get("id", "segment"))


def _load_kind_refs(
    root: Path,
    segment: dict[str, Any],
    key: str,
    cls: type,
) -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    for entry in (segment.get("spec") or {}).get(key) or []:
        ref = entry["ref"]
        path = (root / ref).resolve()
        raw = _load_yaml(path)
        doc_id = (raw.get("metadata") or {}).get("id", path.stem)
        loaded[doc_id] = cls(id=doc_id, path=path, raw=raw)
    return loaded


def load_project(project_dir: Path | str, *, validate: bool = True) -> Project:
    root = Path(project_dir).resolve()
    if validate:
        result = validate_project(root)
        if not result.ok:
            messages = "\n".join(str(i) for i in result.issues if i.severity == "error")
            raise ValueError(messages)

    segment_path = find_segment_file(root)
    if segment_path is None:
        raise FileNotFoundError(f"no segment.yaml in {root}")

    segment = _load_yaml(segment_path)
    landing_spaces = {
        s["id"]: LandingSpace(
            id=s["id"],
            mode=s["mode"],
            storage_ref=s.get("storageRef"),
        )
        for s in (segment.get("spec") or {}).get("landingSpaces") or []
    }

    pipelines: list[Pipeline] = []
    contracts: dict[str, Contract] = {}

    for entry in (segment.get("spec") or {}).get("pipelines") or []:
        ref = entry["ref"]
        pipeline_path = (root / ref).resolve()
        raw = _load_yaml(pipeline_path)
        steps = [
            Step(
                id=s["id"],
                raw=s,
                depends_on=list(s.get("dependsOn") or []),
            )
            for s in (raw.get("spec") or {}).get("steps") or []
        ]
        pid = (raw.get("metadata") or {}).get("id", pipeline_path.stem)
        pipelines.append(
            Pipeline(id=pid, path=pipeline_path, raw=raw, steps=steps)
        )

        for step in steps:
            cref = (step.quality or {}).get("contract_ref")
            if not cref:
                continue
            cpath = (root / cref).resolve()
            if not cpath.is_file():
                cpath = (pipeline_path.parent / cref).resolve()
            if cpath.is_file() and str(cpath) not in {str(c.path) for c in contracts.values()}:
                craw = _load_yaml(cpath)
                cid = (craw.get("metadata") or {}).get("id", cpath.stem)
                contracts[cid] = Contract(id=cid, path=cpath, raw=craw)

    metrics = _load_kind_refs(root, segment, "metrics", Metric)
    products = _load_kind_refs(root, segment, "products", DataProduct)

    return Project(
        root=root,
        segment_path=segment_path,
        segment=segment,
        landing_spaces=landing_spaces,
        pipelines=pipelines,
        contracts=contracts,
        metrics=metrics,
        products=products,
    )


def safe_name(value: str) -> str:
    return (
        value.replace(".", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace(" ", "_")
    )

from __future__ import annotations

from pathlib import Path

from dataplatformos.compiler.validator import validate_project

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
COMMERCE = REPO / "examples" / "commerce_orders"


def test_commerce_with_metrics_products_validates() -> None:
    result = validate_project(COMMERCE)
    assert result.ok, "\n".join(str(i) for i in result.issues)


def test_kpi_skipping_semantic_rejected(tmp_path: Path) -> None:
    root = tmp_path / "bad_kpi"
    (root / "metrics").mkdir(parents=True)
    (root / "products").mkdir()
    (root / "pipelines").mkdir()
    (root / "contracts").mkdir()

    (root / "segment.yaml").write_text(
        """
apiVersion: platform/v1
kind: Segment
metadata: { id: fixtures.bad_kpi }
spec:
  pipelines:
    - ref: pipelines/p.yaml
  metrics:
    - ref: metrics/m.yaml
  products:
    - ref: products/bad.yaml
""",
        encoding="utf-8",
    )
    (root / "pipelines" / "p.yaml").write_text(
        """
apiVersion: pipeline/v1
kind: Pipeline
metadata: { id: fixtures.p }
spec:
  steps:
    - id: s
      target: { zone: gold, object: t, format: iceberg }
      trigger: { mode: event }
      quality: { contract_ref: contracts/c.yaml, on_failure: warn }
""",
        encoding="utf-8",
    )
    (root / "contracts" / "c.yaml").write_text(
        """
apiVersion: contract/v1
kind: Contract
metadata: { id: c }
spec:
  attributes:
    - name: id
      type: string
""",
        encoding="utf-8",
    )
    (root / "metrics" / "m.yaml").write_text(
        """
apiVersion: semantic/v1
kind: Metric
metadata: { id: semantic.fixtures.m }
spec:
  label: M
  type: simple
  model: gold.fixtures.t
  measure: { expr: x, agg: sum }
""",
        encoding="utf-8",
    )
    (root / "products" / "bad.yaml").write_text(
        """
apiVersion: delivery/v1
kind: DataProduct
metadata: { id: product.fixtures.bad }
spec:
  name: Bad KPI
  owningDomain: finance
  productType: kpi
  source: { kind: gold, ref: gold.fixtures.t }
  metricRef: semantic.fixtures.m
  certification: { status: certified, version: "1" }
""",
        encoding="utf-8",
    )

    result = validate_project(root)
    assert not result.ok
    messages = "\n".join(i.message for i in result.issues)
    assert "do not skip Semantic" in messages


def test_ml_requires_model_ref(tmp_path: Path) -> None:
    root = tmp_path / "bad_ml"
    (root / "pipelines").mkdir(parents=True)
    (root / "contracts").mkdir()
    (root / "segment.yaml").write_text(
        """
apiVersion: platform/v1
kind: Segment
metadata: { id: fixtures.ml }
spec:
  pipelines:
    - ref: pipelines/p.yaml
""",
        encoding="utf-8",
    )
    (root / "contracts" / "c.yaml").write_text(
        """
apiVersion: contract/v1
kind: Contract
metadata: { id: c }
spec:
  attributes:
    - name: id
      type: string
""",
        encoding="utf-8",
    )
    (root / "pipelines" / "p.yaml").write_text(
        """
apiVersion: pipeline/v1
kind: Pipeline
metadata: { id: fixtures.ml }
spec:
  steps:
    - id: score
      source: { type: table, object: features }
      target: { zone: gold, object: scores, format: iceberg }
      transform:
        engine: ml
        ml: { task: batch_score }
      trigger: { mode: event }
      quality: { contract_ref: contracts/c.yaml, on_failure: fail_pipeline }
""",
        encoding="utf-8",
    )
    result = validate_project(root)
    assert not result.ok
    messages = "\n".join(i.message for i in result.issues)
    assert "model_ref" in messages

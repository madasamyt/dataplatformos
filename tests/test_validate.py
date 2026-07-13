from __future__ import annotations

from pathlib import Path

from dataplatformos.compiler.validator import validate_project

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples" / "commerce_orders"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_commerce_orders_example_validates() -> None:
    result = validate_project(EXAMPLES)
    assert result.ok, "\n".join(str(i) for i in result.issues)


def test_bronze_quarantine_rejected() -> None:
    result = validate_project(FIXTURES / "bronze_quarantine")
    assert not result.ok
    messages = "\n".join(i.message for i in result.issues)
    assert "quarantine is not allowed" in messages


def test_missing_landing_space_rejected() -> None:
    result = validate_project(FIXTURES / "missing_landing_space")
    assert not result.ok
    messages = "\n".join(i.message for i in result.issues)
    assert "not declared on the segment" in messages


def test_custom_missing_contract_rejected() -> None:
    result = validate_project(FIXTURES / "custom_missing_contract")
    assert not result.ok
    messages = "\n".join(i.message for i in result.issues)
    assert "contract_ref not found" in messages


def test_missing_project_dir() -> None:
    result = validate_project(FIXTURES / "does_not_exist")
    assert not result.ok

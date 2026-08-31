"""Stage A pre-migration alignment metadata tests (no live PostgreSQL required)."""

from __future__ import annotations

import warnings

import app.models  # noqa: F401
from app.db.base import Base
from app.models.recovery_outcome import RecoveryOutcome
from tests.models.helpers import compile_table


def test_policy_reasons_jsonb_array_default() -> None:
    column = Base.metadata.tables["recovery_recommendations"].c.policy_reasons
    assert column.nullable is False
    ddl = compile_table("recovery_recommendations")
    assert "policy_reasons JSONB DEFAULT '[]'::jsonb" in ddl.replace('"', "")


def test_factors_jsonb_array_default() -> None:
    column = Base.metadata.tables["recovery_recommendations"].c.factors
    assert column.nullable is False
    ddl = compile_table("recovery_recommendations")
    assert "factors JSONB DEFAULT '[]'::jsonb" in ddl.replace('"', "")


def test_allowed_action_types_jsonb_array_default() -> None:
    column = Base.metadata.tables["merchant_policies"].c.allowed_action_types
    assert column.nullable is False
    ddl = compile_table("merchant_policies")
    assert "allowed_action_types JSONB DEFAULT '[]'::jsonb" in ddl.replace('"', "")


def test_verified_event_id_remains_nullable() -> None:
    column = Base.metadata.tables["recovery_outcomes"].c.verified_event_id
    assert column.nullable is True


def test_recovery_outcome_verified_event_foreign_key_metadata() -> None:
    table = Base.metadata.tables["recovery_outcomes"]
    verified_fk = next(
        c
        for c in table.foreign_key_constraints
        if c.name == "fk_recovery_outcomes_verified_event_id_webhook_events"
    )
    local_columns = {element.parent.name for element in verified_fk.elements}
    remote = {(element.column.table.name, element.column.name) for element in verified_fk.elements}
    assert local_columns == {"verified_event_id"}
    assert remote == {("webhook_events", "id")}


def test_recovery_outcome_mapper_configures_without_warnings() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from sqlalchemy.orm import configure_mappers

        configure_mappers()
    mapper_warnings = [
        w
        for w in caught
        if issubclass(w.category, (Warning,))
        and "RecoveryOutcome" in str(w.message)
    ]
    assert mapper_warnings == []


def test_recovery_outcome_model_table_has_deferred_fk() -> None:
    fk_names = {c.name for c in RecoveryOutcome.__table__.foreign_key_constraints}
    assert "fk_recovery_outcomes_verified_event_id_webhook_events" in fk_names

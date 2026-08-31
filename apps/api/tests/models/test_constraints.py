import app.models  # noqa: F401
from app.db.base import Base
from tests.models.helpers import (
    compile_index,
    compile_table,
    table_indexes,
)


def _constraint_names(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    names: set[str] = set()
    for constraint in table.constraints:
        if constraint.name:
            names.add(constraint.name)
    for index in table.indexes:
        if index.name:
            names.add(index.name)
    return names


def test_user_profiles_auth_user_id_unique() -> None:
    names = _constraint_names("user_profiles")
    assert "uq_user_profiles_auth_user_id" in names


def test_customers_org_external_id_unique() -> None:
    names = _constraint_names("customers")
    assert "uq_customers_organization_id_external_id" in names


def test_transactions_partial_provider_payment_unique_index() -> None:
    indexes = table_indexes("transactions")
    partial = next(i for i in indexes if i.name == "uq_transactions_provider_payment_id")
    ddl = compile_index(partial)
    assert "UNIQUE" in ddl.upper()
    assert "WHERE" in ddl.upper()
    assert "provider_payment_id IS NOT NULL" in ddl


def test_subscriptions_provider_subscription_unique() -> None:
    names = _constraint_names("subscriptions")
    assert "uq_subscriptions_provider_provider_subscription_id" in names


def test_recovery_cases_source_event_and_tenant_identity_unique() -> None:
    names = _constraint_names("recovery_cases")
    assert "uq_recovery_cases_organization_id_source_event_key" in names
    assert "uq_recovery_cases_id_organization_id" in names


def test_recovery_recommendation_uniqueness_constraints() -> None:
    names = _constraint_names("recovery_recommendations")
    assert "uq_recovery_recommendations_case_analysis_action" in names
    assert "uq_recovery_recommendations_case_analysis_rank" in names


def test_recovery_action_idempotency_and_attempt_uniqueness() -> None:
    names = _constraint_names("recovery_actions")
    assert "uq_recovery_actions_idempotency_key" in names
    assert "uq_recovery_actions_case_id_attempt_number" in names


def test_recovery_action_one_executing_partial_unique_index() -> None:
    indexes = table_indexes("recovery_actions")
    partial = next(i for i in indexes if i.name == "uq_recovery_actions_one_executing")
    ddl = compile_index(partial)
    assert "UNIQUE" in ddl.upper()
    assert "WHERE" in ddl.upper()
    assert "status = 'EXECUTING'" in ddl


def test_recovery_outcome_one_per_case_unique() -> None:
    names = _constraint_names("recovery_outcomes")
    assert "uq_recovery_outcomes_case_id" in names


def test_recovery_outcome_verified_event_foreign_key() -> None:
    table = Base.metadata.tables["recovery_outcomes"]
    verified_fk = next(
        c
        for c in table.foreign_key_constraints
        if c.name == "fk_recovery_outcomes_verified_event_id_webhook_events"
    )
    assert verified_fk.elements[0].parent.name == "verified_event_id"
    assert verified_fk.elements[0].column.table.name == "webhook_events"
    assert verified_fk.elements[0].column.name == "id"


def test_webhook_provider_event_unique() -> None:
    names = _constraint_names("webhook_events")
    assert "uq_webhook_events_provider_provider_event_id" in names


def test_merchant_policy_one_per_organization() -> None:
    names = _constraint_names("merchant_policies")
    assert "uq_merchant_policies_organization_id" in names


def test_recovery_case_child_tables_have_composite_tenant_foreign_keys() -> None:
    for table_name in ("recovery_recommendations", "recovery_actions", "recovery_outcomes"):
        table = Base.metadata.tables[table_name]
        tenant_fk = next(
            c
            for c in table.foreign_key_constraints
            if c.name == f"fk_{table_name}_recovery_cases_tenant"
        )
        local_columns = {element.parent.name for element in tenant_fk.elements}
        remote_columns = {element.column.name for element in tenant_fk.elements}
        assert local_columns == {"case_id", "organization_id"}
        assert remote_columns == {"id", "organization_id"}
        assert tenant_fk.referred_table.name == "recovery_cases"


def test_check_constraints_exist_for_documented_invariants() -> None:
    ddl = compile_table("recovery_cases")
    assert "amount_at_risk_minor > 0" in ddl
    assert "payment_failure_source" in ddl or "PAYMENT_FAILURE" in ddl

    action_ddl = compile_table("recovery_actions")
    assert "attempt_number >= 1" in action_ddl

    outcome_ddl = compile_table("recovery_outcomes")
    assert "recovered_amount_minor >= 0" in outcome_ddl

    policy_ddl = compile_table("merchant_policies")
    assert "minimum_auto_confidence" in policy_ddl


def test_primary_keys_use_naming_convention() -> None:
    for table_name in Base.metadata.tables:
        pk = Base.metadata.tables[table_name].primary_key
        assert pk.name == f"pk_{table_name}"

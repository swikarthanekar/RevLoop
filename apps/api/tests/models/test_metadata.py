import app.models  # noqa: F401
from app.db.base import Base

EXPECTED_TABLES = {
    "organizations",
    "user_profiles",
    "customers",
    "transactions",
    "subscriptions",
    "invoices",
    "recovery_cases",
    "recovery_recommendations",
    "recovery_actions",
    "recovery_outcomes",
    "webhook_events",
    "audit_logs",
    "merchant_policies",
}

TENANT_OWNED_TABLES = {
    "user_profiles",
    "customers",
    "transactions",
    "subscriptions",
    "invoices",
    "recovery_cases",
    "recovery_recommendations",
    "recovery_actions",
    "recovery_outcomes",
    "webhook_events",
    "audit_logs",
    "merchant_policies",
}

MONEY_COLUMNS = {
    ("customers", "lifetime_value_minor"),
    ("transactions", "amount_minor"),
    ("subscriptions", "amount_minor"),
    ("recovery_cases", "amount_at_risk_minor"),
    ("recovery_cases", "expected_recoverable_minor"),
    ("recovery_recommendations", "expected_recovered_minor"),
    ("recovery_recommendations", "expected_value_minor"),
    ("recovery_outcomes", "recovered_amount_minor"),
    ("merchant_policies", "auto_action_limit_minor"),
}

PROBABILITY_COLUMNS = {
    ("recovery_cases", "priority_score"),
    ("recovery_cases", "recovery_probability"),
    ("recovery_recommendations", "success_probability"),
    ("recovery_recommendations", "confidence"),
    ("merchant_policies", "minimum_auto_confidence"),
}


def test_all_required_tables_registered() -> None:
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES


def test_tenant_owned_tables_have_organization_id() -> None:
    for table_name in TENANT_OWNED_TABLES:
        column = Base.metadata.tables[table_name].c.organization_id
        assert column.nullable is False


def test_money_columns_use_bigint() -> None:
    from tests.models.helpers import has_float_money_columns, is_bigint

    for table_name, column_name in MONEY_COLUMNS:
        assert is_bigint(table_name, column_name)

    assert has_float_money_columns() == []


def test_probability_columns_use_numeric_7_6() -> None:
    from tests.models.helpers import is_numeric_7_6

    for table_name, column_name in PROBABILITY_COLUMNS:
        assert is_numeric_7_6(table_name, column_name)


def test_jsonb_metadata_columns_compile_as_jsonb() -> None:
    from tests.models.helpers import compile_table, is_jsonb

    jsonb_columns = [
        ("transactions", "metadata"),
        ("subscriptions", "metadata"),
        ("recovery_recommendations", "policy_reasons"),
        ("recovery_recommendations", "factors"),
        ("recovery_actions", "metadata"),
        ("recovery_outcomes", "metadata"),
        ("webhook_events", "payload"),
        ("audit_logs", "evidence"),
        ("merchant_policies", "allowed_action_types"),
    ]
    for table_name, column_name in jsonb_columns:
        assert is_jsonb(table_name, column_name)
        ddl = compile_table(table_name)
        assert "JSONB" in ddl.upper()


def test_uuid_columns_use_postgresql_uuid_type() -> None:
    from tests.models.helpers import compile_table, is_uuid

    uuid_columns = [
        ("organizations", "id"),
        ("recovery_cases", "id"),
        ("recovery_cases", "organization_id"),
        ("user_profiles", "auth_user_id"),
    ]
    for table_name, column_name in uuid_columns:
        assert is_uuid(table_name, column_name)
        ddl = compile_table(table_name)
        assert "UUID" in ddl.upper()

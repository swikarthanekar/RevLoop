from sqlalchemy.types import CHAR, Numeric

import app.models  # noqa: F401
from app.db.base import Base
from tests.models.helpers import compile_index, compile_table, table_indexes

CURRENCY_COLUMNS = [
    ("organizations", "currency"),
    ("transactions", "currency"),
    ("subscriptions", "currency"),
    ("invoices", "currency"),
    ("recovery_cases", "currency"),
]

NUMERIC_COLUMNS = [
    ("recovery_cases", "priority_score"),
    ("recovery_cases", "recovery_probability"),
    ("recovery_recommendations", "success_probability"),
    ("recovery_recommendations", "confidence"),
    ("merchant_policies", "minimum_auto_confidence"),
]

DESC_INDEX_EXPECTATIONS = {
    "transactions": {
        "ix_transactions_org_customer_provider_created_at": ["provider_created_at DESC"],
        "ix_transactions_org_payment_method_provider_created_at": ["provider_created_at DESC"],
    },
    "recovery_cases": {
        "ix_recovery_cases_org_status_priority_score": ["priority_score DESC"],
        "ix_recovery_cases_organization_id_opened_at": ["opened_at DESC"],
        "ix_recovery_cases_org_customer_opened_at": ["opened_at DESC"],
    },
    "webhook_events": {
        "ix_webhook_events_organization_id_received_at": ["received_at DESC"],
        "ix_webhook_events_org_event_type_received_at": ["received_at DESC"],
    },
    "audit_logs": {
        "ix_audit_logs_organization_id_created_at": ["created_at DESC"],
        "ix_audit_logs_org_event_type_created_at": ["created_at DESC"],
    },
}


def test_currency_columns_compile_as_char_three() -> None:
    for table_name, column_name in CURRENCY_COLUMNS:
        column = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, CHAR)
        assert column.type.length == 3

        ddl = compile_table(table_name)
        assert f"{column_name} CHAR(3)" in ddl


def test_numeric_columns_remain_numeric_seven_six() -> None:
    for table_name, column_name in NUMERIC_COLUMNS:
        column = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, Numeric)
        assert column.type.precision == 7
        assert column.type.scale == 6


def test_documented_desc_indexes_compile_with_desc() -> None:
    for table_name, indexes in DESC_INDEX_EXPECTATIONS.items():
        metadata_indexes = {index.name: index for index in table_indexes(table_name)}
        for index_name, expected_desc_columns in indexes.items():
            ddl = compile_index(metadata_indexes[index_name]).upper()
            for expected in expected_desc_columns:
                assert expected.upper() in ddl


def test_ascending_indexes_remain_unchanged() -> None:
    webhook_indexes = {index.name: index for index in table_indexes("webhook_events")}
    ddl = compile_index(webhook_indexes["ix_webhook_events_processing_status_received_at"]).upper()
    assert "RECEIVED_AT DESC" not in ddl

    audit_indexes = {index.name: index for index in table_indexes("audit_logs")}
    ddl = compile_index(audit_indexes["ix_audit_logs_case_id_created_at"]).upper()
    assert "CREATED_AT DESC" not in ddl


def test_partial_indexes_preserved_after_desc_changes() -> None:
    transaction_indexes = {index.name: index for index in table_indexes("transactions")}
    ddl = compile_index(transaction_indexes["uq_transactions_provider_payment_id"]).upper()
    assert "UNIQUE" in ddl
    assert "WHERE" in ddl
    assert "PROVIDER_PAYMENT_ID IS NOT NULL" in ddl

    action_indexes = {index.name: index for index in table_indexes("recovery_actions")}
    ddl = compile_index(action_indexes["uq_recovery_actions_one_executing"]).upper()
    assert "UNIQUE" in ddl
    assert "WHERE" in ddl
    assert "STATUS = 'EXECUTING'" in ddl

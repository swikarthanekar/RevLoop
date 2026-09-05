"""Alembic migration chain validation tests (no live PostgreSQL required)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REVISIONS = [
    ("m3r01_tenant_foundation", None),
    ("m3r02_revenue_sources", "m3r01_tenant_foundation"),
    ("m3r03_recovery_cases", "m3r02_revenue_sources"),
    ("m3r04_recovery_decisions", "m3r03_recovery_cases"),
    ("m3r05_recovery_outcomes", "m3r04_recovery_decisions"),
    ("m3r06_webhooks_audit_policy", "m3r05_recovery_outcomes"),
    ("m3r07_erv_breakdown", "m3r06_webhooks_audit_policy"),
]

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

API_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = API_ROOT / "alembic" / "versions"


def _alembic_config() -> Config:
    return Config(str(API_ROOT / "alembic.ini"))


def _revision_source(revision_id: str) -> str:
    matches = list(VERSIONS_DIR.glob(f"{revision_id}_*.py"))
    assert len(matches) == 1, f"expected one file for {revision_id}, found {matches}"
    return matches[0].read_text()


def test_every_revision_forms_one_linear_chain() -> None:
    """Asserted against REVISIONS rather than a hardcoded count, so adding a
    migration means updating one list instead of a magic number in two places."""
    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()
    assert heads == [REVISIONS[-1][0]]

    revisions = list(script.walk_revisions(base="base", head="heads"))
    revision_ids = {rev.revision for rev in revisions}
    assert len(revisions) == len(REVISIONS)
    assert revision_ids == {rev_id for rev_id, _ in REVISIONS}

    by_id = {rev.revision: rev for rev in revisions}
    for rev_id, parent in REVISIONS:
        assert by_id[rev_id].down_revision == parent


def test_migration_files_create_all_thirteen_application_tables() -> None:
    combined = "\n".join(_revision_source(rev_id) for rev_id, _ in REVISIONS)
    for table in EXPECTED_TABLES:
        assert f'CREATE TABLE {table}' in combined or f'CREATE TABLE {table} (' in combined


def test_revision_five_creates_verified_event_column_without_fk() -> None:
    source = _revision_source("m3r05_recovery_outcomes")
    assert "verified_event_id UUID" in source
    assert "fk_recovery_outcomes_verified_event_id_webhook_events" not in source


def test_revision_six_creates_webhook_events_then_deferred_fk() -> None:
    source = _revision_source("m3r06_webhooks_audit_policy")
    webhook_pos = source.index("CREATE TABLE webhook_events")
    fk_pos = source.index("fk_recovery_outcomes_verified_event_id_webhook_events")
    audit_pos = source.index("CREATE TABLE audit_logs")
    assert webhook_pos < fk_pos < audit_pos


def test_revision_six_downgrade_drops_fk_before_webhook_events() -> None:
    source = _revision_source("m3r06_webhooks_audit_policy")
    downgrade = source.split("def downgrade")[1]
    fk_name = "fk_recovery_outcomes_verified_event_id_webhook_events"
    fk_drop = downgrade.index(f'drop_constraint(\n        "{fk_name}"')
    webhook_drop = downgrade.index('op.drop_table("webhook_events")')
    assert fk_drop < webhook_drop


def test_critical_ddl_constructs_present_in_migration_chain() -> None:
    combined = "\n".join(_revision_source(rev_id) for rev_id, _ in REVISIONS).upper()
    assert "UUID" in combined
    assert "JSONB" in combined
    assert "CHAR(3)" in combined
    assert "NUMERIC(7, 6)" in combined
    assert "BIGINT" in combined
    assert "UQ_RECOVERY_CASES_ORGANIZATION_ID_SOURCE_EVENT_KEY" in combined
    assert "UQ_RECOVERY_ACTIONS_IDEMPOTENCY_KEY" in combined
    assert "UQ_WEBHOOK_EVENTS_PROVIDER_PROVIDER_EVENT_ID" in combined
    assert "UQ_RECOVERY_OUTCOMES_CASE_ID" in combined
    assert "FK_RECOVERY_RECOMMENDATIONS_RECOVERY_CASES_TENANT" in combined
    assert "FK_RECOVERY_ACTIONS_RECOVERY_CASES_TENANT" in combined
    assert "FK_RECOVERY_OUTCOMES_RECOVERY_CASES_TENANT" in combined
    assert "UQ_TRANSACTIONS_PROVIDER_PAYMENT_ID" in combined
    assert "PROVIDER_PAYMENT_ID IS NOT NULL" in combined
    assert "UQ_RECOVERY_ACTIONS_ONE_EXECUTING" in combined
    assert "STATUS = 'EXECUTING'" in combined
    assert "OPENED_AT DESC" in combined
    assert "RECEIVED_AT DESC" in combined
    assert "CREATED_AT DESC" in combined
    assert "POLICY_REASONS JSONB DEFAULT '[]'::JSONB" in combined
    assert "FACTORS JSONB DEFAULT '[]'::JSONB" in combined
    assert "ALLOWED_ACTION_TYPES JSONB DEFAULT '[]'::JSONB" in combined
    assert "FK_RECOVERY_OUTCOMES_VERIFIED_EVENT_ID_WEBHOOK_EVENTS" in combined


def test_critical_constraint_names_are_deterministic() -> None:
    combined = "\n".join(_revision_source(rev_id) for rev_id, _ in REVISIONS)
    expected = [
        "uq_recovery_cases_organization_id_source_event_key",
        "uq_recovery_actions_idempotency_key",
        "uq_recovery_actions_one_executing",
        "uq_recovery_outcomes_case_id",
        "fk_recovery_outcomes_verified_event_id_webhook_events",
        "uq_webhook_events_provider_provider_event_id",
        "fk_recovery_recommendations_recovery_cases_tenant",
        "fk_recovery_actions_recovery_cases_tenant",
        "fk_recovery_outcomes_recovery_cases_tenant",
    ]
    for name in expected:
        assert name in combined


def test_offline_sql_generation_renders_base_to_head(capsys) -> None:
    from alembic import command

    config = _alembic_config()
    command.upgrade(config, "head", sql=True)
    sql = capsys.readouterr().out.upper()
    assert "CREATE TABLE ORGANIZATIONS" in sql
    assert "CREATE TABLE WEBHOOK_EVENTS" in sql
    assert "FK_RECOVERY_OUTCOMES_VERIFIED_EVENT_ID_WEBHOOK_EVENTS" in sql
    assert "ALTER TABLE RECOVERY_OUTCOMES ADD CONSTRAINT" in sql

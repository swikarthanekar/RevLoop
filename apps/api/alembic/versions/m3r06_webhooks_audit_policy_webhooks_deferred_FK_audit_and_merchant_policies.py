"""webhooks deferred FK audit and merchant policies"""

from alembic import op

revision = "m3r06_webhooks_audit_policy"
down_revision = "m3r05_recovery_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE webhook_events (
	organization_id UUID NOT NULL,
	provider VARCHAR(32) NOT NULL,
	provider_event_id VARCHAR(160) NOT NULL,
	event_type VARCHAR(100) NOT NULL,
	provider_created_at TIMESTAMP WITH TIME ZONE,
	signature_valid BOOLEAN NOT NULL,
	processing_status VARCHAR(32) NOT NULL,
	payload JSONB DEFAULT '{}'::jsonb NOT NULL,
	received_at TIMESTAMP WITH TIME ZONE NOT NULL,
	processed_at TIMESTAMP WITH TIME ZONE,
	processing_error TEXT,
	id UUID NOT NULL,
	CONSTRAINT pk_webhook_events PRIMARY KEY (id),
	CONSTRAINT uq_webhook_events_provider_provider_event_id UNIQUE (provider, provider_event_id),
	CONSTRAINT ck_webhook_events_processing_status CHECK (processing_status IN ('RECEIVED', 'PROCESSED', 'IGNORED', 'FAILED')),
	CONSTRAINT fk_webhook_events_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id)
)""")
    op.execute(
        """CREATE INDEX ix_webhook_events_org_event_type_received_at """
        """ON webhook_events (organization_id, event_type, received_at DESC)"""
    )
    op.execute(
        """CREATE INDEX ix_webhook_events_organization_id_received_at """
        """ON webhook_events (organization_id, received_at DESC)"""
    )
    op.execute(
        """CREATE INDEX ix_webhook_events_processing_status_received_at """
        """ON webhook_events (processing_status, received_at)"""
    )
    op.create_foreign_key(
        "fk_recovery_outcomes_verified_event_id_webhook_events",
        "recovery_outcomes",
        "webhook_events",
        ["verified_event_id"],
        ["id"],
    )
    op.execute("""CREATE TABLE audit_logs (
	organization_id UUID NOT NULL,
	case_id UUID,
	actor_type VARCHAR(32) NOT NULL,
	actor_id VARCHAR(160),
	event_type VARCHAR(80) NOT NULL,
	summary TEXT NOT NULL,
	evidence JSONB DEFAULT '{}'::jsonb NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_audit_logs PRIMARY KEY (id),
	CONSTRAINT ck_audit_logs_actor_type CHECK (actor_type IN ('SYSTEM', 'USER', 'PROVIDER', 'MODEL')),
	CONSTRAINT fk_audit_logs_recovery_cases_tenant FOREIGN KEY(case_id, organization_id) REFERENCES recovery_cases (id, organization_id),
	CONSTRAINT fk_audit_logs_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id)
)""")
    op.execute("""CREATE INDEX ix_audit_logs_case_id_created_at ON audit_logs (case_id, created_at)""")
    op.execute(
        """CREATE INDEX ix_audit_logs_org_event_type_created_at """
        """ON audit_logs (organization_id, event_type, created_at DESC)"""
    )
    op.execute(
        """CREATE INDEX ix_audit_logs_organization_id_created_at """
        """ON audit_logs (organization_id, created_at DESC)"""
    )
    op.execute("""CREATE TABLE merchant_policies (
	organization_id UUID NOT NULL,
	auto_action_limit_minor BIGINT NOT NULL,
	max_recovery_attempts INTEGER NOT NULL,
	max_contacts_per_24h INTEGER NOT NULL,
	minimum_auto_confidence NUMERIC(7, 6) NOT NULL,
	cooldown_minutes INTEGER NOT NULL,
	automation_enabled BOOLEAN NOT NULL,
	allowed_action_types JSONB DEFAULT '[]'::jsonb NOT NULL,
	id UUID NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_merchant_policies PRIMARY KEY (id),
	CONSTRAINT uq_merchant_policies_organization_id UNIQUE (organization_id),
	CONSTRAINT ck_merchant_policies_auto_action_limit_minor_nonneg CHECK (auto_action_limit_minor >= 0),
	CONSTRAINT ck_merchant_policies_max_recovery_attempts_nonneg CHECK (max_recovery_attempts >= 0),
	CONSTRAINT ck_merchant_policies_max_contacts_per_24h_nonneg CHECK (max_contacts_per_24h >= 0),
	CONSTRAINT ck_merchant_policies_cooldown_minutes_nonneg CHECK (cooldown_minutes >= 0),
	CONSTRAINT ck_merchant_policies_minimum_auto_confidence_range CHECK (minimum_auto_confidence >= 0 AND minimum_auto_confidence <= 1),
	CONSTRAINT fk_merchant_policies_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id)
)""")


def downgrade() -> None:
    op.drop_table("merchant_policies")
    op.drop_table("audit_logs")
    op.drop_constraint(
        "fk_recovery_outcomes_verified_event_id_webhook_events",
        "recovery_outcomes",
        type_="foreignkey",
    )
    op.drop_table("webhook_events")

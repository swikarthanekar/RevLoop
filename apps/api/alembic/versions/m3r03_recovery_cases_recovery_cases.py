"""recovery cases"""

from alembic import op

revision = "m3r03_recovery_cases"
down_revision = "m3r02_revenue_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE recovery_cases (
	organization_id UUID NOT NULL, 
	customer_id UUID NOT NULL, 
	transaction_id UUID, 
	subscription_id UUID, 
	invoice_id UUID, 
	source_event_key VARCHAR(200) NOT NULL, 
	case_type VARCHAR(48) NOT NULL, 
	amount_at_risk_minor BIGINT NOT NULL, 
	currency CHAR(3) NOT NULL, 
	failure_category VARCHAR(64), 
	status VARCHAR(32) DEFAULT 'DETECTED' NOT NULL, 
	priority_score NUMERIC(7, 6), 
	recovery_probability NUMERIC(7, 6), 
	expected_recoverable_minor BIGINT, 
	current_analysis_run_id UUID, 
	opened_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_transition_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	version INTEGER DEFAULT 1 NOT NULL, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_recovery_cases PRIMARY KEY (id), 
	CONSTRAINT uq_recovery_cases_organization_id_source_event_key UNIQUE (organization_id, source_event_key), 
	CONSTRAINT uq_recovery_cases_id_organization_id UNIQUE (id, organization_id), 
	CONSTRAINT ck_recovery_cases_amount_at_risk_minor_positive CHECK (amount_at_risk_minor > 0), 
	CONSTRAINT ck_recovery_cases_expected_recoverable_minor_nonneg CHECK (expected_recoverable_minor IS NULL OR expected_recoverable_minor >= 0), 
	CONSTRAINT ck_recovery_cases_priority_score_range CHECK (priority_score IS NULL OR (priority_score >= 0 AND priority_score <= 1)), 
	CONSTRAINT ck_recovery_cases_recovery_probability_range CHECK (recovery_probability IS NULL OR (recovery_probability >= 0 AND recovery_probability <= 1)), 
	CONSTRAINT ck_recovery_cases_version_min CHECK (version >= 1), 
	CONSTRAINT ck_recovery_cases_payment_failure_source CHECK ((case_type != 'PAYMENT_FAILURE') OR (transaction_id IS NOT NULL AND subscription_id IS NULL)), 
	CONSTRAINT ck_recovery_cases_subscription_failure_source CHECK ((case_type != 'SUBSCRIPTION_FAILURE') OR (subscription_id IS NOT NULL)), 
	CONSTRAINT ck_recovery_cases_case_type CHECK (case_type IN ('PAYMENT_FAILURE', 'SUBSCRIPTION_FAILURE', 'OVERDUE_INVOICE')), 
	CONSTRAINT ck_recovery_cases_status CHECK (status IN ('DETECTED', 'ANALYZING', 'RECOMMENDED', 'AWAITING_APPROVAL', 'SCHEDULED', 'EXECUTING', 'WAITING_FOR_OUTCOME', 'RECOVERED', 'FAILED', 'STOPPED')), 
	CONSTRAINT fk_recovery_cases_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	CONSTRAINT fk_recovery_cases_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id), 
	CONSTRAINT fk_recovery_cases_transaction_id_transactions FOREIGN KEY(transaction_id) REFERENCES transactions (id), 
	CONSTRAINT fk_recovery_cases_subscription_id_subscriptions FOREIGN KEY(subscription_id) REFERENCES subscriptions (id), 
	CONSTRAINT fk_recovery_cases_invoice_id_invoices FOREIGN KEY(invoice_id) REFERENCES invoices (id)
)""")
    op.execute("""CREATE INDEX ix_recovery_cases_org_customer_opened_at ON recovery_cases (organization_id, customer_id, opened_at DESC)""")
    op.execute("""CREATE INDEX ix_recovery_cases_org_status_priority_score ON recovery_cases (organization_id, status, priority_score DESC)""")
    op.execute("""CREATE INDEX ix_recovery_cases_organization_id_opened_at ON recovery_cases (organization_id, opened_at DESC)""")
    op.execute("""CREATE INDEX ix_recovery_cases_subscription_id ON recovery_cases (subscription_id)""")
    op.execute("""CREATE INDEX ix_recovery_cases_transaction_id ON recovery_cases (transaction_id)""")


def downgrade() -> None:
    op.drop_table("recovery_cases")

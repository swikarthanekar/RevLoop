"""recovery recommendations and actions"""

from alembic import op

revision = "m3r04_recovery_decisions"
down_revision = "m3r03_recovery_cases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE recovery_recommendations (
	organization_id UUID NOT NULL, 
	case_id UUID NOT NULL, 
	analysis_run_id UUID NOT NULL, 
	action_type VARCHAR(64) NOT NULL, 
	rank INTEGER NOT NULL, 
	success_probability NUMERIC(7, 6) NOT NULL, 
	expected_recovered_minor BIGINT NOT NULL, 
	expected_value_minor BIGINT NOT NULL, 
	confidence NUMERIC(7, 6) NOT NULL, 
	policy_eligible BOOLEAN NOT NULL, 
	requires_approval BOOLEAN NOT NULL, 
	policy_reasons JSONB DEFAULT '[]'::jsonb NOT NULL, 
	factors JSONB DEFAULT '[]'::jsonb NOT NULL, 
	model_version VARCHAR(100) NOT NULL, 
	feature_schema_version VARCHAR(64) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_recovery_recommendations PRIMARY KEY (id), 
	CONSTRAINT fk_recovery_recommendations_recovery_cases_tenant FOREIGN KEY(case_id, organization_id) REFERENCES recovery_cases (id, organization_id), 
	CONSTRAINT uq_recovery_recommendations_case_analysis_action UNIQUE (case_id, analysis_run_id, action_type), 
	CONSTRAINT uq_recovery_recommendations_case_analysis_rank UNIQUE (case_id, analysis_run_id, rank), 
	CONSTRAINT ck_recovery_recommendations_rank_positive CHECK (rank > 0), 
	CONSTRAINT ck_recovery_recommendations_success_probability_range CHECK (success_probability >= 0 AND success_probability <= 1), 
	CONSTRAINT ck_recovery_recommendations_confidence_range CHECK (confidence >= 0 AND confidence <= 1), 
	CONSTRAINT ck_recovery_recommendations_action_type CHECK (action_type IN ('WAIT', 'RETRY_SAME_METHOD', 'REQUEST_ALTERNATE_PAYMENT_METHOD', 'CREATE_PAYMENT_LINK', 'SEND_RECOVERY_MESSAGE', 'ESCALATE_TO_HUMAN', 'STOP'))
)""")
    op.execute("""CREATE INDEX ix_recovery_recommendations_case_analysis_rank ON recovery_recommendations (case_id, analysis_run_id, rank)""")
    op.execute("""CREATE TABLE recovery_actions (
	organization_id UUID NOT NULL, 
	case_id UUID NOT NULL, 
	recommendation_id UUID, 
	action_type VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	attempt_number INTEGER NOT NULL, 
	requires_approval BOOLEAN NOT NULL, 
	approved_by UUID, 
	approved_at TIMESTAMP WITH TIME ZONE, 
	idempotency_key VARCHAR(160) NOT NULL, 
	request_fingerprint VARCHAR(128), 
	scheduled_for TIMESTAMP WITH TIME ZONE, 
	execution_started_at TIMESTAMP WITH TIME ZONE, 
	executed_at TIMESTAMP WITH TIME ZONE, 
	provider_reference VARCHAR(160), 
	provider_status VARCHAR(64), 
	error_category VARCHAR(64), 
	error_message TEXT, 
	metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_recovery_actions PRIMARY KEY (id), 
	CONSTRAINT fk_recovery_actions_recovery_cases_tenant FOREIGN KEY(case_id, organization_id) REFERENCES recovery_cases (id, organization_id), 
	CONSTRAINT uq_recovery_actions_idempotency_key UNIQUE (idempotency_key), 
	CONSTRAINT uq_recovery_actions_case_id_attempt_number UNIQUE (case_id, attempt_number), 
	CONSTRAINT ck_recovery_actions_attempt_number_min CHECK (attempt_number >= 1), 
	CONSTRAINT ck_recovery_actions_action_type CHECK (action_type IN ('WAIT', 'RETRY_SAME_METHOD', 'REQUEST_ALTERNATE_PAYMENT_METHOD', 'CREATE_PAYMENT_LINK', 'SEND_RECOVERY_MESSAGE', 'ESCALATE_TO_HUMAN', 'STOP')), 
	CONSTRAINT ck_recovery_actions_status CHECK (status IN ('PENDING_APPROVAL', 'SCHEDULED', 'EXECUTING', 'SUCCEEDED', 'FAILED', 'UNKNOWN', 'CANCELLED'))
)""")
    op.execute("""CREATE INDEX ix_recovery_actions_case_id_created_at ON recovery_actions (case_id, created_at)""")
    op.execute("""CREATE INDEX ix_recovery_actions_org_status_scheduled_for ON recovery_actions (organization_id, status, scheduled_for)""")
    op.execute("""CREATE UNIQUE INDEX uq_recovery_actions_one_executing ON recovery_actions (case_id) WHERE status = 'EXECUTING'""")


def downgrade() -> None:
    op.drop_table("recovery_actions")
    op.drop_table("recovery_recommendations")

"""recovery outcomes"""

from alembic import op

revision = "m3r05_recovery_outcomes"
down_revision = "m3r04_recovery_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE recovery_outcomes (
	organization_id UUID NOT NULL, 
	case_id UUID NOT NULL, 
	outcome VARCHAR(32) NOT NULL, 
	recovered_amount_minor BIGINT NOT NULL, 
	recovered_payment_id VARCHAR(128), 
	verification_source VARCHAR(32) NOT NULL, 
	verified_event_id UUID, 
	recovered_at TIMESTAMP WITH TIME ZONE, 
	time_to_recovery_seconds BIGINT, 
	metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_recovery_outcomes PRIMARY KEY (id), 
	CONSTRAINT fk_recovery_outcomes_recovery_cases_tenant FOREIGN KEY(case_id, organization_id) REFERENCES recovery_cases (id, organization_id), 
	CONSTRAINT uq_recovery_outcomes_case_id UNIQUE (case_id), 
	CONSTRAINT ck_recovery_outcomes_recovered_amount_minor_nonneg CHECK (recovered_amount_minor >= 0), 
	CONSTRAINT ck_recovery_outcomes_recovered_outcome_amount_positive CHECK ((outcome != 'RECOVERED') OR (recovered_amount_minor > 0)), 
	CONSTRAINT ck_recovery_outcomes_outcome CHECK (outcome IN ('RECOVERED', 'NOT_RECOVERED', 'STOPPED')), 
	CONSTRAINT ck_recovery_outcomes_verification_source CHECK (verification_source IN ('WEBHOOK', 'PROVIDER_FETCH', 'SIMULATED_BATCH'))
)""")


def downgrade() -> None:
    op.drop_table("recovery_outcomes")

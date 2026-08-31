"""revenue source entities"""

from alembic import op

revision = "m3r02_revenue_sources"
down_revision = "m3r01_tenant_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE transactions (
	organization_id UUID NOT NULL, 
	customer_id UUID NOT NULL, 
	provider VARCHAR(32) NOT NULL, 
	provider_payment_id VARCHAR(128), 
	provider_order_id VARCHAR(128), 
	amount_minor BIGINT NOT NULL, 
	currency CHAR(3) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	payment_method VARCHAR(48), 
	error_code VARCHAR(128), 
	error_reason VARCHAR(128), 
	error_source VARCHAR(128), 
	error_step VARCHAR(128), 
	error_description TEXT, 
	provider_created_at TIMESTAMP WITH TIME ZONE, 
	last_provider_event_at TIMESTAMP WITH TIME ZONE, 
	metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
	is_synthetic BOOLEAN DEFAULT false NOT NULL, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_transactions PRIMARY KEY (id), 
	CONSTRAINT ck_transactions_amount_minor_positive CHECK (amount_minor > 0), 
	CONSTRAINT fk_transactions_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	CONSTRAINT fk_transactions_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id)
)""")
    op.execute("""CREATE INDEX ix_transactions_org_customer_provider_created_at ON transactions (organization_id, customer_id, provider_created_at DESC)""")
    op.execute("""CREATE INDEX ix_transactions_org_payment_method_provider_created_at ON transactions (organization_id, payment_method, provider_created_at DESC)""")
    op.execute("""CREATE INDEX ix_transactions_organization_id_status ON transactions (organization_id, status)""")
    op.execute("""CREATE UNIQUE INDEX uq_transactions_provider_payment_id ON transactions (provider, provider_payment_id) WHERE provider_payment_id IS NOT NULL""")
    op.execute("""CREATE TABLE subscriptions (
	organization_id UUID NOT NULL, 
	customer_id UUID NOT NULL, 
	provider VARCHAR(32) NOT NULL, 
	provider_subscription_id VARCHAR(128) NOT NULL, 
	amount_minor BIGINT NOT NULL, 
	currency CHAR(3) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	retry_count INTEGER DEFAULT 0 NOT NULL, 
	current_period_end TIMESTAMP WITH TIME ZONE, 
	next_charge_at TIMESTAMP WITH TIME ZONE, 
	last_provider_event_at TIMESTAMP WITH TIME ZONE, 
	metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
	is_synthetic BOOLEAN DEFAULT false NOT NULL, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_subscriptions PRIMARY KEY (id), 
	CONSTRAINT uq_subscriptions_provider_provider_subscription_id UNIQUE (provider, provider_subscription_id), 
	CONSTRAINT ck_subscriptions_retry_count_nonneg CHECK (retry_count >= 0), 
	CONSTRAINT ck_subscriptions_amount_minor_positive CHECK (amount_minor > 0), 
	CONSTRAINT fk_subscriptions_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	CONSTRAINT fk_subscriptions_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id)
)""")
    op.execute("""CREATE INDEX ix_subscriptions_organization_id_customer_id ON subscriptions (organization_id, customer_id)""")
    op.execute("""CREATE INDEX ix_subscriptions_organization_id_status ON subscriptions (organization_id, status)""")
    op.execute("""CREATE TABLE invoices (
	organization_id UUID NOT NULL, 
	customer_id UUID NOT NULL, 
	provider VARCHAR(32) NOT NULL, 
	provider_invoice_id VARCHAR(128), 
	amount_due_minor BIGINT NOT NULL, 
	amount_paid_minor BIGINT NOT NULL, 
	currency CHAR(3) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	due_at TIMESTAMP WITH TIME ZONE, 
	paid_at TIMESTAMP WITH TIME ZONE, 
	is_synthetic BOOLEAN DEFAULT false NOT NULL, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_invoices PRIMARY KEY (id), 
	CONSTRAINT ck_invoices_amount_due_minor_nonneg CHECK (amount_due_minor >= 0), 
	CONSTRAINT ck_invoices_amount_paid_minor_nonneg CHECK (amount_paid_minor >= 0), 
	CONSTRAINT fk_invoices_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	CONSTRAINT fk_invoices_customer_id_customers FOREIGN KEY(customer_id) REFERENCES customers (id)
)""")


def downgrade() -> None:
    op.drop_table("invoices")
    op.drop_table("subscriptions")
    op.drop_table("transactions")

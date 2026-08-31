"""tenant foundation"""

from alembic import op

revision = "m3r01_tenant_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE organizations (
	name VARCHAR(160) NOT NULL, 
	currency CHAR(3) DEFAULT 'INR' NOT NULL, 
	automation_enabled BOOLEAN DEFAULT true NOT NULL, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_organizations PRIMARY KEY (id)
)""")
    op.execute("""CREATE TABLE user_profiles (
	organization_id UUID NOT NULL, 
	auth_user_id UUID NOT NULL, 
	role VARCHAR(32) NOT NULL, 
	id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_user_profiles PRIMARY KEY (id), 
	CONSTRAINT uq_user_profiles_auth_user_id UNIQUE (auth_user_id), 
	CONSTRAINT ck_user_profiles_role CHECK (role IN ('ADMIN', 'OPERATOR', 'ANALYST')), 
	CONSTRAINT fk_user_profiles_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id)
)""")
    op.execute("""CREATE INDEX ix_user_profiles_organization_id ON user_profiles (organization_id)""")
    op.execute("""CREATE TABLE customers (
	organization_id UUID NOT NULL, 
	external_id VARCHAR(128) NOT NULL, 
	display_name VARCHAR(200) NOT NULL, 
	email VARCHAR(320), 
	phone VARCHAR(32), 
	segment VARCHAR(32) DEFAULT 'REGULAR' NOT NULL, 
	lifetime_value_minor BIGINT NOT NULL, 
	is_synthetic BOOLEAN DEFAULT false NOT NULL, 
	id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_customers PRIMARY KEY (id), 
	CONSTRAINT uq_customers_organization_id_external_id UNIQUE (organization_id, external_id), 
	CONSTRAINT ck_customers_lifetime_value_minor_nonneg CHECK (lifetime_value_minor >= 0), 
	CONSTRAINT fk_customers_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id)
)""")
    op.execute("""CREATE INDEX ix_customers_organization_id_segment ON customers (organization_id, segment)""")


def downgrade() -> None:
    op.drop_table("customers")
    op.drop_table("user_profiles")
    op.drop_table("organizations")

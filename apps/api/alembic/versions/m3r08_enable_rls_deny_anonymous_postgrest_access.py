"""enable row level security on every application table

Supabase exposes the `public` schema through PostgREST, and the browser bundle
necessarily ships the project URL and the anon key because Supabase Auth needs
both to sign a user in. Those two facts together mean that with RLS disabled,
anyone who views source on the deployed frontend can read and write every table
directly, bypassing the API entirely.

RevLoop never uses PostgREST. The frontend's Supabase client only ever calls
`auth.*`; all data travels through the FastAPI service, which enforces tenant
scoping and role checks on every request. So the correct posture for the Data
API is "closed", and enabling RLS with no policies expresses exactly that:
`anon` and `authenticated` match no policy and therefore see no rows.

WHY THIS DOES NOT AFFECT THE APPLICATION

The API connects as the role that owns these tables, and PostgreSQL exempts a
table's owner from its row level security unless the table is additionally set
to FORCE ROW LEVEL SECURITY, which is deliberately not done here. Enabling RLS
therefore closes the PostgREST path and leaves the service's own queries
untouched. The same holds for local development and CI, where the migration
runs as the owner of a plain PostgreSQL database.

Adding a policy later is what grants access; until then the default is denial,
which is the safe direction for a table to fail in.
"""

from alembic import op

revision = "m3r08_enable_rls"
down_revision = "m3r07_erv_breakdown"
branch_labels = None
depends_on = None

#: Every table in the `public` schema, which is the schema PostgREST exposes.
#: `alembic_version` is included deliberately: it is as reachable as any other
#: table over the Data API, and leaving it open would publish the schema
#: revision this deployment is running.
_TABLES = (
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
    "alembic_version",
)


def upgrade() -> None:
    for table in _TABLES:
        # No policy accompanies this: the absence of one is what denies.
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")

"""persist the ERV component breakdown on each recommendation

Expected value is already computed from five components -- expected recovery,
action cost, fatigue penalty, operational risk penalty and delay penalty -- but
only the first and the net total were stored. Showing the arithmetic therefore
meant recomputing the components on read, which cannot be done exactly: the
fatigue penalty depends on `contacts_last_24h` at the moment of analysis, and
that is not persisted anywhere. A recomputed waterfall could silently fail to
sum to the stored `expected_value_minor`, which is precisely the kind of number
that must never be approximated.

Storing what was actually computed makes the breakdown exact and auditable.

Nullable on purpose: rows written before this migration have no breakdown, and
the read path omits the waterfall for them rather than inventing one.
"""

from alembic import op

revision = "m3r07_erv_breakdown"
down_revision = "m3r06_webhooks_audit_policy"
branch_labels = None
depends_on = None

#: Every component is a non-negative integer in minor units, matching the
#: money representation used end to end. `expected_value_minor` (already
#: present) is the signed net and can legitimately be negative, which is why it
#: is not constrained here.
_COLUMNS = (
    "erv_action_cost_minor",
    "erv_fatigue_penalty_minor",
    "erv_operational_risk_penalty_minor",
    "erv_delay_penalty_minor",
)


def upgrade() -> None:
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE recovery_recommendations ADD COLUMN {column} BIGINT")
        op.execute(
            "ALTER TABLE recovery_recommendations "
            f"ADD CONSTRAINT ck_recovery_recommendations_{column}_nonneg "
            f"CHECK ({column} IS NULL OR {column} >= 0)"
        )


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.execute(
            "ALTER TABLE recovery_recommendations "
            f"DROP CONSTRAINT ck_recovery_recommendations_{column}_nonneg"
        )
        op.execute(f"ALTER TABLE recovery_recommendations DROP COLUMN {column}")

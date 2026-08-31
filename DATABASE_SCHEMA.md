# RevLoop — PostgreSQL Database Schema

**Status:** Phase 0 schema contract  
**Database:** PostgreSQL 15+ compatible  
**ORM:** SQLAlchemy 2.x  
**Migrations:** Alembic

## 1. Global rules

### 1.1 IDs
Use UUID primary keys generated server-side (`uuid4` in application or database UUID default). Do not expose sequential IDs as authorization boundaries.

### 1.2 Money
- Store all money as `BIGINT` integer **minor units**.
- INR ₹4,999.00 is stored as `499900` paise.
- Never use `FLOAT`, `REAL`, JavaScript floating-point calculations, or `NUMERIC(10,2)` for authoritative money fields.
- API field names should end in `_minor` when ambiguity exists.

### 1.3 Probabilities/scores
Use `NUMERIC(7,6)` or equivalent to store [0,1] model probability/confidence. Validate range in application and DB check constraints where practical.

### 1.4 Timestamps
- `TIMESTAMPTZ` only.
- Application operates in UTC.
- Use `created_at DEFAULT now()` and explicit `updated_at` where mutable.
- Provider timestamps are stored separately from receive/process timestamps.

### 1.5 Tenant scoping
Every tenant-owned business table contains `organization_id UUID NOT NULL`.

For child tables of a case, use composite foreign-key consistency where practical:
- `UNIQUE (id, organization_id)` on parent;
- child FK `(case_id, organization_id) -> recovery_cases(id, organization_id)`.

This prevents accidental cross-tenant references at the database layer.

### 1.6 JSON
Use `JSONB` for provider metadata/evidence only. Do not place query-critical fields solely inside JSON.

## 2. Enumerations

Implementation recommendation: Python `StrEnum` + PostgreSQL `VARCHAR` with `CHECK` constraints for easier hackathon migrations. Do not create a new PostgreSQL enum for every value during rapid iteration.

### Recovery case statuses

```text
DETECTED
ANALYZING
RECOMMENDED
AWAITING_APPROVAL
SCHEDULED
EXECUTING
WAITING_FOR_OUTCOME
RECOVERED
FAILED
STOPPED
```

### Case types

```text
PAYMENT_FAILURE
SUBSCRIPTION_FAILURE
OVERDUE_INVOICE   # reserved P1
```

### Action types

```text
WAIT
RETRY_SAME_METHOD
REQUEST_ALTERNATE_PAYMENT_METHOD
CREATE_PAYMENT_LINK
SEND_RECOVERY_MESSAGE
ESCALATE_TO_HUMAN
STOP
```

### Action statuses

```text
PENDING_APPROVAL
SCHEDULED
EXECUTING
SUCCEEDED
FAILED
UNKNOWN
CANCELLED
```

## 3. Migration order

Use this dependency order:

1. `organizations`
2. `user_profiles`
3. `customers`
4. `transactions`
5. `subscriptions`
6. `invoices` (schema may exist but APIs deferred)
7. `recovery_cases`
8. `recovery_recommendations`
9. `recovery_actions`
10. `recovery_outcomes`
11. `webhook_events`
12. `audit_logs`
13. `merchant_policies`
14. optional analytics indexes/materialized helpers only after profiling

Do not combine every table into one opaque migration after initial scaffold. Keep dependency-safe revisions.

## 4. Tables

### 4.1 `organizations`

| Column | Type | Null | Rules |
|---|---|---:|---|
| id | UUID | no | PK |
| name | VARCHAR(160) | no | |
| currency | CHAR(3) | no | default `INR` |
| automation_enabled | BOOLEAN | no | default true in demo |
| created_at | TIMESTAMPTZ | no | default now |
| updated_at | TIMESTAMPTZ | no | |

Indexes:
- PK `id`.

### 4.2 `user_profiles`

| Column | Type | Null | Rules |
|---|---|---:|---|
| id | UUID | no | PK |
| organization_id | UUID | no | FK organizations |
| auth_user_id | UUID | no | unique |
| role | VARCHAR(32) | no | `ADMIN`, `OPERATOR`, `ANALYST` |
| created_at | TIMESTAMPTZ | no | |

Indexes:
- unique `auth_user_id`;
- `organization_id`.

### 4.3 `customers`

| Column | Type | Null | Rules |
|---|---|---:|---|
| id | UUID | no | PK |
| organization_id | UUID | no | FK |
| external_id | VARCHAR(128) | no | merchant identifier |
| display_name | VARCHAR(200) | no | |
| email | VARCHAR(320) | yes | synthetic/demo only for seed |
| phone | VARCHAR(32) | yes | synthetic/demo only |
| segment | VARCHAR(32) | no | default `REGULAR` |
| lifetime_value_minor | BIGINT | no | >=0 |
| is_synthetic | BOOLEAN | no | default false |
| created_at | TIMESTAMPTZ | no | |
| updated_at | TIMESTAMPTZ | no | |

Constraints/indexes:
- `UNIQUE(organization_id, external_id)`;
- index `(organization_id, segment)`;
- check `lifetime_value_minor >= 0`.

### 4.4 `transactions`

| Column | Type | Null | Rules |
|---|---|---:|---|
| id | UUID | no | PK |
| organization_id | UUID | no | FK |
| customer_id | UUID | no | FK customers |
| provider | VARCHAR(32) | no | `RAZORPAY`/`SYNTHETIC` |
| provider_payment_id | VARCHAR(128) | yes | unique when non-null |
| provider_order_id | VARCHAR(128) | yes | |
| amount_minor | BIGINT | no | >0 |
| currency | CHAR(3) | no | |
| status | VARCHAR(32) | no | normalized provider status |
| payment_method | VARCHAR(48) | yes | |
| error_code | VARCHAR(128) | yes | |
| error_reason | VARCHAR(128) | yes | |
| error_source | VARCHAR(128) | yes | |
| error_step | VARCHAR(128) | yes | |
| error_description | TEXT | yes | |
| provider_created_at | TIMESTAMPTZ | yes | |
| last_provider_event_at | TIMESTAMPTZ | yes | stale-event guard |
| metadata | JSONB | no | default `{}` |
| is_synthetic | BOOLEAN | no | |
| created_at | TIMESTAMPTZ | no | |
| updated_at | TIMESTAMPTZ | no | |

Indexes/constraints:
- partial unique index on `(provider, provider_payment_id)` where `provider_payment_id IS NOT NULL`;
- `(organization_id, customer_id, provider_created_at DESC)`;
- `(organization_id, status)`;
- `(organization_id, payment_method, provider_created_at DESC)`;
- check `amount_minor > 0`.

### 4.5 `subscriptions`

| Column | Type | Null | Rules |
|---|---|---:|---|
| id | UUID | no | PK |
| organization_id | UUID | no | FK |
| customer_id | UUID | no | FK |
| provider | VARCHAR(32) | no | |
| provider_subscription_id | VARCHAR(128) | no | |
| amount_minor | BIGINT | no | >0 |
| currency | CHAR(3) | no | |
| status | VARCHAR(32) | no | provider-normalized |
| retry_count | INTEGER | no | default 0 |
| current_period_end | TIMESTAMPTZ | yes | |
| next_charge_at | TIMESTAMPTZ | yes | |
| last_provider_event_at | TIMESTAMPTZ | yes | |
| metadata | JSONB | no | default `{}` |
| is_synthetic | BOOLEAN | no | |
| created_at | TIMESTAMPTZ | no | |
| updated_at | TIMESTAMPTZ | no | |

Indexes/constraints:
- `UNIQUE(provider, provider_subscription_id)`;
- `(organization_id, customer_id)`;
- `(organization_id, status)`;
- check `retry_count >= 0`;
- check `amount_minor > 0`.

### 4.6 `invoices` — P1 schema reservation

Include only if doing so does not delay P0 migrations.

| Column | Type | Null |
|---|---|---:|
| id | UUID PK | no |
| organization_id | UUID | no |
| customer_id | UUID | no |
| provider | VARCHAR(32) | no |
| provider_invoice_id | VARCHAR(128) | yes |
| amount_due_minor | BIGINT | no |
| amount_paid_minor | BIGINT | no |
| currency | CHAR(3) | no |
| status | VARCHAR(32) | no |
| due_at | TIMESTAMPTZ | yes |
| paid_at | TIMESTAMPTZ | yes |
| is_synthetic | BOOLEAN | no |
| created_at | TIMESTAMPTZ | no |
| updated_at | TIMESTAMPTZ | no |

Do not build invoice UI/API until P0 is stable.

### 4.7 `recovery_cases`

| Column | Type | Null | Rules |
|---|---|---:|---|
| id | UUID | no | PK |
| organization_id | UUID | no | FK |
| customer_id | UUID | no | FK |
| transaction_id | UUID | yes | FK |
| subscription_id | UUID | yes | FK |
| invoice_id | UUID | yes | reserved P1 |
| source_event_key | VARCHAR(200) | no | dedupes case creation |
| case_type | VARCHAR(48) | no | |
| amount_at_risk_minor | BIGINT | no | >0 |
| currency | CHAR(3) | no | |
| failure_category | VARCHAR(64) | yes | set by normalizer |
| status | VARCHAR(32) | no | default `DETECTED` |
| priority_score | NUMERIC(7,6) | yes | [0,1] |
| recovery_probability | NUMERIC(7,6) | yes | recommended action probability |
| expected_recoverable_minor | BIGINT | yes | >=0 |
| current_analysis_run_id | UUID | yes | identifies latest analysis snapshot |
| opened_at | TIMESTAMPTZ | no | |
| last_transition_at | TIMESTAMPTZ | no | |
| resolved_at | TIMESTAMPTZ | yes | terminal only |
| version | INTEGER | no | default 1 optimistic concurrency |
| created_at | TIMESTAMPTZ | no | |
| updated_at | TIMESTAMPTZ | no | |

Constraints:
- `UNIQUE(organization_id, source_event_key)`;
- `UNIQUE(id, organization_id)` for composite children;
- check `amount_at_risk_minor > 0`;
- checks probability/priority ranges;
- source XOR constraint for P0:
  - `PAYMENT_FAILURE` => transaction_id non-null, subscription_id null;
  - `SUBSCRIPTION_FAILURE` => subscription_id non-null; transaction_id may reference latest failed attempt only if schema allows, but primary source remains subscription;
- `resolved_at IS NOT NULL` iff terminal is preferred but may be enforced in application first.

Indexes:
- `(organization_id, status, priority_score DESC)`;
- `(organization_id, opened_at DESC)`;
- `(organization_id, customer_id, opened_at DESC)`;
- `transaction_id`;
- `subscription_id`.

### 4.8 `recovery_recommendations`

| Column | Type | Null |
|---|---|---:|
| id | UUID PK | no |
| organization_id | UUID | no |
| case_id | UUID | no |
| analysis_run_id | UUID | no |
| action_type | VARCHAR(64) | no |
| rank | INTEGER | no |
| success_probability | NUMERIC(7,6) | no |
| expected_recovered_minor | BIGINT | no |
| expected_value_minor | BIGINT | no |
| confidence | NUMERIC(7,6) | no |
| policy_eligible | BOOLEAN | no |
| requires_approval | BOOLEAN | no |
| policy_reasons | JSONB | no |
| factors | JSONB | no |
| model_version | VARCHAR(100) | no |
| feature_schema_version | VARCHAR(64) | no |
| created_at | TIMESTAMPTZ | no |

Constraints/indexes:
- composite FK `(case_id, organization_id)`;
- `UNIQUE(case_id, analysis_run_id, action_type)`;
- `UNIQUE(case_id, analysis_run_id, rank)`;
- index `(case_id, analysis_run_id, rank)`;
- checks probability/confidence [0,1];
- check `rank > 0`.

### 4.9 `recovery_actions`

| Column | Type | Null |
|---|---|---:|
| id | UUID PK | no |
| organization_id | UUID | no |
| case_id | UUID | no |
| recommendation_id | UUID | yes |
| action_type | VARCHAR(64) | no |
| status | VARCHAR(32) | no |
| attempt_number | INTEGER | no |
| requires_approval | BOOLEAN | no |
| approved_by | UUID | yes |
| approved_at | TIMESTAMPTZ | yes |
| idempotency_key | VARCHAR(160) | no |
| request_fingerprint | VARCHAR(128) | yes |
| scheduled_for | TIMESTAMPTZ | yes |
| execution_started_at | TIMESTAMPTZ | yes |
| executed_at | TIMESTAMPTZ | yes |
| provider_reference | VARCHAR(160) | yes |
| provider_status | VARCHAR(64) | yes |
| error_category | VARCHAR(64) | yes |
| error_message | TEXT | yes |
| metadata | JSONB | no |
| created_at | TIMESTAMPTZ | no |
| updated_at | TIMESTAMPTZ | no |

Constraints/indexes:
- `UNIQUE(idempotency_key)`;
- composite FK to case;
- `UNIQUE(case_id, attempt_number)`;
- check `attempt_number >= 1`;
- `(organization_id, status, scheduled_for)`;
- `(case_id, created_at)`.

Optional PostgreSQL partial uniqueness to prevent two executing actions per case:

```sql
CREATE UNIQUE INDEX uq_one_executing_action_per_case
ON recovery_actions(case_id)
WHERE status = 'EXECUTING';
```

### 4.10 `recovery_outcomes`

| Column | Type | Null |
|---|---|---:|
| id | UUID PK | no |
| organization_id | UUID | no |
| case_id | UUID | no |
| outcome | VARCHAR(32) | no |
| recovered_amount_minor | BIGINT | no |
| recovered_payment_id | VARCHAR(128) | yes |
| verification_source | VARCHAR(32) | no |
| verified_event_id | UUID | yes | FK webhook_events, optional circular migration added later |
| recovered_at | TIMESTAMPTZ | yes |
| time_to_recovery_seconds | BIGINT | yes |
| metadata | JSONB | no |
| created_at | TIMESTAMPTZ | no |

Constraints:
- `UNIQUE(case_id)`;
- composite FK to case;
- check `recovered_amount_minor >= 0`;
- application/DB check: outcome `RECOVERED` requires recovered amount >0.

### 4.11 `webhook_events`

| Column | Type | Null |
|---|---|---:|
| id | UUID PK | no |
| organization_id | UUID | no |
| provider | VARCHAR(32) | no |
| provider_event_id | VARCHAR(160) | no |
| event_type | VARCHAR(100) | no |
| provider_created_at | TIMESTAMPTZ | yes |
| signature_valid | BOOLEAN | no |
| processing_status | VARCHAR(32) | no |
| payload | JSONB | no |
| received_at | TIMESTAMPTZ | no |
| processed_at | TIMESTAMPTZ | yes |
| processing_error | TEXT | yes |

Constraints/indexes:
- `UNIQUE(provider, provider_event_id)` — hard idempotency boundary;
- `(organization_id, received_at DESC)`;
- `(organization_id, event_type, received_at DESC)`;
- `(processing_status, received_at)`.

Note: if invalid-signature requests should not retain attacker-controlled body, log only minimal metadata instead of storing payload. P0 preferred behavior: reject before insert, and store a security log without body.

### 4.12 `audit_logs`

| Column | Type | Null |
|---|---|---:|
| id | UUID PK | no |
| organization_id | UUID | no |
| case_id | UUID | yes |
| actor_type | VARCHAR(32) | no |
| actor_id | VARCHAR(160) | yes |
| event_type | VARCHAR(80) | no |
| summary | TEXT | no |
| evidence | JSONB | no |
| created_at | TIMESTAMPTZ | no |

Indexes:
- `(organization_id, created_at DESC)`;
- `(case_id, created_at)`;
- `(organization_id, event_type, created_at DESC)`.

No update/delete through normal application code.

### 4.13 `merchant_policies`

One active policy row per organization for P0.

| Column | Type | Null |
|---|---|---:|
| id | UUID PK | no |
| organization_id | UUID | no |
| auto_action_limit_minor | BIGINT | no |
| max_recovery_attempts | INTEGER | no |
| max_contacts_per_24h | INTEGER | no |
| minimum_auto_confidence | NUMERIC(7,6) | no |
| cooldown_minutes | INTEGER | no |
| automation_enabled | BOOLEAN | no |
| allowed_action_types | JSONB | no |
| created_at | TIMESTAMPTZ | no |
| updated_at | TIMESTAMPTZ | no |

Constraints:
- `UNIQUE(organization_id)`;
- non-negative checks;
- confidence [0,1].

## 5. Idempotency design

### Webhook idempotency
Primary guard:

```text
UNIQUE(provider, provider_event_id)
```

Processing pattern:
1. verify signature;
2. attempt insert `RECEIVED`;
3. on uniqueness conflict, return 200/204 idempotently;
4. only the successful inserter performs event processing.

### Recovery case idempotency
`source_event_key` is a deterministic business key, for example:

```text
razorpay:payment_failed:<payment_id>
razorpay:subscription_pending:<subscription_id>:<billing_cycle_or_provider_event_key>
```

Do not use a changing random UUID as the only dedup key.

### Recovery action idempotency
Construct a stable local key from immutable intent:

```text
recovery:<case_id>:<attempt_number>:<action_type>
```

Store before side effect and enforce unique index.

For Payment Links also create a provider `reference_id` derived from the action ID/key and <= provider limit. Fetch/reconcile existing provider reference before creating another after uncertain failure.

## 6. Transaction boundaries

Use DB transactions for:

### A. Case creation
- upsert source entity;
- create case if absent;
- audit record.

### B. Recommendation publication
- insert all rows for `analysis_run_id`;
- update case analysis pointers/scores;
- transition case to `RECOMMENDED`;
- audit.

### C. Action intent
- create action;
- transition case;
- audit;
- commit;
- **then** perform external network side effect.

### D. Outcome resolution
- insert exactly one outcome;
- transition case to terminal status;
- audit;
- commit atomically.

## 7. Optimistic concurrency

`recovery_cases.version` increments on every state transition.

Workflow update should behave like:

```sql
UPDATE recovery_cases
SET status = :new_status,
    version = version + 1,
    last_transition_at = now()
WHERE id = :id
  AND version = :expected_version;
```

If zero rows change, reload and re-evaluate rather than forcing state.

## 8. Seed/demo requirements

Seed script must create:
- one demo organization;
- demo user profile or setup instructions;
- 50+ customers;
- 500+ transactions;
- 80–120 open/historical cases;
- recommendation/action/outcome history;
- a few deterministic demo cases reserved for live story.

Every synthetic record: `is_synthetic = true` where field exists; audit/demo analytics must expose the source label.

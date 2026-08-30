# RecoverIQ — P0 API Contracts

**Status:** Initial P0 HTTP contract  
**Base path:** `/api/v1`  
**Format:** JSON over HTTPS except raw webhook request body  
**Source of truth:** FastAPI OpenAPI generated from these contracts. Frontend types should be generated from OpenAPI.

## 1. Common conventions

### Authentication
Authenticated business endpoints require:

```http
Authorization: Bearer <Supabase JWT>
```

The backend validates signature/claims and resolves `organization_id` and role from server-side user profile. The client must not be allowed to switch tenant by passing arbitrary organization IDs.

### Roles

| Role | Read | Analyze | Execute safe action | Approve high-risk action |
|---|---:|---:|---:|---:|
| ANALYST | yes | yes | no | no |
| OPERATOR | yes | yes | yes | limited/no depending policy |
| ADMIN | yes | yes | yes | yes |

For hackathon simplicity, `OPERATOR` may execute already policy-eligible automatic actions; `ADMIN` approves approval-gated actions.

### Money
All API money fields are integer minor units and are named with `_minor` where not obvious.

### Pagination
Use cursor or page pagination consistently. P0 recommendation: simple `limit` + `offset` for Recovery Opportunities because dataset is small.

Defaults:

```text
limit=25
max_limit=100
offset=0
```

### Error schema

```json
{
  "error": {
    "code": "CASE_NOT_FOUND",
    "message": "Recovery case was not found.",
    "details": {},
    "request_id": "req_..."
  }
}
```

Never return stack traces to browser.

## 2. Health

### `GET /health`

Auth: none.

Response `200`:

```json
{
  "status": "ok",
  "database": "ok",
  "model": "loaded",
  "version": "0.1.0"
}
```

The health route must not call Razorpay or the LLM on every request.

## 3. Dashboard

### `GET /api/v1/dashboard/summary`

Auth: any authenticated role.

Query params:
- optional `from` ISO timestamp;
- optional `to` ISO timestamp;
- optional `source=all|synthetic|razorpay_test`.

Response:

```json
{
  "currency": "INR",
  "revenue_at_risk_minor": 48200000,
  "revenue_recovered_minor": 31600000,
  "baseline_recovered_minor": 23400000,
  "incremental_recovered_minor": 8200000,
  "recovery_rate": 0.655602,
  "active_cases": 47,
  "recovered_cases": 61,
  "average_recovery_seconds": 5130,
  "recovery_trend": [
    {
      "date": "2026-08-29",
      "at_risk_minor": 9200000,
      "recovered_minor": 6100000
    }
  ],
  "action_effectiveness": [
    {
      "action_type": "REQUEST_ALTERNATE_PAYMENT_METHOD",
      "attempted": 21,
      "recovered": 15,
      "recovery_rate": 0.714286,
      "recovered_minor": 8700000
    }
  ],
  "failure_breakdown": [
    {
      "failure_category": "PAYMENT_RAIL_DOWNTIME",
      "cases": 18,
      "amount_minor": 6600000
    }
  ],
  "source_label": "SYNTHETIC_DEMO"
}
```

Validation:
- `to >= from`;
- max range may be capped if needed.

Errors: `401`, `403`, `422`, `500`.

## 4. Recovery Opportunities

### `GET /api/v1/recovery-cases`

Auth: any authenticated role.

Query parameters:

```text
status               optional repeated/comma list
case_type             optional
failure_category      optional
min_amount_minor      optional integer >=0
max_amount_minor      optional integer >= min
min_confidence        optional 0..1
customer_id           optional UUID
search                optional display-name/external-id query
sort                   priority_desc | amount_desc | opened_desc
limit                  1..100
 offset                 >=0
```

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "customer": {
        "id": "uuid",
        "display_name": "Acme Learning",
        "segment": "HIGH_VALUE"
      },
      "case_type": "PAYMENT_FAILURE",
      "amount_at_risk_minor": 499900,
      "currency": "INR",
      "failure_category": "PAYMENT_RAIL_DOWNTIME",
      "status": "RECOMMENDED",
      "priority_score": 0.891200,
      "recovery_probability": 0.820000,
      "expected_recoverable_minor": 409918,
      "recommended_action": "REQUEST_ALTERNATE_PAYMENT_METHOD",
      "confidence": 0.870000,
      "opened_at": "2026-08-30T08:20:00Z"
    }
  ],
  "total": 47,
  "limit": 25,
  "offset": 0
}
```

Errors: `401`, `403`, `422`, `500`.

## 5. Case detail

### `GET /api/v1/recovery-cases/{case_id}`

Auth: any authenticated role in same organization.

Response:

```json
{
  "case": {
    "id": "uuid",
    "case_type": "PAYMENT_FAILURE",
    "status": "RECOMMENDED",
    "amount_at_risk_minor": 499900,
    "currency": "INR",
    "failure_category": "PAYMENT_RAIL_DOWNTIME",
    "opened_at": "...",
    "last_transition_at": "...",
    "version": 4
  },
  "customer": {
    "id": "uuid",
    "display_name": "Acme Learning",
    "segment": "HIGH_VALUE",
    "lifetime_value_minor": 17800000
  },
  "source": {
    "type": "TRANSACTION",
    "transaction_id": "uuid",
    "provider_payment_id": "pay_...",
    "payment_method": "upi",
    "provider_status": "failed",
    "failure_evidence": {
      "error_code": "...",
      "error_reason": "...",
      "error_source": "...",
      "error_step": "..."
    }
  },
  "analysis": {
    "analysis_run_id": "uuid",
    "model_version": "lr-v1.0.0",
    "feature_schema_version": "recovery_features_v1",
    "selected_action": "REQUEST_ALTERNATE_PAYMENT_METHOD",
    "confidence": 0.87,
    "candidates": [
      {
        "action_type": "REQUEST_ALTERNATE_PAYMENT_METHOD",
        "rank": 1,
        "success_probability": 0.82,
        "expected_recovered_minor": 409918,
        "expected_value_minor": 402500,
        "policy_eligible": true,
        "requires_approval": false,
        "policy_reasons": [],
        "factors": [
          {"code": "ACTIVE_UPI_DOWNTIME", "impact": "HIGH", "source": "RAZORPAY_DOWNTIME"}
        ]
      }
    ],
    "structured_explanation": {
      "summary": "Alternative payment is preferred because the failed rail is degraded.",
      "evidence": ["UPI rail degradation is active", "Customer recently paid successfully by card"],
      "safety": ["Amount is below automatic-action limit"]
    }
  },
  "latest_action": null,
  "outcome": null
}
```

Errors:
- `404 CASE_NOT_FOUND`;
- `403 TENANT_ACCESS_DENIED`.

## 6. Analyze/re-analyze case

### `POST /api/v1/recovery-cases/{case_id}/analyze`

Auth: `ANALYST`, `OPERATOR`, `ADMIN`.

Request:

```json
{
  "reason": "MANUAL_ANALYSIS"
}
```

`reason` enum:
- `MANUAL_ANALYSIS`
- `SCHEDULED_REEVALUATION`
- `NEW_PROVIDER_EVIDENCE`

The browser should normally send only `MANUAL_ANALYSIS`. Internal workers call application services directly or a protected internal route, not user routes.

Behavior:
- only allowed from states permitted by state machine;
- creates new immutable analysis run;
- never executes action automatically in the same DB transaction;
- LLM explanation failure does not fail analysis.

Response `200`:

```json
{
  "case_id": "uuid",
  "analysis_run_id": "uuid",
  "status": "RECOMMENDED",
  "selected": {
    "action_type": "REQUEST_ALTERNATE_PAYMENT_METHOD",
    "success_probability": 0.82,
    "expected_recovered_minor": 409918,
    "expected_value_minor": 402500,
    "confidence": 0.87,
    "requires_approval": false
  },
  "candidates": []
}
```

Errors:
- `404`;
- `409 INVALID_CASE_STATE`;
- `422 INSUFFICIENT_CASE_DATA`;
- `503 MODEL_UNAVAILABLE_AND_NO_FALLBACK` only if fallback intentionally disabled.

## 7. Create/execute recovery action

### `POST /api/v1/recovery-cases/{case_id}/actions`

Auth:
- `OPERATOR` or `ADMIN` for execution;
- analyst cannot execute.

Request:

```json
{
  "analysis_run_id": "uuid",
  "action_type": "CREATE_PAYMENT_LINK"
}
```

Important validations:
1. case belongs to caller organization;
2. analysis run belongs to case and is current enough to use;
3. action exists in that run;
4. action is policy-eligible;
5. case is not terminal;
6. no conflicting active/unknown action exists;
7. server re-evaluates current policy and payment-success status;
8. frontend cannot supply amount, probability, ERV or recipient as authoritative values.

Behavior:
- if approval required: create action `PENDING_APPROVAL`, case -> `AWAITING_APPROVAL`;
- if WAIT: create scheduled action and case -> `SCHEDULED`;
- if STOP: create action, case -> `STOPPED`;
- if immediate executable: create intent, commit, then execute and move to appropriate state.

Response `201`:

```json
{
  "action": {
    "id": "uuid",
    "action_type": "CREATE_PAYMENT_LINK",
    "status": "SUCCEEDED",
    "requires_approval": false,
    "provider_reference": "plink_...",
    "scheduled_for": null
  },
  "case_status": "WAITING_FOR_OUTCOME",
  "customer_action": {
    "type": "PAYMENT_LINK",
    "url": "https://..."
  }
}
```

For `PENDING_APPROVAL`, `provider_reference/customer_action` are null.

Errors:
- `403 ROLE_NOT_ALLOWED`;
- `404`;
- `409 CASE_ALREADY_RESOLVED`;
- `409 ACTION_ALREADY_EXISTS`;
- `409 INVALID_CASE_STATE`;
- `422 ACTION_NOT_IN_ANALYSIS`;
- `422 ACTION_BLOCKED_BY_POLICY` with structured reasons;
- `502 PAYMENT_PROVIDER_ERROR`;
- `504 PAYMENT_PROVIDER_TIMEOUT` only when result is known not to have created side effect; unknown-result timeouts return action state `UNKNOWN` rather than encouraging retry.

## 8. Approve action

### `POST /api/v1/recovery-actions/{action_id}/approve`

Auth: `ADMIN` for P0.

Request:

```json
{
  "expected_case_version": 5
}
```

Why version is sent: prevent approving stale recommendation after case changed.

Response:

```json
{
  "action_id": "uuid",
  "action_status": "SUCCEEDED",
  "case_status": "WAITING_FOR_OUTCOME"
}
```

Errors:
- `404`;
- `409 ACTION_NOT_PENDING_APPROVAL`;
- `409 STALE_CASE_VERSION`;
- `409 CASE_ALREADY_RESOLVED`;
- provider error mapping as above.

## 9. Reject/stop approval

### `POST /api/v1/recovery-actions/{action_id}/reject`

Auth: `ADMIN`.

Request:

```json
{
  "reason": "Prefer manual handling",
  "reanalyze": true
}
```

Behavior:
- action -> `CANCELLED`;
- if `reanalyze=true`, workflow -> `ANALYZING` excluding this specific action for immediate rerank;
- otherwise case -> `STOPPED`.

## 10. Timeline

### `GET /api/v1/recovery-cases/{case_id}/timeline`

Auth: any authenticated role.

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "occurred_at": "2026-08-30T08:20:03Z",
      "event_type": "CASE_CREATED",
      "actor_type": "PROVIDER",
      "summary": "Failed UPI payment detected.",
      "evidence": {
        "provider_event_id": "..."
      }
    }
  ]
}
```

Sort ascending for a timeline display. Do not expose secrets/raw PII.

## 11. Razorpay webhook

### `POST /api/v1/webhooks/razorpay`

Auth: no user JWT. Authentication is webhook signature.

Headers:
- `X-Razorpay-Signature` required;
- `x-razorpay-event-id` required for idempotency in production integration path.

Request body: raw Razorpay JSON bytes.

Processing:
1. read raw bytes;
2. validate HMAC-SHA256 signature using webhook secret;
3. inspect event-id header;
4. parse JSON only after signature validation;
5. persist event with unique provider event ID;
6. upsert provider entity/create or resolve case;
7. do **not** call LLM or slow customer messaging inline;
8. return success promptly.

Response:
- `204 No Content` for accepted/duplicate valid event;
- `400` malformed event;
- `401` invalid/missing signature;
- `500` only if event could not be durably persisted/processed safely, allowing Razorpay retry.

## 12. Demo-only endpoints

These routes exist only when `DEMO_MODE=true`, require `ADMIN`, and must never be confused with real provider events.

### `POST /api/v1/demo/reset`
Resets deterministic demo records to seed state.

### `POST /api/v1/demo/run-batch`
Runs synthetic evaluation policy over the seeded synthetic batch.

Response includes explicit:

```json
{"data_source": "SYNTHETIC_SIMULATION"}
```

Do not create a real Razorpay Payment Link for every synthetic record.

## 13. API-level invariants

- no route accepts an arbitrary `organization_id` for tenant selection;
- no route accepts authoritative financial amount for an existing recovery case;
- no client-provided probability/ERV is trusted;
- every mutating route is safe against duplicate clicks;
- terminal cases return conflict for mutating operations;
- analysis and action responses expose structured policy reasons;
- request IDs are present in error logs and returned errors.

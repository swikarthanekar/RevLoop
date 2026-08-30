# RecoverIQ — Recovery Engine Specification

**Status:** Authoritative P0 recovery decision contract  
**Goal:** Convert a persisted `RecoveryCase` into a safe, explainable, ranked next-best action.

## 1. Pipeline

```text
RecoveryCase
  ↓
Failure Normalization
  ↓
Feature Construction
  ↓
Candidate Action Generation
  ↓
Action-specific Propensity Prediction
  ↓
Expected Recovery Value
  ↓
Confidence
  ↓
Policy Filtering / Approval
  ↓
Deterministic Ranking
  ↓
Recommendation Snapshot
```

The recovery engine does **not** execute external side effects. Execution is owned by the workflow/action executor.

## 2. Inputs

Required:
- `RecoveryCase`;
- source `Transaction` or `Subscription`;
- `Customer`;
- transaction/payment history;
- previous recovery actions;
- contact history;
- merchant policy;
- current time;
- optional payment-downtime context;
- model service metadata.

The input snapshot used for one analysis run should be stable for the duration of that run.

## 3. Failure normalization

### 3.1 Output taxonomy

P0 normalized categories:

```text
PAYMENT_RAIL_DOWNTIME
INSUFFICIENT_FUNDS
AUTHENTICATION_FAILURE
BANK_OR_ISSUER_DECLINE
EXPIRED_OR_INVALID_METHOD
CUSTOMER_ABANDONMENT
MANDATE_OR_RECURRING_FAILURE
TECHNICAL_FAILURE
UNKNOWN
```

### 3.2 Evidence precedence

Normalize using this order:

1. **Explicit active downtime evidence** matching payment method/instrument.
2. Exact provider `error_reason` mapping.
3. Exact provider `error_code` + `error_step` + `error_source` mapping.
4. Subscription state semantics (`pending`, `halted`).
5. Conservative fallback `TECHNICAL_FAILURE` only when provider fields clearly indicate technical processing failure.
6. `UNKNOWN` otherwise.

An LLM is never part of authoritative failure normalization.

### 3.3 Mapping implementation

Keep mapping in versioned Python data, for example:

```python
ERROR_REASON_MAP: dict[str, FailureCategory] = {
    # Populate only with Razorpay values we have verified in fixtures/docs.
}
```

Do not use broad substring matching like `"fund" in reason` if an exact value is known.

For unrecognized provider tokens:

```text
FailureCategory.UNKNOWN
```

and retain original fields as evidence.

### 3.4 Downtime rule

If a currently active Razorpay downtime record matches the payment method/instrument and is `started` or otherwise active/ongoing, classify as `PAYMENT_RAIL_DOWNTIME` even if the original provider error is generic.

If downtime lookup times out, set:

```text
downtime_status = UNKNOWN
```

Never silently interpret timeout as `NO_DOWNTIME`.

## 4. Feature construction

### 4.1 Feature schema version

All runtime features belong to a named immutable schema, initially:

```text
recovery_features_v1
```

The model bundle declares the expected schema version. Runtime must fail closed to deterministic fallback if schemas mismatch.

### 4.2 Case-level features

Recommended P0 features:

| Feature | Type | Definition |
|---|---|---|
| `amount_minor` | integer | Amount at risk |
| `amount_log1p` | float | `log1p(amount_minor)` for model only |
| `case_type` | categorical | payment/subscription |
| `failure_category` | categorical | normalized category |
| `payment_method` | categorical | upi/card/netbanking/etc |
| `hour_of_day` | integer | UTC or explicitly merchant-local; choose one consistently |
| `day_of_week` | integer | 0–6 |
| `hours_since_failure` | float | current time - source failure time |
| `retry_count_provider` | integer | provider retry/auth attempts if known |
| `recovery_attempts_so_far` | integer | RecoverIQ business attempts |
| `contacts_last_24h` | integer | outbound recovery contacts |
| `rail_degraded` | boolean | verified downtime match |
| `downtime_severity` | categorical | high/medium/low/none/unknown |

### 4.3 Customer-history features

| Feature | Definition |
|---|---|
| `customer_tenure_days` | days since first known customer activity |
| `successful_payments_90d` | count |
| `failed_payments_30d` | count |
| `payment_success_rate_90d` | successes / attempts |
| `historical_recovery_rate` | recovered prior cases / prior cases, with missing flag |
| `lifetime_value_minor` | merchant LTV field |
| `customer_segment` | NEW/REGULAR/HIGH_VALUE/VIP |
| `same_method_recent_success` | boolean |
| `alternate_method_recent_success` | boolean |

### 4.4 Action feature

Each model row includes:

```text
action_type
```

This is essential because the model predicts outcome conditional on intervention.

### 4.5 Missing data

Do not invent zero for unknown values where zero has meaning.

Use:
- imputer in ML pipeline;
- explicit categorical `UNKNOWN`;
- optional missing indicator for high-value numeric features.

## 5. Candidate action generation

Candidate generation is deterministic and based on case type, failure category and provider context.

### 5.1 Universal candidates

Potential set:

```text
WAIT
RETRY_SAME_METHOD
REQUEST_ALTERNATE_PAYMENT_METHOD
CREATE_PAYMENT_LINK
SEND_RECOVERY_MESSAGE
ESCALATE_TO_HUMAN
STOP
```

Not every case gets every action.

### 5.2 Default candidate matrix

| Situation | Candidate actions |
|---|---|
| Active payment-rail downtime | WAIT, REQUEST_ALTERNATE_PAYMENT_METHOD, CREATE_PAYMENT_LINK, STOP |
| Insufficient funds | WAIT, SEND_RECOVERY_MESSAGE, CREATE_PAYMENT_LINK, STOP |
| Authentication failure | RETRY_SAME_METHOD, REQUEST_ALTERNATE_PAYMENT_METHOD, CREATE_PAYMENT_LINK, STOP |
| Bank/issuer decline | WAIT, REQUEST_ALTERNATE_PAYMENT_METHOD, CREATE_PAYMENT_LINK, STOP |
| Expired/invalid method | REQUEST_ALTERNATE_PAYMENT_METHOD, CREATE_PAYMENT_LINK, SEND_RECOVERY_MESSAGE, STOP |
| Technical failure, no confirmed downtime | WAIT, RETRY_SAME_METHOD, REQUEST_ALTERNATE_PAYMENT_METHOD, STOP |
| Unknown | WAIT, ESCALATE_TO_HUMAN, STOP; add Payment Link only if existing case data is sufficient |
| Subscription `pending` with Razorpay retries active | WAIT, REQUEST_ALTERNATE_PAYMENT_METHOD, SEND_RECOVERY_MESSAGE, STOP |
| Subscription `halted` | REQUEST_ALTERNATE_PAYMENT_METHOD, CREATE_PAYMENT_LINK, ESCALATE_TO_HUMAN, STOP |

### 5.3 `RETRY_SAME_METHOD` semantics

This action does not mean RecoverIQ may create an unsupported autonomous debit.

- For one-time payment: it represents presenting/recommending another attempt with same method when product flow supports it.
- For subscription `pending`: exclude by default when Razorpay is already retrying.
- For uncertain provider state: exclude until reconciliation completes.

## 6. Propensity prediction

For each candidate action `a`:

```text
p_a = P(recovered_within_horizon = 1 | case_features, action=a)
```

Return a calibrated probability in `[0, 1]`.

The model does not select the action. It supplies one input into deterministic ranking.

### 6.1 Deterministic fallback probabilities

If model load/inference fails, use a versioned rule table, not random numbers.

Example shape only:

```python
FALLBACK_PROBABILITIES = {
  FailureCategory.PAYMENT_RAIL_DOWNTIME: {
      Action.WAIT: Decimal("0.60"),
      Action.REQUEST_ALTERNATE_PAYMENT_METHOD: Decimal("0.72"),
      Action.CREATE_PAYMENT_LINK: Decimal("0.65"),
      Action.STOP: Decimal("0.00"),
  },
}
```

Actual demo values belong in config/fixtures and must be labeled as heuristic baseline values.

## 7. Expected Recovery Value (ERV)

All financial calculations use integer minor units and Python `Decimal` for intermediate multipliers.

For action `a`:

```text
ExpectedRecovered_a = round_half_up(Psuccess_a × AmountAtRisk)

ERV_a = ExpectedRecovered_a
        − ActionCost_a
        − FatiguePenalty_a
        − OperationalRiskPenalty_a
        − DelayPenalty_a
```

### 7.1 Action cost

Configurable minor-unit cost representing operational/messaging effort. For demo it can be small but non-zero for actions with real effort.

### 7.2 Fatigue penalty

Only contact-producing actions incur fatigue.

Recommended deterministic form:

```text
FatiguePenalty =
    contact_action_indicator
    × base_contact_penalty_minor
    × (1 + contacts_last_24h)
```

Optional customer-value sensitivity can be added only if documented and tested; do not overfit.

### 7.3 Operational risk penalty

Use configured basis points by action:

```text
OperationalRiskPenalty =
    round_half_up(AmountAtRisk × risk_bps[action] / 10_000)
```

For example, an action that may cause customer friction can carry higher risk than WAIT.

These are decision-engine policy coefficients, not claimed real-world financial estimates.

### 7.4 Delay penalty

For actions intentionally delaying recovery:

```text
DelayPenalty =
    round_half_up(
      AmountAtRisk
      × delay_hours[action]
      × delay_penalty_bps_per_hour
      / 10_000
    )
```

Keep the coefficient configurable and small.

### 7.5 STOP action

`STOP` has:

```text
Psuccess = 0
ExpectedRecovered = 0
ERV = 0
```

This provides a rational floor. If every non-stop valid action has `ERV <= 0`, select `STOP`.

## 8. Confidence

Confidence is a product-level reliability score, not a formal statistical confidence interval.

Define:

```text
prediction_certainty = 2 × abs(p_selected − 0.5)
```

where 0 means maximally ambiguous and 1 means prediction at 0 or 1.

```text
confidence =
    0.45 × feature_completeness
  + 0.35 × prediction_certainty
  + 0.20 × evidence_strength
```

All inputs in `[0,1]`; clamp final output to `[0,1]`.

### Feature completeness
Fraction of important v1 features present before imputation.

### Evidence strength
Suggested deterministic values:

```text
1.00 exact provider failure evidence + relevant downtime/subscription context
0.80 exact provider failure evidence
0.65 partial provider evidence
0.40 UNKNOWN failure / sparse context
```

Low confidence does not automatically mean low recovery probability.

## 9. Policy filtering

Policy runs **after** scoring so the UI can show useful blocked alternatives, but blocked actions cannot be selected for execution.

For each action return:

```json
{
  "eligible": false,
  "requires_approval": true,
  "reasons": ["AMOUNT_ABOVE_AUTO_LIMIT"]
}
```

### 9.1 Hard blocks

Examples:
- action not in merchant allowlist;
- max recovery attempts reached;
- contact action when contact cap reached;
- immediate same-method retry during verified rail downtime;
- action would duplicate an already active/unknown equivalent action;
- case terminal;
- provider success already known;
- missing minimum data required to safely create Payment Link;
- automation globally disabled and route asks for auto execution.

### 9.2 Approval requirements

Require human approval when any is true:
- amount at risk > `auto_action_limit_minor`;
- confidence < `minimum_auto_confidence` but action is still allowed for human review;
- action type configured as approval-only;
- escalation/manual customer-contact policy requires it.

### 9.3 Cooldown

If recent RecoverIQ action was executed within `cooldown_minutes`, contact/retry-like candidates should be blocked or scheduled after cooldown.

## 10. Ranking

Rank **policy-eligible** candidates by:

1. highest `ERV`;
2. highest `success_probability`;
3. lower contact/operational burden;
4. fixed tie-break priority.

Suggested fixed tie-break order:

```text
WAIT
REQUEST_ALTERNATE_PAYMENT_METHOD
CREATE_PAYMENT_LINK
RETRY_SAME_METHOD
SEND_RECOVERY_MESSAGE
ESCALATE_TO_HUMAN
STOP
```

The tie-break order is not a business preference; it exists for deterministic reproducibility. ERV dominates it.

Blocked candidates may be displayed below eligible candidates with their block reason but are never rank 1 executable recommendation.

## 11. Priority score for case queue

After recommendation:

```text
normalized_erv = min(max(selected_erv / merchant_erv_scale_minor, 0), 1)
urgency = deterministic function of case age/case type
customer_value = normalized LTV or segment mapping

PriorityScore =
    0.50 × normalized_erv
  + 0.20 × urgency
  + 0.15 × customer_value
  + 0.15 × confidence
```

Store `[0,1]`.

This score orders the operations queue; it does not affect provider money state.

## 12. Analysis pseudocode

```python
def analyze_case(case_id: UUID) -> AnalysisResult:
    case = repo.get_case_for_update(case_id)
    assert case.status in ANALYZABLE_STATES

    context = feature_service.build_context(case)
    failure = failure_normalizer.normalize(context)
    candidates = candidate_generator.generate(context, failure)

    model_scores = propensity_model.score_actions(
        features=context.features,
        actions=candidates,
    )

    rows = []
    for action in candidates:
        p = model_scores[action]
        expected_recovered = money.mul_probability(case.amount_at_risk_minor, p)
        erv = erv_engine.calculate(case, context, action, p)
        confidence = confidence_engine.calculate(context, action, p)
        policy = policy_engine.evaluate(case, context, action, confidence, erv)

        rows.append(RecommendationCandidate(
            action=action,
            success_probability=p,
            expected_recovered_minor=expected_recovered,
            expected_value_minor=erv,
            confidence=confidence,
            eligible=policy.eligible,
            requires_approval=policy.requires_approval,
            reasons=policy.reasons,
            factors=explainable_factors(context, action),
        ))

    ranked = rank_deterministically(rows)

    if no_positive_valid_action(ranked):
        selected = ensure_stop_candidate(ranked)
    else:
        selected = first_valid_candidate(ranked)

    persist_analysis_snapshot(case, ranked, selected)
    return AnalysisResult(...)
```

## 13. Stopping rules

Select `STOP` or transition to STOPPED when:
- no eligible non-stop action has positive ERV;
- contact/attempt policy prohibits every intervention;
- user/operator explicitly stops;
- case has opt-out marker;
- case is already paid;
- repeated low-confidence analyses produce no human-approved strategy;
- business retry limit reached.

Transition to `FAILED` when recovery was attempted and is conclusively exhausted according to `STATE_MACHINE.md`.

## 14. Explainable factors

The recovery engine emits evidence tags such as:

```json
[
  {"code": "ACTIVE_UPI_DOWNTIME", "impact": "HIGH", "source": "RAZORPAY_DOWNTIME"},
  {"code": "RECENT_CARD_SUCCESS", "impact": "MEDIUM", "source": "TRANSACTION_HISTORY"},
  {"code": "NO_RECENT_CONTACTS", "impact": "LOW", "source": "RECOVERY_HISTORY"}
]
```

The LLM can turn these into readable prose. It cannot add unsupported factors.

## 15. Batch evaluation contract

The batch evaluator must compare RecoverIQ against at least one simple baseline.

Preferred baseline:

```text
Immediate retry where eligible; otherwise WAIT; no personalized action ranking.
```

Report:
- number of cases;
- amount at risk;
- recovered amount under baseline simulation;
- recovered amount under RecoverIQ policy simulation;
- incremental recovered amount;
- recovery rate;
- actions per recovered case;
- contact count;
- stop count.

Synthetic counterfactual evaluation must be clearly labeled synthetic.

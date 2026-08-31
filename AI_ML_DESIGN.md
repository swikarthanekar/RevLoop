# RevLoop — AI & ML Design

**Status:** P0 intelligence contract  
**Principle:** Use ML where prediction creates economic value, deterministic code where correctness matters, and LLMs only where language/unstructured presentation adds value.

## 1. Responsibility split

### Deterministic code owns
- Razorpay webhook signature verification;
- event deduplication;
- workflow state;
- failure taxonomy rules from provider evidence;
- feature computation definitions;
- candidate action eligibility basics;
- money calculations;
- Expected Recovery Value;
- policy and approval rules;
- stopping rules;
- idempotency;
- payment success verification;
- recovered revenue;
- audit records.

### ML owns
- probability of successful recovery for a `(case, candidate_action)` pair;
- optional offline comparison of action-selection policy;
- model-derived probability only, not policy authorization.

### LLM owns
- concise evidence-grounded recommendation explanation;
- bounded customer outreach draft;
- optional analyst summary.

### LLM explicitly does not own
- payment amount;
- failure classification as authoritative truth;
- recovery probability;
- ERV;
- policy eligibility;
- action authorization;
- payment verification;
- state transitions.

## 2. Prediction task

### Unit of prediction
One row = one **case-action pair**.

Example:

```text
Case C123 + WAIT
Case C123 + CREATE_PAYMENT_LINK
Case C123 + REQUEST_ALTERNATE_PAYMENT_METHOD
```

### Target label

```text
recovered_within_72h: {0,1}
```

For synthetic data, this is generated from a hidden outcome mechanism. For future real data, it is derived from verified recovery outcomes following the action.

### Why not just predict generic recoverability?
Because the product needs to answer:

> Which action is most likely to recover this particular revenue?

A generic risk score cannot distinguish interventions.

## 3. Feature set v1

### Numerical

```text
amount_log1p
customer_tenure_days
successful_payments_90d
failed_payments_30d
payment_success_rate_90d
historical_recovery_rate
lifetime_value_log1p
hours_since_failure
retry_count_provider
recovery_attempts_so_far
contacts_last_24h
```

### Boolean

```text
rail_degraded
same_method_recent_success
alternate_method_recent_success
is_subscription
```

### Categorical

```text
case_type
failure_category
payment_method
customer_segment
downtime_severity
action_type
hour_bucket (optional)
```

Do not include:
- raw customer name/email/phone;
- provider IDs;
- fields created after the outcome;
- recommendation/result fields that leak label.

## 4. Leakage prevention

Critical rules:
- split by `case_id`, never random rows, because one case produces multiple action rows;
- no future transaction/outcome features;
- no `recovered_amount` in model features;
- no action execution status in pre-action features;
- generator must create features before outcomes are sampled.

## 5. Synthetic data methodology

### 5.1 Goals
Synthetic data exists to:
- exercise the complete ML pipeline;
- demonstrate action-specific learning;
- support an honest held-out benchmark;
- seed believable UI/business scenarios.

It is not evidence of production performance.

### 5.2 Dataset size
Recommended:
- 12,000–25,000 cases for generation;
- 3–6 candidate actions per case;
- action-level training table ~50k–100k rows;
- deterministic random seed.

If development time is tight, 10k cases is sufficient.

### 5.3 Generate case features
Sample realistic-but-clearly-synthetic distributions for:
- amount;
- payment method;
- normalized failure category;
- tenure;
- success history;
- customer segment;
- provider retries;
- downtime;
- contact history.

Use conditional dependencies. Examples:
- subscription cases have provider retry counts more often than one-time payments;
- high-value customers tend to have longer tenure;
- active downtime is correlated with `PAYMENT_RAIL_DOWNTIME`, not independent noise.

### 5.4 Hidden recovery probability function
For each case-action pair compute latent log-odds:

```text
logit(p) =
    global_intercept
  + action_bias[action]
  + failure_action_interaction[failure, action]
  + payment_method_action_interaction[method, action]
  + b1 * prior_success_rate
  + b2 * same_method_recent_success
  + b3 * alternate_method_recent_success
  - b4 * contacts_last_24h
  - b5 * recovery_attempts_so_far
  + b6 * customer_tenure_scaled
  + bounded_noise
```

Then:

```text
p = sigmoid(logit(p))
y ~ Bernoulli(p)
```

The exact coefficients must live in the data generator and be documented as simulation assumptions.

Examples of intended relationships:
- active downtime + immediate same-method retry => low success;
- active downtime + alternate method => higher success;
- expired/invalid method + same-method retry => very low success;
- expired/invalid method + alternate method/payment link => high success;
- repeated contacts => lower response probability;
- customers with strong payment history generally recover more often.

Do not make one action universally best.

### 5.5 Counterfactual evaluation
Because synthetic generation knows latent `p` for every candidate action, the evaluator can compare policies on the same holdout cases without pretending observed real-world counterfactuals exist.

Label outputs clearly:

```text
SYNTHETIC POLICY SIMULATION
```

## 6. Data split

Recommended:

```text
70% train
15% validation
15% test
```

Group by case ID.

Use a deterministic split seed.

The test split is never used for model selection.

## 7. Baseline model — Logistic Regression

### Pipeline
Use scikit-learn `ColumnTransformer`:
- numeric: median imputation + standardization where appropriate;
- categorical: most-frequent/constant imputation + one-hot encoding;
- estimator: `LogisticRegression`.

Use regularization and fixed seed where applicable.

### Why baseline matters
- simple;
- interpretable;
- fast;
- calibrated probabilities can be good;
- establishes whether XGBoost adds genuine value.

### Required evaluation
- ROC-AUC;
- PR-AUC;
- log loss;
- Brier score;
- calibration curve/bins;
- policy-level recovered-value simulation.

## 8. XGBoost candidate

Train XGBoost only after the baseline works.

Use:
- shallow/moderate trees;
- early stopping on validation data;
- limited hyperparameter search;
- fixed random seed.

If probabilities are poorly calibrated, calibrate using validation data with Platt/logistic or isotonic calibration where sample size supports it.

### Selection rule
Choose XGBoost for runtime only if it materially improves one or more of:
- Brier/log loss;
- held-out policy recovered value;
- PR-AUC;

without unacceptable latency or complexity.

If improvements are marginal, keep Logistic Regression. This is a product decision, not a model-prestige contest.

## 9. Business-policy evaluation

The most important offline comparison is not AUC alone.

Evaluate:

```text
RevLoop selected action
vs
Naive baseline policy
```

Baseline policy example:
1. choose `RETRY_SAME_METHOD` if eligible;
2. else choose `WAIT`;
3. obey hard safety rules.

Report on test cases:
- expected/realized synthetic recovered amount;
- recovery rate;
- average actions/case;
- contact actions/case;
- stopped cases;
- incremental recovered amount.

## 10. Model artifact

Serialize a trusted local bundle, for example:

```python
{
  "model": fitted_pipeline,
  "model_version": "lr-v1.0.0",
  "feature_schema_version": "recovery_features_v1",
  "trained_at": "...",
  "action_types": [...],
  "metrics": {...},
  "training_seed": 20260830
}
```

Recommended path:

```text
apps/api/app/ml/artifacts/recovery_model.joblib
```

or environment-configured external path.

Security: only load model artifacts created by this project; joblib/pickle is not safe for untrusted files.

## 11. Runtime inference contract

Python protocol:

```python
class RecoveryPropensityModel(Protocol):
    @property
    def model_version(self) -> str: ...

    @property
    def feature_schema_version(self) -> str: ...

    def score_actions(
        self,
        *,
        features: RecoveryFeaturesV1,
        actions: list[RecoveryActionType],
    ) -> list[ActionProbability]: ...
```

Output:

```python
class ActionProbability(BaseModel):
    action_type: RecoveryActionType
    probability: float  # validated 0..1
```

Runtime validations:
- requested action supported by artifact;
- all required feature names available after preprocessing;
- probability finite and 0..1;
- no NaN/Inf;
- model/schema version included in analysis record.

If inference throws:
- log model failure;
- use deterministic fallback probabilities if enabled;
- mark model source in recommendation as fallback version;
- do not call LLM to invent probabilities.

## 12. LLM provider architecture

Use a small interface:

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self,
        *,
        task: str,
        input: BaseModel,
        output_schema: type[T],
    ) -> T: ...
```

Default implementation can use Gemini. Provider selection is configuration, not domain logic.

No LangChain/LangGraph in P0.

## 13. Explanation input schema

Only provide approved structured evidence:

```json
{
  "case_type": "PAYMENT_FAILURE",
  "amount_minor": 499900,
  "currency": "INR",
  "failure_category": "PAYMENT_RAIL_DOWNTIME",
  "selected_action": "REQUEST_ALTERNATE_PAYMENT_METHOD",
  "success_probability": 0.82,
  "expected_recovered_minor": 409918,
  "expected_value_minor": 402500,
  "confidence": 0.87,
  "evidence_factors": [
    {"code": "ACTIVE_UPI_DOWNTIME", "impact": "HIGH"},
    {"code": "RECENT_CARD_SUCCESS", "impact": "MEDIUM"}
  ],
  "policy": {
    "eligible": true,
    "requires_approval": false,
    "reasons": []
  }
}
```

No raw secrets. Avoid unnecessary PII.

## 14. LLM explanation output schema

```python
class RecommendationExplanation(BaseModel):
    summary: str                 # <= 240 chars
    evidence: list[str]          # 1..4 items
    safety: list[str]            # 0..3 items
    customer_impact: str | None  # concise
```

Validation rules:
- no new numeric financial claims except exact values provided in input;
- no hidden chain-of-thought request;
- no unsupported provider state;
- no payment instruction beyond selected approved action.

## 15. Outreach input schema

```json
{
  "customer_first_name": "Aarav",
  "amount_minor": 149900,
  "currency": "INR",
  "approved_action": "CREATE_PAYMENT_LINK",
  "payment_link_url": "https://...",
  "failure_message_class": "PAYMENT_DID_NOT_COMPLETE",
  "tone": "professional",
  "language": "en"
}
```

Use only synthetic/customer-consented data in hackathon demo.

## 16. Outreach output schema

```python
class OutreachDraft(BaseModel):
    subject: str | None
    message: str
    cta_text: str | None
    language: Literal["en", "hi", "hinglish"]
```

P0 limit: one short message. No persuasive dark patterns, threats, or invented urgency.

## 17. LLM fallback behavior

If provider times out, rate-limits, returns invalid JSON, or fails schema validation:

### Explanation fallback
Generate from deterministic templates:

```text
Recommended: {action_label}.
Estimated recovery probability: {p_display}%.
Reason: {top_factor_1}; {top_factor_2}.
Policy: {approval_text}.
```

### Outreach fallback
Use safe templates by action/failure category.

The API should still return analysis success with:

```text
explanation_source = TEMPLATE_FALLBACK
```

## 18. LLM evaluation

Use a fixed set of 50 cases.

Measure:
- schema-valid output rate;
- unsupported-factor rate;
- numeric mismatch rate;
- latency median/p95;
- fallback success rate.

Target for demo build:

```text
schema validity       100% after retry/fallback
numeric mismatch        0% in accepted output
unsupported facts       0% in accepted output
fallback success      100%
```

## 19. Prompt safety

- system/developer prompt defines fixed role and output schema;
- user/customer free text, if ever included, is quoted as data and not instructions;
- never place API keys/provider responses containing secrets in prompts;
- do not ask model for private chain-of-thought;
- request concise structured reasons/evidence only.

## 20. Files expected

```text
apps/api/app/ml/
  features.py
  service.py
  schemas.py
  fallback.py
  artifacts/

apps/api/app/ai/
  provider.py
  schemas.py
  explanations.py
  outreach.py
  fallback.py

scripts/ml/
  generate_training_data.py
  train_baseline.py
  train_xgboost.py
  evaluate.py
```

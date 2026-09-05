# Judge Q&A

Answers written to be defended out loud, with the file paths behind each claim.
Where a number is modelled rather than measured, it says so.

---

## 1. How do you know you beat the baseline?

**Short answer.** A held-out policy evaluation: 250 cases neither policy has
seen, scored by the same frozen model, with the decision policy as the only
variable. RevLoop realises **28.80%** of at-risk revenue against a naive
baseline at **22.40%** — a 6.40-point gap, ₹2,39,524.16 incremental realised.
Visible at `/proof`, recomputable in front of you.

**What makes it a fair comparison.**

- **Same cases.** Both policies run over an identical cohort, drawn from the
  test split in sorted case-id order — a rule that depends only on generated
  identifiers, so neither policy can be advantaged by cohort selection
  (`app/demo/evaluation.py`).
- **Same model.** Both are scored by the frozen `lr-v1.0.0` artifact, so the
  comparison isolates the policy rather than the predictor.
- **Genuinely held out.** The test split is never used for model selection
  (`AI_ML_DESIGN.md` §6).
- **Realised, not predicted.** The metric uses the outcomes the generator
  sampled, not the model's own probabilities. A confident-but-wrong model scores
  badly here.
- **Deterministic.** Press Recompute: the timestamp moves, every figure is
  identical. That is the check that it computes rather than reads a fixture.

**What this is not.** Synthetic data with a hand-specified outcome mechanism,
which lives in `scripts/ml/common.py` and can be read. It shows the policy beats
a naive baseline *under assumptions we wrote down*. It is not evidence about
real merchant traffic, and the page says so above the numbers rather than
underneath them.

**The interesting detail.** The figure used to be 28.00%. Constraining selection
to actions RevLoop can actually execute moved it to 28.80% —
**constraining the policy improved it.** The mechanism is checkable:
`RETRY_SAME_METHOD` carries `ACTION_BIAS -0.05` against `+0.20` and `+0.25` for
the alternate-method and payment-link actions. It topped the expected-value
ranking only because its action cost is ₹1, not because it recovers more.
Removing it pushed selection onto actions that genuinely work. The benchmark is
now also measuring the policy that actually ships, rather than one that would
sometimes pick an action the product cannot perform.

**The separate dashboard number.** "Incremental vs Baseline" on `/dashboard` is
a *different*, weaker figure: a modelled counterfactual over the demo tenant
with an assumed 40% naive recovery rate and no untreated holdout. The UI labels
it "Modelled, not measured" and the server supplies the explanation text, so the
disclosure cannot drift from the constant
(`app/repositories/analytics_repo.py:29-30`). If you want a defensible uplift
number, use `/proof`, not this one.

---

## 2. What is real and what is synthetic?

### Real

| | Evidence |
|---|---|
| Razorpay Payment Links | Live Test Mode API calls. `POST /v1/payment_links`, real `rzp.io` URLs that open a real checkout |
| Webhook verification | HMAC-SHA256 over the **raw body before JSON parsing**, `hmac.compare_digest`, enforced in production (`app/integrations/razorpay/webhooks.py`) |
| Webhook dedup | Real unique constraint on the provider event id with `ON CONFLICT DO NOTHING` — visible on `/provider-events` |
| Razorpay downtime API | Live `GET /v1/payments/downtimes` during analysis |
| Authentication | Supabase ES256/JWKS verification. `Bearer dev-admin` returns 401 in production |
| Tenant isolation | Cross-organization id probing returns 403 |
| The model | scikit-learn logistic regression, `lr-v1.0.0`, loaded from a SHA-256-verified artifact |
| The decision engine | Candidate generation, ERV, policy, ranking, selection — all production code, all exercised by the simulator |
| Money arithmetic | Integer minor units end to end, `Decimal` with `ROUND_HALF_UP`; the frontend never recomputes a figure |
| Dashboard aggregates | Computed by SQL over the actual case rows; they reconcile to the rupee |

### Synthetic

| | How it is labelled |
|---|---|
| All 100 demo cases, customers, transactions | `is_synthetic` on the rows; "DEMO / RAZORPAY TEST MODE" badge on every screen |
| Training data (15,000 cases) | `dataset_version: synthetic_recovery_v1`, generator and seed published on `/proof` |
| Recovery outcomes in the seed | `verification_source: SIMULATED_BATCH`, `recovered_payment_id: synthetic-recovered-*` |
| Model metrics (ROC-AUC 0.776) | Offline evaluation on the synthetic test split |
| The `/proof` evaluation | `SYNTHETIC POLICY SIMULATION` label above the figures |
| Explanations | Deterministic templates — see question 5 |

**We did not clean any of this labelling up.** Being visibly honest about
synthetic data is worth more than a screen that looks more impressive.

### Deliberately not built

`RETRY_SAME_METHOD` and `SEND_RECOVERY_MESSAGE` are ranked but not executed.
That is a documented P0 boundary, not an omission —
`RAZORPAY_INTEGRATION.md` §1 lists "direct autonomous same-method debit" and
"delivery of email/WhatsApp" under **Simulated in P0**, and `DOMAIN_MODEL.md:229`
states "P0 does not invent unsupported direct payment debits." The UI shows the
model's preference for them and explains, in a sentence, why RevLoop is not the
component that acts on it.

---

## 3. What happens if the model is unavailable?

**Analyze fails closed and the case does not move.**

`RecoveryAnalysisService` is constructed with `allow_model_fallback` and the
API path leaves it off, so a load or inference failure raises
`ModelUnavailableError` → `503 MODEL_UNAVAILABLE_AND_NO_FALLBACK`. No
recommendation is written, no transition is recorded, the case stays in
`DETECTED`, and the operator sees "Model unavailable — no recommendation was
recorded and the case is unchanged."

**Why not fall back to a heuristic?** A heuristic probability rendered under a
card that says "AI recovery decision" and stamps a `model_version` is a lie the
user cannot detect. A visible failure is better than an invisible substitution.
The same rule is applied in three places:

- **Analysis** — `503`, nothing persisted.
- **Seeding** — `allow_model_fallback=False`. If the artifact cannot load, the
  seed raises `SeedAnalysisError` and the transaction rolls back, leaving the
  previous tenant intact. Tested.
- **The simulator** — `503 SIMULATION_UNAVAILABLE` rather than heuristic numbers
  on a page whose whole claim is that they came from the model.

A deterministic fallback table does exist (`app/ml/fallback.py`) for contexts
that explicitly opt in, and when it is used the response carries
`inference_source: "fallback"` and an `INFERENCE_FALLBACK` factor. It is never
silently substituted.

**What still works without the model:** every read path — dashboard, case list,
case detail, timeline, compliance, and the cached `/proof` evaluation. Only new
analysis stops.

---

## 4. How do you guarantee a customer is never double-charged?

Five independent mechanisms. Any one failing does not create a duplicate.

**1 · A deterministic idempotency key.** Derived from
`(case_id, recommendation_id, action_type)` — not random, not time-based
(`app/actions/keys.py`). The same logical request always produces the same key.

**2 · A unique database constraint.** Not an application check. Two concurrent
requests can both pass a `SELECT`; only one survives the `INSERT`. The
`IntegrityError` is caught and the existing action is returned, so the caller
gets the original action rather than an error.

**3 · A row lock before deciding.** `lock_case` takes `SELECT … FOR UPDATE`, so
concurrent executions on one case serialise rather than interleave.

**4 · A stable provider `reference_id`.** Every Payment Link carries a reference
derived from the action id. If a response is lost after Razorpay created the
link, reconciliation looks the link up *by that reference* rather than creating
another. An ambiguous provider response marks the action `UNKNOWN` — never
`FAILED`, because retrying a `FAILED` action is exactly how you double-charge.

**5 · Webhook dedup and stale-event precedence.** Provider events are
deduplicated on the provider's own event id via a unique constraint, and a stale
`failed` event cannot downgrade a payment already known to be captured.

**Proven at the browser level.** `e2e/action-safety.spec.ts` fires rapid
duplicate clicks at Execute and at Approve and asserts exactly one action row
results, and drives a genuine concurrent conflict to a `409` that reconciles
against server state.

**The honest limit.** These prevent RevLoop from creating a second *charge
attempt*. RevLoop never debits a customer directly — it creates a Payment Link
the customer chooses to pay. A customer who pays two different links has paid
twice, and no idempotency key on our side prevents that; blocking it is why
`get_blocking_payment_link_action` refuses to create a second link while one is
unresolved.

---

## 5. Are the explanations LLM-generated?

**Not in production, no.** `explanation_source` returns `TEMPLATE_FALLBACK`,
because `GEMINI_API_KEY` is not set. The explanations you see are deterministic
templates assembled from approved statements.

**Do not pitch them as LLM-generated.** The accurate line is: *"Explanations are
deterministic templates built from an allowlist of approved statements. The LLM
integration exists and is confined to phrasing — it can never influence a
number, a ranking or an authorisation."*

**Why the LLM is off, precisely.** The first measurement showed 0 of 10 calls
returning `LLM`, all with `invalid_response`. That looked like a model failing
the allowlist. It was not — the diagnostic found:

```
400 INVALID_ARGUMENT: Manually set deadline 3s is too short.
                      Minimum allowed deadline is 10s.
```

Our own configuration set a 3-second HTTP deadline; Gemini rejects anything
under ten. Every request was refused at the transport layer **before the model
ran**. The bug is fixed (the deadline is now floored at the provider's minimum
while our own wall-clock budget stays tight), but production has never run with
both a key and the fix, so the honest state is: *not enabled, and not yet
measured with the fix in place.*

If asked why it is off, the accurate answer is "we found a configuration bug in
our own client, fixed it, and have not re-measured — so we are not claiming
LLM explanations." That is a better answer than a number we no longer trust.

**If it is later enabled**, the safety design is the interesting part and holds
either way: the model receives only approved facts, its output is validated
against an allowlist where every percent and money token must match an approved
value exactly, and any failure degrades to the template. That validation is what
makes "the LLM cannot invent a number" a checkable claim rather than a promise —
and it is also why enabling the key does not by itself produce LLM explanations.

---

## 6. Shorter answers to likely follow-ups

**"Why does the dashboard credit recovery to actions you can't execute?"**
It used to, and that was a real defect — seeded history was built from the
model's rank-1 action instead of the action the engine selected. Fixed at the
source: seeded action history now contains zero advisory actions, asserted by
`test_seeded_action_history_contains_only_executable_actions`.

**"Is the ML real, or a lookup table?"**
`action_type` is a genuine model feature — scoring builds one row per candidate
action and returns different probabilities per action. The simulator lets you
watch that: change the failure category and the ordering changes because the
model has learned failure-category × action interactions.

**"Average time to recover is exactly 1 day. Suspicious?"**
It was, and you would have been right. Every seeded outcome carried exactly
86400 seconds. It is now a deterministic spread across 12 buckets from 23
minutes to just under 3 days, keyed on the case UUID so it is stable. Still
synthetic, still labelled; the point was to stop a fabricated constant looking
like a measurement.

**"Your API docs are public."**
Deliberate. `/docs`, `/redoc` and `/openapi.json` are open so you can inspect
the API surface yourself. Nothing behind them is reachable without a verified
Supabase token. It would be closed before any real deployment.

**"The demo password is in your JavaScript bundle."**
Also deliberate — it is a one-click demo sign-in, documented as such in
`lib/config/public.ts`. Two things worth knowing: no dev-bypass token shipped
(`NEXT_PUBLIC_DEV_AUTH_TOKEN` survives in the bundle as an *unresolved*
reference), and the Supabase key is the `anon` key, not `service_role`. The
destructive reset is separately gated behind `DEMO_RESET_ENABLED`, so a stranger
with the password cannot wipe the tenant.

**"What would you do next?"**
Executable outreach so `SEND_RECOVERY_MESSAGE` stops being advisory;
webhook-verified rather than simulated outcomes across the seed; tenant-scoped
idempotency and dedup constraints (they are global today, which is correct for a
single-tenant P0 and wrong for real multi-tenancy); and `iss` validation on the
JWT, which currently checks `aud` and `exp` only.

**"What's the weakest part?"**
The evaluation is synthetic end to end, so it validates the machinery rather
than the market. The second weakest is that recovery outcomes in the demo are
`SIMULATED_BATCH` rather than webhook-verified — the live path exists and works,
but the seeded history did not come through it.

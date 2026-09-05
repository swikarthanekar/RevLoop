# Audit response — keep / change decision log

An independent audit probed the deployed product and read the source. This
document records what we did about each finding and, more importantly, **why**,
so that any of it can be defended to someone who asks "why does it do that?".

Three verdicts are used:

- **KEEP** — the behaviour is correct. It is not changing. If it looked wrong
  from outside, the surfacing changed, not the control.
- **KEEP BUT RESURFACE** — the behaviour is correct and unchanged; how it is
  presented, named or explained changed.
- **CHANGE** — the behaviour was wrong for this product at this stage.

Findings the audit got wrong, or that we found ourselves while verifying, are in
[§7](#7-findings-the-audit-missed-or-got-wrong).

---

## 1. Critical

### C1 — The primary CTA failed on 15 of 16 actionable cases

`RETRY_SAME_METHOD` ranked first on 93 of 100 cases and on 17 of 21
`RECOMMENDED` cases (we re-measured; the audit said 15 of 16). Clicking "Execute
recovery" returned `422 ACTION_NOT_EXECUTABLE`.

The audit framed the non-executable set as the defect. **We disagree.** The set
is a documented product boundary, decided before any of this was built:

- `RAZORPAY_INTEGRATION.md` §1, **"Simulated in P0"** — *"direct autonomous
  same-method debit for one-time failures"* and *"delivery of email/WhatsApp
  unless optional email adapter is added later"*.
- `DOMAIN_MODEL.md:229` — *"`RETRY_SAME_METHOD` is a strategy type. P0 does not
  invent unsupported direct payment debits."*

RevLoop holds no mandate or saved token for these customers. Making the action
"executable" would mean either inventing a capability that does not exist, or
relabelling a Payment Link as a same-method retry. Both trade honesty for a
smoother demo.

**The real defect is that the decision engine selected an action its own
executor cannot perform, and the UI then offered a button for it.**
`select_recommendation` picked the highest-EV eligible candidate with no notion
of executability.

| Component | Verdict | Rationale |
|---|---|---|
| Executor's refusal to run `RETRY_SAME_METHOD` / `SEND_RECOVERY_MESSAGE` | **KEEP** | A documented P0 boundary. The executor must never trust its caller about its own capabilities. |
| `select_recommendation` ignoring executability | **CHANGE** | `apps/api/app/recovery/ranking.py`. Selection is now narrower than ranking: the selected action must be eligible **and** executable. |
| Candidate generation including advisory actions | **KEEP** | Dropping them would hide a real model output. `RECOVERY_ENGINE.md` §5.2 lists `RETRY_SAME_METHOD` in the candidate matrix for authentication and technical failures, and the model genuinely prefers it there. |
| `PROMPT16_EXECUTABLE`, and the message *"not executable in Prompt 16"* | **CHANGE** | Internal prompt numbering leaking through a public API. Replaced by `app/domain/capabilities.py`; the message now names the capability gap. |
| The 422 guard itself | **KEEP** | Now unreachable through the UI, retained as defence in depth. |
| Frontend rendering 422 as *"Validation failed — review the input"* | **CHANGE** | Meaningless on a screen with no input. `ACTION_NOT_EXECUTABLE` and six sibling codes now map to real explanations. |

**What was built.** `apps/api/app/domain/capabilities.py` is the single source of
truth: each action type is `EXECUTABLE` or `ADVISORY`, with a machine-readable
reason code and an operator-facing sentence. The executor gates on it, selection
reads it, and both API read paths serve it per candidate so no client keeps a
second copy.

The advisory candidate still appears, at its true rank, with its true
probability and ERV, next to a sentence saying why RevLoop is not the component
that acts on it. That divergence is the honest and the more interesting thing to
show: *the model's best action is retry-same-method; RevLoop will not perform an
autonomous debit, so it executes the best action it actually can.*

> **Optional refinement we declined.** It was suggested that
> `DOMAIN_MODEL.md:229`'s note — provider-managed retry "may mean this action is
> represented by waiting/re-evaluation" — gives an honest path where
> `RETRY_SAME_METHOD` maps to a scheduled wait on `SUBSCRIPTION_FAILURE`.
> We checked: `resolve_effective_scenario` (`candidates.py:112-121`) routes
> *every* subscription case to one of three subscription matrices before the
> failure-category branch is reached, and none of them contains
> `RETRY_SAME_METHOD`. There is no subscription path that can generate it, so
> the mapping would be dead code. Declined as a no-op, not on principle.

### C2 — Demo reset dead in production, and a landmine behind it

| Component | Verdict | Rationale |
|---|---|---|
| Refusing to reset in production | **KEEP BUT RESURFACE** | A genuine safety control. It was raising a plain `RuntimeError` that fell through to the catch-all handler and surfaced as `500 INTERNAL_ERROR`, so a deliberate refusal read as a broken service. `ResetNotAllowedError` is now an `AppError` returning `403` with `DEMO_RESET_NOT_ENABLED` or `DEMO_MODE_DISABLED`. |
| Reset being unreachable in production at all | **CHANGE** | The demo tenant genuinely needs restoring between rehearsals. Added `DEMO_RESET_ENABLED`, a second independent opt-in consulted only under `APP_ENV=production`. `DEMO_MODE` alone is not enough on purpose: it is already on so the demo *routes* exist, so gating a destructive operation on it means that operation is permanently one flag-flip away. |
| `delete_demo_tenant` removing all `user_profiles` | **CHANGE** | The landmine. It would have deleted the hand-provisioned `af7ff7a7-…` row for `demo@gmail.com` and reseeded three different synthetic `auth_user_id`s, leaving the demo account authenticated but unauthorized — `403 NO_ORGANIZATION_MEMBERSHIP` on every request, the whole deployed app unusable until someone re-ran the provisioning SQL. Externally provisioned profiles are now captured before the delete and restored after the reseed, with their original id, role and timestamps. The response reports `preserved_user_profiles` so it can be confirmed without signing out to find out. |
| `DEPLOYMENT.md` §10.1 documenting the opposite of the code | **CHANGE** | Rewritten. §10.2 (what reset preserves) is new. |

### C3 — Analyze flow not demonstrable

**CHANGE**, at the source. The audit consumed all 8 `DETECTED` cases. Rather
than only restoring them, the seeded dataset is now asserted to leave every
reachable control in a working state — see [§6](#6-the-test-that-was-missing).
`scripts/emit_demo_repair_sql.py` generates repair SQL from the canonical spec
for the case where a redeploy is not possible.

---

## 2. High priority

### H1 — Dark-mode outcome card at 1.04:1 — **CHANGE**

The panel hardcoded `bg-emerald-50` (near-white) while its text inherited the
dark theme's near-white foreground. Both were individually "correct"; only the
combination was broken, which is why no unit test saw it.

Root-caused as a class of bug, not one card: any hardcoded Tailwind pastel is
theme-blind. Added semantic status tokens (`--success-*`, `--warning-*`,
`--danger-*`, `--info-*`) defined for both themes, and moved every pastel
surface onto them — the outcome card, policy and mutation banners, timeline
badges and markers, status badges, the environment badge, and error states.

Measured in a real dark-mode browser: **worst pair 9.71:1** (was 1.04:1). The
synthetic-data disclosure *"Verified via Simulated batch"* now measures 13.46:1.
Regression-protected by `e2e/presentation.spec.ts`, which computes contrast from
resolved styles rather than asserting class names.

### H2 — 94 of 100 cases showed heuristic output under an "AI" heading — **CHANGE**

The seed shipped a canned table labelled `demo-heuristic-v1` with round
probabilities, and hardcoded `RETRY_SAME_METHOD` as rank 1 for every generic
case — *regardless of failure category*, including `PAYMENT_RAIL_DOWNTIME`,
where the engine would never generate it and policy blocks it. The seeded data
contradicted the engine running beside it.

Seeding now runs the production engine over the persisted cases
(`apps/api/app/demo/analysis_seed.py`). Measured before → after:

| | before | after |
|---|---|---|
| Recommendations from the real model | 6% | **100%** (368/368 `lr-v1.0.0`) |
| Distinct probability values | a handful of round numbers | **277** |
| Rank-1 advisory (`RETRY_SAME_METHOD`) | 93 | **18** |
| Advisory actions in seeded history | 72 | **0** |
| Rows where expected value == expected recovery | 94 | **0** |

Two inputs are pinned so the seed stays deterministic: each case is analysed at
its own seeded timestamp, and rail health is supplied per case from its own
synthetic scenario rather than read from the live Razorpay downtimes API.
Without the second, seeding would fire ~100 live provider calls and produce a
dataset that varied with the provider's mood. `compute_analysis` gained an
explicit `downtime_override` that only seeding passes.

Seeding **fails closed**: `allow_model_fallback=False`. A seed that quietly fell
back to heuristic probabilities would reintroduce exactly the credibility gap
this removes, and would do it invisibly.

### H3 — Approval flow unreachable — **CHANGE**

All five `AWAITING_APPROVAL` cases had `latest_action: null`, so `canApprove`
(which requires a non-null action) was always false. The state was internally
incoherent: the case claimed to be awaiting approval of nothing. The seed now
creates the pending action, with `approved_by`/`approved_at` left null — an
action awaiting approval has not been approved, and filling those in would have
the row claim an approval that never happened.

### H4 — Mobile — **CHANGE**

Two independent problems, and the audit's diagnosis of the second was wrong.

1. **No navigation below `md`.** The sidebar is `hidden md:flex` with no
   replacement. Added `components/app-shell/mobile-nav.tsx` — a plain
   disclosure, not a modal, so it needs no focus trap or scroll lock.

2. **`/recovery` reporting 1232px of scroll at 390px.** The audit read this as
   "a squeezed column with two-thirds of the screen empty". It was not: the
   tables were scrolling correctly all along (`clientWidth 340, scrollWidth
   1218`). The overflow came from the `<caption className="sr-only">`.
   Tailwind's `sr-only` is `position: absolute`, and an absolutely positioned
   box is clipped by an `overflow` ancestor **only when that ancestor is also
   its containing block**. The scroll wrappers were `position: static`, so the
   caption escaped to document x≈1231 and stretched `<html>`. Fixed by making
   the four scroll wrappers `relative`.

Verified at 390px: `/dashboard`, `/recovery` and `/compliance` all report
`scrollWidth 390 == clientWidth 390`, with the wide table still scrolling
locally.

### H5 — Demo ADMIN credentials in the public bundle — **KEEP, pending your call**

Confirmed in `chunks/135-*.js`. This is a deliberate one-click-demo feature and
it is documented as such in `lib/config/public.ts`. Two things the audit was
right to note as mitigations, both re-verified: `NEXT_PUBLIC_DEV_AUTH_TOKEN`
survives in the bundle as an *unresolved* property access, so no dev bypass
token shipped; and the Supabase key is the `anon` key (`"role":"anon"`).

Not changed in this pass. Reducing the blast radius means either demoting the
demo account below ADMIN (which breaks the approval demo, since approval is
ADMIN-only) or splitting demo endpoints onto a separate role. That is a product
decision, and `DEMO_RESET_ENABLED` already removes the worst capability the
account had — a stranger can no longer wipe the tenant mid-judging.

### H6 — `/docs`, `/redoc`, `/openapi.json` public — **KEEP**

Re-verified: all `200`. Kept deliberately. For a hackathon this is a net
positive — it lets a judge inspect the API surface, which is a strength here
rather than a liability. Nothing behind those paths is reachable without a
verified Supabase token, and the one internal string that leaked through them
("in Prompt 16") is gone. Revisit before any real deployment.

### H7 — Latency — **partially addressed, see §5**

---

## 3. Medium priority

| Finding | Verdict | What happened |
|---|---|---|
| Dashboard credits ~all recovery to `RETRY_SAME_METHOD` | **CHANGE** | Not fixed by capability-aware selection alone — `factory.py` built every seeded action row from `rank1.action_type`. Seeded history now follows the *selected* action. Advisory actions in seeded history: 72 → 0. |
| `NAIVE_BASELINE_RECOVERY_RATE = 0.40` undisclosed | **KEEP BUT RESURFACE** (Phase 2) | The metric is sound; the assumption must be visible. A modelled-counterfactual note costs nothing and buys a lot. |
| Every recovered case at exactly `86400` seconds | **CHANGE** | Replaced with a deterministic latency spread keyed on case UUID — a heavy cluster inside the first few hours, a tail to three days. Still synthetic and still labelled; the point is to stop a fabricated constant masquerading as a measurement. 12 distinct values. |
| `run-batch` has no frontend caller | **CHANGE** (Phase 3) | Being built as the Proof page. |
| `explanation_source: TEMPLATE_FALLBACK` in production | **KEEP BUT MEASURE FIRST** | See [§8](#8-the-gemini-decision). Setting the key does not by itself make explanations LLM-generated, so the decision is being made on measurement rather than assumption. |
| Sidebar "Analytics — Coming in a later milestone" | **CHANGE** | It links to working, backend-fed charts. Now reads "Recovery trend, action effectiveness, failure mix". |
| No branded error pages | **CHANGE** | Added `not-found.tsx`, `error.tsx`, `global-error.tsx`. `global-error.tsx` uses inline styles on purpose — it replaces `<html>`, so no provider, font or theme token is mounted. |
| JWT `iss` unvalidated | **open** (Phase 2) | `aud` and `exp` are checked. Applying the keep-or-change protocol next. |
| Webhook dedup / `idempotency_key` global not tenant-scoped | **KEEP** (Phase 2 to confirm) | Correct for a deliberate single-tenant P0; wrong for real multi-tenancy. Will be recorded as a known boundary rather than changed. |
| `RECOVERED` requires an outcome row but not `verified_event_id` | **open** (Phase 2) | |

---

## 4. Honesty properties we deliberately did **not** "clean up"

Called out because each could be mistaken for an oversight:

- The **"DEMO / RAZORPAY TEST MODE"** badge, now on a themed token so it stays
  legible in dark mode, and kept visible at mobile widths while the workspace
  label is dropped.
- `verification_source: SIMULATED_BATCH` and `synthetic-recovered-*` identifiers.
- `is_synthetic` on customers and transactions.
- The `SYNTHETIC POLICY SIMULATION` label on batch output.
- **Advisory candidates stay on screen.** The cheapest fix for C1 was to stop
  generating them. We did not, because that would hide what the model actually
  preferred.
- **`demo-heuristic-v1` labelling was honest** and is only gone because the
  underlying data is now genuinely model-produced.

---

## 5. Latency

| Operation | Before | Now | Note |
|---|---|---|---|
| Seed / reset | n/a | **~4–6s** | Now runs 100 real analyses; still one transaction |
| `run-batch` cold | ~21.6s | — | Regenerates the 15k-case dataset |
| `run-batch` warm | — | **~1.6s** | `canonical_dataset()` is `lru_cache`d |

The cold-start gap is why the Proof page will warm the cache at startup and
serve a cached result with a visible "computed at" timestamp plus a Recompute
button, rather than making a judge wait 20s on a cold worker.

Analyze and Execute latency against the deployed backend is Phase 2 work.

---

## 6. The test that was missing

936 tests passed while the primary CTA failed on most cases that rendered it.
Every unit was correct in isolation. What nothing asserted was that the *dataset
the demo actually ships* drives those correct units into a working combination.

`apps/api/tests/demo/test_seeded_dataset_is_demonstrable.py` asserts, against
the real seeded rows:

- every `RECOMMENDED` case's selected action is executable — *"Execute would
  fail with 422 ACTION_NOT_EXECUTABLE on these cases: [...]"* if not;
- every analysed case has an executable selection, not only those currently
  rendering a button;
- seeded action history contains no advisory action;
- `DETECTED` and `AWAITING_APPROVAL` are non-empty, so Analyze and Approve are
  reachable at all;
- every `AWAITING_APPROVAL` case carries the pending action it is waiting on;
- all recommendations come from `lr-v1.0.0`;
- expected value is strictly less than expected recovery on every non-STOP row;
- recovery latency is not a single constant;
- at least one case still shows the model preferring an advisory action, so the
  explanation is actually visible;
- the state distribution matches the canonical plan.

Verified to fail correctly: reverting the selection fix makes these fail by
name, listing the exact case ids that would 422.

---

## 7. Findings the audit missed or got wrong

1. **The frontend suite was not green — it was flaky.** The audit reported "335
   passed... No flakes across repeated runs." Three consecutive full runs gave
   **335, 334 and 333**. Intermittent `Unable to find role="row"` in
   `dashboard-client.test.tsx` and `recovery-client.test.tsx`; both files pass
   in isolation. Cause: Testing Library's default `findBy*` timeout is 1000ms of
   wall clock, and 25 files across parallel workers on a shared CPU can starve a
   component past it. Fixed by raising `asyncUtilTimeout` and awaiting the row
   rather than the table.

2. **The 500-on-committed-work path was findable.** The audit could not
   reproduce it. `apps/api/app/api/routes/recovery_analysis.py` ran explanation
   enrichment *after* `analyze_recovery_case()` had committed and *outside* the
   try/except. `explanations.py:129-141` can raise `NoResultFound` from
   `scalar_one()` or a bare `ValueError("Analysis run is not current for
   case.")`. Either turns a fully successful, committed analysis into `500`, and
   invites the caller to retry a non-idempotent operation. Enrichment now
   degrades to no explanation, which every client already handles.

3. **The mobile overflow diagnosis was wrong** — see H4 above. The tables were
   fine; an absolutely positioned `sr-only` caption was escaping its scroll
   container.

4. **The read path made capability-aware selection a no-op.**
   `recovery_case_service.py:276-281` defined `selected_action` as
   `rank1.action_type`. Fixing only `select_recommendation` would have changed
   nothing about the button the UI renders, because case detail is what the UI
   reads. Both paths now share one selection rule via
   `app/recovery/selection.py`.

5. **`request_id` is `req_unknown` on unhandled errors.** Visible in the reset
   `500`: `{"code":"INTERNAL_ERROR", ..., "request_id":"req_unknown"}`. The
   request-id context is not populated on the catch-all path, so the one
   identifier a user could quote is useless exactly when it matters most. Not
   yet fixed; logged here.

6. **93, not 91.** Rank-1 `RETRY_SAME_METHOD` was 93 of 100 and 17 of 21
   `RECOMMENDED`, not 91 and 15 of 16.

---

## 8. The Gemini decision

`explanation_source` returns `TEMPLATE_FALLBACK` on every production analyze
because `GEMINI_API_KEY` is unset. The obvious response — set the key — is not
obviously right, for a reason that only shows up on inspection.

**Setting the key does not make explanations LLM-generated.**
`validate_explanation_semantics` (`app/ai/validation.py`) checks every model
response against a server-side allowlist, and the strictest rule is this:

```python
for item in explanation.evidence:
    if _normalize_token(item) not in approved_evidence:
        raise AISemanticValidationError("Unsupported evidence statement.")
```

Each evidence bullet must match an approved statement **verbatim** (normalised
for case, whitespace and commas). Percent and money tokens are checked the same
way. This is the control that makes "the LLM cannot influence a number" true, and
it stays — but it means a model that rounds `75.4%` to `75%`, or paraphrases an
approved sentence, fails validation and falls back to the template.

That failure is invisible from outside: the response still carries a perfectly
good explanation, just with `explanation_source: TEMPLATE_FALLBACK`. So a
deployment could pay live-LLM latency on the analyze path for every case and
show none of the benefit, with nothing surfacing the fact.

**Verified locally** with a stub provider against real seeded cases:

| Model behaviour | Result |
|---|---|
| Copies approved evidence verbatim, uses the approved probability phrase | `LLM` |
| Rounds `75.4%` to `75%`, evidence otherwise correct | `TEMPLATE_FALLBACK` (`semantic_validation`) |
| Writes its own evidence sentence | `TEMPLATE_FALLBACK` (`semantic_validation`) |

**Measured against the live API**, then diagnosed. The first run reported
`0/10 LLM, all invalid_response` at a median 1.13s. The `--debug` mode found the
cause immediately:

```
400 INVALID_ARGUMENT: Manually set deadline 3s is too short.
                      Minimum allowed deadline is 10s.
```

**The bug was ours.** `gemini_timeout_seconds` defaults to 3.0, which set an
HTTP deadline of 3000ms. Gemini rejects any client-set deadline below ten
seconds, so every request was refused at the transport layer *before the model
ran*. Because a `400 INVALID_ARGUMENT` is neither a rate limit nor an auth
failure, `gemini_provider.py` mapped it to a generic `AIProviderResponseError`,
which surfaced as `invalid_response`. The result looked exactly like a model
that would not comply with the allowlist. It had never been asked.

Two lessons worth keeping:

- **`invalid_response` at 100% is a smell, not a measurement.** A model that
  genuinely struggles with a constraint fails *some* of the time. Uniform
  structural failure points at the integration, and reading the split between
  `invalid_response` and `semantic_validation` is what separated the two.
- **An error taxonomy that collapses unknown provider errors into one bucket
  hides its own bugs.** The mapping is otherwise good -- rate limit, auth and
  timeout are all distinguished -- but everything else became "the response was
  bad", which pointed the investigation at the model instead of at us.

**Fixed** in `_build_http_options`: the transport deadline is floored at
`GEMINI_MINIMUM_DEADLINE_SECONDS = 10.0`, while the application's own
wall-clock budget stays `gemini_timeout_seconds` and is enforced separately by
`asyncio.wait_for`. These are genuinely different things -- one is what the
provider will accept, the other is how long an analyze request is willing to
wait -- and conflating them was the underlying mistake.

Two existing tests asserted `options.timeout == 3000` and so had **codified the
bug**; they now assert the floor and explain why the expectation changed. A new
test proves the wall-clock cap is unaffected, so flooring the deadline does not
mean analyze will wait ten seconds.

**The enable decision is still open** and now needs a re-measurement with the
fix in place, which requires a key. Until that exists, the pitch stays on
deterministic allowlist-validated templates, because that is what production
does.

Other findings from this investigation:

- `gemini-3.6-flash`, the configured default, is a current stable model ID —
  verified against Google's model documentation. No change needed.
- `google-genai>=2.21.0` is in `requirements.txt`, so the deployed image can use
  it. The key is genuinely the only missing input.
- The provider is already well-bounded: a 3s timeout, `attempts=1` (no retries),
  and errors mapped to typed `AIProviderError`s that degrade to the template.
- **A bug this uncovered.** `_build_input` selected the `rank == 1`
  recommendation. Once selection became capability-aware those diverge, so the
  analyze response would have returned an `explanation` arguing for an advisory
  action while its own `selected` field named a different, executable one. Now
  fixed to use the shared `select_candidate_row`, with a regression test that
  asserts the divergence exists in the seeded data and that the explanation
  follows the selected action on every case.

---

## 9. What capability-aware selection did to the benchmark

`scripts/ml/evaluate.py:232` calls `select_recommendation`, so the held-out
policy simulation evaluates whatever selection rule the product runs. Making
selection capability-aware therefore changed the benchmark, and the change is
worth stating plainly because the audit quoted the old figure.

| Policy | RevLoop realized recovery | Naive baseline | Incremental realized |
|---|---|---|---|
| **Capability-aware (current)** | **28.80%** | 22.40% | ₹2,39,524.16 |
| Unconstrained (before the fix) | 28.00% | 22.40% | ₹2,36,843.97 |

Both measured on the same 250-case held-out split, same seed, same frozen
`lr-v1.0.0` artifact; the only difference is whether selection was allowed to
pick an action RevLoop cannot execute.

**Constraining the policy improved it.** That is not a happy accident, and the
mechanism is checkable in `scripts/ml/common.py`: `RETRY_SAME_METHOD` carries
`ACTION_BIAS` of `-0.05`, against `+0.20` for
`REQUEST_ALTERNATE_PAYMENT_METHOD` and `+0.25` for `CREATE_PAYMENT_LINK`. Retry
tops the ERV ranking because its action cost is ₹1 (`ACTION_COST_MINOR`), not
because it recovers more often. Excluding it moves selection onto actions that
genuinely perform better in that world.

The benchmark is also now measuring the right thing. Previously it scored a
policy that would sometimes "select" an action the product cannot carry out, so
the number described a system nobody could ship. It now scores the policy that
actually runs.

**The honest limits of this number.** It is a synthetic world with a
hand-specified outcome mechanism, on a held-out split of that same generated
dataset. It says the model and policy beat a naive baseline *under assumptions
this repository wrote down*, and `scripts/ml/common.py` is where those
assumptions live. It is not evidence about real merchant traffic, and the
`SYNTHETIC POLICY SIMULATION` label on the response says so.

`API_CONTRACTS.md` §12 still shows `"0.2800"` in its example payload. That block
uses round placeholder amounts (`100000000`, `45000000`) and documents the shape
of the response rather than measured output, so it was left alone.

---

## 10. Phase 3 — what was built, and the honesty constraints on each

### The evaluation had no interface (`/proof`)

The audit's sharpest observation: `POST /api/v1/demo/run-batch` already produced
a rigorous held-out counterfactual and **nothing called it**. The most
defensible evidence in the product was unreachable.

Three things had to be true for a page to be worth building:

- **It must be fast.** A cold run regenerates the 15,000-case dataset, ~10s.
  `app/demo/batch_cache.py` computes it on a daemon thread at startup and serves
  the stored result. Caching is legitimate only because the evaluation is
  deterministic -- the cached answer *is* the fresh answer.
- **It must not look like a fixture.** So `computed_at` and the run duration are
  printed, and a **Recompute** button re-runs it. Watching the timestamp move
  while every figure stays identical is the check that it computes rather than
  reads.
- **It must state its own limits above the numbers, not below them.** The
  `SYNTHETIC POLICY SIMULATION` label, the generator seed, the split and the
  scorer version are all on the page. A reader who discovers the synthetic
  provenance themselves discounts everything else on the screen.

### The model was a claim, not something you could touch (`/simulator`)

`POST /api/v1/simulator/score` runs a hypothetical scenario through the
production path -- `generate_candidates`, the frozen model, `calculate_erv`,
`evaluate_policy`, `rank_candidates`, `select_recommendation`. It owns no
decision logic of its own; the only thing `app/services/simulator.py` does is
translate a request into the feature vector those functions already expect.

That constraint is the point. A simplified copy of the engine would demonstrate
the copy. Because it shares the implementation, a probability shown there is the
probability the live system would use.

Properties that make it safe to hand to a stranger mid-demo:

- **Read-only by construction.** No case id, no writes, no provider call. The
  one database read is the merchant policy, because a policy verdict against a
  hardcoded stand-in would be theatre. Asserted by
  `test_simulation_writes_nothing`.
- **Bounded inputs.** Outside the training range a probability is extrapolation
  dressed as a prediction, so out-of-range scenarios are rejected rather than
  scored.
- **Fails closed.** No model, no numbers -- `503`, never a heuristic under a page
  that credits the model.
- **Labelled.** `data_source: INTERACTIVE_SIMULATION`, so a client cannot
  present simulator output as a recovery that happened.

### The arithmetic was computed and then thrown away (ERV waterfall)

`ERVBreakdown` already produced five components; only two were persisted. Making
the arithmetic visible required a decision about *where the numbers come from*.

Recomputing the components on read would have been cheaper and is what the
obvious implementation does -- but it cannot be exact: the fatigue penalty
depends on `contacts_last_24h` at the moment of analysis, which was not stored.
A waterfall whose parts disagree with its total is worse than no waterfall,
because it invites a reader to trust arithmetic that is wrong.

So migration `m3r07` persists the components, nullable, and
`_map_erv_breakdown` applies a hard reconciliation check: if the stored parts do
not sum to the stored total, **or** if the row predates the migration, the
server returns no breakdown at all. Silence is the correct failure mode.
Exercised by `test_read_path_withholds_a_breakdown_that_does_not_reconcile`.

The renderer displays the server's `expected_value_minor` rather than summing
the parts itself -- asserted by a test that feeds it inconsistent input. A
component that recomputed the total would always agree with itself and would
hide exactly the discrepancy worth catching.

### What was deliberately not built

**Live webhook replay.** Genuinely memorable, but it means a write path firing
during judging. The read-only provider-events view is the version worth having,
and it is not done. Recorded here rather than quietly dropped.

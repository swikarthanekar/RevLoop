# RevLoop demo script

Five minutes, in order, with what to say and what to do when something breaks.

Timings are measured against the deployed stack. Anything marked **⚠** is a step
where the audience waits, so fill the silence deliberately rather than watching
a spinner with them.

---

## Before you start

Run this checklist. It takes two minutes and removes every failure mode that
has actually occurred.

| # | Check | Why |
|---|---|---|
| 1 | `curl -s https://revloop.up.railway.app/health` returns `"model":"loaded"` | A cold Railway container takes ~30s to boot. Never let the first request of the demo be the one that wakes it. |
| 2 | Open `/proof` once | Warms the evaluation cache if the startup warm-up has not finished. It should render instantly; if it takes ~10s, you just paid that cost instead of your audience. |
| 3 | Open `/dashboard`, `/recovery`, `/simulator` once each | Warms Vercel's edge and the model bundle. |
| 4 | Confirm at least one `DETECTED` case in `/recovery` | The Analyze step needs one. Filter by status. |
| 5 | Pick your case ids now and keep them in a scratch tab | Hunting for a case on stage is dead air. |

Do **not** warm up by executing a recovery action or creating a payment link —
that consumes demo state.

**If you have time for one rehearsal**, rehearse step 4 (Execute → payment link).
It is the only step that calls Razorpay live.

---

## The run

### 0 · Frame it (15s, on the dashboard)

> "RevLoop is a decision engine for failed payments. When a payment fails it
> opens a case, predicts which recovery action will actually work, prices each
> option, checks it against the merchant's policy, and executes the ones it's
> allowed to. Everything you'll see is Razorpay Test Mode against synthetic
> data — that badge stays on screen the whole time."

Point at the **DEMO / RAZORPAY TEST MODE** badge. Say it before anyone asks.

### 1 · The money view (30s, `/dashboard`)

Revenue at risk, recovered revenue, recovery rate, incremental vs baseline.

> "These reconcile exactly against the underlying hundred cases — not
> approximately, exactly."

Then expand **"Modelled, not measured"** under Incremental vs Baseline.

> "This one is different from the others and I want to flag it myself. There's
> no untreated control group here, so the baseline is a modelled counterfactual
> with a stated assumption. The server tells the UI what that assumption is, so
> the disclosure can't drift from the number."

**Why this is worth 15 seconds:** volunteering the weakest number buys you
credibility on the other five.

### 2 · A case, and the boundary (60s, `/recovery` → any `RECOMMENDED` case)

Open a case. Land on the decision card.

> "The model scored every candidate action. It gave the highest expected value
> to retry-same-method."

Point at the blue **Why not retry same method?** panel.

> "But RevLoop doesn't do that one. There's no stored mandate for this customer,
> so a payment provider can't re-debit without them authorising it again. We
> decided not to invent a capability we don't have. So the engine executes the
> best action it *can* actually perform, and tells you what it skipped and why."

Then expand **"Show the arithmetic"**.

> "And this is how expected value is derived: expected recovery, minus action
> cost, operational risk, delay. Integer paise, Decimal, explicit rounding —
> the browser never recomputes it."

**This is the single most important 60 seconds of the demo.** It is where a
payments person decides whether you understand payments.

### 3 · Let them drive (60s, `/simulator`) ⚠ *~0.5s per change*

Hand over the laptop if you can.

> "Same engine, no database. Move anything."

Three moves that always land, in this order:

1. **Drag the amount up past ₹10,000.** Policy verdict flips to *requires
   approval*. → *"That's the merchant's own auto-action limit, enforced
   server-side."*
2. **Tick "payment rail is degraded".** Retry-same-method disappears from the
   list entirely. → *"That's candidate generation, not a UI filter — during a
   rail outage retrying the same rail is not a candidate at all."*
3. **Switch failure category to Expired/invalid method.** The ranking reorders.

> "Nothing here is stored. It's the production scorer, the production ERV maths
> and the production policy engine over a hypothetical case."

### 4 · The closed loop (90s) ⚠ *~10s on Execute*

Back to a `RECOMMENDED` case. Press **Execute recovery**.

Fill the wait:

> "That's a real Razorpay Test Mode Payment Link being created right now. The
> action row is written first with an idempotency key, so a double-click can't
> produce two links."

When the link appears, open it. Show the Razorpay checkout page.

> "Real link, test mode. If the customer pays, Razorpay fires a webhook, we
> verify the HMAC over the raw body before parsing, dedupe on the event id, and
> only then does the case move to RECOVERED."

**If you have rehearsed it:** pay with test card `4111 1111 1111 1111`, any
future expiry, any CVV, and watch the case flip. **If you have not, do not try
it live.** Describe it instead.

### 4b · The part nobody else shows (30s, `/provider-events`) — optional

Only if you are ahead of time, or if someone asks about webhook handling.

> "Every webhook Razorpay sent us, whether its signature verified, and what we
> decided. That row is a duplicate delivery — the unique constraint on the
> provider's event id caught it, so it was suppressed rather than applied
> twice. Retries are normal; double-applying them is how you double-charge
> someone."

Read-only page. There is deliberately no replay button — a re-fired webhook is
a write, and this exists to show what already happened.

### 5 · The evidence (45s, `/proof`)

> "Last thing, and it's the part I'd want to see if I were you."

Point at the two bars.

> "Held-out split, 250 cases neither policy has seen. RevLoop's policy realises
> 28.80% against a naive baseline at 22.40%. Same cases, same frozen model —
> the only difference is the policy."

Press **Recompute**.

> "That just re-ran it. Timestamp moved, every number identical — because it's
> deterministic, and because it's actually computing rather than reading a
> fixture."

Then, unprompted:

> "This is synthetic. The outcome mechanism is written down in the repo. It
> shows the policy beats a naive baseline under assumptions we wrote — that's
> what an offline evaluation can tell you, and I'm not going to claim more."

---

## If something breaks

| Symptom | What to do | What to say |
|---|---|---|
| Any page slow to first paint | Wait it out; it is a cold container | "Cold start on the free tier." |
| Execute returns an error banner | **Do not press it again.** Refresh the case | "The action is idempotent, so let me refresh rather than risk a duplicate." — then move to the simulator |
| Payment link opens but payment fails | Abandon the live payment | Move to step 5; describe the webhook path |
| `/proof` slow or errors | Reload once | "Cache warm-up hasn't finished." If it still fails, skip to the case detail — the ERV waterfall carries the technical story |
| Simulator shows an error | Change any control to re-fire | The scenario controls stay usable during an error, by design |
| No `DETECTED` case for Analyze | Skip Analyze; open a `RECOMMENDED` case | The story works without it |
| Someone signs in and mutates state mid-demo | Switch to `/simulator` and `/proof` | Both are read-only and cannot be disturbed |

**The universal fallback:** `/simulator`, `/proof` and `/provider-events` need
no state, no provider, and no writes. If the demo tenant is in a bad way, those two pages
alone carry the model, the maths, the policy and the evaluation.

---

## Questions you will get, in one line each

Full answers are in `JUDGE_QA.md`.

- *"Is the AI real?"* — Logistic regression, `lr-v1.0.0`, action-conditional; the simulator scores live, and the model version is printed on every card.
- *"Is this real money?"* — No. Razorpay Test Mode throughout, badge always on screen.
- *"How do you know you beat the baseline?"* — Held-out split, same cases, same model, policy is the only variable. Offline and synthetic, and the page says so.
- *"What if the model is down?"* — Analyze fails closed with `MODEL_UNAVAILABLE_AND_NO_FALLBACK`; no recommendation is written and the case does not move.
- *"Could you double-charge someone?"* — Deterministic idempotency key, unique DB constraint, `FOR UPDATE` row lock, and webhook dedup on the provider event id.
- *"Why won't it retry the card?"* — No stored mandate. We don't invent a capability we don't have; the UI says so on the case.

---

## Reset between runs

```
POST https://revloop.up.railway.app/api/v1/demo/reset
Authorization: Bearer <supabase token for the admin user>
```

Requires `DEMO_RESET_ENABLED=true` on the service — otherwise it answers
`403 DEMO_RESET_NOT_ENABLED` and changes nothing. Confirm the response reports
`recovery_case_count: 100` and `preserved_user_profiles: 1`; the second number
is your proof the sign-in account survived the rebuild.

Turn the flag back off before judging.

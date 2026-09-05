# RevLoop — 5-minute submission video

Word-for-word recording script for the Track 03 submission video.

This is not the same document as [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md), which is for a
live demo where a judge can interrupt you. This one is for a recording: fixed
running order, exact dialogue, exact mouse directions, and a fallback for every
step that can fail.

**Target 4:45. Hard maximum 5:00.**

The core script is **675 spoken words**. At a natural 150 words per minute that is
**4 minutes 30 seconds of speech**, plus roughly 18 seconds of measured page
loading, for about **4:48**.

That leaves only 12 seconds of headroom, so two things are not optional:

- **Rehearse once with a timer before the real take.** If you land over 4:50,
  cut the last two sentences of segment 4 (the "if that came out at or below
  zero" clause). That is the least load-bearing content in the video and buys
  about 9 seconds.
- **Skip the optional breadth insert** unless the rehearsal finishes at 4:30 or
  under.

If you naturally speak slower than 150 wpm, cut segment 4's closing clause from
the start rather than trying to speed up. Rushed delivery reads as nervousness;
a slightly shorter video does not.

---

## Why the video is built this way

Three principles drive every decision below.

**A live demo removes doubt, and doubt is what a judge is managing under time
pressure.** A judge watching a hackathon submission is not asking "is this
impressive". They are asking "is this real". Every claim in this script is
answered by something visible on screen in the same breath.

**Put the judge in the shoes of the user.** The spine of this video is one case
moving through the product: detected, analysed, decided, executed, recorded. Not
a tour of seven pages.

**When torn, default to the most literal format the idea allows.** This is a
real screen recording of the deployed application at
`revloop-bay.vercel.app`, hitting the real API at `revloop.up.railway.app`,
creating a real Razorpay Test Mode payment link. No slides, no mockups, no
edited-together "happy path" that never actually ran.

The one thing that buys the most credibility is the segment where the model's
top-ranked action is *refused* by the product. Anyone can demo software doing
what it wants to do. Showing the system decline its own recommendation, and
explain why, is what separates a working control system from a wrapper.

---

## Locked facts

Every number spoken in this script is verified against production. Do not
substitute remembered values.

| Item | Verified value |
| --- | --- |
| Frontend | `https://revloop-bay.vercel.app` |
| Backend | `https://revloop.up.railway.app` |
| Deployed version | `5c04f6e` — local, GitHub `main` and production all match |
| Revenue at risk | **₹3,53,561.00** across 40 active cases |
| Recovered revenue | **₹2,47,362.00** across 38 recovered cases |
| Recovery rate | **41.2%** |
| Incremental vs baseline | **₹1,19,023.78** (labelled "Modelled, not measured") |
| Model Evidence | RevLoop **28.80%** vs naive baseline **22.40%**, uplift **+6.40 pts** |
| Evidence provenance | `lr-v1.0.0`, `recovery_features_v1`, seed `20260901`, 250 held-out cases |
| Auto-action limit | **₹10,000.00** |
| Minimum confidence | **70%** |
| Stopping rule | **3 attempts per case**, 2 contacts / 24h, 30m cooldown |
| Dataset | 100 cases, 93 distinct probabilities, all `lr-v1.0.0` |

### Measured API latency (warm, repeatable — not cold start)

| Endpoint | Time |
| --- | --- |
| Dashboard summary | 3.2s |
| Case detail | 2.9s |
| Case timeline | 2.2s |
| Case list | 2.4s |
| Compliance policies | 1.7s |
| Model evidence | 1.4s |
| **Analyze** | **unmeasured — budget 3–8s** |

This latency is the single biggest risk to the timing. It is why every page in
the running order is pre-opened in its own tab. Do not skip that step.

---

## Reserved cases

| Purpose | Case ID | State | Never click before recording |
| --- | --- | --- | --- |
| Analyze live | `ac026ec2-eb7c-5830-8761-095e70b44d54` — Rohan Sharma, ₹9,999, authentication failure | DETECTED | **Analyze** |
| Backup analyze | `e424bdad-f30e-5895-bca4-c63deb41b04d` — Meera Sharma, ₹4,999 | DETECTED | **Analyze** |
| Advisory boundary (guaranteed) | `21d7a0b4-2a70-538b-bf41-3e926f6bd4c6` — Meera Patel, ₹14,999 | RECOMMENDED | **Execute recovery** |
| Approval demo | `7aed038c-5115-5a38-82ab-a5c5749b2feb` — Dev Patel, ₹199 | AWAITING_APPROVAL | **Approve action** |

`ac026ec2` is chosen deliberately. It is an authentication failure, which in the
read-only Decision Simulator produced `RETRY_SAME_METHOD` ranked first and marked
**advisory**, with `REQUEST_ALTERNATE_PAYMENT_METHOD` selected instead. And at
₹9,999 it sits just under the ₹10,000 auto-action limit, so it should execute
directly rather than routing to approval. That gives you the advisory boundary
*and* a live Razorpay link from a single case.

The real case's features differ from the simulated ones, so this is likely, not
certain. Segment 5 has a fallback that costs eight seconds.

---

## Pre-flight

Run this in order. The first item matters most: a cold Railway container takes
around 30 seconds, and that must never be the first thing on camera.

- [ ] `curl https://revloop.up.railway.app/health` returns `200` with `"model":"loaded"`
- [ ] Run the state re-check below; output matches exactly
- [ ] Signed in, header shows **Admin**
- [ ] `DEMO / RAZORPAY TEST MODE` badge visible
- [ ] All five tabs opened and loaded once
- [ ] Browser console **closed** (it held an access token)
- [ ] No `.env`, terminal, Railway or Supabase tab open or visible in the tab strip
- [ ] Bookmarks bar hidden (`Ctrl+Shift+B`)
- [ ] Browser and OS notifications off, Do Not Disturb on
- [ ] Password manager and autofill prompts disabled
- [ ] Microphone tested with a 10-second playback
- [ ] Recording at 1920×1080
- [ ] GitHub repository confirmed public in a private window

### State re-check

Paste into the browser console on the dashboard while signed in, then **close the
console** before recording.

```js
const k=Object.keys(localStorage).find(x=>x.startsWith('sb-')&&x.endsWith('-auth-token'));
const t=JSON.parse(localStorage.getItem(k)).access_token, A='https://revloop.up.railway.app';
const s=ms=>new Promise(r=>setTimeout(r,ms));
for (const id of ['ac026ec2-eb7c-5830-8761-095e70b44d54','e424bdad-f30e-5895-bca4-c63deb41b04d',
                  '21d7a0b4-2a70-538b-bf41-3e926f6bd4c6','7aed038c-5115-5a38-82ab-a5c5749b2feb']) {
  const d=await fetch(A+'/api/v1/recovery-cases/'+id,{headers:{Authorization:'Bearer '+t}}).then(r=>r.json());
  console.log(id.slice(0,8), d.case.status, d.analysis?d.analysis.selected_action:'(no analysis)');
  await s(700);
}
```

Safe to record when the output is exactly:

```
ac026ec2 DETECTED (no analysis)
e424bdad DETECTED (no analysis)
21d7a0b4 RECOMMENDED REQUEST_ALTERNATE_PAYMENT_METHOD
7aed038c AWAITING_APPROVAL CREATE_PAYMENT_LINK
```

If `ac026ec2` is anything other than `DETECTED`, it has been analysed. Switch to
`e424bdad` and change the customer name and amount in segment 3.

**Do not fire parallel requests against production.** A burst of concurrent
requests deadlocked the connection pool on the single Railway worker during
preparation and took the API down for twenty minutes. The snippet above is
deliberately serial with a 700ms gap.

---

## Browser setup

Window **1920×1080**, browser zoom **110%**, bookmarks hidden. Record the window,
not full-screen: leaving the address bar visible proves this is a deployed URL,
which is worth more than the pixels it costs.

| Tab | Page | URL | Refresh before recording |
| --- | --- | --- | --- |
| 1 | Dashboard | `/dashboard` | Yes, ~30s before |
| 2 | Recovery Opportunities | `/recovery?status=DETECTED` | Yes |
| 3 | Reserved DETECTED case | `/recovery/ac026ec2-eb7c-5830-8761-095e70b44d54` | Yes — **do not click Analyze** |
| 4 | Compliance Guardrails | `/compliance` | Yes |
| 5 | Model Evidence | `/proof` | Yes |

Left to right in that order. You move rightward through the video with one hop
back to tab 3.

---

## The script

Timestamps are cumulative. Bracketed italics are directions, not spoken.

---

### Segment 1 — Problem and solution · 00:00–00:18

**Tab 1, dashboard already loaded. No clicks.**

> "Hi, I'm Swikar, a final-year Computer Science student at NITR. When an online
> payment fails, most of that revenue is just lost. The hard part isn't noticing
> the failure. It's knowing why it failed, what to do about it, and whether that
> action is safe to take automatically. RevLoop is an agent that detects revenue
> at risk, picks a recovery action it's actually allowed to perform, executes it
> inside policy limits, and records the whole decision."

**On screen:** dashboard with the `DEMO / RAZORPAY TEST MODE` badge.

**If it fails:** if the dashboard is blank, refresh and keep talking. The words
carry this segment, not the screen.

---

### Segment 2 — The money view · 00:18–00:44

**Tab 1.** *[Trace the four cards with the cursor as you speak. Rest on the fourth.]*

> "This is a synthetic batch of a hundred failed payments, running against
> Razorpay Test Mode. Three lakh fifty-three thousand rupees at risk. Two lakh
> forty-seven thousand recovered, across thirty-eight cases. The fourth card is
> the one I'd question if I were judging. It compares RevLoop against a naive
> retry policy, and it's labelled modelled, not measured, because there's no
> untreated control group here. It's an estimate, and the page says so."

**On screen:** all four metric cards, and the "Modelled, not measured" link.

**Why this matters:** volunteering the weakest number before a judge finds it is
the cheapest credibility you will buy all video.

**If it fails:** if figures differ from the table above, read what is on screen.
Never say a number the judge cannot see.

---

### Segment 3 — A detected case, analysed live · 00:44–01:32

*[Click tab 2. Point at the DETECTED rows. Click tab 3. Click **Analyze case**.]*

> "These eight cases are detected but not yet analysed. RevLoop knows a payment
> failed and nothing more. Let's take this one. Rohan Sharma, nine thousand nine
> hundred and ninety-nine rupees, an authentication failure on UPI. Everything on
> the left is provider evidence from the failed payment. There's no recommendation
> yet, so I'll run the analysis now."

*[Click Analyze. While it runs, keep talking — do not watch the spinner in silence.]*

> "This is calling the deployed model, not a cached result. It scores every action
> RevLoop could take on this case, prices each one, and checks it against merchant
> policy before anything is offered to me."

**On screen:** DETECTED badge, provider evidence panel, the button changing to
"Analyzing…", then the decision card appearing.

**Expected duration:** 48 seconds including 3–8 seconds of analysis.

**If it fails:** if Analyze errors, do not retry twice on camera. Say *"That call
failed, which is worth showing honestly. Let me use a case that's already been
analysed,"* then go to `21d7a0b4` and continue from segment 4. If it is still
running past ten seconds, add *"Cold container on the free tier, so the first
call takes a moment."*

---

### Segment 4 — The decision, and what it's worth · 01:32–02:16

**Tab 3.** *[Point at the probability, then scroll to "How expected value is derived".]*

> "Now it has a decision. There's the estimated recovery probability, and below it
> the expected recovery value. That second number is the one that matters
> commercially. RevLoop doesn't just ask how likely an action is to work. It takes
> the amount at risk, multiplies by the probability, then subtracts what the action
> costs and the operational risk of taking it. What's left is what the action is
> actually worth. If that came out at or below zero, the right move would be to
> stop, and stopping is one of the options it scores."

**On screen:** probability, expected recovery value, and the derivation breaking
down into expected recovery minus action cost minus operational risk.

**Read the numbers off the screen.** This case has not been analysed yet, so its
figures do not exist while you are reading this document. The script deliberately
contains no values here.

**If it fails:** if the breakdown is collapsed, expand it. If it is absent, use
the ERV column in the candidate table below instead.

---

### Segment 5 — Advisory versus executable · 02:16–02:44

**Tab 3.** *[Scroll to **Candidate action comparison**. Point at rank 1, then at
the row tagged Selected.]*

> "This is the part I'd most want a judge to see. Look at rank one. The model
> ranks retry same method highest. RevLoop will not execute it, and it says why.
> There's no mandate or saved token for this customer, so it can't re-attempt that
> payment on its own. Your checkout owns that retry. So it's marked advisory, and
> RevLoop drops to the highest-ranked action it can genuinely carry out itself. A
> model recommendation does not automatically become a customer-facing action here."

**On screen:** the **Advisory** tag on rank 1, the **Selected** tag on the chosen
row, and both probabilities visible at once.

**This is the most valuable twenty-eight seconds in the video.** Do not rush it.

**If rank 1 comes back executable:** say *"On this case the top-ranked action is
one RevLoop can perform, so it goes straight through. Let me show you a case where
it can't,"* then open `21d7a0b4` and point at its candidate table, where rank 1 is
*Retry same method* at 85.3% marked Advisory and rank 2 *Request alternate payment
method* at 84.5% is Selected. This costs about eight seconds. It is exactly why
that case is reserved.

---

### Segment 6 — Bounded execution · 02:44–03:18

**Tab 3.** *[Point at the Action control panel on the right. Click **Execute recovery**.]*

> "The action control is on the right, and it reflects the policy decision, not
> just the model's preference. This case is nine thousand nine hundred and
> ninety-nine rupees, just under the ten thousand rupee auto-action limit, so it's
> cleared to execute. Above that limit it would create an approval request for a
> human instead. Let me run it."

**On screen:** the case status transitioning, and the action being recorded.

**If approval is required instead:** this is a better outcome, not a worse one.
Say *"This one needs a human, so submitting creates an approval request rather
than executing. That's the boundary working."* Click Execute, show the case at
`AWAITING_APPROVAL`, click **Approve action** as Admin, and continue to segment 7
unchanged.

---

### Segment 7 — Razorpay Test Mode · 03:18–03:38

**Tab 3.** *[Point at the customer action link. Do not click into Razorpay.]*

> "That's a real payment link, created through the Razorpay API in Test Mode. No
> real money moves, and the customer here is synthetic. But the integration is
> real, and the case has moved out of recommended into waiting for the customer to
> act."

**On screen:** the `rzp.io` link and the updated case status.

**If no link appears:** say *"The link hasn't come back yet, so I won't pretend it
has,"* and move to segment 8. Do not refresh repeatedly on camera.

---

### Segment 8 — Guardrails and the audit trail · 03:38–04:10

*[Click tab 4. Point at the limit cards. Return to tab 3 and scroll to the timeline.]*

> "These limits aren't UI copy. The engine enforces them server-side on every
> action. Ten thousand rupees before a human is required, seventy percent minimum
> confidence, and recovery stops after three attempts on a case, so it can't chase
> someone forever. And every step is recorded. The case being opened, the analysis,
> which action was selected, and the note that the model ranked a different action
> first."

**On screen:** the auto-action limit, minimum confidence and max-attempts cards,
then the timeline showing `CASE_CREATED` and `ANALYSIS_COMPLETED`.

**If the timeline lags:** click **Refresh timeline** once and keep talking.

---

### Segment 9 — Evidence, and the close · 04:10–04:40

**Tab 5, `/proof`.** *[Point at the amber banner first, then the two bars.]*

> "Last thing. This is a held-out evaluation, and the banner is deliberate. It's
> generated data, not merchant traffic. On two hundred and fifty unseen cases,
> RevLoop's policy recovers twenty-eight point eight percent against a naive
> baseline at twenty-two point four. That's evidence the decision pipeline behaves
> sensibly under stated assumptions. It is not a claim about real-world accuracy.
> So that's the loop. RevLoop detects revenue at risk, works out the cause, prices
> the options, checks what it's allowed to do, executes inside those limits, and
> leaves an audit trail for every decision. Thanks for watching."

**On screen:** the SYNTHETIC POLICY SIMULATION banner, 28.80% against 22.40%, and
the provenance row naming the model and seed.

**Pointing at the disclaimer while claiming the result is the single most
persuasive thing in the video.** It tells a judge the rest of your numbers are
probably honest too.

---

## Optional breadth insert

Only if a timed rehearsal finishes at 4:30 or under. Costs about 18 seconds.

Insert between segments 8 and 9, at `/simulator`.

*[Toggle **Payment rail is degraded** on while speaking.]*

> "Same engine, pointed at a hypothetical case instead of a real one. Nothing is
> saved here. And when I mark the payment rail as degraded, retry-same-method
> disappears from the options completely, because candidate generation drops it
> rather than the interface hiding it."

**Why this and not Provider Events.** I checked `/provider-events` on the live
deployment and every counter reads zero. The page is well built and explains
signature verification and de-duplication clearly, but the reset cleared the
webhook history, so it currently displays an empty state. Narrating webhook
rigour over five zeroes reads as weaker than saying nothing. Leave it out unless
a webhook actually lands during the recording.

**Cut the simulator insert first if the rehearsal runs long.** Breadth is worth
less than the advisory boundary in segment 5.

---

## Failure matrix

| Failure | On screen | Exact words | Continue? |
| --- | --- | --- | --- |
| Analyze slow (>10s) | Stay on the case | "Cold container on the free tier, so the first call takes a moment." | Continue |
| Analyze fails | Do not retry twice | "That call failed, which is worth showing honestly. Let me use a case that's already been analysed." | Continue on `21d7a0b4` |
| Analyze fails twice | Go to `/simulator` | "Rather than keep retrying, let me show the same engine scoring a case live here." | Continue — simulator needs no writes |
| Reserved case already analysed | Switch to `e424bdad` | "Let me take a different detected case." | Continue |
| Rank 1 is executable | Open `21d7a0b4` | "Here the top action is executable. Let me show one where it isn't." | Continue |
| Approval required unexpectedly | Show request, approve as Admin | "This one crosses the limit, so it goes to a human first." | Continue — stronger |
| No Razorpay link | Do not refresh repeatedly | "The link hasn't come back yet, so I won't pretend it has." | Continue |
| Dashboard figures shifted | Read the screen | Read the actual numbers | Continue |
| Timeline lagging | One refresh click | "Timeline's catching up." | Continue |
| Backend unresponsive | Stop recording | — | **Abort.** `curl /health` until 200, restart the take |

Never re-record a mutation you already performed as though it were happening for
the first time. If you execute a case in a discarded take, that case is spent —
move to the backup.

---

## No-mutation backup route

If production is unstable close to the deadline, drop segments 3, 6 and 7 and run
everything on `21d7a0b4`, which is RECOMMENDED and has never been touched.

1. Dashboard, unchanged.
2. `21d7a0b4` — root cause, candidates, probability, expected value breakdown.
3. Same page — advisory rank 1 against selected rank 2.
4. Action control panel. Read the approval notice **without clicking**: *"This
   case is above the ten thousand rupee limit, so submitting would create an
   approval request instead of executing. I'm not going to click it here."*
5. `/recovery?status=AWAITING_APPROVAL` — five real cases waiting on a human.
6. Compliance, audit trail and Model Evidence as scripted.

**What gets weaker:** you still show detection, diagnosis, decision, expected
value, the advisory boundary, the approval boundary, stopping rules, the audit
trail and the held-out evidence. You lose the live state transition and the live
Razorpay link. Say so once, plainly: *"I'm showing the decision and the controls
rather than executing live here."* Never imply a transition happened when it did
not.

---

## Emergency 20-second close

If the recording is running long, cut segment 9's narration and use this over the
Model Evidence page.

> "So, quickly. Failed payments lose real revenue, and the hard part is knowing
> what to do about each one. You've seen RevLoop detect a case, work out the cause,
> price each possible action, refuse the one it isn't able to perform, execute
> inside the merchant's limits, and record every step. Detection through to a
> measured, audited outcome. That's the recovery loop Track 03 asks for."

---

## Two things this script deliberately does not do

**It does not quote numbers for `ac026ec2`.** That case has not been analysed, so
its probability and expected value do not exist yet. Segments 4 and 5 are written
so you read them off the screen. That is deliberate, not vagueness.

**It does not claim the held-out result predicts production performance.** The
evaluation is synthetic and the video says so out loud. A judge who catches an
overclaim discounts everything else you said; a judge who hears you volunteer the
limitation extends credit to the rest.

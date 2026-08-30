# RecoverIQ — P0 Frontend Specification

**Status:** Essential screens only  
**Stack:** Next.js + TypeScript + Tailwind + shadcn/ui + TanStack Table + Recharts

## 1. UX objective

The UI must feel like a credible revenue-operations SaaS product. In the first five seconds, judges should understand:

1. how much revenue is at risk;
2. how much RecoverIQ recovered;
3. that cases are prioritized by AI/financial value;
4. that actions are explainable, governed and auditable.

The P0 frontend has four essential surfaces:
- Executive Dashboard;
- Recovery Opportunities;
- Recovery Case Detail;
- Agent/Audit Timeline.

Do not build a generic chatbot, CRM, settings suite, mobile app or campaign builder before these are complete.

## 2. Global application shell

### Desktop-first layout

```text
┌──────────────┬─────────────────────────────────────────┐
│ RecoverIQ    │ Top bar: merchant / demo source / user │
│              ├─────────────────────────────────────────┤
│ Dashboard    │                                         │
│ Opportunities│              page content               │
│ Analytics*   │                                         │
│              │                                         │
└──────────────┴─────────────────────────────────────────┘
```

`Analytics` may link to dashboard sections initially; do not implement an extra page before P0 screens.

### Persistent UI
- product logo/name;
- environment badge: `DEMO / RAZORPAY TEST MODE`;
- navigation;
- authenticated user menu;
- backend health indicator only if it is unobtrusive.

### Design language
- B2B, clean, dense enough for financial operations;
- clear typography;
- avoid excessive gradients/glass effects;
- use semantic status badges;
- reserve motion for state changes and KPI update during demo.

## 3. Data-access rules

- Use generated TypeScript types from FastAPI OpenAPI where practical.
- Use one typed API client wrapper.
- No direct Supabase database queries from browser for domain data in P0; domain reads/writes go through FastAPI.
- Browser never knows Razorpay key secret or LLM key.
- Format minor units centrally:

```ts
formatMoney(amountMinor: number | string, currency: string): string
```

For values that can exceed JavaScript safe integer in future, API type/client should support string or bigint strategy. P0 seed values are small, but do not scatter money math through components.

## 4. Screen 1 — Executive Dashboard

Route:

```text
/dashboard
```

### Purpose
Answer: “What is at risk, what has been recovered, and is RecoverIQ outperforming the baseline?”

### Page hierarchy

#### A. Header

```text
Revenue Recovery Overview
Synthetic batch + Razorpay Test Mode
[Refresh]
```

Show source label. Never imply synthetic batch is production money.

#### B. KPI row

Cards:
1. `Revenue at Risk`
2. `Recovered Revenue`
3. `Recovery Rate`
4. `Incremental vs Baseline`
5. optional compact `Active Cases`

For demo, recovered revenue card should animate/update when a live case resolves, but the value must come from a backend refresh/event, not hardcoded UI state.

#### C. Primary chart — Recovery Trend
Use line/area chart:
- at-risk amount;
- recovered amount.

Do not show more than two main series.

#### D. Recovery funnel
Simple funnel/step cards:

```text
Detected → Actionable → Actioned → Recovered
```

If backend does not yet expose all counts, omit rather than invent.

#### E. Action effectiveness
Horizontal bar chart:
- action type;
- recovery rate;
- tooltip includes attempts and recovered amount.

#### F. Failure breakdown
Bar or donut:
- normalized failure category;
- amount at risk.

#### G. Top recovery opportunities
5-row table with CTA `View case`.

### Data
`GET /api/v1/dashboard/summary`
plus optionally top cases from `GET /recovery-cases?limit=5`.

### Interactions
- date/source filters optional only if backend contract ready;
- click top case -> case detail;
- refresh button re-fetches metrics.

### Loading
- skeleton KPI cards;
- chart placeholder skeleton;
- no spinner covering whole app.

### Error
Banner:

> Dashboard metrics are temporarily unavailable. Recovery cases can still be viewed.

Offer retry.

### Empty

> No recovery activity yet. Seed demo data or wait for a payment failure event.

### Demo-critical
- source badge;
- money-first KPIs;
- incremental baseline card;
- fast refresh after recovered case.

## 5. Screen 2 — Recovery Opportunities

Route:

```text
/recovery
```

### Purpose
Present prioritized recoverable revenue cases.

### Header

```text
Recovery Opportunities
47 active cases · ₹X at risk
```

### Filter bar
P0 filters:
- status;
- failure category;
- case type;
- minimum amount;
- search customer;
- sort priority/amount/recent.

Do not build an advanced filter builder.

### Table columns

| Column | Notes |
|---|---|
| Customer | name + segment badge |
| Amount at Risk | prominent money |
| Failure | normalized category |
| P(Recovery) | selected action probability |
| ERV / Expected Recoverable | money |
| Recommendation | action label |
| Confidence | badge/progress |
| Status | state badge |
| Opened | relative + exact tooltip |

Default sort: priority descending.

### Row interaction
Whole row or `View` button opens case detail.

### Bulk actions
Do not implement in P0. They create major policy/idempotency complexity.

### Data
`GET /api/v1/recovery-cases`

### Loading
Table skeleton preserving header layout.

### Error
Inline error with retry; preserve user filters.

### Empty states
Filtered empty:

> No recovery cases match these filters.

Global empty:

> No active recovery opportunities.

### Demo-critical
Ensure the preselected demo case is visible near top and marked `HIGH_VALUE` or high priority without looking artificially pinned.

## 6. Screen 3 — Recovery Case Detail

Route:

```text
/recovery/[caseId]
```

This is the most important P0 screen.

### Desktop layout

```text
┌───────────────────────────────────────────────────────────┐
│ Case header: customer | ₹ at risk | state | source       │
├────────────────┬────────────────────────┬─────────────────┤
│ Failure/Evidence│ AI Recovery Decision  │ Action Control  │
│                │                        │                 │
├────────────────┴────────────────────────┴─────────────────┤
│ Candidate Action Comparison                               │
├───────────────────────────────────────────────────────────┤
│ Agent / Audit Timeline                                    │
└───────────────────────────────────────────────────────────┘
```

On smaller screens stack sections.

### A. Case header
Display:
- customer name/segment;
- amount at risk;
- case type;
- current case state;
- opened time;
- provider/test/synthetic source label.

### B. Failure & Evidence card
Show:
- normalized failure category;
- payment method;
- source payment/subscription status;
- provider evidence fields in a compact disclosure;
- downtime badge if verified.

Do not dump raw webhook JSON by default.

### C. AI Recovery Decision card
Show:
- recommended action;
- recovery probability;
- expected recovered amount;
- ERV;
- confidence;
- concise structured explanation;
- top evidence factors.

Use wording:

```text
Recommended action
Estimated recovery probability
Expected recovery value
Confidence
Why this action
```

Avoid pretending probability is certainty.

### D. Candidate Action Comparison
Table/cards:

| Action | Success probability | Expected recovered | ERV | Policy | Rank |

Blocked actions remain visible with reason such as:

```text
Blocked: active payment-rail downtime
```

This is a judge-visible engineering depth feature.

### E. Action control panel
State-dependent controls:

#### DETECTED / ANALYZING
- disabled action controls;
- `Analyze` where allowed.

#### RECOMMENDED
- `Execute Recovery` if auto-eligible and user role permits;
- `Request Approval` semantics happen automatically through backend if required;
- no client-side bypass.

#### AWAITING_APPROVAL
- admin: Approve / Reject;
- other roles: pending approval label.

#### SCHEDULED
- show planned next time/action;
- no duplicate execute button.

#### EXECUTING
- disabled controls + status.

#### WAITING_FOR_OUTCOME
- show provider reference/payment link when appropriate;
- `Refresh status` can refetch case; do not blindly execute again.

#### RECOVERED
Large success module:

```text
RECOVERED
₹4,999
Verified via Razorpay Test Mode
```

#### FAILED/STOPPED
Show terminal reason and no execute button.

### F. Payment Link
If an action created a link:
- show copy/open button;
- make clear it is Razorpay Test Mode in demo;
- never reveal provider secrets.

### Loading
Render header skeleton + section skeletons.

### Error
404 -> clean “Case not found or unavailable” state.
409 mutation errors -> refresh case and show conflict message rather than optimistic incorrect state.

### Demo-critical
The page must support the full narrated sequence:

```text
failed case
→ candidate probabilities
→ downtime evidence
→ policy result
→ execute
→ waiting
→ recovered
```

## 7. Screen 4 — Agent / Audit Timeline

Timeline is embedded on case detail first. A separate route is not required for P0.

### Purpose
Make agentic workflow and safety visible without exposing chain-of-thought.

### Data
`GET /api/v1/recovery-cases/{id}/timeline`

### Entry anatomy

```text
[time] [icon] ANALYSIS_COMPLETED
Alternative payment ranked #1.
Evidence: UPI downtime, prior card success.
Model: lr-v1.0.0
```

### Visual event categories
- provider event;
- system analysis;
- policy decision;
- user approval;
- action execution;
- recovery outcome;
- warning/stale event.

### Important timeline entries
- case detected;
- failure normalized;
- downtime checked;
- analysis completed;
- action blocked/approved;
- action execution started;
- Payment Link created;
- payment success webhook received;
- case recovered.

### Evidence disclosure
A `Details` disclosure can show safe structured JSON-like fields, but not raw secrets/PII.

## 8. State refresh strategy

P0 simplest reliable approach:
- standard query fetching;
- after mutation, immediately refetch case and dashboard;
- while `WAITING_FOR_OUTCOME`, poll case every 3–5 seconds for a bounded time (for live demo) or provide manual refresh.

Do not add WebSockets unless polling demonstrably hurts the demo.

## 9. Error behavior

Map backend codes to user messages.

Examples:

| Code | UI behavior |
|---|---|
| `INVALID_CASE_STATE` | Refresh case; show “Case changed while you were viewing it.” |
| `ACTION_BLOCKED_BY_POLICY` | Display block reasons; do not retry |
| `ACTION_ALREADY_EXISTS` | Refetch latest action; no duplicate toast spam |
| `PAYMENT_PROVIDER_ERROR` | Show provider unavailable; existing case remains safe |
| `STALE_CASE_VERSION` | Refetch and require user to review latest state |

## 10. Component map

Suggested:

```text
components/
  app-shell/
  money/
  status-badge/
  charts/

features/dashboard/
  DashboardKpis.tsx
  RecoveryTrendChart.tsx
  ActionEffectivenessChart.tsx
  FailureBreakdownChart.tsx
  TopOpportunities.tsx

features/recovery/
  RecoveryTable.tsx
  RecoveryFilters.tsx
  CaseHeader.tsx
  FailureEvidenceCard.tsx
  RecommendationCard.tsx
  CandidateActionsTable.tsx
  ActionControlPanel.tsx
  RecoveryOutcomeCard.tsx
  AuditTimeline.tsx
```

Avoid single 1,000-line page components.

## 11. Accessibility

- semantic buttons;
- keyboard-accessible table actions/disclosures;
- visible focus;
- color is not the only status signal;
- chart information has text/tooltip equivalents;
- `aria-live` for recovered-state update where appropriate.

## 12. Frontend P0 completion criteria

P0 UI is complete when:
- all four surfaces use real API data;
- no critical CTA is a dead button;
- mutation conflicts/errors are handled;
- money comes from backend authoritative fields;
- synthetic/test source is visible;
- one live case can update from `RECOMMENDED` to `RECOVERED` without page corruption;
- no console errors in the demo path;
- loading/error/empty states exist for all essential data regions.

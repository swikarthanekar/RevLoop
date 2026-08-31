# RevLoop — Implementation Plan

**Goal:** Build the P0 closed loop reliably before adding P1 polish.  
**Sequence rule:** A milestone may depend on previous milestones. Do not jump ahead when its prerequisites are not green.

## Standard quality checks

Backend milestones should progressively support:

```bash
cd apps/api
python -m pytest -q
ruff check app tests
```

Frontend milestones should progressively support:

```bash
cd apps/web
npm run lint
npm run typecheck
npm test -- --run
```

E2E after Playwright is introduced:

```bash
cd apps/web
npx playwright test
```

Exact scripts may be adjusted during repository initialization, but once established all later milestones must use them consistently.

---

# Milestone 0 — Repository Initialization

## Objective
Create a predictable monorepo skeleton and development conventions without implementing product features.

## Prerequisites
- starter documentation present;
- Node.js and Python available locally.

## Expected files/modules

```text
apps/web/
apps/api/
data/
scripts/
docs/
infra/
.env.example
.gitignore
README.md
```

Move/copy the authoritative root docs only if the chosen repository organization keeps them at root; do not hide them where Cursor misses them.

## Tasks
- initialize Next.js TypeScript app;
- initialize FastAPI Python project;
- configure Ruff + pytest;
- configure frontend lint/typecheck/unit-test runner;
- add `.env.example` with placeholders only;
- add backend `/health` skeleton;
- add root README with local boot commands;
- ensure `.cursor/rules/architecture.mdc` is active;
- no DB models yet.

## Tests
- backend imports/starts;
- `/health` unit/API smoke test;
- frontend build/lint/typecheck;
- no secrets committed.

## Completion criteria
Both apps boot independently and CI-style local commands are documented.

## Do NOT work on yet
Database entities, Razorpay, ML, LLM, dashboard design.

---

# Milestone 1 — Backend Core Skeleton

## Objective
Establish application settings, dependency injection boundaries, error envelopes and API versioning.

## Prerequisites
Milestone 0 green.

## Files/modules

```text
apps/api/app/main.py
apps/api/app/core/config.py
apps/api/app/core/errors.py
apps/api/app/core/logging.py
apps/api/app/api/router.py
apps/api/app/domain/enums.py
apps/api/tests/
```

## Tasks
- typed settings with environment validation;
- `/api/v1` router;
- request ID middleware;
- standard error response mapping;
- domain enums from docs;
- DB dependency interface placeholder;
- authentication interface placeholder, with dev/test strategy clearly isolated.

## Tests
- settings validation;
- request ID/error format;
- health route.

## Completion criteria
Backend has stable skeleton; route handlers can be added without architectural changes.

## Do NOT work on yet
Razorpay calls, DB schema, recovery logic.

---

# Milestone 2 — Database Session and ORM Models

## Objective
Implement the authoritative domain schema mappings without API behavior.

## Prerequisites
Milestone 1.

## Files/modules

```text
apps/api/app/db/base.py
apps/api/app/db/session.py
apps/api/app/models/*.py
apps/api/app/domain/enums.py
apps/api/tests/models/
```

## Tasks
Implement:
- Organization/UserProfile;
- Customer;
- Transaction;
- Subscription;
- RecoveryCase;
- RecoveryRecommendation;
- RecoveryAction;
- RecoveryOutcome;
- WebhookEvent;
- AuditLog;
- MerchantPolicy;
- invoice reservation only if it does not delay P0.

Add relationships and model-level constraints mirroring `DATABASE_SCHEMA.md`.

## Tests
- metadata model import;
- constraint-oriented model tests where feasible;
- money/timestamp type assertions.

## Completion criteria
All models import cleanly and accurately represent domain documents.

## Do NOT work on yet
APIs, scoring, seed generator.

---

# Milestone 3 — Alembic Migrations

## Objective
Create a clean database from zero with all required constraints/indexes.

## Prerequisites
Milestone 2.

## Files/modules

```text
apps/api/alembic.ini
apps/api/alembic/
```

## Tasks
- initialize Alembic;
- create dependency-safe migrations;
- add uniqueness/idempotency indexes;
- add check constraints;
- confirm upgrade from empty DB;
- confirm downgrade at least for local development path if practical.

## Tests
- automated migration smoke test against disposable PostgreSQL if available;
- inspect schema/indexes.

## Completion criteria
`alembic upgrade head` produces the intended schema from empty DB.

## Do NOT work on yet
Seed dashboards or provider data.

---

# Milestone 4 — Deterministic Seed Generator

## Objective
Create repeatable, realistic demo records for UI/API development.

## Prerequisites
Migrations green.

## Files/modules

```text
scripts/seed_demo.py
apps/api/app/demo/seed.py
data/demo/
apps/api/tests/demo/
```

## Tasks
- deterministic seed;
- one organization;
- 50+ customers;
- 500+ transactions;
- payment/subscription failures;
- 80–120 historical/open recovery cases;
- recommendations/actions/outcomes for historical dashboard data;
- reserve 2–3 named deterministic demo cases;
- tag synthetic records.

## Tests
- same seed -> same aggregate counts/key demo IDs;
- no invalid cross-tenant relationships;
- sensible amount ranges/status mix.

## Completion criteria
Fresh DB + seed immediately supports meaningful dashboard/query development.

## Do NOT work on yet
ML training data generator; this milestone seeds product/demo records only.

---

# Milestone 5 — Read APIs: Dashboard, Cases, Timeline

## Objective
Expose authoritative server reads required by first frontend screens.

## Prerequisites
Seed data.

## Files/modules

```text
apps/api/app/api/routes/dashboard.py
apps/api/app/api/routes/recovery_cases.py
apps/api/app/schemas/*.py
apps/api/app/services/analytics.py
apps/api/app/repositories/*.py
apps/api/tests/api/
```

## Tasks
- dashboard summary;
- case list/filter/sort;
- case detail;
- timeline;
- tenant scoping;
- role-independent read authorization.

## Tests
- pagination/filter validation;
- tenant isolation;
- not-found behavior;
- server-derived monetary totals.

## Completion criteria
All initial read endpoints match `API_CONTRACTS.md` against seeded data.

## Do NOT work on yet
Mutations, AI, Razorpay.

---

# Milestone 6 — Recovery State Machine

## Objective
Implement one authoritative transition service before any mutation endpoint exists.

## Prerequisites
Domain models.

## Files/modules

```text
apps/api/app/workflows/state_machine.py
apps/api/app/workflows/events.py
apps/api/tests/workflows/test_state_machine.py
```

## Tasks
- legal transition map;
- required evidence checks;
- optimistic concurrency/version update;
- audit creation;
- terminal outcome transaction helper;
- high-priority verified-success resolution from non-terminal states.

## Tests
- every allowed transition;
- representative/all prohibited transitions;
- terminal immutability;
- stale version;
- success precedence.

## Completion criteria
No other module needs direct status assignment.

## Do NOT work on yet
Razorpay webhooks/actions.

---

# Milestone 7 — Failure Normalization and Feature Builder

## Objective
Produce deterministic normalized evidence and `recovery_features_v1`.

## Prerequisites
State/domain services.

## Files/modules

```text
apps/api/app/recovery/failure_normalizer.py
apps/api/app/recovery/features.py
apps/api/app/recovery/schemas.py
apps/api/tests/recovery/
```

## Tasks
- failure taxonomy;
- verified mapping table;
- UNKNOWN fallback;
- feature definitions/lookback queries;
- feature completeness/evidence strength;
- no LLM.

## Tests
- mapping fixtures;
- missing fields;
- transaction and subscription cases;
- no label-leak fields.

## Completion criteria
A seeded case can produce deterministic normalized failure + feature object.

## Do NOT work on yet
ERV/ML.

---

# Milestone 8 — Candidate Generation, ERV, Confidence, Policy

## Objective
Implement the deterministic decision framework independently of learned model.

## Prerequisites
Milestone 7.

## Files/modules

```text
apps/api/app/recovery/candidates.py
apps/api/app/recovery/erv.py
apps/api/app/recovery/confidence.py
apps/api/app/recovery/ranking.py
apps/api/app/policies/service.py
apps/api/app/ml/fallback.py
apps/api/tests/recovery/
apps/api/tests/policies/
```

## Tasks
- candidate matrix;
- fallback probabilities;
- exact money-safe ERV;
- confidence heuristic;
- hard policy blocks;
- approval requirements;
- stopping rules;
- deterministic tie breaks.

## Tests
- Decimal/rounding examples;
- downtime retry block;
- high amount approval;
- contact cap;
- negative ERV selects STOP;
- deterministic ranking.

## Completion criteria
A case receives a complete recommendation without ML artifact or LLM.

## Do NOT work on yet
Provider execution.

---

# Milestone 9 — Synthetic ML Training Dataset

## Objective
Create a reproducible, leakage-safe action-level dataset.

## Prerequisites
Feature/action semantics frozen.

## Files/modules

```text
scripts/ml/generate_training_data.py
data/synthetic/.gitkeep
apps/api/tests/ml/test_synthetic_data.py
```

## Tasks
- generate case features;
- expand to case-action rows;
- latent conditional recovery probabilities;
- sample outcomes;
- group-aware train/validation/test split metadata;
- summary report.

## Tests
- deterministic seed;
- no case crosses split;
- probability and label validity;
- expected directional relationships.

## Completion criteria
Dataset is reproducible and supports honest model training.

## Do NOT work on yet
XGBoost until baseline is trained.

---

# Milestone 10 — Logistic Regression Baseline

## Objective
Train/evaluate the required baseline model.

## Prerequisites
Synthetic dataset.

## Files/modules

```text
scripts/ml/train_baseline.py
scripts/ml/evaluate.py
apps/api/app/ml/artifacts/
```

## Tasks
- preprocessing pipeline;
- grouped splits;
- Logistic Regression;
- metrics: ROC-AUC, PR-AUC, log loss, Brier, calibration;
- synthetic policy simulation vs naive baseline;
- serialize trusted model bundle.

## Tests
- model loads;
- finite probability predictions;
- schema version matches;
- deterministic evaluation within tolerance.

## Completion criteria
`recovery_model.joblib` + metrics report generated and reproducible.

## Do NOT work on yet
XGBoost tuning beyond a basic candidate.

---

# Milestone 11 — XGBoost Candidate and Model Selection

## Objective
Determine whether XGBoost materially improves the product.

## Prerequisites
Baseline green.

## Tasks
- train modest XGBoost candidate;
- calibrate if needed;
- compare held-out metrics and policy value;
- choose winner using documented selection rule;
- save only chosen runtime bundle as default, keep metrics for both.

## Tests
Same runtime contract tests for chosen artifact.

## Completion criteria
Explicit `MODEL_SELECTION.md` or metrics JSON records why LR/XGBoost was selected.

## Do NOT work on yet
Deep learning, neural networks, hyperparameter sweeps.

---

# Milestone 12 — Runtime Model Service + Analysis Workflow

## Objective
Connect case analysis to chosen model/fallback and persist recommendation snapshots.

## Files/modules

```text
apps/api/app/ml/service.py
apps/api/app/recovery/service.py
apps/api/app/workflows/recovery.py
apps/api/app/api/routes/recovery_analysis.py
```

## Tasks
- load artifact at startup/lazy singleton;
- score candidate actions;
- calculate ERV/policy/rank;
- persist complete analysis run atomically;
- transition state;
- implement `POST /recovery-cases/{id}/analyze`.

## Tests
- endpoint against seeded case;
- model failure fallback;
- invalid case state;
- immutable prior runs;
- model version persisted.

## Completion criteria
Real API analysis returns the documented recommendation structure.

## Do NOT work on yet
LLM or Razorpay execution.

---

# Milestone 13 — Razorpay Webhook Receiver

## Objective
Implement secure, idempotent provider event ingestion.

## Files/modules

```text
apps/api/app/integrations/razorpay/webhooks.py
apps/api/app/integrations/razorpay/schemas.py
apps/api/app/api/routes/razorpay_webhooks.py
apps/api/app/services/provider_events.py
apps/api/tests/integrations/razorpay/
```

## Tasks
- raw-body HMAC verification;
- event-id dedup;
- `payment.failed`, `payment.captured`;
- subscription pending/charged/halted mapping;
- Payment Link paid mapping when reference exists;
- stale/out-of-order protections;
- create/resolve case quickly without LLM.

## Tests
All required cases in `RAZORPAY_INTEGRATION.md`.

## Completion criteria
Webhook tests prove duplicate and stale event safety.

## Do NOT work on yet
Payment Link POST until webhook path is safe.

---

# Milestone 14 — Razorpay Read Integrations

## Objective
Add payment and downtime reconciliation reads.

## Files/modules

```text
apps/api/app/integrations/razorpay/client.py
apps/api/app/integrations/razorpay/payments.py
apps/api/app/integrations/razorpay/downtime.py
apps/api/app/integrations/razorpay/errors.py
```

## Tasks
- auth/client timeout;
- fetch payment;
- fetch downtimes;
- typed DTO mapping;
- downtime match logic integration;
- typed error behavior.

## Tests
Mocked success, timeout, auth/validation errors, malformed response.

## Completion criteria
Analysis can incorporate live/test downtime context without becoming dependent on it.

## Do NOT work on yet
New payment providers.

---

# Milestone 15 — Recovery Action Execution + Payment Links

## Objective
Safely execute the selected P0 actions.

## Files/modules

```text
apps/api/app/actions/service.py
apps/api/app/integrations/razorpay/payment_links.py
apps/api/app/api/routes/recovery_actions.py
apps/api/tests/actions/
```

## Tasks
- local idempotency key;
- persist-before-side-effect;
- WAIT/schedule;
- STOP;
- create Standard Payment Link for eligible cases;
- `UNKNOWN` timeout state;
- approval-gated action creation;
- approve/reject endpoints;
- outcome flow through webhook.

## Tests
- duplicate click;
- approval required;
- provider success;
- provider validation error;
- unknown timeout no duplicate retry;
- terminal case block.

## Completion criteria
One backend-only case can go `DETECTED -> ... -> WAITING_FOR_OUTCOME -> RECOVERED` with mocked provider, plus one manual Razorpay test-mode smoke run.

## Do NOT work on yet
Bulk execution.

---

# Milestone 16 — LLM Explanation and Outreach

## Objective
Add non-authoritative language value without destabilizing recovery.

## Files/modules

```text
apps/api/app/ai/provider.py
apps/api/app/ai/schemas.py
apps/api/app/ai/explanations.py
apps/api/app/ai/outreach.py
apps/api/app/ai/fallback.py
```

## Tasks
- provider abstraction;
- Gemini adapter/default;
- structured explanation schema;
- outreach schema;
- timeouts;
- schema validation;
- deterministic fallback;
- record explanation source.

## Tests
- valid output;
- invalid JSON;
- unsupported numeric mutation rejected;
- timeout fallback;
- provider disabled fallback.

## Completion criteria
Case detail gets concise explanation, but disabling LLM leaves core flow working.

## Do NOT work on yet
RAG, memory, multi-agent.

---

# Milestone 17 — Frontend App Shell + Typed API Client

## Objective
Create production-like UI foundations tied to actual contracts.

## Tasks
- app shell/navigation;
- auth boundary or isolated demo auth mode;
- generated/typed API client;
- money/status components;
- query/error handling conventions.

## Tests
- unit tests for money/status formatting;
- lint/typecheck.

## Completion criteria
Authenticated shell can call health/read endpoint.

## Do NOT work on yet
Fancy animation or extra pages.

---

# Milestone 18 — Executive Dashboard

Implement exactly `FRONTEND_SPEC.md` dashboard using real API data.

Tests:
- loading/error;
- money rendering;
- source label;
- KPI/card data from API fixture.

Completion: screenshot-ready dashboard, no hardcoded KPI values.

---

# Milestone 19 — Recovery Opportunities

Implement table/filters/sort/detail navigation.

Tests:
- filters query API correctly;
- empty/error/loading;
- row navigation.

Completion: demo case appears naturally in queue.

---

# Milestone 20 — Case Detail + Audit Timeline + Actions

Implement:
- evidence;
- recommendation/candidates;
- policy states;
- execute/approve/reject;
- Payment Link display;
- bounded status polling;
- recovered outcome;
- timeline.

Tests:
- state-dependent controls;
- conflict refresh;
- waiting/recovered transition.

Completion: complete narrated UI flow works with mocked/local backend.

---

# Milestone 21 — Demo Batch + Analytics Integrity

## Objective
Make business impact measurable and honest.

Tasks:
- synthetic batch evaluator;
- baseline comparison;
- demo reset endpoint/script;
- source labels;
- ensure dashboard aggregates real stored outcomes, not frontend constants.

Tests:
- reset reproducibility;
- baseline/recovered arithmetic;
- live/test outcome does not corrupt synthetic labels.

---

# Milestone 22 — End-to-End and Failure Testing

## Objective
Prove the demo path cannot easily break.

Introduce Playwright.

Critical E2E:

```text
Dashboard
→ opportunity
→ case detail
→ analyze
→ execute Payment Link action (mock adapter in CI)
→ simulated verified webhook
→ RECOVERED
→ dashboard KPI increases
```

Failure E2E/API:
- LLM down;
- Razorpay read timeout;
- duplicate webhook;
- action double click;
- stale case version.

Completion: critical automated tests green repeatedly.

---

# Milestone 23 — Deployment and Demo Hardening

## Objective
Deploy without changing core architecture.

Tasks:
- Vercel web;
- Render API;
- Supabase DB/Auth;
- migrations;
- secrets;
- Razorpay test webhook URL;
- CORS;
- health checks;
- warm backend strategy;
- demo reset procedure;
- backup local/video flow.

Completion:
- public URL works;
- five consecutive demo rehearsals succeed;
- no secret exposed;
- test-mode/synthetic labels visible.

---

# Freeze rule

After Milestone 22 is green, no new P1/P2 feature may be added unless:
1. it can be completed and tested without weakening the critical demo path; and
2. rollback is simple.

Recommended extra-time order only:
1. overdue invoice recovery;
2. Hinglish message generation;
3. recovery forecasting;
4. anomaly detection;
5. optional actual email delivery.

# RecoverIQ — Sequential Cursor Implementation Prompts

These prompts are intentionally milestone-scoped. Use them in order. Do not ask Cursor to continue into the next prompt automatically.

## How to use

Before each prompt:
1. commit or checkpoint the previous green milestone;
2. ensure authoritative docs are in the repository root;
3. paste only the next prompt into Cursor Agent;
4. inspect its plan/diff;
5. require tests to pass before accepting.

Each prompt assumes paths from `ARCHITECTURE.md` and `IMPLEMENTATION_PLAN.md`. If initialization generates slightly different framework boilerplate paths, adapt only path names—not architectural ownership.

---

# Prompt 01 — Repository Initialization

```text
You are implementing RecoverIQ Phase 0.

Read first, in this order:
1. ARCHITECTURE.md
2. IMPLEMENTATION_PLAN.md — Milestone 0 only
3. .cursor/rules/architecture.mdc

Scope: repository initialization only.

Allowed to create/modify:
- apps/web/**
- apps/api/**
- data/** only placeholders/.gitkeep
- scripts/** only placeholders
- docs/** only placeholders
- infra/** only minimal local/deployment placeholders
- .env.example
- .gitignore
- README.md
- package/tool configuration required to boot/lint/test the two apps

Do NOT modify the authoritative root specification documents.
Do NOT implement database models, Razorpay, ML, LLM, recovery logic, dashboard features, or extra integrations.
Do NOT introduce Kafka, Kubernetes, LangChain, LangGraph, RAG, a second payment provider, or a monorepo framework that is not necessary.

Requirements:
- Create a Next.js TypeScript app at apps/web.
- Create a FastAPI app at apps/api with a clean Python project configuration.
- Add backend pytest and Ruff configuration.
- Add frontend lint, typecheck, and a lightweight unit-test runner.
- Implement only GET /health on the backend with a smoke test.
- Create .env.example with placeholders only; never put secrets in repository.
- README must explain exact local boot, test, lint, and typecheck commands.
- Preserve modular-monolith directories described in ARCHITECTURE.md.

Run and fix related failures:
Backend: import/start smoke, pytest, Ruff.
Frontend: lint, typecheck, unit-test command, production build if reasonable.

Completion criteria:
- both apps boot independently;
- GET /health returns a stable JSON response;
- all configured checks pass;
- no business features are implemented.

At the end report only:
1. files created/changed;
2. commands run and pass/fail;
3. any environment prerequisite the human must install.
Stop after this milestone.
```

---

# Prompt 02 — Backend Skeleton

```text
Read first:
- ARCHITECTURE.md sections 4, 6, 7, 8
- DOMAIN_MODEL.md sections 1, 14, 15
- API_CONTRACTS.md sections 1 and 2
- IMPLEMENTATION_PLAN.md Milestone 1
- .cursor/rules/architecture.mdc

Scope: backend core skeleton only.

Allowed to modify:
- apps/api/app/main.py
- apps/api/app/core/**
- apps/api/app/api/** except product feature routes
- apps/api/app/domain/enums.py
- apps/api/tests/core/**
- apps/api/tests/test_health.py
- backend dependency/config files only if required

Do NOT create SQLAlchemy domain models yet.
Do NOT implement recovery engine, provider integrations, ML, LLM, or frontend work.

Implement:
- typed settings/environment configuration;
- /api/v1 router root;
- request/correlation ID middleware;
- standard API error envelope from API_CONTRACTS.md;
- typed base exceptions and one API exception mapper;
- domain enums exactly matching documentation;
- a CurrentUser/AuthContext interface/dependency placeholder that can support test/dev auth and later Supabase verification without leaking tenant selection to requests;
- structured logging setup sufficient for request IDs.

Keep route handlers thin and modules focused.

Tests:
- settings required/default behavior;
- health response;
- request ID present on error path;
- standardized error schema.

Run all backend pytest + Ruff checks and fix only related failures.
Report files changed, test commands/results, and stop.
```

---

# Prompt 03 — Database Models

```text
Read first:
- DOMAIN_MODEL.md in full
- DATABASE_SCHEMA.md sections 1–5
- ARCHITECTURE.md component/data rules
- .cursor/rules/architecture.mdc

Scope: SQLAlchemy database/session/model layer only. Do not create API features.

Allowed to create/modify:
- apps/api/app/db/**
- apps/api/app/models/**
- apps/api/app/domain/enums.py only if an enum documented in DOMAIN_MODEL/DATABASE_SCHEMA is missing
- apps/api/tests/models/**
- apps/api/pyproject.toml or dependency file only for SQLAlchemy/PostgreSQL driver requirements

Implement SQLAlchemy 2.x models for:
Organization, UserProfile, Customer, Transaction, Subscription, RecoveryCase, RecoveryRecommendation, RecoveryAction, RecoveryOutcome, WebhookEvent, AuditLog, MerchantPolicy.
Invoice may be added only as the minimal P1 schema reservation described in DATABASE_SCHEMA.md and only if it does not complicate P0.

Requirements:
- UUID PKs;
- organization_id tenant scope;
- BIGINT minor-unit money;
- TIMESTAMPTZ-aware timestamps;
- relationships without network/domain side effects;
- constraints/index declarations matching DATABASE_SCHEMA.md as closely as SQLAlchemy supports;
- no float money columns;
- no ORM event hooks that perform business workflows.

Do not build migrations in this prompt.

Tests:
- all models import;
- expected tables appear in metadata;
- money columns are integer/bigint types;
- key uniqueness/check/index metadata is present where testable.

Run backend tests + Ruff. Fix related failures. Stop after reporting changes and results.
```

---

# Prompt 04 — Alembic Migrations

```text
Read first:
- DATABASE_SCHEMA.md in full, especially migration order, indexes, idempotency and transaction boundaries
- DOMAIN_MODEL.md invariants
- IMPLEMENTATION_PLAN.md Milestone 3
- .cursor/rules/architecture.mdc

Scope: Alembic/database migrations only.

Allowed to modify:
- apps/api/alembic.ini
- apps/api/alembic/**
- apps/api/app/db/** only if needed to expose metadata/migration URL safely
- apps/api/tests/migrations/**
- backend dependency config only if Alembic is missing

Do NOT change domain semantics to make migration easier.
Do NOT implement APIs.

Implement dependency-safe migrations that produce the schema defined in DATABASE_SCHEMA.md, including:
- tenant foreign keys;
- unique provider/event IDs;
- RecoveryCase source_event_key uniqueness;
- RecoveryAction idempotency_key uniqueness;
- one outcome per case;
- probability/money/basic validity checks;
- important indexes including one-executing-action-per-case partial index where supported.

Use environment DATABASE_URL; never hardcode credentials.

Test a migration from an empty PostgreSQL database if available. If the local environment cannot provide PostgreSQL, add a migration smoke-test path/config and clearly report the missing external prerequisite rather than pretending it ran.

Run backend tests + Ruff. Report migration revisions, checks, and stop.
```

---

# Prompt 05 — Demo Seed Generator

```text
Read first:
- DATABASE_SCHEMA.md section 8
- DOMAIN_MODEL.md entities/invariants
- IMPLEMENTATION_PLAN.md Milestone 4
- FRONTEND_SPEC.md so seed records support the required screens
- .cursor/rules/architecture.mdc

Scope: deterministic product/demo seed data only.

Allowed to modify:
- scripts/seed_demo.py
- apps/api/app/demo/**
- data/demo/**
- apps/api/tests/demo/**
- minimal repository helpers needed to run the seed script

Do NOT implement ML training data here.
Do NOT call Razorpay or an LLM.
Do NOT add fake claims that the data is production data.

Generate reproducibly with a fixed seed:
- one demo organization;
- 50+ customers;
- 500+ transactions;
- realistic payment methods/failure categories;
- subscription records;
- 80–120 recovery cases across active and terminal states;
- enough historical recommendation/action/outcome/audit rows for dashboard charts;
- 2–3 deterministic named demo cases for live storytelling;
- explicit synthetic flags/source labels.

Keep distributions believable and internally consistent; recovered cases require outcomes.

Tests:
- running seed twice after reset produces stable counts and named demo identifiers;
- no invalid tenant/source relationships;
- no terminal RECOVERED case without positive outcome;
- money values positive/in integer minor units.

Run relevant tests + Ruff. Report aggregate seed counts and stop.
```

---

# Prompt 06 — Read APIs

```text
Read first:
- API_CONTRACTS.md sections 1–5 and 10
- FRONTEND_SPEC.md sections 3–7
- DATABASE_SCHEMA.md relevant entities
- ARCHITECTURE.md dependency rules
- IMPLEMENTATION_PLAN.md Milestone 5
- .cursor/rules/architecture.mdc

Scope: read-only P0 APIs for dashboard, recovery list/detail, and timeline.

Allowed to modify:
- apps/api/app/api/routes/dashboard.py
- apps/api/app/api/routes/recovery_cases.py
- apps/api/app/api/router.py
- apps/api/app/schemas/**
- apps/api/app/services/analytics.py
- apps/api/app/repositories/**
- apps/api/tests/api/**
- auth dependency implementation only as needed for server-side tenant/role context

Do NOT implement analyze/action mutations yet.
Do NOT add frontend code.

Implement exactly the documented P0 response semantics:
- GET /api/v1/dashboard/summary
- GET /api/v1/recovery-cases
- GET /api/v1/recovery-cases/{id}
- GET /api/v1/recovery-cases/{id}/timeline

Requirements:
- server derives organization scope from auth context;
- pagination/filter/sort validation;
- monetary aggregates computed server-side;
- synthetic source labels retained;
- no raw secrets/PII in timeline evidence.

Tests must cover tenant isolation, 404, filters, invalid query parameters, and dashboard arithmetic.
Run pytest + Ruff. Stop after report.
```

---

# Prompt 07 — Recovery State Machine

```text
Read first:
- STATE_MACHINE.md in full
- DOMAIN_MODEL.md RecoveryCase/Action/Outcome/AuditLog sections
- DATABASE_SCHEMA.md transaction boundaries and optimistic concurrency
- .cursor/rules/architecture.mdc

Scope: implement the authoritative RecoveryCase state machine only.

Allowed to modify:
- apps/api/app/workflows/state_machine.py
- apps/api/app/workflows/events.py
- apps/api/app/workflows/schemas.py if needed
- apps/api/app/repositories/recovery_cases.py only for transition-safe persistence
- apps/api/tests/workflows/**

Do NOT implement Razorpay, ML, ERV, API mutation routes, or LLM.
Do NOT permit direct status assignment elsewhere as part of this prompt.

Implement:
- every ordinary allowed transition in STATE_MACHINE.md;
- invalid transition typed error;
- optimistic version checking;
- audit record per transition;
- terminal outcome transition helper;
- verified-success resolver that can safely resolve any non-terminal state;
- terminal immutability;
- action/evidence preconditions described by the state document.

Tests:
- table-driven allowed transitions;
- prohibited transitions;
- stale version;
- outcome requirement for RECOVERED;
- STOPPED/FAILED terminal behavior;
- verified success from scheduled/waiting and at least one earlier non-terminal state.

Run all backend tests + Ruff. Stop after report.
```

---

# Prompt 08 — Failure Classification + Feature Builder

```text
Read first:
- RECOVERY_ENGINE.md sections 2–4
- AI_ML_DESIGN.md sections 2–4
- DOMAIN_MODEL.md Transaction/Subscription/Customer
- RAZORPAY_INTEGRATION.md failed-payment/subscription semantics
- .cursor/rules/architecture.mdc

Scope: deterministic failure normalization and recovery_features_v1 only.

Allowed to modify:
- apps/api/app/recovery/failure_normalizer.py
- apps/api/app/recovery/features.py
- apps/api/app/recovery/schemas.py
- apps/api/tests/recovery/**
- repository/query helpers only if required for documented lookback features

Do NOT add ML model code yet.
Do NOT use an LLM for failure classification.
Do NOT broaden taxonomy.

Implement exact normalized failure categories from RECOVERY_ENGINE.md. Populate exact Razorpay mapping only for provider values represented in verified fixtures/docs; unknown values must map conservatively to UNKNOWN.

Implement RecoveryFeaturesV1 with documented numerical/categorical/boolean fields, missing-value semantics, feature completeness and evidence strength.

Tests:
- representative payment failure mappings;
- unknown mapping;
- subscription pending/halted cases;
- missing data behavior;
- lookback feature correctness;
- no post-outcome/leakage fields.

Run tests + Ruff and stop.
```

---

# Prompt 09 — ERV, Candidate Generation, Confidence, Policy

```text
Read first:
- RECOVERY_ENGINE.md sections 5–13 in full
- DATABASE_SCHEMA.md merchant_policies/recommendations/actions
- STATE_MACHINE.md stopping rules
- .cursor/rules/architecture.mdc

Scope: deterministic recovery decision primitives using fallback probabilities. No trained model yet.

Allowed to modify:
- apps/api/app/recovery/candidates.py
- apps/api/app/recovery/erv.py
- apps/api/app/recovery/confidence.py
- apps/api/app/recovery/ranking.py
- apps/api/app/policies/**
- apps/api/app/ml/fallback.py
- apps/api/tests/recovery/**
- apps/api/tests/policies/**

Requirements:
- action candidates match documented matrix;
- explicit RETRY_SAME_METHOD subscription restrictions;
- Decimal-based money math with deterministic rounding;
- ERV formula exactly documented;
- STOP floor behavior;
- confidence heuristic exactly documented unless a numeric ambiguity is found and reported;
- hard blocks, approval rules, cooldown, attempt/contact caps;
- deterministic ranking/tie break;
- blocked alternatives remain representable for UI.

Tests must cover:
- ERV exact values;
- no float money;
- downtime retry blocked;
- high-value approval;
- contact cap;
- no positive action -> STOP;
- same input -> same ranking.

Run backend tests + Ruff and stop.
```

---

# Prompt 10 — Synthetic ML Dataset

```text
Read first:
- AI_ML_DESIGN.md sections 2–6
- RECOVERY_ENGINE.md candidate/action semantics
- .cursor/rules/architecture.mdc

Scope: synthetic action-level ML dataset generation only.

Allowed to modify:
- scripts/ml/generate_training_data.py
- scripts/ml/common.py if needed
- data/synthetic/.gitkeep and generated outputs only if repository policy allows committing small samples
- apps/api/tests/ml/test_synthetic_data.py
- backend dev dependencies only if needed for pandas/numpy

Do NOT train a model in this prompt.
Do NOT change RecoveryFeaturesV1.

Implement deterministic generation with a fixed seed:
- 10k+ cases by default configurable downward for fast tests;
- 3–6 valid candidate actions/case;
- latent probability conditional on failure/action/customer/history;
- outcome labels recovered_within_72h;
- group split assignment by case ID;
- no case crossing train/validation/test;
- summary JSON with distributions.

Include tests for intended directional relationships, e.g. active downtime should make same-method retry worse than alternate-method action on average.

Run generator in a small test mode plus pytest/Ruff. Report produced row counts/distributions and stop.
```

---

# Prompt 11 — Logistic Regression Baseline

```text
Read first:
- AI_ML_DESIGN.md sections 6–11
- RECOVERY_ENGINE.md batch evaluation section
- .cursor/rules/architecture.mdc

Scope: train/evaluate Logistic Regression baseline only.

Allowed to modify:
- scripts/ml/train_baseline.py
- scripts/ml/evaluate.py
- scripts/ml/common.py
- apps/api/app/ml/artifacts/**
- apps/api/app/ml/schemas.py if model-bundle metadata schema is needed
- apps/api/tests/ml/**
- backend ML dependencies only

Do NOT implement XGBoost yet.
Do NOT change synthetic generator coefficients merely to make metrics look better unless there is a documented generator bug.

Requirements:
- ColumnTransformer preprocessing;
- group-preserved split data created by generator;
- LogisticRegression with reproducible configuration;
- ROC-AUC, PR-AUC, log loss, Brier and calibration summary;
- policy simulation vs naive baseline on test set;
- serialize trusted model bundle with model_version and recovery_features_v1;
- write machine-readable metrics JSON.

Tests:
- artifact loads;
- finite 0..1 probabilities;
- schema/version fields;
- same artifact predicts repeatably.

Run training once, report held-out metrics honestly, run tests/Ruff, stop.
```

---

# Prompt 12 — XGBoost Evaluation and Selection

```text
Read first:
- AI_ML_DESIGN.md sections 8–10
- metrics produced by Logistic Regression milestone
- .cursor/rules/architecture.mdc

Scope: one restrained XGBoost candidate, calibration if necessary, and documented model selection.

Allowed to modify:
- scripts/ml/train_xgboost.py
- scripts/ml/evaluate.py/common helpers
- apps/api/app/ml/artifacts/**
- docs/MODEL_SELECTION.md
- apps/api/tests/ml/**
- dependency file only for xgboost if selected for evaluation

Do NOT run a large hyperparameter sweep.
Do NOT select XGBoost just because it is more complex.

Train a modest candidate using validation-based early stopping. Compare test/calibration/business-policy metrics using the selection rule in AI_ML_DESIGN.md.

If Logistic Regression is better or essentially tied, keep it as runtime default and say so clearly.
If XGBoost materially wins, save the calibrated XGBoost bundle as runtime default.

Tests must use the same runtime inference contract regardless of winner.
Report both metric sets, selection reason, files changed, checks, and stop.
```

---

# Prompt 13 — Runtime Model Service + Analyze API

```text
Read first:
- AI_ML_DESIGN.md runtime inference contract
- RECOVERY_ENGINE.md full analysis pseudocode
- API_CONTRACTS.md section 6
- STATE_MACHINE.md relevant DETECTED/ANALYZING/RECOMMENDED transitions
- .cursor/rules/architecture.mdc

Scope: connect the chosen model/fallback into a persisted case analysis workflow and POST analyze API.

Allowed to modify:
- apps/api/app/ml/service.py
- apps/api/app/ml/schemas.py
- apps/api/app/recovery/service.py
- apps/api/app/workflows/recovery.py
- apps/api/app/api/routes/recovery_analysis.py
- apps/api/app/api/router.py
- apps/api/app/schemas/recovery_analysis.py
- relevant repositories
- apps/api/tests/recovery/**
- apps/api/tests/api/test_recovery_analysis.py

Do NOT add Razorpay network calls or LLM calls.

Requirements:
- load versioned artifact safely;
- validate recovery_features_v1;
- fallback on configured inference failure;
- persist all candidate recommendations in one immutable analysis_run_id;
- compute probabilities, ERV, confidence, policy, ranks;
- persist selected case summary fields;
- use state-machine service for transitions only;
- expose POST /api/v1/recovery-cases/{id}/analyze exactly per API contract.

Tests:
- seeded case analysis;
- previous analysis remains immutable after reanalysis;
- invalid state;
- model unavailable fallback;
- model/schema version persisted;
- tenant auth.

Run all backend checks and stop.
```

---

# Prompt 14 — Razorpay Webhook Receiver

```text
Read first:
- RAZORPAY_INTEGRATION.md sections 1–9, 11, 16
- STATE_MACHINE.md out-of-order/success precedence
- DATABASE_SCHEMA.md webhook idempotency
- API_CONTRACTS.md webhook section
- .cursor/rules/architecture.mdc

Scope: secure Razorpay webhook ingestion only. No Payment Link POST yet.

Allowed to modify:
- apps/api/app/integrations/razorpay/webhooks.py
- apps/api/app/integrations/razorpay/schemas.py
- apps/api/app/integrations/razorpay/errors.py
- apps/api/app/api/routes/razorpay_webhooks.py
- apps/api/app/services/provider_events.py
- apps/api/app/repositories/webhook_events.py
- transaction/subscription repositories only as required
- apps/api/tests/integrations/razorpay/**
- apps/api/tests/api/test_razorpay_webhooks.py

Implement:
- exact raw-body HMAC-SHA256 verification with constant-time compare or official SDK equivalent;
- x-razorpay-event-id uniqueness;
- parse only after signature validation;
- payment.failed -> source upsert + idempotent case detection;
- payment.captured -> verified-success resolution when correlated;
- subscription.pending/charged/halted handling;
- payment_link.paid mapping only if an existing action/provider reference is present;
- stale/out-of-order event checks;
- no LLM/slow analysis inside webhook route.

Tests must include valid/invalid signature, duplicate ID, captured-before-failed, charged-before-old-pending, unknown event, and idempotent case creation.

Use fixtures modeled on official payload shapes but keep them minimal and synthetic.
Run backend tests/Ruff and stop.
```

---

# Prompt 15 — Razorpay Payment/Downtime Reads

```text
Read first:
- RAZORPAY_INTEGRATION.md sections 2, 3, 12–14
- RECOVERY_ENGINE.md downtime semantics
- .cursor/rules/architecture.mdc

Scope: Razorpay API client plus read-only payment/downtime adapters.

Allowed to modify:
- apps/api/app/integrations/razorpay/client.py
- apps/api/app/integrations/razorpay/payments.py
- apps/api/app/integrations/razorpay/downtime.py
- apps/api/app/integrations/razorpay/schemas.py
- apps/api/app/integrations/razorpay/errors.py
- apps/api/app/recovery/context.py or feature-context integration only as necessary
- tests for these modules
- provider dependency only if justified

Implement documented endpoints:
- GET /v1/payments/:id
- GET /v1/payments/downtimes
- optional GET /v1/payments/downtimes/:id helper

Requirements:
- backend credentials only;
- explicit connect/read timeout;
- typed DTOs/errors;
- bounded retries only for safe reads;
- downtime lookup failure maps to UNKNOWN context, not NO_DOWNTIME;
- matching uses method/instrument/time/status, not global “any downtime”.

Tests use mocked HTTP. No test suite should require live internet/Razorpay.
Run checks and stop.
```

---

# Prompt 16 — Policy-safe Recovery Actions + Payment Link

```text
Read first:
- API_CONTRACTS.md sections 7–9
- RAZORPAY_INTEGRATION.md sections 10, 13–15
- STATE_MACHINE.md execution/unknown/retry semantics
- DATABASE_SCHEMA.md idempotency and transaction boundaries
- RECOVERY_ENGINE.md policy/stopping rules
- .cursor/rules/architecture.mdc

Scope: P0 action creation/execution, approval, WAIT/STOP, and Razorpay Standard Payment Link adapter.

Allowed to modify:
- apps/api/app/actions/**
- apps/api/app/integrations/razorpay/payment_links.py
- apps/api/app/api/routes/recovery_actions.py
- apps/api/app/schemas/recovery_actions.py
- workflow/repository files required to use existing state machine
- tests for actions/API/integration

Do NOT implement bulk actions.
Do NOT create arbitrary debits.
Do NOT trust frontend-supplied amount/probability/ERV.

Implement:
- POST case action endpoint;
- server-side revalidation of current case, recommendation and policy;
- deterministic local idempotency key and attempt_number;
- persist action intent before external call;
- WAIT schedule;
- STOP;
- CREATE_PAYMENT_LINK via POST /v1/payment_links with accept_partial=false and unique reference_id;
- PENDING_APPROVAL path;
- approve and reject endpoints;
- UNKNOWN provider timeout behavior requiring reconciliation before retry;
- action/provider references needed for payment_link.paid outcome mapping.

Tests:
- double click creates one action;
- amount over threshold requires approval;
- stale case version blocks approval;
- terminal case blocks action;
- provider validation error;
- unknown timeout does not issue a second POST;
- successful mocked Payment Link moves case to WAITING_FOR_OUTCOME.

After automated tests, if Razorpay test credentials are locally configured, add/document a manual smoke command but do not make CI depend on it.
Run checks and stop.
```

---

# Prompt 17 — LLM Explanation Service

```text
Read first:
- AI_ML_DESIGN.md sections 12–19
- DOMAIN_MODEL.md AuditLog/Recommendation semantics
- ARCHITECTURE.md LLM boundary
- .cursor/rules/architecture.mdc

Scope: structured non-authoritative explanation and bounded outreach generation.

Allowed to modify:
- apps/api/app/ai/**
- apps/api/app/recovery/service.py only to attach explanation after authoritative recommendation is persisted
- relevant response schemas
- tests for AI/fallback
- backend dependency config for the selected direct LLM SDK only

Do NOT modify model probabilities, ERV, action selection, policy, or state-machine logic.
Do NOT add RAG, agent memory, LangChain, LangGraph, or tool-calling payment access.

Implement:
- LLMProvider protocol;
- configured Gemini provider/default if key exists;
- RecommendationExplanation and OutreachDraft schemas;
- prompts built exclusively from approved structured facts;
- strict schema validation;
- deterministic template fallback for timeout/rate limit/invalid output/no key;
- explanation_source field;
- no chain-of-thought storage/exposure.

Tests:
- valid structured response;
- malformed JSON;
- provider timeout;
- attempted unsupported numeric/factual changes rejected or replaced by fallback;
- no-key fallback.

Run backend checks and stop.
```

---

# Prompt 18 — Frontend Shell + API Client

```text
Read first:
- FRONTEND_SPEC.md sections 1–3 and 8–12
- API_CONTRACTS.md common conventions/errors
- ARCHITECTURE.md frontend/backend boundary
- .cursor/rules/architecture.mdc

Scope: frontend foundation only.

Allowed to modify:
- apps/web/app/** shell/layout/navigation only
- apps/web/components/app-shell/**
- apps/web/components/money/**
- apps/web/components/status-badge/**
- apps/web/lib/api/**
- apps/web/lib/auth/**
- apps/web/types/generated/** if generated from OpenAPI
- frontend tests/config/dependencies needed for these pieces

Do NOT build dashboard/opportunity/case pages yet beyond route placeholders.
Do NOT query PostgreSQL directly from the browser for domain data.
Do NOT expose backend/provider secrets.

Implement:
- polished desktop-first B2B shell;
- environment badge for Demo / Razorpay Test Mode;
- typed API client/error handling;
- authenticated token injection boundary;
- central money formatter;
- domain status badge mapper;
- loading/error primitives.

Generate frontend API types from current FastAPI OpenAPI if practical; otherwise create a documented temporary generated-client step rather than duplicate handwritten contracts.

Tests: money formatting, status badges, API error mapping; lint, typecheck, unit tests.
Stop after report.
```

---

# Prompt 19 — Executive Dashboard

```text
Read first:
- FRONTEND_SPEC.md Screen 1
- API_CONTRACTS.md dashboard response
- .cursor/rules/architecture.mdc

Scope: /dashboard only.

Allowed to modify:
- apps/web/app/dashboard/**
- apps/web/features/dashboard/**
- apps/web/components/charts/** as needed
- API hooks specific to dashboard
- dashboard tests

Do NOT hardcode KPI/chart results except test fixtures.
Do NOT create new backend fields silently; if the API does not provide required documented data, report the mismatch before changing contracts.

Implement:
- money-first KPI cards;
- synthetic/test source label;
- recovery trend;
- action effectiveness;
- failure breakdown;
- top opportunities;
- skeleton loading;
- localized error with retry;
- empty state.

Keep charts readable on a projector and avoid decorative complexity.

Run frontend lint/typecheck/unit tests and production build. Stop after report.
```

---

# Prompt 20 — Recovery Opportunities Page

```text
Read first:
- FRONTEND_SPEC.md Screen 2
- API_CONTRACTS.md recovery list endpoint
- .cursor/rules/architecture.mdc

Scope: /recovery list page only.

Allowed to modify:
- apps/web/app/recovery/page.tsx and route-local files
- apps/web/features/recovery/RecoveryTable.tsx
- apps/web/features/recovery/RecoveryFilters.tsx
- shared small recovery display components
- list API hooks/tests

Do NOT implement bulk actions.
Do NOT add client-calculated risk/ERV.

Implement documented columns, filters, sort, search, pagination, loading/error/empty states, and row navigation to /recovery/[caseId].
Default sort by backend priority descending.

Tests: filter query mapping, empty/error, row navigation, money/probability display.
Run frontend checks/build and stop.
```

---

# Prompt 21 — Recovery Case Detail

```text
Read first:
- FRONTEND_SPEC.md Screen 3
- API_CONTRACTS.md case detail/analyze/actions/approval sections
- STATE_MACHINE.md state-dependent behavior
- .cursor/rules/architecture.mdc

Scope: /recovery/[caseId] detail and action controls, excluding timeline implementation if it is clearer to do separately.

Allowed to modify:
- apps/web/app/recovery/[caseId]/**
- apps/web/features/recovery/CaseHeader.tsx
- FailureEvidenceCard.tsx
- RecommendationCard.tsx
- CandidateActionsTable.tsx
- ActionControlPanel.tsx
- RecoveryOutcomeCard.tsx
- relevant API hooks/tests

Implement state-aware controls exactly from FRONTEND_SPEC.md.
The server remains authoritative: never enable a blocked action merely because local UI thinks it is safe.
Handle 409/stale conflicts by refetching and explaining that case state changed.
While WAITING_FOR_OUTCOME, implement bounded 3–5 second polling or a manual refresh strategy; do not add WebSockets.

Tests: controls by state/role, execute mutation, approval state, conflict refresh, recovered view.
Run frontend checks/build and stop.
```

---

# Prompt 22 — Agent / Audit Timeline

```text
Read first:
- FRONTEND_SPEC.md Screen 4
- DOMAIN_MODEL.md AuditLog
- API_CONTRACTS.md timeline endpoint
- .cursor/rules/architecture.mdc

Scope: audit timeline embedded on case detail.

Allowed to modify:
- apps/web/features/recovery/AuditTimeline.tsx
- case detail composition
- timeline API hook/tests

Do NOT expose model chain-of-thought, raw webhook bodies, secrets, full phone/email, or unnecessary PII.

Implement chronological entries with event category icons, concise summary, timestamp, safe evidence disclosure, model/provider labels where present, and stale-event warnings.

Ensure the following events read clearly in the demo:
Detected → Diagnosed → Analyzed → Policy checked → Executed → Provider success → Recovered.

Run frontend checks/build and stop.
```

---

# Prompt 23 — Demo Batch + Reset

```text
Read first:
- RECOVERY_ENGINE.md batch evaluation
- AI_ML_DESIGN.md business-policy evaluation
- API_CONTRACTS.md demo-only endpoints
- IMPLEMENTATION_PLAN.md Milestone 21
- .cursor/rules/architecture.mdc

Scope: deterministic synthetic batch evaluation and demo reset only.

Allowed to modify:
- apps/api/app/demo/**
- apps/api/app/api/routes/demo.py
- scripts/demo/**
- apps/api/tests/demo/**
- dashboard analytics only if needed to correctly expose resulting stored metrics
- frontend source-label rendering only if needed

Requirements:
- routes exist only when DEMO_MODE=true and require ADMIN;
- reset restores exact deterministic demo state;
- run-batch clearly returns data_source=SYNTHETIC_SIMULATION;
- compare RecoverIQ policy vs documented naive baseline;
- do not call Razorpay for each synthetic case;
- do not mix simulated outcome evidence with Razorpay test evidence.

Tests: deterministic reset, arithmetic, role/environment gate, no real-provider adapter invoked in batch.
Run backend and affected frontend checks, stop.
```

---

# Prompt 24 — Full Integration Review

```text
Read first:
- ARCHITECTURE.md in full
- STATE_MACHINE.md in full
- API_CONTRACTS.md P0 routes
- RAZORPAY_INTEGRATION.md in full
- FRONTEND_SPEC.md
- .cursor/rules/architecture.mdc

Goal: integrate existing milestones; do not add features.

Allowed to modify only files necessary to fix integration contract mismatches among existing P0 modules.
Do NOT redesign schemas or add features simply to make wiring easier.
Do NOT perform broad refactoring.

Verify the complete local/mock-provider flow:
1. qualifying failure event creates one case;
2. case can be analyzed;
3. candidate probabilities/ERV/policy are persisted;
4. safe action can be created exactly once;
5. action enters WAITING_FOR_OUTCOME;
6. verified synthetic Razorpay-style success event resolves it;
7. RecoveryOutcome exists exactly once;
8. timeline reflects every step;
9. dashboard recovered revenue changes from database data;
10. LLM disabled still leaves entire flow working.

Find and fix contract mismatches one by one, adding regression tests.
Run full backend and frontend checks. Do not proceed to E2E until green. Report remaining blockers and stop.
```

---

# Prompt 25 — End-to-End Tests

```text
Read first:
- IMPLEMENTATION_PLAN.md Milestone 22
- FRONTEND_SPEC.md demo-critical elements
- API_CONTRACTS.md mutation flows
- .cursor/rules/architecture.mdc

Scope: automated critical-path E2E reliability using Playwright plus any test-only deterministic provider hooks already allowed by DEMO_MODE/test config.

Allowed to modify:
- apps/web/e2e/** or tests/e2e/**
- Playwright config
- test fixtures
- narrowly scoped test-mode backend helpers that are inaccessible outside test/DEMO_MODE
- bug fixes required by failing E2E, each with regression coverage

Do NOT change product behavior merely to make tests easy.
Do NOT require live Razorpay or live LLM for CI E2E.

Automate:
Dashboard → Recovery Opportunities → Case Detail → Analyze → Execute mock Payment Link action → inject verified test success through safe test fixture → RECOVERED → dashboard KPI increases.

Also cover at least:
- action double click;
- stale case version/409 refresh;
- LLM unavailable fallback;
- duplicate webhook idempotency.

Run full backend tests/Ruff, frontend lint/typecheck/unit tests, Playwright, and production build. Fix related failures. Stop with a pass/fail table.
```

---

# Prompt 26 — Razorpay Test-Mode Smoke and Deployment Hardening

```text
Read first:
- RAZORPAY_INTEGRATION.md test-mode workflow
- ARCHITECTURE.md configuration and locked decisions
- IMPLEMENTATION_PLAN.md Milestone 23
- .cursor/rules/architecture.mdc

Scope: deploy/harden existing P0 system. No new product features.

Allowed to modify:
- deployment/environment config
- CORS/host settings
- health/start commands
- Razorpay adapter fixes proven necessary by actual test-mode behavior
- docs/README deployment/demo instructions
- narrowly scoped bugs found during deployment

Do NOT put secrets in source or NEXT_PUBLIC variables.
Do NOT move to Kubernetes/microservices.
Do NOT replace working frameworks.

Tasks:
- document Vercel web deployment;
- document Render FastAPI deployment and startup command;
- document Supabase DATABASE_URL/Auth configuration;
- apply Alembic migrations;
- configure Razorpay Test Mode webhook URL/events;
- perform one real Standard Payment Link create/fetch/payment-success smoke flow if credentials are available;
- verify subscription webhook setup/test flow if it is reliable, but do not make the main demo depend on a fragile manual setup;
- verify backend warm-up strategy;
- verify demo reset;
- verify public URLs and no browser console errors.

Run all automated tests after deployment-related edits. Report exact real integration steps that passed and anything that remained simulated. Stop.
```

---

# Prompt 27 — Final Architecture and Safety Review

```text
You are doing a final pre-submission review, not adding features.

Read all root RecoverIQ engineering documents and .cursor/rules/architecture.mdc.

Audit the implementation for these failure classes:
- direct RecoveryCase.status assignments outside workflow state machine;
- float money arithmetic;
- tenant scope omissions;
- duplicate webhook/action vulnerabilities;
- provider POST retry after unknown result;
- stale/out-of-order webhook state regression;
- LLM influencing authoritative amount, ERV, policy or action authorization;
- RECOVERED without verified outcome;
- synthetic metrics presented without source label;
- secrets in frontend or repository;
- dead demo buttons;
- unhandled 409/timeout paths;
- divergence between API contracts and frontend assumptions.

Make only targeted correctness fixes with regression tests. Do not refactor stylistically or add features.

Then run the full backend test/lint suite, frontend lint/typecheck/unit/build, and E2E suite.

Return:
1. critical issues found and fixed;
2. files changed;
3. full pass/fail checks;
4. any remaining known limitation that should be disclosed in README/demo.
```

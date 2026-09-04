# RevLoop

**AI revenue-recovery control plane for Razorpay merchants — Track 03: AI Revenue Recovery.**

RevLoop detects revenue at risk (failed payments, failed/halted subscriptions),
diagnoses why it happened using Razorpay's own failure evidence, predicts the
recovery probability of each candidate intervention, ranks interventions by
**Expected Recovery Value (ERV)** under merchant safety policy, executes the
selected action, verifies the outcome through a webhook, and measures exactly
how much revenue came back — with a full audit trail and deterministic
stopping rules.

It is not a failed-payments dashboard with a chatbot bolted on. The
closed loop is:

```text
EVENT → EVIDENCE → PREDICTION → DECISION → POLICY → ACTION → VERIFICATION → MONEY → AUDIT
```

## The problem

A payment failure doesn't have to mean lost revenue, but merchants rarely
have a system that decides *which* failures are recoverable, *which*
intervention to use, and *when to stop*. Blind retrying can make things
worse (retrying into a degraded payment rail, over-contacting a customer,
retrying a subscription Razorpay is already retrying). RevLoop replaces
that guesswork with an optimizer: for every case it estimates
`P(recovery | case, action)` for each candidate action — not just whether the
customer will pay, but whether they'll pay *if we choose this specific
intervention* — combines that with the amount at risk to get ERV, and picks
the highest-ERV action that survives the policy gate.

## How recovery works

```text
Razorpay webhook (payment.failed / subscription.pending / subscription.halted)
    ↓ verify signature, dedupe by event id
Normalize failure (AUTHENTICATION_FAILURE, PAYMENT_RAIL_DOWNTIME, MANDATE_FAILURE, …)
    ↓
Build features (customer history, payment-downtime context, contact/attempt counts)
    ↓
Score candidate actions (WAIT, RETRY, ALT_PAYMENT_METHOD, PAYMENT_LINK, ESCALATE, STOP)
    ↓
Rank by Expected Recovery Value
    ↓
Apply merchant policy (amount ceiling, confidence floor, contact caps, downtime blocks)
    ↓
Execute (Razorpay Standard Payment Link, wait/schedule, escalate, or stop)
    ↓
Verify via webhook (never "message sent" = "recovered")
    ↓
RECOVERED — measured, audited, dashboarded
```

Every step is a state transition inside one authoritative `RecoveryCase`
state machine (`STATE_MACHINE.md`) — no code outside the workflow layer may
assign case status directly.

## AI architecture

- **Recovery Propensity Model** — predicts `P(recovery | case, action)` per
  candidate action. Logistic Regression baseline and an XGBoost challenger
  were both trained on a deterministic synthetic dataset with genuine
  conditional structure (e.g. active downtime + same-method retry scores
  much lower than downtime + alternate method); XGBoost did not clear the
  predeclared materiality bar, so **Logistic Regression is the runtime
  default** — see `docs/MODEL_SELECTION.md` for the full honest comparison.
- **Expected Recovery Value engine** — deterministic, `Decimal`-based money
  math combining action-specific probability, amount at risk, and
  cost/fatigue/delay/risk penalties. No floats touch money anywhere in the
  codebase.
- **Policy engine** — deterministic safety gate: automatic-amount ceiling,
  minimum confidence, contact caps, cooldown, attempt limits, downtime
  retry blocks, human-approval requirements.
- **LLM (Gemini, optional)** — generates the structured explanation and
  bounded outreach copy shown on a case, from server-approved facts only. It
  cannot alter amounts, probabilities, policy outcomes, or which action was
  selected, and every numeric/factual claim it produces is schema- and
  semantically-validated against the authoritative values before it's shown.
  If Gemini is unavailable or unconfigured, a deterministic template
  fallback keeps the rest of the system fully working — the AI layer is
  never on the critical path for money-moving decisions.

## Architecture diagram

```mermaid
flowchart TD
    USER[Revenue Ops / Finance User]
    CUSTOMER[Customer]
    WEB[Next.js Web App]
    API[FastAPI API]
    WH[Razorpay Webhook Endpoint]
    WF[Recovery Workflow Orchestrator]
    REC[Recovery Engine]
    POLICY[Policy Engine]
    ML[ML Inference Service]
    LLM[LLM Explanation / Outreach]
    EXEC[Action Executor]
    DB[(PostgreSQL)]
    AUDIT[Audit + Structured Logs]
    RP[Razorpay Test APIs]
    DOWN[Razorpay Payment Downtime]

    USER --> WEB --> API --> DB
    API --> WF
    RP --> WH --> WF
    WF --> REC --> ML
    REC --> DOWN
    REC --> POLICY --> WF
    WF --> LLM
    WF --> EXEC --> RP
    WF --> DB
    API --> AUDIT
    WF --> AUDIT
    EXEC --> AUDIT
    CUSTOMER --> RP
```

Full component ownership and dependency rules: `ARCHITECTURE.md`.

## Technology stack

| Layer | Technology |
|---|---|
| Web UI | Next.js, TypeScript, Tailwind, TanStack Table, Recharts |
| API | FastAPI, Pydantic |
| Persistence | PostgreSQL, SQLAlchemy 2, Alembic |
| Recovery engine | Plain Python domain services (deterministic) |
| ML | scikit-learn (runtime default), XGBoost (evaluated challenger) |
| LLM | Provider abstraction, Gemini default, deterministic fallback |
| Payments | Razorpay Test Mode — Payments, Subscriptions, Payment Downtime, Standard Payment Links, Webhooks |
| Deployment | Vercel (web) + Railway (API, containerized) + Supabase (Postgres) |

## Razorpay integration

Real, not simulated: signature-verified webhook ingestion (`payment.failed`,
`payment.captured`, `subscription.pending`, `subscription.charged`,
`subscription.halted`, `payment_link.paid`), Standard Payment Link
creation/fetch for selected recovery actions, Payment Downtime reads used to
block/penalize same-rail retries during a known outage, and out-of-order /
duplicate webhook handling driven by provider event timestamps and status
precedence rather than delivery order. RevLoop deliberately does not
compete with Razorpay's own subscription retry behavior — it decides
*whether to wait for that retry* versus intervening. Details and the exact
field mappings used: `RAZORPAY_INTEGRATION.md`.

## Dataset & evaluation

Two distinct, clearly labeled datasets:

- **Demo/dashboard seed** (`scripts/seed_demo.py`) — one deterministic demo
  organization, 79 customers, 655 transactions, 115 recovery cases across
  active/recovered/failed/stopped states, tagged `is_synthetic`.
- **ML training data** (`scripts/ml/generate_training_data.py`) — a larger
  synthetic case-action dataset with genuine conditional latent-probability
  structure (not noise), group-split by case id so no case crosses
  train/validation/test.

Batch evaluation (`POST /api/v1/demo/run-batch`, demo-mode only) compares
RevLoop's policy against a naive immediate-retry baseline and reports
`data_source: SYNTHETIC_SIMULATION` explicitly — synthetic results are never
presented as production recovered revenue. The one live path (Payment Link
creation → webhook → RECOVERED) runs against real Razorpay Test Mode.

## Safety & explainability

- Every external action carries a deterministic, DB-enforced idempotency
  key; a duplicate click or duplicate webhook cannot create a duplicate
  action or duplicate outcome.
- A case can only reach `RECOVERED` after a persisted, webhook-verified
  `RecoveryOutcome` — never on "action sent."
- A non-idempotent POST (e.g. Payment Link creation) is never auto-retried
  after a timeout/unknown result; it's reconciled via a provider read first.
- Every case-level recommendation records its model version and confidence;
  low confidence routes to human approval instead of automation.
- Every state transition, policy decision, and executed action is written
  to an append-only audit log, rendered as the case timeline.

## Project structure

```text
apps/web/     Next.js dashboard (dashboard, opportunities, case detail, audit timeline)
apps/api/     FastAPI modular monolith (recovery engine, workflows, policies, ML, AI, Razorpay adapter)
data/         Synthetic/demo data
scripts/      Seed and ML training scripts
docs/         Supplementary docs (model selection)
infra/        Local/deployment placeholders
```

See `ARCHITECTURE.md` for module ownership and `DATABASE_SCHEMA.md` /
`DOMAIN_MODEL.md` for the data model.

## Local setup

### Prerequisites

- **Node.js** 20+ and npm
- **Python** 3.10+
- **PostgreSQL** (or Docker, to run one locally) — most integration/workflow
  tests and the demo seed require it

### Environment variables

Copy `.env.example` to `.env` and fill in local values (a local `DATABASE_URL`
is required; Razorpay, Gemini, and Supabase JWT verification are optional —
see the comments in `.env.example`). Never commit real secrets.

### Backend (`apps/api`)

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Apply migrations against your local Postgres
alembic upgrade head

# Boot
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check: `GET http://localhost:8000/health`.

### Frontend (`apps/web`)

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:3000`.

### Database setup

```bash
cd apps/api
source .venv/bin/activate
alembic upgrade head
python ../../scripts/seed_demo.py
```

The seed is idempotent and reproducible — rerunning it against an already
seeded database is a no-op; reset behavior is via `POST /api/v1/demo/reset`
(demo mode, admin-only) or by dropping and recreating the database.

### Running the ML pipeline

```bash
cd apps/api
source .venv/bin/activate
python ../../scripts/ml/generate_training_data.py
python ../../scripts/ml/train_baseline.py     # Logistic Regression
python ../../scripts/ml/train_xgboost.py      # XGBoost challenger
```

Selection reasoning and metrics: `docs/MODEL_SELECTION.md`.

### Running tests

```bash
# Backend — set REVLOOP_TEST_DATABASE_URL to run the full suite (otherwise
# Postgres-backed tests are skipped, not failed)
cd apps/api
source .venv/bin/activate
REVLOOP_TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/revloop_test \
  python -m pytest -q
ruff check app tests

# Frontend
cd apps/web
npm run lint
npm run typecheck
npm test -- --run
npm run build

# End-to-end (spins up its own backend/frontend/provider-stub stack)
cd apps/web
REVLOOP_TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/revloop_test \
  npx playwright test
```

## Deployment

`DEPLOYMENT.md` covers the full hosted setup — Vercel, Railway, Supabase,
and Razorpay Test Mode — including exact environment variables, the
migration strategy, CORS, warm-up timing, and the demo reset procedure. The
backend ships as a container built from the repository-root `Dockerfile`;
the build context must be the repository root so the demo's canonical ML
bridge can resolve `scripts/ml`:

```bash
docker build -t revloop-api .
```

## Demo mode

`DEMO_MODE=true` registers `/api/v1/demo/*` (reset, run-batch); these routes
do not exist when demo mode is off. `APP_ENV=development` or `test` selects
`DevAuthBackend`, which accepts the literal bearer tokens `dev-analyst`,
`dev-operator`, and `dev-admin` — this is what the current UI and E2E suite
run against.

## Limitations

- **Production authentication is not implemented.** `SupabaseAuthBackend`
  currently returns `501` for every token; only the development bearer
  tokens work. A public deployment today is a private demo, not a
  production-ready multi-tenant system — see `DEPLOYMENT.md` section 1.
- **Batch/model evaluation uses synthetic data**, clearly labeled as such
  everywhere it's surfaced; only the single live Payment-Link-to-webhook
  flow runs against real Razorpay Test Mode.
- Overdue-invoice recovery, Hinglish/multilingual outreach, forecasting,
  and anomaly detection are intentionally out of scope for this phase (see
  `MASTER_PRD.md` for the full future roadmap).

## Future roadmap

In priority order once the above is addressed: overdue-invoice/B2B
receivables recovery, Hinglish recovery messages, recovery forecasting,
payment-failure anomaly detection, real email delivery, and a recovery
playbook knowledge base.

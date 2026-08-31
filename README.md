# RevLoop

AI-assisted revenue recovery control plane for Razorpay merchants.

Phase 0 provides a monorepo skeleton with a Next.js frontend and FastAPI backend. No business features are implemented yet.

## Prerequisites

- **Node.js** 20+ and npm
- **Python** 3.10+
- Optional: copy `.env.example` to `.env` for later milestones (not required for Phase 0 boot)

## Repository layout

```text
apps/web/     Next.js dashboard (Phase 0 placeholder UI)
apps/api/     FastAPI modular monolith backend
data/         Synthetic/demo data (placeholder)
scripts/      Seed and utility scripts (placeholder)
docs/         Supplementary docs (placeholder)
infra/        Local/deployment placeholders
```

## Backend (`apps/api`)

### Setup

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Boot (development)

```bash
cd apps/api
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check: `GET http://localhost:8000/health` → `{"status":"ok","service":"revloop-api"}`

### Test

```bash
cd apps/api
source .venv/bin/activate
python -m pytest -q
```

### Lint

```bash
cd apps/api
source .venv/bin/activate
ruff check app tests
```

### Import smoke

```bash
cd apps/api
source .venv/bin/activate
python -c "from app.main import app; print(app.title)"
```

## Frontend (`apps/web`)

### Setup

```bash
cd apps/web
npm install
```

### Boot (development)

```bash
cd apps/web
npm run dev
```

Open `http://localhost:3000`.

### Lint

```bash
cd apps/web
npm run lint
```

### Typecheck

```bash
cd apps/web
npm run typecheck
```

### Unit tests

```bash
cd apps/web
npm test -- --run
```

### Production build

```bash
cd apps/web
npm run build
```

## Phase 0 scope

- Modular-monolith directory structure per `ARCHITECTURE.md`
- Backend `GET /health` with smoke test
- Frontend lint, typecheck, unit-test runner, and build tooling
- No database models, Razorpay, ML, LLM, or recovery logic

See `IMPLEMENTATION_PLAN.md` for subsequent milestones.

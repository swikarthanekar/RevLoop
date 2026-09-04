# RevLoop deployment

Hosting layout for the hackathon demo:

| Piece | Host | Source |
| --- | --- | --- |
| Frontend | Vercel | `apps/web` |
| Backend | Railway | repository root `Dockerfile` |
| Database | Supabase PostgreSQL | `DATABASE_URL` |
| Payments | Razorpay **Test Mode** | backend-only credentials |

Every value in this document is a placeholder. Real secrets belong in the
hosting provider's environment settings and never in the repository.

---

## 1. Authentication

Two backends exist and are selected by `APP_ENV` (`apps/api/app/core/auth.py`):

- **`DevAuthBackend`** — accepts the literal bearer strings `dev-analyst`,
  `dev-operator`, `dev-admin`, mapped to a fixed `DEV_AUTH_USER_ID` /
  `DEV_AUTH_ORGANIZATION_ID`. Selected only when `APP_ENV` is `development`
  or `test`.
- **`SupabaseAuthBackend`** — verifies a real Supabase Auth access token
  (audience `authenticated`), then resolves `organization_id`/`role` from the
  `user_profiles` row matching the token's `sub`. Selected for every other
  `APP_ENV` value (i.e. `production`). A verified token with no matching
  `user_profiles` row is `403 NO_ORGANIZATION_MEMBERSHIP`, not a silent
  grant.

  Supabase signs user access tokens one of two ways depending on the
  project, and the backend reads which from the token's own `alg` header
  rather than assuming one:
  - **Legacy shared secret (`HS256`)** — verified against
    `SUPABASE_JWT_SECRET`.
  - **JWT Signing Keys (`ES256`, the current default for new projects)** —
    verified against the project's public JWKS
    (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`), which requires
    `SUPABASE_URL` to be set. There is no shared secret to configure for
    this case; `SUPABASE_JWT_SECRET` is simply unused.

  Check **Supabase Dashboard → Project Settings → API → JWT Keys** to see
  which one a given project uses — decode any access token's header (the
  part before the first `.`) if unsure, and look at `alg`.

The frontend mirrors this: `apps/web/lib/auth/session.tsx` uses Supabase Auth
(`/login`, session persistence, sign-out) whenever
`NEXT_PUBLIC_SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_ANON_KEY` are both set, and
falls back to `NEXT_PUBLIC_DEV_AUTH_TOKEN` otherwise — see [section
4.1](#41-public-environment-variables).

**Do not** set `NEXT_PUBLIC_DEV_AUTH_TOKEN` on a public Vercel deployment
that also has Supabase configured (Supabase takes priority, so the dev token
would be unused there) or, especially, on one that does **not** have
Supabase configured — an unset Supabase config with the dev token set
inlines an ADMIN credential into the browser bundle for anyone who opens the
site. A production deployment should configure Supabase and leave
`NEXT_PUBLIC_DEV_AUTH_TOKEN` unset.

Before a real login works, a Supabase Auth user must exist and be linked to
the demo organization — see [section 2.5](#25-provisioning-a-real-admin-user).

---

## 2. Supabase

### 2.1 Manual steps

1. Create a Supabase project and choose a region close to the Railway region.
2. Copy the **Session pooler** connection string from
   *Project settings → Database → Connection string → Session pooler*.
3. Substitute the database password you set when creating the project.

### 2.2 Which connection string to use

Use the **session pooler on port 5432**:

```
postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

- The **direct** host (`db.<project-ref>.supabase.co`) resolves over IPv6 only,
  which a Railway service generally cannot reach.
- The **transaction pooler** (port 6543) is usually offered with
  `?pgbouncer=true`. `normalize_database_url` rewrites only the URL scheme, so
  that parameter is passed through to libpq, which rejects it as an unknown
  connection option. If you use port 6543, remove `?pgbouncer=true`; the session
  pooler avoids the question entirely and also supports the prepared statements
  SQLAlchemy issues.

### 2.3 URL normalization

`Settings.database_url` normalizes the scheme so SQLAlchemy 2 uses psycopg 3:

| Given | Used |
| --- | --- |
| `postgresql://…` | `postgresql+psycopg://…` |
| `postgres://…` | `postgresql+psycopg://…` |
| `postgresql+psycopg://…` | unchanged |

Userinfo, host, port, database and query string are preserved exactly,
including the dotted `postgres.<project-ref>` pooler username. Covered by
`apps/api/tests/db/test_supabase_database_url.py`.

### 2.4 Schema

The deployment path is: empty Supabase database → `alembic upgrade head` →
current head (`m3r06_webhooks_audit_policy`). Alembic reads `DATABASE_URL`
through the same `Settings` object the application uses
(`apps/api/alembic/env.py`), so there is one configuration boundary.

`Base.metadata.create_all()` is never used to initialize a deployed database.

### 2.5 Provisioning a real admin user

`SupabaseAuthBackend` verifies the token, then requires a matching
`user_profiles` row to know which organization/role it grants — creating a
Supabase Auth user alone is not enough.

1. **Supabase Dashboard → Authentication → Users → Add user.** Set an email
   and password (or invite by email). Copy the generated user UUID.
2. **Supabase Dashboard → Project Settings → API → JWT Secret.** This is the
   value for `SUPABASE_JWT_SECRET` on Railway (see [section
   3.6](#36-backend-environment-variables)) — not a value you invent. It
   must not start with `dev-`, or `Settings.validate_production_secrets`
   refuses to boot in `APP_ENV=production`.
3. **Supabase Dashboard → SQL Editor**, run (substituting the user UUID from
   step 1 and the demo organization id from [section
   7](#7-demo-data-and-identities)):

   ```sql
   insert into user_profiles (id, organization_id, auth_user_id, role)
   values (
     gen_random_uuid(),
     '82757dbc-e0d0-5285-8f26-7a9ab9837a24',  -- demo organization
     '<supabase-auth-user-uuid-from-step-1>',
     'ADMIN'
   );
   ```

   `gen_random_uuid()` is available by default on Supabase Postgres
   (`pgcrypto`). `role` must be one of `ADMIN`, `OPERATOR`, `ANALYST`
   (enforced by a check constraint) — use `ADMIN` for the primary demo
   account so it can approve/reject actions and run demo reset.
4. Sign in at `<vercel-url>/login` with that email/password. `GET
   /api/v1/auth/me` (called by the frontend right after sign-in) should
   return the organization and role from the row above; if it 403s with
   `NO_ORGANIZATION_MEMBERSHIP`, the `auth_user_id` in step 3 doesn't match
   the signed-in user's UUID.
5. Optional: to give judges/reviewers a one-click "Continue as demo" button
   instead of asking them to type this account's credentials, set
   `NEXT_PUBLIC_DEMO_LOGIN_EMAIL`/`NEXT_PUBLIC_DEMO_LOGIN_PASSWORD` on Vercel
   to this same email/password — see [section
   4.1](#41-public-environment-variables) for the exposure tradeoff before
   doing so.

---

## 3. Railway backend

### 3.1 Build

| Setting | Value |
| --- | --- |
| Source repository root directory | `/` (repository root) |
| Builder | Dockerfile (auto-detected) |
| Dockerfile path | `Dockerfile` |
| Build context | repository root |
| Base image | `python:3.10-slim` |
| Dependencies | `apps/api/requirements.txt` |
| Runtime working directory | `/app/apps/api` |
| Process user | non-root (`revloop`, uid 10001) |

**The build context must be the repository root, not `apps/api`.** The demo's
canonical evaluation bridge (`apps/api/app/demo/canonical_ml.py`) locates the
training modules relative to its own file, four levels up plus `scripts`, so the
image reproduces that layout: application at `/app/apps/api`, canonical ML at
`/app/scripts/ml`. A service rooted at `apps/api` cannot see `scripts/` and the
demo batch endpoint fails with `CANONICAL_EVALUATION_UNAVAILABLE`.

### 3.2 Start command and port

The image's entrypoint (`apps/api/deploy/entrypoint.sh`) runs:

```sh
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
```

Railway injects `PORT`; nothing is hardcoded for the hosted deployment. Leave
Railway's start command empty so the image entrypoint is used.

### 3.3 Migrations

Migrations run in the entrypoint, before the server starts. The script uses
`set -eu`, so a failed `alembic upgrade head` exits non-zero and the deployment
fails instead of serving against a schema the code does not expect. There is no
fallback branch.

Run **one replica**. One instance means one migration runner, which is what this
strategy assumes.

Railway's *Pre-Deploy Command* field is an equally valid place for
`alembic upgrade head`. It is not used here because it lives only in the
dashboard, where it is invisible to the repository and easy to forget; the
entrypoint travels with the image and is covered by tests.

### 3.4 Health check

| Setting | Value |
| --- | --- |
| Healthcheck path | `/health` |
| Suggested timeout | 300 seconds |

`GET /health` (`apps/api/app/api/routes/health.py`) requires no authentication,
issues no Razorpay or Gemini call, opens no database connection, and mutates
nothing. It reports the API version and whether the configured model artifact is
present. The image sets `MODEL_BUNDLE_PATH` to the artifact it ships, so a
healthy deployment reports `"model": "loaded"`.

`/health` is the only readiness route; there is no `/ready`.

### 3.5 Config as code

No `railway.toml` or `railway.json` is committed. Railway's Config as Code is
deprecated, new services cannot opt into it, and existing files stop being read
on 2026-12-01. The build is therefore described by the `Dockerfile` in source,
and the handful of remaining settings are configured in the Railway UI as
listed above.

### 3.6 Backend environment variables

Set these on the Railway service. All are backend-only and must never be
mirrored into Vercel.

| Variable | Value | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Supabase session pooler URL | secret |
| `APP_ENV` | `development` or `production` | see [section 10](#10-demo-reset). `development` also keeps the `DEV_AUTH_*` bearer tokens working alongside Supabase, which is convenient while rehearsing; `production` requires the frontend's Supabase config and a provisioned admin user (section 2.5) for anything to authenticate, `/demo/reset` included |
| `DEMO_MODE` | `true` | registers the demo routes |
| `PUBLIC_APP_BASE_URL` | `https://<project>.vercel.app` | CORS origin |
| `DEV_AUTH_USER_ID` | `bc9f0349-0af8-557e-9557-4bdaadda544d` | canonical demo identity; only used when `APP_ENV=development` |
| `DEV_AUTH_ORGANIZATION_ID` | `82757dbc-e0d0-5285-8f26-7a9ab9837a24` | canonical demo tenant; only used when `APP_ENV=development` |
| `SUPABASE_JWT_SECRET` | project JWT secret | secret; used only if the project signs tokens with the legacy shared HS256 secret (section 1) — must be the real value from Supabase, not a placeholder, if used |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` | not secret; required if the project signs tokens asymmetrically (ES256, the current default) — see section 1 |
| `RAZORPAY_KEY_ID` | `rzp_test_…` | secret |
| `RAZORPAY_KEY_SECRET` | test key secret | secret |
| `RAZORPAY_WEBHOOK_SECRET` | webhook signing secret | secret |
| `LOG_LEVEL` | `INFO` | optional |
| `GEMINI_API_KEY` | Gemini key | optional, see [section 8](#8-gemini) |

Do **not** set `RAZORPAY_API_BASE_URL`. Leaving it unset pins the canonical host
`https://api.razorpay.com`. The Prompt 25 localhost provider stub override
exists only for the browser test suite.

`MODEL_BUNDLE_PATH` is already set by the image and does not need an override.

---

## 4. Vercel frontend

| Setting | Value |
| --- | --- |
| Root directory | `apps/web` |
| Framework preset | Next.js |
| Install command | `npm ci` (lockfile-exact) |
| Build command | `npm run build` |
| Output | default Next.js (no `standalone` configuration) |

### 4.1 Public environment variables

Only these `NEXT_PUBLIC_*` names are read anywhere in `apps/web`:

| Variable | Set on Vercel | Value |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | yes | `https://<service>.up.railway.app` |
| `NEXT_PUBLIC_APP_MODE` | optional | `demo` (the default and only accepted value) |
| `NEXT_PUBLIC_SUPABASE_URL` | yes, for a real login | `https://<project-ref>.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | yes, for a real login | Supabase anon/public key — safe to expose (Supabase's own design); used only for Auth, never data access |
| `NEXT_PUBLIC_DEMO_LOGIN_EMAIL` | optional | email of the demo account from [section 2.5](#25-provisioning-a-real-admin-user); enables a "Continue as demo" one-click button on `/login` |
| `NEXT_PUBLIC_DEMO_LOGIN_PASSWORD` | optional | that account's password — see the exposure note below before setting this |
| `NEXT_PUBLIC_DEV_AUTH_TOKEN` | **no**, once Supabase is set | see [section 1](#1-authentication) |

Both `NEXT_PUBLIC_SUPABASE_*` variables must be set together — the frontend
requires a real Supabase sign-in whenever they're both present (`/login`
becomes functional) and falls back to `NEXT_PUBLIC_DEV_AUTH_TOKEN` only when
either is absent.

`NEXT_PUBLIC_DEMO_LOGIN_PASSWORD` is inlined into the public bundle exactly
like `NEXT_PUBLIC_DEV_AUTH_TOKEN` was — anyone who opens the deployed site
can extract it and sign in as that account. Only set it for an account
scoped to demo/synthetic data (the one provisioned in section 2.5 is
designed for exactly this); never for a real customer or personal account.
Omit both `NEXT_PUBLIC_DEMO_LOGIN_*` variables to require typed credentials
instead — the demo button simply doesn't render.

The variable is `NEXT_PUBLIC_API_BASE_URL`, not `NEXT_PUBLIC_API_URL`.
`NEXT_PUBLIC_*` values are inlined into the browser bundle at build time, so
changing one requires a redeploy.

### 4.2 Never expose to the frontend

`DATABASE_URL`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
`RAZORPAY_WEBHOOK_SECRET`, `GEMINI_API_KEY`, `SUPABASE_JWT_SECRET`, the Supabase
service-role key, and the Supabase database password. None of these has a
`NEXT_PUBLIC_` counterpart, and none may be given one.

---

## 5. CORS

The backend grants exactly one origin, read from `PUBLIC_APP_BASE_URL`
(`apps/api/app/main.py`):

- exact origin only, never `*`;
- `allow_credentials=False`, because authentication travels as a Bearer header
  rather than a cookie;
- methods limited to `GET`, `POST`, `OPTIONS`;
- headers limited to `Authorization` and `Content-Type`;
- a trailing slash in the configured value is stripped, so
  `https://app.example.com/` and `https://app.example.com` behave identically;
- any other origin receives no allow-origin header.

Set `PUBLIC_APP_BASE_URL` to the Vercel production domain, scheme included.
A preview deployment on a different domain will be refused by the browser.

---

## 6. Razorpay

Test Mode only.

- Credentials stay backend-only: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
  `RAZORPAY_WEBHOOK_SECRET`.
- The provider host is pinned to `https://api.razorpay.com`. In `APP_ENV=production`
  an override is rejected outright by settings validation.
- Webhook URL to register in the Razorpay dashboard:
  `https://<service>.up.railway.app/api/v1/webhooks/razorpay`
- Signatures are verified with HMAC-SHA256 over the exact raw request body
  before any JSON parsing, and events are deduplicated by event id.

Manual steps (dashboard, cannot be automated from the repository): generate Test
Mode API keys, create the webhook with the events the integration consumes, copy
the webhook secret into Railway, and run one test payment when rehearsing.

---

## 7. Demo data and identities

The canonical demo tenant is deterministic (`apps/api/app/demo/constants.py`):

| Identity | UUID |
| --- | --- |
| Organization | `82757dbc-e0d0-5285-8f26-7a9ab9837a24` |
| Demo auth user used by `DEV_AUTH_*` | `bc9f0349-0af8-557e-9557-4bdaadda544d` |

`DEV_AUTH_ORGANIZATION_ID` must equal the demo organization id, otherwise the
authenticated session is scoped to an empty tenant and the dashboard is blank.

Audit rows record the actor as a plain string, not a foreign key to
`user_profiles`, so `DEV_AUTH_USER_ID` does not need a matching profile row.

---

## 8. Gemini

Optional. With no `GEMINI_API_KEY` the LLM path is disabled and explanations
come from the deterministic template fallback, which is the accepted behavior
and the mode the browser test suite runs in. The demo does not depend on Gemini.

If a key is set it stays backend-only. No Gemini variable may become
`NEXT_PUBLIC_*`.

---

## 9. Warm-up before a demo

Manual, no scheduler or background pinger:

1. `GET https://<service>.up.railway.app/health` and wait for `200`.
2. Open the Vercel URL and let the dashboard load.
3. Perform one authenticated read (the dashboard's own summary request counts).
4. Wait until responses are consistently fast — the first database query after
   an idle period is the slowest, because the pooler connection is cold.
5. Run the demo reset (section 10).
6. Begin the demonstration.

Measured locally on the deployment image against a container database, as a
lower bound for what a hosted instance will do:

| Step | Time |
| --- | --- |
| Container start → `/health` 200 (includes `alembic upgrade head` at head) | ~7.5 s |
| First authenticated dashboard read | ~0.7 s |
| Same read once warm | ~0.1 s |
| `POST /api/v1/demo/reset` | ~1.2 s |
| `POST /api/v1/demo/run-batch` | ~11 s |

A hosted deployment adds network latency and, on a cold container, image start
time. Budget a minute for warm-up rather than starting the demo on the first
request. Note that run-batch takes about ten seconds and is CPU-bound; run it
before presenting, not during.

Do not warm up with a Payment Link creation, a recovery action, a webhook, or
any other mutation. Warm-up must not consume demo state.

---

## 10. Demo reset

`POST /api/v1/demo/reset` restores the canonical deterministic demo state. It
exists only when `DEMO_MODE=true` — with demo mode off the route is not
registered at all and the path is a genuine 404 — and requires the ADMIN role
resolved server-side.

### 10.1 The environment combination that works

`APP_ENV` accepts `development`, `test` or `production`. There is no `demo`
value. `DEMO_MODE` is a separate switch that only controls route registration.

| `APP_ENV` | `DEMO_MODE` | Result |
| --- | --- | --- |
| `development` | `true` | Demo routes exist; `Bearer dev-admin` resolves ADMIN. **Working demo, simplest to rehearse with.** |
| `development` | `false` | Routes not registered → 404. |
| `production` | `true` | Routes registered; a verified Supabase token for a `user_profiles` row with `role=ADMIN` (section 2.5) resolves ADMIN and can reset. `dev-admin` no longer works here — production selects `SupabaseAuthBackend`. |
| `production` | `false` | No route to call. |

Either working combination's route-level protections are identical: demo
mode registration, server-resolved ADMIN role, and tenant scoping all apply
regardless of which auth backend resolved that role.

`APP_ENV=development` additionally skips the production secret validation, so
the operator is responsible for setting real Razorpay Test Mode credentials
even though nothing enforces it. `APP_ENV=production` runs that validation
(`Settings.validate_production_secrets`) and refuses to boot on a
`dev-`-prefixed secret.

### 10.2 Procedure

```
POST https://<service>.up.railway.app/api/v1/demo/reset
Authorization: Bearer dev-admin
```

With `APP_ENV=production`, replace the header with a real Supabase access
token for the provisioned admin user (obtain it by signing in at `/login`
and reading it from the Supabase client session, e.g. via the browser
devtools network tab on the `/api/v1/auth/me` request).

The reset deletes and reseeds the demo tenant in a single transaction, so a
failure rolls back rather than leaving a half-reset database.

---

## 11. Backup demo strategy

| Plan | What it is |
| --- | --- |
| Primary | Live Vercel + Railway + Supabase + Razorpay Test Mode |
| Backup A | The deployed app on deterministic demo state, presenting the synthetic batch evidence, which is labeled synthetic in the UI |
| Backup B | The local Playwright/demo path from Prompt 25, run against the local stack |
| Backup C | A screen recording of a successful end-to-end run |

Synthetic results stay visibly labeled as synthetic in every fallback. Never
present a simulated result as a live integration.

---

## 12. Local verification

Build and run the deployment image exactly as Railway would, against a
disposable database rather than Supabase:

```sh
# From the repository root — the build context matters.
docker build -t revloop-api:deploy-check .

docker run --rm \
  --env DATABASE_URL='postgresql+psycopg://user:password@host:5432/dbname' \
  --env APP_ENV=development \
  --env DEMO_MODE=true \
  --env DEV_AUTH_USER_ID=bc9f0349-0af8-557e-9557-4bdaadda544d \
  --env DEV_AUTH_ORGANIZATION_ID=82757dbc-e0d0-5285-8f26-7a9ab9837a24 \
  --env PUBLIC_APP_BASE_URL=http://localhost:3000 \
  --env PORT=8080 \
  --publish 8080:8080 \
  revloop-api:deploy-check
```

Then check the packaging invariants inside the running container:

```sh
docker exec <container> python deploy/verify_runtime_packaging.py
```

That reports whether the canonical `scripts/ml` modules resolve, the demo
run-batch dependency imports, the frozen model artifact is present and loads,
and no duplicate copy of the canonical ML source shipped. The same checks run in
the normal test suite through `apps/api/tests/deploy/test_runtime_packaging.py`.

---

## 13. Operational runbooks

### 13.1 A Payment Link action is stuck `UNKNOWN`

`RecoveryActionService._maybe_reconcile_payment_link_action`
(`apps/api/app/actions/service.py`) automatically reconciles an unresolved
`CREATE_PAYMENT_LINK` action the next time its idempotency key is looked up,
by fetching the link from Razorpay by `reference_id`. If that fetch comes
back `not_found` — the link genuinely does not exist, as opposed to a
transient error or an ambiguous match — reconciliation intentionally does
nothing further: it does not fabricate a replacement action, and it does not
change case state on a single unconfirmed read.

Because the action's idempotency key is deterministic
(`case_id` + `recommendation_id` + `action_type`), no new
`CREATE_PAYMENT_LINK` action can ever be created for that same
recommendation — the same key would collide with the stuck row. The case
stays `WAITING_FOR_OUTCOME` until an operator intervenes.

**Manual recovery:** call `POST /api/v1/recovery-cases/{id}/analyze` with
`reason=NEW_PROVIDER_EVIDENCE` while the case is `WAITING_FOR_OUTCOME`. This
produces a fresh `analysis_run_id` and a fresh recommendation, which changes
the idempotency key's inputs and unblocks a new action on the next
`POST /recovery-cases/{id}/actions` call. Confirm first (via the Razorpay
dashboard or a manual `GET /v1/payment_links/{id}`) that the original link
truly never existed, so a new one isn't created alongside a link that was
actually there.

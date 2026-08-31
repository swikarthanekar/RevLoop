# RevLoop synthetic demo dataset

This directory documents the deterministic **product/demo seed** used for RevLoop development and hackathon storytelling.

It is **not** the ML training dataset.

## Seed version

`revloop-demo-v1`

## Usage

From repository root, after migrations:

```bash
cd apps/api
alembic upgrade head
cd ../..
python scripts/seed_demo.py
python scripts/seed_demo.py --reset
```

The seed creates one synthetic demo merchant (**Acme Learning Labs**) with customers, transactions, subscriptions, recovery cases, recommendations, actions, outcomes, audit logs, and merchant policy data.

All generated business records use `is_synthetic = true` where supported.

## Safety

`--reset` is allowed only when:

- `APP_ENV != production`
- `DEMO_MODE=true`

Reset deletes **only** rows belonging to the demo organization ID, never the entire database.

## Source label

Demo analytics should expose `SYNTHETIC_DEMO` as the data source label.

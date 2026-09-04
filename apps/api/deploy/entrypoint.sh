#!/bin/sh
# Container entrypoint: migrate, then serve.
#
# `set -e` is what makes the migration a gate. If `alembic upgrade head` fails
# the script exits non-zero and the container dies, so the platform reports a
# failed deployment instead of serving the application against a schema it was
# not built for. There is deliberately no "continue anyway" branch.
#
# This assumes a single backend instance, which is the hackathon deployment
# shape: one replica means one migration runner and no concurrent upgrade.
set -eu

alembic upgrade head

# Railway (and any similar host) assigns the port; binding 0.0.0.0 is required
# for the platform to reach the process. One worker keeps the demo's in-process
# caches — settings, model bundle — consistent across requests.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1

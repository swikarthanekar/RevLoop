# RevLoop backend image.
#
# The build context is the repository root rather than apps/api. The demo's
# canonical evaluation bridge (app/demo/canonical_ml.py) reaches the training
# modules through Path(__file__).parents[4] / "scripts", so the image has to
# keep apps/api and scripts in the same relative positions the repository uses.
# Copying scripts/ml to a flatter location would create a second copy of code
# that the test suite does not exercise, and the two would drift.
#
# Python 3.10 matches the repository's supported version (requires-python
# ">=3.10", ruff target py310); deployment is not the place to move it.
#
# No apt layer is needed. Every runtime dependency ships a prebuilt manylinux
# wheel, and scikit-learn vendors its own OpenMP runtime
# (scikit_learn.libs/libgomp-*.so), so there is no system package to install.
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/apps/api

# Dependencies resolve from requirements.txt only. requirements-dev.txt (pytest,
# ruff, xgboost) is deliberately absent so the deployed image cannot pick up a
# test-only package as a runtime dependency.
COPY apps/api/requirements.txt ./requirements.txt
RUN pip install --requirement requirements.txt

COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/alembic ./alembic
COPY apps/api/deploy ./deploy
COPY apps/api/app ./app

# Repository-root position, not a copy nested under apps/api. scripts/ml also
# imports from `app`, which resolves because the working directory is apps/api.
COPY scripts/ml /app/scripts/ml

# Inference already falls back to this artifact when the configured path is
# missing, but /health reports the model as loaded only for the configured
# path, so point the setting at the artifact the image actually ships.
ENV MODEL_BUNDLE_PATH=/app/apps/api/app/ml/artifacts/recovery_model.joblib

RUN chmod +x ./deploy/entrypoint.sh \
    && useradd --create-home --uid 10001 revloop \
    && chown --recursive revloop:revloop /app
USER revloop

# No EXPOSE: the listening port comes from the platform-provided PORT.
ENTRYPOINT ["/app/apps/api/deploy/entrypoint.sh"]

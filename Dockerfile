# syntax=docker/dockerfile:1.6
# =====================================================================
# VanguardOps - Multi-stage production image
#
# Stage 1 ("builder") creates a clean virtualenv with all dependencies.
# Stage 2 ("runtime") copies the venv on top of a minimal base image,
# adds a non-root user, and runs the API.
#
# Image surface is intentionally small: no compilers, no build artefacts,
# no shell history.
# =====================================================================

ARG PYTHON_VERSION=3.12-slim-bookworm

# ---------- Stage 1: builder ----------
FROM python:${PYTHON_VERSION} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    VIRTUAL_ENV=/opt/venv

# Build deps for psycopg2 / bcrypt
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv ${VIRTUAL_ENV}
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

WORKDIR /build
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    APP_USER=vanguard \
    APP_HOME=/app

# Runtime deps only (libpq for psycopg2, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 ${APP_USER} \
    && useradd --system --uid 1001 --gid ${APP_USER} --create-home --shell /sbin/nologin ${APP_USER}

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

WORKDIR ${APP_HOME}
COPY --chown=${APP_USER}:${APP_USER} . .

# Drop privileges
USER ${APP_USER}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:8000/livez || exit 1

# tini handles signal forwarding so SIGTERM is propagated to uvicorn cleanly
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default command runs the API. Compose / k8s can override for the worker.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

FROM python:3.12-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ffmpeg libchromaprint-tools nodejs ca-certificates curl tar \
    && useradd --create-home --uid 10001 app \
    && rm -rf /var/lib/apt/lists/*

# OmniGet CLI is OPTIONAL. The build no longer depends on a GitHub release archive: by default it is
# skipped; with --build-arg INSTALL_OMNIGET=1 it is installed best-effort and a missing archive only
# prints a warning (see deploy/install_omniget.sh). Without it the bot works, /omniget just says so.
ARG TARGETARCH
ARG INSTALL_OMNIGET=0
ARG OMNIGET_VERSION=0.9.2
ARG OMNIGET_URL=
COPY deploy/install_omniget.sh /tmp/install_omniget.sh
RUN INSTALL_OMNIGET="$INSTALL_OMNIGET" OMNIGET_VERSION="$OMNIGET_VERSION" OMNIGET_URL="$OMNIGET_URL" \
    TARGETARCH="$TARGETARCH" sh /tmp/install_omniget.sh; rm -f /tmp/install_omniget.sh

# Dependency layer first for Docker cache.
COPY pyproject.toml README.md ./
RUN uv sync --no-dev --no-install-project

COPY . .
RUN uv sync --no-dev \
    && mkdir -p /app/static/logs /app/static/backups \
    && chown -R app:app /app

USER app
CMD ["uv", "run", "--no-dev", "-m", "bot"]

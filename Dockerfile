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

# OmniGet CLI is pinned so a future upstream release cannot silently break Kira.
ARG TARGETARCH
ARG OMNIGET_VERSION=0.9.2
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in amd64) OMNI_ARCH=x86_64 ;; arm64) OMNI_ARCH=aarch64 ;; *) echo "Unsupported OmniGet arch: ${TARGETARCH}"; exit 1 ;; esac; \
    URL="https://github.com/tonhowtf/omniget/releases/download/v${OMNIGET_VERSION}/omniget-cli-${OMNIGET_VERSION}-${OMNI_ARCH}-unknown-linux-gnu.tar.gz"; \
    curl -fL --retry 5 "$URL" -o /tmp/omniget.tar.gz; \
    mkdir -p /tmp/omniget; tar -xzf /tmp/omniget.tar.gz -C /tmp/omniget; \
    BIN="$(find /tmp/omniget -type f -name omniget -o -name omniget-cli | head -n1)"; \
    test -n "$BIN"; install -m 0755 "$BIN" /usr/local/bin/omniget; \
    rm -rf /tmp/omniget /tmp/omniget.tar.gz; \
    /usr/local/bin/omniget --help >/dev/null

# Dependency layer first for Docker cache.
COPY pyproject.toml README.md ./
RUN uv sync --no-dev --no-install-project

COPY . .
RUN uv sync --no-dev \
    && mkdir -p /app/static/logs /app/static/backups \
    && chown -R app:app /app

USER app
CMD ["uv", "run", "--no-dev", "-m", "bot"]

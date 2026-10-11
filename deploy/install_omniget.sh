#!/bin/sh
# Optional OmniGet CLI install for the Docker image. NEVER fails the build:
# any problem (missing release, no network, unknown arch) only prints a warning, the bot
# then works without /omniget (its commands say the CLI is not installed).
#
#   INSTALL_OMNIGET=1            enable (default 0: skipped, build has no dependency on GitHub releases)
#   OMNIGET_URL=https://...      exact archive URL (overrides the version/arch template)
#   OMNIGET_VERSION=0.9.2        used by the template when OMNIGET_URL is empty
#   OMNIGET_SHA256=...           optional checksum of the archive
set -u

warn() { echo "[omniget] WARNING: $*" >&2; }

[ "${INSTALL_OMNIGET:-0}" = "1" ] || { echo "[omniget] skipped (INSTALL_OMNIGET != 1)"; exit 0; }

case "${TARGETARCH:-amd64}" in
  amd64) ARCH=x86_64 ;;
  arm64) ARCH=aarch64 ;;
  *) warn "unsupported arch '${TARGETARCH:-}', skipping"; exit 0 ;;
esac

DEST="${OMNIGET_INSTALL_DIR:-/usr/local/bin}"
VERSION="${OMNIGET_VERSION:-0.9.2}"
URL="${OMNIGET_URL:-https://github.com/tonhowtf/omniget/releases/download/v${VERSION}/omniget-cli-${VERSION}-${ARCH}-unknown-linux-gnu.tar.gz}"
WORK="$(mktemp -d)" || { warn "mktemp failed, skipping"; exit 0; }
trap 'rm -rf "$WORK"' EXIT

if ! curl -fsSL --retry 3 --connect-timeout 15 "$URL" -o "$WORK/omniget.tar.gz"; then
  warn "could not download $URL (release missing or no network) - continuing WITHOUT OmniGet"
  exit 0
fi
if [ -n "${OMNIGET_SHA256:-}" ]; then
  echo "${OMNIGET_SHA256}  $WORK/omniget.tar.gz" | sha256sum -c - >/dev/null 2>&1 \
    || { warn "checksum mismatch, skipping"; exit 0; }
fi
mkdir -p "$WORK/x"
if ! tar -xzf "$WORK/omniget.tar.gz" -C "$WORK/x" 2>/dev/null; then
  warn "archive is not a valid tar.gz, skipping"; exit 0
fi
BIN="$(find "$WORK/x" -type f \( -name omniget -o -name omniget-cli \) | head -n1)"
[ -n "$BIN" ] || { warn "binary not found in archive, skipping"; exit 0; }
install -m 0755 "$BIN" "$DEST/omniget" || { warn "install failed, skipping"; exit 0; }
if "$DEST/omniget" --help >/dev/null 2>&1; then
  echo "[omniget] installed"
else
  warn "installed binary does not run, removing it"
  rm -f "$DEST/omniget"
fi
exit 0

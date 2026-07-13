#!/usr/bin/env bash
# Download the pinned PubMed MCP source needed by docker-compose.yml.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${ROOT}/data/runtime/pubmed-mcp-server"
REPOSITORY="https://github.com/cyanheads/pubmed-mcp-server.git"
VERSION="v2.9.8"

mkdir -p "$(dirname "$TARGET")"
if [[ -d "${TARGET}/.git" ]]; then
  git -C "$TARGET" fetch --depth 1 origin "refs/tags/${VERSION}:refs/tags/${VERSION}"
  git -C "$TARGET" checkout --detach "$VERSION"
elif [[ -e "$TARGET" ]]; then
  echo "${TARGET} exists but is not a Git checkout; move it aside before retrying" >&2
  exit 1
else
  git clone --branch "$VERSION" --depth 1 "$REPOSITORY" "$TARGET"
fi

ACTUAL_VERSION="$(git -C "$TARGET" describe --tags --exact-match)"
ACTUAL_COMMIT="$(git -C "$TARGET" rev-parse HEAD)"
if [[ "$ACTUAL_VERSION" != "$VERSION" ]]; then
  echo "expected ${VERSION}, got ${ACTUAL_VERSION}" >&2
  exit 1
fi
echo "PubMed MCP source ready: ${ACTUAL_VERSION} (${ACTUAL_COMMIT})"

#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

# Run against an already-started COOP/COEP shipping-build server. The driver
# refuses to overwrite evidence, so LABEL must be unique.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
DRIVER="$ROOT/sandbox/gpu-r61/cycles-windowed/drive_cycles_f12.mjs"
NODE="$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node"
LABEL="${1:-}"
PORT="${2:-8153}"
TIMEOUT_MS="${3:-600000}"

if [[ -z "$LABEL" || ! "$LABEL" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "usage: $0 <unique-label> [port] [timeout-ms]" >&2
  exit 2
fi

"$NODE" --check "$DRIVER"
NODE_PATH="/Users/paws/plushly/game-platform/node_modules" "$NODE" "$DRIVER" --selfcheck
NODE_PATH="/Users/paws/plushly/game-platform/node_modules" "$NODE" "$DRIVER" \
  "$PORT" "$TIMEOUT_MS" "$LABEL"

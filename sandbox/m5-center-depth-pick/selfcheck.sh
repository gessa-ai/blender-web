#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$ROOT/.host-tools/bin/python3.13" \
  "$ROOT/sandbox/m5-center-depth-pick/verify_source.py" \
  --source-root "${BW_SOURCE_ROOT:-$ROOT/upstream}" --selfcheck

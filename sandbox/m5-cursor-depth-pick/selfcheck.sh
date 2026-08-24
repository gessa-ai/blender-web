#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SOURCE_ROOT="${BW_SOURCE_ROOT:-$ROOT/upstream}"
"$ROOT/.host-tools/bin/python3.13" "$HERE/verify_source.py" \
  --source-root "$SOURCE_ROOT" --selfcheck

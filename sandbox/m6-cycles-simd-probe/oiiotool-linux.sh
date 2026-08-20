#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OIIO="$ROOT/lib/linux_x64/openimageio/bin/oiiotool"
mapfile -t library_dirs < <(
  find "$ROOT/lib/linux_x64" -mindepth 2 -maxdepth 2 -type d -name lib -print | LC_ALL=C sort
)
[[ -x "$OIIO" && "${#library_dirs[@]}" -gt 0 ]] || {
  echo "OIIOTOOL_WRAPPER_FAIL bundled Linux payload incomplete" >&2
  exit 1
}

prefix="$(IFS=:; echo "${library_dirs[*]}")"
export LD_LIBRARY_PATH="$prefix${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$OIIO" "$@"

#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Compile every upstream .po catalog into the runtime locale tree Blender expects
# (datafiles/locale/<lang>/LC_MESSAGES/blender.mo + the `languages` index), using the
# NATIVE host msgfmt built by scripts/build-hosttools.sh (ADR-002 / patch 0127).
#
# Output is a repo-owned, gitignored tree (build-hosttools/locale) that
# patches/platform_wasm.cmake preloads at /bw/datafiles/locale when WITH_INTERNATIONAL
# is ON. The .mo files are deterministic build artifacts, never committed. English is the
# source language and has no catalog, so this only matters when a non-English UI language
# is selected. See notes/i18n-restore-r45.md.
#
# Idempotent. Run before configuring build-wasm-windowed-opt with WITH_INTERNATIONAL=ON.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MSGFMT="$ROOT/build-hosttools/bin-native/msgfmt"
PO_DIR="$ROOT/upstream/locale/po"
LANGUAGES="$ROOT/upstream/locale/languages"
OUT="$ROOT/build-hosttools/locale"

if [ ! -x "$MSGFMT" ]; then
  echo "[build-locale] ERROR: native msgfmt not found at $MSGFMT" >&2
  echo "[build-locale]        run scripts/build-hosttools.sh first." >&2
  exit 1
fi
if [ ! -d "$PO_DIR" ] || [ ! -f "$LANGUAGES" ]; then
  echo "[build-locale] ERROR: upstream locale sources missing ($PO_DIR / $LANGUAGES)." >&2
  exit 1
fi

rm -rf "$OUT"
mkdir -p "$OUT"
cp "$LANGUAGES" "$OUT/languages"

n=0
total=0
for po in "$PO_DIR"/*.po; do
  lang="$(basename "$po" .po)"
  dst_dir="$OUT/$lang/LC_MESSAGES"
  mkdir -p "$dst_dir"
  "$MSGFMT" "$po" "$dst_dir/blender.mo"
  sz=$(stat -c %s "$dst_dir/blender.mo" 2>/dev/null || stat -f %z "$dst_dir/blender.mo")
  total=$((total + sz))
  n=$((n + 1))
done

lang_bytes=$(stat -c %s "$OUT/languages" 2>/dev/null || stat -f %z "$OUT/languages")
echo "[build-locale] compiled $n catalogs into $OUT"
echo "[build-locale] languages index: $lang_bytes B (rides stage-0)"
echo "[build-locale] total .mo bytes: $total (rides stage-1 with the CJK fonts)"

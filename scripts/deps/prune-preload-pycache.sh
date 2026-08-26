#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Prune CPython __pycache__ (.pyc bytecode) from the browser --preload-file roots
# before file_packager builds blender_browser.data.
#
# Why: Emscripten's --preload-file / file_packager has NO exclude globs, so the
# shipped .data would otherwise carry every stdlib + script .py source PLUS its
# compiled .pyc at THREE optimisation levels (plain / opt-1 / opt-2) -- up to four
# copies of the same code. Measured on this tree that is ~46 MiB of pure redundancy
# (lib/wasm python ~37 MiB, upstream/scripts ~9 MiB).
#
# Safety: the staged-loading probe (notes/m8-staged-loading.md section 2) proved
# dropping ALL __pycache__ while KEEPING the .py is zero import-correctness risk --
# the .py source is authoritative and CPython transparently recompiles to an
# in-memory code object on first import; the only cost is first-import compile CPU.
# The node-embed builds (build-wasm-cycles) read the SAME lib/wasm python tree via
# NODERAWFS and are equally safe: a missing .pyc simply recompiles in memory.
#
# Idempotent: re-running on an already-pruned tree removes nothing and reports 0.
# See notes/m8-pycache-strip.md for the implementation record.
#
# Usage: scripts/deps/prune-preload-pycache.sh <root> [<root> ...]
set -uo pipefail

if [ "$#" -lt 1 ]; then
  echo "prune-preload-pycache: usage: $0 <root> [<root> ...]" >&2
  exit 2
fi

total_dirs=0
total_files=0
total_kib=0

for root in "$@"; do
  if [ ! -d "$root" ]; then
    # A preload root that does not exist is not this script's error to raise
    # (the link's own EXISTS() guard owns that); just skip and keep going.
    echo "prune-preload-pycache: skip (not a dir): $root" >&2
    continue
  fi
  # Collect the __pycache__ dirs first so the size/count report reflects exactly
  # what is deleted. NUL-delimited to survive any path oddity.
  dirs_kib=0
  dirs_n=0
  files_n=0
  while IFS= read -r -d '' d; do
    dirs_n=$((dirs_n + 1))
    n=$(find "$d" -type f -name '*.pyc' 2>/dev/null | wc -l | tr -d ' ')
    files_n=$((files_n + n))
    k=$(du -ck "$d" 2>/dev/null | tail -1 | awk '{print $1}')
    [ -n "$k" ] && dirs_kib=$((dirs_kib + k))
  done < <(find "$root" -type d -name '__pycache__' -print0 2>/dev/null)

  # Delete them.
  find "$root" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null

  total_dirs=$((total_dirs + dirs_n))
  total_files=$((total_files + files_n))
  total_kib=$((total_kib + dirs_kib))
  printf 'prune-preload-pycache: %s -> removed %d __pycache__ dir(s), %d .pyc, %d KiB\n' \
    "$root" "$dirs_n" "$files_n" "$dirs_kib"
done

printf 'prune-preload-pycache: TOTAL removed %d __pycache__ dir(s), %d .pyc, %.2f MiB\n' \
  "$total_dirs" "$total_files" "$(awk "BEGIN{print $total_kib/1024}")"

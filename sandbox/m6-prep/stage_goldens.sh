#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# M6-prep — stage render goldens (ONE-TIME / idempotent).
#
# Copies Blender's OWN committed reference images (the render goldens) out of the
# upstream LFS tree into sandbox/m6-prep/goldens/<engine>/<dir>/<test>.png so M6
# starts with ready goldens WITHOUT an LFS pull, and writes manifest.tsv — the
# per-test map test -> input(.blend) -> golden -> Blender's own threshold. The
# .blend INPUTS are NOT copied (multi-MB LFS); the manifest records their upstream
# path and the runner pulls them on demand (see the git lfs pull line it prints).
#
# Requires the reference PNGs materialized in upstream (git lfs pull, done in
# notes/m6-prep.md). Reads suite_plan.tsv. No raw logs; prints a count summary.
# Usage: bash sandbox/m6-prep/stage_goldens.sh
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
MP=sandbox/m6-prep
PLAN="$ROOT/$MP/suite_plan.tsv"
GOLD="$ROOT/$MP/goldens"
MAN="$ROOT/$MP/manifest.tsv"
SRC="$ROOT/upstream/tests/files/render"

ref_subdir() { case "$1" in workbench) echo workbench_renders;; eevee) echo eevee_renders;; cycles) echo cycles_renders;; *) echo "";; esac; }

printf '# engine\tdir\ttest\tinput_blend\tgolden\tfail_threshold\tfail_percent\n' > "$MAN"
n=0; missing=0
while IFS=$'\t' read -r engine dir thr fp; do
  case "$engine" in ''|\#*) continue;; esac
  sub="$(ref_subdir "$engine")"
  refdir="$SRC/$dir/$sub"
  for png in "$refdir"/*.png; do
    [ -e "$png" ] || continue
    test="$(basename "$png" .png)"
    blend="upstream/tests/files/render/$dir/$test.blend"
    if [ ! -f "$ROOT/$blend" ]; then
      # blend absent entirely (not even an LFS pointer) — real problem
      echo "WARN no blend for $engine/$dir/$test"; missing=$((missing+1)); continue
    fi
    dst="$GOLD/$engine/$dir/$test.png"
    mkdir -p "$(dirname "$dst")"
    cp "$png" "$dst"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$engine" "$dir" "$test" "$blend" "$MP/goldens/$engine/$dir/$test.png" "$thr" "$fp" >> "$MAN"
    n=$((n+1))
  done
done < "$PLAN"

echo "staged $n goldens into $MP/goldens/  (manifest: $MP/manifest.tsv, missing=$missing)"
echo "by engine:"
for e in workbench eevee cycles; do
  c=$(awk -F'\t' -v e="$e" '$1==e{n++} END{print n+0}' "$MAN"); echo "  $e: $c"
done

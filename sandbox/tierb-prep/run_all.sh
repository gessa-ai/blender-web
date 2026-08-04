#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
#
# Run the whole tier-(b) candidate manifest on the native oracle and collate
# results into results.tsv (committed).  Each suite -> baseline-<name>.txt.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
res="$HERE/results.tsv"
: > "$res"
printf '# name\tverdict\texit\twall_s\tsummary\n' >> "$res"
while IFS= read -r name; do
  [ -n "$name" ] || continue
  "$HERE/run_suite.sh" "$name" | tee -a "$res"
done < <(grep -vE '^\s*#' "$HERE/suites.tsv" | awk -F'\t' 'NF{print $1}')

echo "----"
awk -F'\t' '!/^#/{c[$2]++} END{for(k in c) printf "%s: %d\n", k, c[k]}' "$res"

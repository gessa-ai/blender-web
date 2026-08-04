#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
#
# Run the 75-suite m2b CORE set on the wasm build -> results-wasm.tsv.
# Skips the 5 AMBER (wasm-gated deps) + 1 design-EXCLUDED suite; those are
# baselined on the oracle only.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
res="$HERE/results-wasm.tsv"
# AMBER (numpy/sqlite3/oceansim/slow) + EXCLUDED (desktop bundle) — not in the gate.
SKIP="script_pyapi_doc_gen script_load_addons script_load_modules script_disk_file_hash_service_test physics_ocean script_bundled_modules"
: > "$res"
printf '# name\tverdict\texit\twall_s\tdiff\tsummary\n' >> "$res"
while IFS= read -r name; do
  [ -n "$name" ] || continue
  case " $SKIP " in *" $name "*) continue;; esac
  "$HERE/run_suite_wasm.sh" "$name" | tee -a "$res"
done < <(grep -vE '^\s*#' "$HERE/suites.tsv" | awk -F'\t' 'NF{print $1}')

echo "----"
awk -F'\t' '!/^#/{v[$2]++; d[$5]++} END{printf "verdict:"; for(k in v) printf " %s=%d",k,v[k]; printf "\ndiff:"; for(k in d) printf " %s=%d",k,d[k]; print ""}' "$res"

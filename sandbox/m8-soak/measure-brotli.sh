#!/usr/bin/env bash
# SPDX-License-Identifier: CC0-1.0
BR=/opt/homebrew/bin/brotli
cd /Users/paws/blender-web
out=sandbox/m8-soak/brotli-results.txt
echo "name-section-alone raw=23145958 brotli=1265177" > "$out"
for pair in "BEFORE-proffuncs:bin-proffuncs" "AFTER-namestrip:bin-namestrip"; do
  label="${pair%%:*}"; dir="${pair##*:}"
  f="build-wasm-windowed-opt/$dir/blender_browser.wasm"
  raw=$(stat -f %z "$f")
  t0=$(date +%s)
  br=$("$BR" -q 11 -c "$f" | wc -c | tr -d ' ')
  t1=$(date +%s)
  echo "$label raw=$raw brotli=$br secs=$((t1-t0))" >> "$out"
done
echo "DONE" >> "$out"

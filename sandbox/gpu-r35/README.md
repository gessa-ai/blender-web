<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M6 r35 render-result bridge - suite comparator rigs

The TICK-PUMPED RENDER-RESULT BRIDGE (patch 0125) plus the decode + score + run tooling
that turns the BW_DIAG diag dumps into a real M6 pass/fail table. See
notes/gpu-r35-render-result-bridge.md (design + self-test) and
notes/m6-gpu-suite-real-scores.md (the 50-row table).

Files:
- bridge_render.mjs - factory self-test + open_mainfile inject driver.
- bridge_boot.mjs   - SUITE driver: seeds the .blend into OPFS (mounted at /projects) via
                      the same-origin seed page, boots windowed.html?args=/projects/... so
                      the blend opens as the STARTUP FILE (clean GPU context, no live
                      open_mainfile). Crash-tolerant (heavy EEVEE scenes device-lose).
- bw_seed.html      - the same-origin OPFS seed page. bridge_boot fetches it at
                      /bin/bw_seed.html, so copy it into the served BIN dir
                      (build-wasm-windowed-opt/bin/) before running the suite.
- decode_readback.py- BWRB dump -> 8-bit PNG (sRGB OETF = Blender Standard). No numpy/PIL.
- score.py          - pick render-result dump, decode, oiiotool-compare, cluster.
- run_suite.sh      - iterate manifest, bridge_boot + score, checkpoint per test.
- rescore_from_caps.sh - clean re-score of all rows from persisted caps (dedup-safe).
- make_note.py      - render notes/m6-gpu-suite-real-scores.md from results.tsv.
- results.tsv       - the authoritative scored table (one row per test).
- evidence/         - representative renders (CC0 sidecars).

Prereq: serve build-wasm-windowed-opt on 8126
  BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" bash scripts/serve-web.sh 8126 &
  cp sandbox/gpu-r35/bw_seed.html build-wasm-windowed-opt/bin/
Run: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
     REUSE=1 /opt/homebrew/bin/bash sandbox/gpu-r35/run_suite.sh all

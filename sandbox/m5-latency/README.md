<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M5 latency evidence

The immutable pre-split reference receipt is
`evidence/m5-trusted-latency-r8/receipt.json`. A headed Playwright run sends ten
trusted `N` inputs to the shipping canvas. Blender CLOG proves the exact
`wm.context_toggle` operator-start time, while timestamped Playwright screenshot
responses provide a conservative visible-response upper bound.

The visual oracle is the rightmost 200 pixels of the View3D WINDOW region,
derived from the read-only READY geometry as `{left: 850, top: 26, width: 200,
height: 621}` at the pinned 1280×720/DPR1 gate. Noise and signal are measured in
that same ROI. The detector remains `MAD > max(p25*8, median*5, 5)`; the ROI
targets the sidebar instead of lowering the detector.

Final r8 results:

- 10/10 trusted inputs, operators, and visible responses;
- keydown → operator median 8.8 ms (budget ≤33 ms);
- keydown → visible median 97.0 ms (budget ≤100 ms);
- keydown → visible p95 122.3 ms (budget ≤150 ms);
- no page, network, GPU-validation, device-loss, or isolation failures.

Earlier r1–r7 attempts are retained as honest FAIL receipts. They demonstrate
why stale OffscreenCanvas screencasts and full-frame-diluted/localized changes
are rejected rather than reclassified as green.

Each fresh receipt preflights and binds exactly the shipping JS, primary Wasm,
deferred Wasm, and data files. The split manifest is recorded as provenance and
must expose only the primary/deferred Wasm shipping roles.

Re-run with a fresh immutable label after starting the shipping server:

```sh
BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed-opt/bin \
  scripts/serve-web.sh 8169
BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed-opt/bin \
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/m5-latency/drive-trusted-latency-roi.mjs \
    --port 8169 --run m5-trusted-latency-NEW
```

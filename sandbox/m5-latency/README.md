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
node --version  # must be v22.16.0
npm install --prefix .m4-node --no-save \
  @playwright/test@1.61.1 pngjs@7.0.0 sharp@0.35.3
export BW_NODE_MODULES="$PWD/.m4-node/node_modules"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.m4-browsers"
export BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin"
bash scripts/serve-web.sh 8169

node sandbox/m5-latency/drive-trusted-latency-roi.mjs --selfcheck
node sandbox/m5-latency/drive-trusted-latency-roi.mjs \
  --port 8169 --run m5-trusted-latency-NEW
```

The producer accepts only Playwright 1.61.1, Sharp 0.35.3, and the bundled libvips 8.18.3.
Sharp remains a host-only measurement dependency: the established ROI greyscale/resize/MAD
detector is unchanged and no Sharp code enters the browser product. A fresh receipt still requires
the hardware-adapter CAPTURE/APPLY sequence; llvmpipe binds no M5 receipt.

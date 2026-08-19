<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M5 final gate

`verify_m5.py` is the deterministic, fail-closed M5 gate. It launches no
browser and performs no build. It re-hashes the exact current shipping set
(JS, primary Wasm, deferred Wasm, and data), validates the split-build manifest
shipping roles, validates the immutable headed click, keyboard, and trusted-latency receipts,
and rechecks the seven non-click native/Wasm state and operator-trace parity
sessions. The only trace normalization is removal of the two already-recorded
native macro-representation NUL artifacts.

The historical pre-split latency binding is
`sandbox/m5-latency/evidence/m5-trusted-latency-r8/receipt.json`. It uses ten
trusted `N` sidebar toggles, the exact rightmost-200-pixel View3D ROI derived
from the receipt's READY geometry, an unchanged MAD `> 5` detector, and the
published 100/150/33 ms budgets. Receipt r8 measured 97.0 ms end-to-end median,
122.3 ms p95, and 8.8 ms keydown-to-operator median.

Run directly or through the harness:

```sh
python3 sandbox/m5-final/verify_m5.py
harness/run.sh --scope m5
```

Fresh immutable receipt labels are selected without editing the verifier. Each
non-default label must carry an independently copied SHA-256 from that run's
`receipt.sha256`; selecting a label without its digest fails closed:

```sh
M5_CLICK_RUN_LABEL=m5-click-pick-FINAL \
M5_CLICK_RECEIPT_SHA256=<64-lowercase-hex> \
M5_CANVAS_RUN_LABEL=m5-canvas-smoke-FINAL \
M5_CANVAS_RECEIPT_SHA256=<64-lowercase-hex> \
M5_LATENCY_RUN_LABEL=m5-trusted-latency-FINAL \
M5_LATENCY_RECEIPT_SHA256=<64-lowercase-hex> \
  python3 sandbox/m5-final/verify_m5.py
```

All three drivers preflight the same four files and reject a split manifest
unless its only shipping Wasm roles are `primary` and `deferred`. The original
unsplit Wasm, split maps, and split manifest remain provenance/build files, not
members of the shipping runtime set.

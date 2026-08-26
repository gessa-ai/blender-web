<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 first-pixel loader coherence

`measure_boot.mjs` records loader state against the uncapped GHOST WebGPU presentation counter.
It always forces Chromium's software adapter and is diagnostic-only: its pixels, adapter, and
profile bind no milestone receipt.

Serve the current windowed product first, then run a zero-input trace:

```sh
BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" bash scripts/serve-web.sh 8123
DISPLAY=:0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
  BW_COHERENCE_SETTLE_MS=30000 \
  node sandbox/m4-frame-coherence/measure_boot.mjs 8123 current
```

Two diagnostic mutations exercise the fallback boundary without modifying served files:

- `BW_FORCE_LEGACY_WM_TIMER=1` restores the rejected 2.5-second `WM_main` timer.
- `BW_MASK_PRESENT_MARKER=1` hides the primary printf marker so only the uncapped counter can
  dismiss the loader.

`verify.py` is the device-free fail-closed source contract. It preserves the primary
`presentBackbuffer` marker and gate-mode behavior, requires a positive finite uncapped counter,
bounds polling to 120 seconds, and rejects zero-present or wall-clock dismissal.

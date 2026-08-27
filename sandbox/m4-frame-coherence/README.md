<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M4 first-pixel loader coherence

`measure_boot.mjs` records loader state against both the uncapped generic presentation counter and
the stricter VIEW_3D-content presentation counter. It fails unless a validated viewport-content
frame is observed and the loader dismisses only after that edge. It always forces Chromium's
software adapter and is diagnostic-only: its pixels, adapter, and profile bind no milestone
receipt.

Serve the current windowed product first, then run a zero-input trace:

```sh
BLENDER_WEB_BIN="$PWD/build-wasm-windowed-opt/bin" bash scripts/serve-web.sh 8123
DISPLAY=:0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
  node sandbox/m4-frame-coherence/measure_boot.mjs 8123 current
```

`verify.py` is the device-free fail-closed source contract. It preserves the primary
VIEW_3D-content export and gate-mode behavior, requires a positive finite semantic counter, bounds
polling to 120 seconds, and rejects generic-present or wall-clock dismissal. The controlled browser
negative cases live in `sandbox/m4-loader-redesign/verify_browser.mjs`.

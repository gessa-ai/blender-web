<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 particle-edit depth-cache continuation

This focused contract binds particle click, linked-pick, box, lasso, circle, and brush-start
paths to an owned full-viewport request. XRAY remains an immediate bypass; non-XRAY callers do
not traverse `PEData` until the producing context and cache settle.

The source verifier checks the opaque prepare/consume session, exact operator inputs, one-shot
generic gesture owners, persistent circle/direct-circle state, brush invoke/recorded-stroke
continuations, bounded identified polls, safe queues, and complete cancellation. Source mutations
must fail closed. The native/wasm32 model exercises all six caller families byte-for-byte. The
receipt also reverses and reapplies patch 0273 and compiles the exact particle and View3D product
translation units in the native and windowed Wasm graphs.

Run from the repository root:

```sh
harness/buildwrap.sh sandbox/m5-particle-edit-depth-cache/run.sh
```

This is device-free evidence only. It creates no hardware WebGPU receipt and does not alter the
M5 live acceptance blocker.

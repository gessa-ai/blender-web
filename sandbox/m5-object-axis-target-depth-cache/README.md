<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 object axis-target depth-cache continuation

This focused contract binds `OBJECT_OT_transform_axis_target` to one operation-owned
full-viewport request. The render override is restored before any readback return, and selected
objects plus transform backups remain untouched until a valid cache settles. The stock immediate,
pass-through, no-depth cancellation, initiating-event, and modal behavior stay intact.

The source verifier checks the exact ready-only tail, start event, bounded safe FIFO,
producing-context identity, identified 240-tick poll, render-override restoration, cleanup, and
external cancellation. Seventeen mutations must fail closed. The native/wasm32 model exercises eight
contracts and 36 cases byte-for-byte. The receipt also reverses and reapplies patch 0272 and
compiles the exact `object_transform.cc` production translation unit in the native and windowed
Wasm graphs.

Run from the repository root:

```sh
harness/buildwrap.sh sandbox/m5-object-axis-target-depth-cache/run.sh
```

This is device-free evidence only. It creates no hardware WebGPU receipt and does not alter the M5
live acceptance blocker.

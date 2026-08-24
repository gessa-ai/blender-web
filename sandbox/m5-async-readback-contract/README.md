<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M5 owned-readback and framebuffer continuation contract

This device-free reconciliation binds the current shipping L-B owned-result API
and the C1 Select-Next object-pick continuation to Blender's real
`gpu_readback.cc` and `gpu_select_next.cc` on native and wasm32. The shared
contract covers ready/failed ownership, undersized consume, cancellation,
Pending-to-Ready conversion, all three Select-Next modes, exact-key replay,
immutable ID-map transfer, repeated replay, terminal failure, null requests,
and overlapping-request rejection.

The same contract now exercises the production owned-transform request used by
asynchronous framebuffer region reads. The public color/depth entry points keep
native backends immediately ready while WebGPU owns one exact subresource ticket,
then applies the existing crop, row-order, channel-extension, and format
conversion only after that ticket settles. This is the shared primitive needed
before legacy selection-buffer and depth callers can become modal continuations;
it does not claim either caller family is converted yet.

`verify_source.py` separately binds the public texture/storage/framebuffer APIs,
exact WebGPU tickets, temporary select-engine ownership transfer, and the bounded
modal operator re-entry. It also requires the five still-synchronous caller families
(legacy selection-buffer read, depth pick, depth cache, WM window capture, and
WM window colour sampling) to stay visible. The screenshot operator has its own
owned-capture continuation contract; the ledger row remains `partial` for these
five families.

Run through the build wrapper:

```sh
harness/buildwrap.sh bash sandbox/m5-async-readback-contract/run.sh
harness/buildwrap.sh bash sandbox/m5-async-readback-contract/selfcheck.sh
```

Both compilations use `scripts/ninja-locked.sh`. The driver requires the
canonical clean-pin replay, Linux x86_64, clang++ 17, emcc 6.0.5, pinned Node
22.16.0, and byte-identical native/Wasm fmt headers before accepting evidence.
No WebGPU instance, adapter, device, browser profile, split product, or milestone
receipt is created; live object-pick proof remains part of the s7-blocked M5
browser receipt.

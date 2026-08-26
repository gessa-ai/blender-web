<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 callback-registration metadata soak — 2026-08-26

## Outcome

Commit `56dae2f` stops GHOST-web from retaining one heap allocation for every HTML5 callback
registration attempt.
Each successful or rolled-back listener transaction now takes one address from a fixed 4,096-byte
pool. Tokens are opaque, never dereferenced, never freed, and never reused, so a callback already
proxied to the WM worker can still reject safely after arbitrary window replacement. The pool is a
hard 4,096-attempt process budget; exhaustion logs the boundary and fails window publication
closed.

The previous `std::vector<std::unique_ptr<CallbackRegistration>>` grew for process lifetime.
The fail-first contract rejects that predecessor at the missing fixed budget
(`20260826T073335-513269`). The final source contract rejects 17 budget, uniqueness, publication,
retirement, and soak mutations (`20260826T073549-516616`). The recurring pattern is recorded as
Class 114 in `notes/porting-patterns.md`.

## Real-worker soak

The real WasmFS + `PROXY_TO_PTHREAD` harness rebuild is green
(`20260826T073503-515989`). Its lifecycle test deliberately hides the owned IME selector so 128
registrations install a prefix and roll it back, restores the selector, then performs 256 complete
dispose/replacement cycles. One key callback captured before that churn remains held until the last
replacement.

The 13-second browser run proves all of the following (`20260826T073549-516615`):

- the attempt counter advances by exactly `128 + 1 + 256`;
- the reported budget and fixed metadata are both exactly 4,096;
- active DOM listener count returns to baseline and adds equal removals;
- the callback held across every failed/successful generation is rejected; and
- a fresh trusted key still reaches the final GHOST window.

The integrated native/wasm32 pipeline and lifecycle mutation matrix remain green
(`20260826T073749-519336`). Adjacent real-worker focus, IME, Pointer Lock, clipboard, and custom
cursor cases are green (`20260826T073825-521497`, `521498`, `521502`, `521509`, `521524`).

## Product and gate evidence

The required locked CAPTURE product relinks and then reports exact no-work
(`20260826T073846-522793`, `20260826T074012-524580`). The new profile generation is:

- JavaScript: 707,146 bytes, SHA-256 `901fa6ac74f0caa8f133b054ca0e0ba5edc894c80710867030d70ab79b999fa9`;
- instrumented Wasm: 120,496,010 bytes, SHA-256
  `86bf266ad55da6c70f7d32b49b18cb572ce93c81cafe27627d0fa843f1c28ca2`;
- `.wasm.orig`: 119,142,906 bytes, SHA-256
  `edd94c4208c4c5229b197db20779336fb85293a79eb2ad7dc1fc3a8058e89336`;
- data: 167,143,248 bytes, SHA-256
  `09e58a25849eb6290a181141f5f83f928f469fe1e4d9fbdba23210bcada5a351`; and
- split manifest: 13,218 bytes, SHA-256
  `9889c28204591b11199fbe22e5395e2177a9bf52e2f477b7a4d7a4b23ea49636`.

Exact CAPTURE inventory, the strict producer self-check, and the two-phase source contract are
green (`20260826T074018-525140`, `525141`, `525145`). The exact artifact reaches running Blender
on the forced fallback diagnostic with input/presentation progress and zero target bind-group,
submission, transaction, or device-loss failures (`20260826T074040-525681`). This is explicitly
diagnostic-nonreceipt evidence.

Pinned REUSE 6.2.0 is green (`20260826T074517-530777`). Required M4 remains RED pending Apple
semantic pixels, and M8 remains RED at its existing 25 APPLY/receipt/release boundaries
(`20260826T074159-526864`, `20260826T074202-526932`). Container-backed regression restores M0
6/6 GREEN while M1-M8 retain their strict existing boundaries
(`20260826T074210-527012`).

No hardware profile, deferred shard, APPLY product, pixel receipt, result promotion, dependency,
tolerance, golden, blacklist, deferral, or promise changed. This relink supersedes the prior
CAPTURE hash; the driver-operated Apple rig must capture against the new `.wasm.orig` generation.
The pre-existing shared-worktree release residue remains unclaimed.

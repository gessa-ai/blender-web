<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 axis-target producer-state guard — 2026-08-25

## Outcome

Commit `7271d4e` and patch 0276 close AUDIT-R10 MAJOR-3. A pending
`OBJECT_OT_transform_axis_target` request no longer treats stable context pointers as immutable
operation state. Before the continuation can install its timer, it retains the exact scene frame
and every compatible target's object/session identity, parent identity/session, data identity,
rotation mode, local transform channels, parent/constraint inverses, and evaluated world/inverse
matrices.

Every pending event re-enumerates the target selection and compares that state before the depth
cache can transfer. A frame step, same-size target replacement, deletion, reparent, local transform
edit, or evaluated-matrix change cancels the owned request while `initialized` is still false, so no
modal transform backup exists to restore. The native-immediate path and the stock ready-only
selection/backup tail remain unchanged.

## Evidence

- The predecessor fails the new source contract before evidence allocation because it has no
  producer snapshot (`20260825T103912-1162682`).
- Final focused verification passes 9 native/wasm32 contracts and 39 cases byte-for-byte at 535
  bytes, `sha256:bc0268fb6f151a4c0d1f3a375d955868db2e1e55ce83b7c44adb6fde65db9400`.
  It rejects 23 source mutations, reverses/reapplies patch 0276 at
  `sha256:b2aec8dc6afe5eda4bbd5e686894b70e2dd3ac9cff1b88167902488ef4d95745`, and
  compiles the exact native and windowed-Wasm product translation unit against source
  `sha256:9a6848772686302feadc173342bf278513049a6e71b6348027c703b761c0e3c7`
  (`20260825T105130-1174176`).
- The aggregate owned-readback contract now includes `object_transform.cc`. Its 51-source census
  rejects 52 mutations, including independent same-pointer frame, selection, identity, and
  evaluated-transform controls; native/wasm32 output remains byte-identical at 627 bytes,
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`
  (`20260825T104620-1168765`).
- A fresh clean-pin freeze retains 20,258 entries with byte-identical live/replay manifests at
  `sha256:a3fccf6278cf6d6a49bb56258b7057e0331f99709fb6ca5644cda4599602fb38`; the
  2,332,698-byte canonical patch is
  `sha256:91a2fb2d03b794e5fab1a8171a305624c859f1dd6661063b3d58868e5eab29c0`
  (`20260825T104300-1166259`). Final canonical replay covers 303 paths and 253 active numbered
  patches (`20260825T104931-1172530`). The separately queued fixed-path receipt-freshness finding
  is intentionally not claimed here.
- The real `blender_browser` relinks and ends locked no-work
  (`20260825T104635-1168995` / `20260825T104727-1169565`). Strict OFF preflight binds the
  659,848-byte JavaScript, 119,001,919-byte Wasm, and 167,143,248-byte data artifact
  (`20260825T104748-1170635`).
- Repository-local REUSE 6.2.0 covers 2,519/2,519 files (`20260825T105317-1175866`). Final
  container-backed regression at `2026-08-25T10:48:36Z` restores M0 6/6 GREEN; M5 remains
  honestly RED only at the absent `blender_browser.deferred.wasm` boundary, and M1–M8 retain their
  existing strict manifest/product/browser/run-label/hardware/release boundaries.

This is device-free correctness evidence. It creates no adapter, device, browser profile, split
product, live receipt, result promotion, dependency decision, tolerance, golden, blacklist, or
milestone promise. The hardware blocker remains **no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)**; dzn and Windows were not attempted, and WSL was
not restarted.

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 particle producer-state guard — 2026-08-25

## Outcome

Commit `9e9fc95` and patch 0277 close AUDIT-R10 MAJOR-4. A pending particle-edit depth
request no longer treats a stable `PTCacheEdit *` as immutable operation state. Before depth
preparation, the shared session captures the exact scene frame, object session identity and
evaluated world/inverse matrices, plus a short-lived 128-bit token over particle-system state,
point/key topology, storage identities, coordinates, times, and visibility/selection flags.

The potentially linear token is recomputed only when the backend reports `Ready`, immediately
before the one-shot depth transfer. Pending input therefore keeps the existing cheap pointer/mode/
XRAY checks rather than scanning every particle on every event. A mismatch returns `Failed` while
the caller is still uninitialized, so click, linked-pick, box/lasso/circle, and brush continuations
all retire without pairing old pixels with current `PEData`.

## Evidence

- The exact predecessor rejects before evidence allocation because it has no producer snapshot
  (`20260825T111906-1199124`).
- Final post-commit focused verification passes 9 native/wasm32 contracts and 53 cases
  byte-for-byte at 631 bytes,
  `sha256:32d271f8f3272aeac9b7b7434eecdfd626ae0eed02c7cdaf860b46c14d73c617`.
  It rejects 26 source mutations, reverses/reapplies patch 0277 at
  `sha256:0a27a6d887a63e55558399274bbb2b4a9a5efd351d8a2669d683e5fbb35ced3d`,
  and compiles the exact native and windowed-Wasm product translation unit against source
  `sha256:14bf387aab78cb8276c3bffe0c2a267d81c3fbca9af21514e23bb0145be6e7d1`
  (`20260825T112340-1203359`).
- The 51-source aggregate rejects 56 mutations, including independent particle frame,
  object-matrix, key-coordinate, and ready-guard controls. Native/wasm32 output remains
  byte-identical at 627 bytes,
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`
  (`20260825T112405-1203647`).
- The clean-pin freezer reproduces all 20,258 manifest entries byte-for-byte at
  `sha256:b7e79677ee7f3a40dee6195423a113251dcb3ed69fd5aeb31e584ed15027af89`.
  Its 2,339,419-byte canonical patch is
  `sha256:1eade204c8420b2c520109a5cea550a790f34000d650b6f5457494eec6785462`
  (`20260825T112018-1199632`); post-commit replay covers 303 paths and 254 active numbered
  patches. The separately queued fixed-path receipt-freshness finding remains intentionally open.
- The real `blender_browser` relinks and ends locked no-work
  (`20260825T112137-1201451` / `20260825T112424-1203944`). Strict OFF preflight binds the
  659,848-byte JavaScript, 119,012,207-byte Wasm, and 167,143,248-byte data artifact
  (`20260825T112436-1204136`).
- Repository-local REUSE 6.2.0 covers 2,520/2,520 files
  (`20260825T112424-1203943`). The six-tier deferral contract retains the exact blocker
  (`20260825T112529-1205995`). Required M5 remains honestly RED only at the absent current
  `blender_browser.deferred.wasm` boundary (`20260825T112445-1204249`); final container-backed
  regression restores M0 6/6 GREEN while M1-M8 retain their existing strict boundaries
  (`20260825T112454-1204338`).

This is device-free correctness evidence. It creates no adapter, device, browser profile, split
product, live receipt, result promotion, dependency decision, tolerance, golden, blacklist, or
milestone promise. The hardware blocker remains **no conformant hardware Vulkan ICD in WSL2
(NVIDIA ships none; Mesa dzn rejected by Dawn)**; dzn and Windows were not attempted, and WSL was
not restarted.

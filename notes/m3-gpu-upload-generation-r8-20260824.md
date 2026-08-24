<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU upload generation ownership R8 — 2026-08-24

## Outcome

Implementation commit `393e33c` and numbered patch 0245 close the R8 stale-upload
generation defect. A VBO or derived float buffer-texture upload now consumes only
the dirty snapshot whose exact bytes were retained by the ordered queue. Acceptance
of that snapshot cannot clear a later Blender frontend mutation; the newer payload
is scheduled next, and static host data is released only after the newest accepted
transaction.

## Evidence

- The unchanged shipping postimage fails the extracted production-shaped
  A-schedule/B-`GPU_vertbuf_attr_set`-A-accept contract at the first stale dirty
  transition (`20260824T004835-3507605`).
- Root and descendant-CWD native/wasm32 runs pass 20 byte-identical integrated
  contracts. The new ordinary and float-expansion cases issue five exact ordered
  A/B payloads and finish with B published. Evidence is 1,786 bytes at SHA-256
  `e0ab099360aacebafd1822ce6fba38c53f843c9341c59584ff5bdc3de857ade8`;
  shipping inputs are SHA-256
  `7fc4f9f34ed2baeef6afc9337a581b49fc702f39ec24ddb12fd8f65f716530f9`
  (`20260824T005544-3514068`, `20260824T005617-3514993`).
- The wrong-Node control rejects before its requested evidence directory exists
  (`20260824T005644-3516152`). Malformed frontend extraction is also fail-closed in
  every successful focused run.
- The independent canonical vertex CPU suite remains byte-identical across native
  and wasm32: eight contracts, 584 bytes at SHA-256
  `0bd73ad2c268a1f97b8508fc8d4b6349f679ce82e722b4b67145bbaf5e0c54ad`
  (`20260824T005955-3519469`).
- Numbered patch 0245 is 7,706 bytes at SHA-256
  `04b30c2fcebc76c547808a4acaeee9ca857cfa9ddd08f90f5894d8ad5de2efcb`
  and passes isolated reverse/forward blob-identity checks. The canonical freezer
  and clean-pin replayer retain 257 paths and 20,258 entries at patch SHA-256
  `322f38255fc7ff8317a8af9324cd9690c3ae713f0a72d76fba32c4f7e108d486`
  and manifest SHA-256
  `ceb72294ea8b234e0a02455be5e25961fe80f8f503000f22f3de92af1b19f2ef`.
- The real optimized `blender_browser` target rebuilds and ends locked no-work
  (`20260824T005801-3517375`, `20260824T005847-3517822`). OFF preflight binds a
  657,928-byte JavaScript file, 118,764,654-byte Wasm, and 167,143,248-byte data file.
- Final container-backed regression keeps M0 6/6 green at
  `2026-08-24T01:01:21Z`. Required M3 remains honestly red at the absent fresh
  strict candidate; M4-M8 retain their existing browser, split-product, run-label,
  hardware, and release boundaries. No result was promoted.

## Boundary

This is device-free CPU/source and compile/link proof. It creates no accepted
hardware adapter, browser/pixel receipt, profile, split product, result promotion,
dependency decision, deferral, tolerance, golden, blacklist, or milestone promise.
Live proof remains deferred by the named blocker: no conformant hardware Vulkan ICD
in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not retry
dzn, attempt the staged Windows path, or restart WSL.

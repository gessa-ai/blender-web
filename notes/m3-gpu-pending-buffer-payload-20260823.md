<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 GPU pending buffer payload contract — 2026-08-23

## Outcome

Commit `d999280` and patch 0240 close R7's pending persistent-buffer payload defect. Storage and uniform updates,
clears, and attached UBO data now transfer ownership into an ordered byte queue whenever browser
validation has not published the allocation. Rejection leaves the queue retryable; the scoped
cache's accepted-publication callback drains every payload exactly once without another frontend
update call. Binding still waits for an accepted allocation.

## Evidence

- The unchanged frontend early-return path fails the source-bound contract before evidence
  allocation (`20260823T173920-3107301`). A wrong Node 22.22.1 also rejects before allocating its
  requested evidence directory (`20260823T175556-3123161`).
- Final root and descendant-CWD native/wasm32 runs pass 19 byte-identical contracts, including four
  actual extracted SSBO/UBO frontend cases and eight ordered sentinel payloads. Evidence is 1,656
  bytes at SHA-256 `35f1339ed54ab9bc1cb22defa09ccfd18ac06bbf55f403679d612256e856fd19`;
  shipping inputs are SHA-256
  `a23d84e44a3226ff60066149fb38fe80e7612bdd41c6ab77bdc5b78eef9c0737`
  (`20260823T175255-3118671`, `20260823T175319-3120100`).
- Pinned Dawn on llvmpipe rejects a real non-null persistent-buffer error object, retains the
  one-shot sentinel, and writes it once after the clean allocation retry
  (`20260823T175337-3121069`, `20260823T175348-3121166`). Its transcript remains
  `SOFTWARE_CONTROL_NON_RECEIPT`.
- Numbered patch 0240 is 19,587 bytes at SHA-256
  `2c6919c04e01e88905406bcb8bb64dd13cffd94f774af7ee14cf175465983cd5` and passes isolated
  reverse/forward exact-byte round trip. The canonical freeze retains 257 paths and 20,258 entries;
  its 1,741,106-byte patch is SHA-256 `542c0c2b4f251a576d6b91c7d7d5da9d7b543377e7ae0e691037f2a801957484`,
  with byte-identical 3,477,335-byte manifests at SHA-256
  `442c9e35a2b393594cc504c2ad6677907ec411e4abc9083f094779ac75ec4b5d`
  (`20260823T175148-3117846`, `20260823T175245-3118533`).
- The real `blender_browser` rebuild and locked no-work check pass
  (`20260823T175356-3121278`, `20260823T175443-3121731`). OFF preflight binds the 657,910-byte JS,
  118,731,844-byte Wasm, and 167,143,248-byte data product (`20260823T175504-3121942`).
- Final REUSE 6.2.0 is green for all 2,224 tracked files (`20260823T180236-3129336`). Required M3
  remains red only for the absent fresh strict candidate (`20260823T175739-3124255`); final
  container-backed regression keeps M0 6/6 green while M1-M8 retain their existing strict-receipt,
  product, browser, run-label, hardware, and release boundaries (`20260823T175748-3124354`).

## Boundary

This is device-free CPU/source and compile/link proof. It creates no accepted hardware adapter,
browser/pixel receipt, profile, split product, result promotion, tolerance, golden, blacklist, or
milestone promise. Live hardware proof remains deferred by the named blocker: no conformant
hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn). This iteration did not
retry dzn, attempt the staged Windows path, or restart WSL.

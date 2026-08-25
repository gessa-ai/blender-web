<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 asset-preview window-capture continuation — 2026-08-25

## Outcome

Commit `564cd59` and patch 0274 move `ASSET_OT_screenshot_preview`'s general-window capture
behind an operator-owned `WMWindowPixelsRead` continuation. The 3D-viewport offscreen-render path
and native immediate completion remain immediate. A pending browser capture retains the exact crop,
window manager, window, screen, main database, asset type, and asset weak reference behind one
identified 100 Hz timer for at most 240 ticks. Direct execution installs its own modal owner; the
interactive operator continues through its existing modal owner.

Ready settlement transfers the owned pixels once, applies the retained crop, resolves the retained
asset identity, and only then mutates or saves its preview. Context drift, missing target, backend or
consume failure, invalid crop, timeout, Escape/right-click, and external cancellation remove the
timer and retire the readback before freeing operator state. `Window.screenshot()` remains the one
explicitly counted synchronous caller; this unit does not change its synchronous Python return
contract.

## Source and contract evidence

- The pinned Linux oracle preserves `ASSET_OT_screenshot_preview` with `p1`, `p2`, and
  `force_square`, and confirms the public `Window.screenshot()` method
  (`20260825T075013-1009826`). The exact predecessor retains the synchronous asset call and fails
  before acceptance evidence (`20260825T075013-1009827`).
- Focused receipt `20260825T081222-1026760` passes eight native/wasm32 contracts and 28 cases
  byte-for-byte under clang++ 17 and em++ 6.0.5/Node 22.16.0. Its 366-byte output is
  `sha256:6d61aa830a73a73850cb4376523dffa27c2976c3ef406125b57c7dd1b131de80`; the four-source
  postimage is `sha256:3a3bbb060c091ba4c61a8b0629e828d7e472a04eb8aa1a36ca3d59aae00a8aec`.
  Eighteen ownership, crop, context, timer, caller-census, and cleanup mutations fail closed. The
  same receipt reverses/reapplies patch 0274 at
  `sha256:65d6ab73245bb0eecaaf912e61490b2e5cfb1881dd05eba9433b26a317111acc` and compiles the exact
  native and windowed-wasm product-graph `asset_ops.cc` translation unit. The initial exact native
  and wasm production compiles are independently green
  (`20260825T075541-1013560` / `20260825T075541-1013561`).
- Aggregate async-readback receipt `20260825T081000-1024727` binds 50 sources and rejects 46
  mutations. Native and wasm output remains byte-identical at 627 bytes /
  `sha256:ff5caab45d5120ca63367f2e2955fd39721dfcf69f602b583ab3dc9d71bcf720`, with source
  `sha256:5ea8ea81f309e11f1e9b59b13b06aa4c11b29a3d306bef962f2ff652dac21ed5`. It reports the
  converted asset-preview caller and the remaining Python caller separately while retaining
  `window_capture` as the sole open synchronous family.

## Integration evidence

- Clean-pin freeze `20260825T080327-1019512` reproduces 20,258 source entries with byte-identical
  live/replay manifests at
  `sha256:f9b2481993708fc3a4768f2c5e21a18d4581d809dedee2d0ad1f99fe895db15e`.
  `PREVIEW_SNAPSHOT.patch` is 2,326,979 bytes at
  `sha256:49d338c178ebb875d5b523299b6e905e7e43e2265f98a8ff9d1982f8fcacd0ad`.
  Authoritative replay binds 302 canonical paths and 251 numbered patch entries
  (`20260825T080424-1020940`); an independent clean replay/cmp also succeeds
  (`20260825T080424-1020941`).
- The real `blender_browser` relinks `libbf_editor_asset.a` and the shipping executable, then ends
  locked no-work (`20260825T081126-1026210` / `20260825T081212-1026669`). Strict OFF preflight
  `20260825T081601-1030134` binds 658,702-byte JavaScript, 118,999,509-byte wasm, and
  167,143,248-byte data artifacts.
- Final repository-wide REUSE 6.2.0 covers 2,505/2,505 files
  (`20260825T081950-1033084`). The six-tier hardware-deferral contract retains the exact named
  blocker (`20260825T081601-1030135`).
- Required M5 remains honestly red at the absent
  `build-wasm-windowed-opt/bin/blender_browser.deferred.wasm` complete-product boundary
  (`20260825T081317-1027365`). Container-backed regression keeps M0 6/6 green while M1–M8 retain
  their existing strict receipt, browser, product, run-label, hardware, and release boundaries
  (`20260825T081327-1027500`).

Only synchronous Python `Window.screenshot()` remains in the WM window-capture family. Its
synchronous public return value cannot be converted by silently returning a future, spinning the
WM worker, or enabling JSPI/Asyncify; it needs a separate API/design decision. Live C1/M5 acceptance
also remains deferred by the named blocker: no conformant hardware Vulkan ICD in WSL2 (NVIDIA
ships none; Mesa dzn rejected by Dawn). This work creates no adapter, browser profile, split
product, or live receipt and changes no result promotion, dependency decision, tolerance, golden,
blacklist, or milestone promise. dzn and Windows were not attempted, and WSL was not restarted.

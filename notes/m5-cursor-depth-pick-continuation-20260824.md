<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M5 cursor depth-pick continuation

## Outcome

Commit `24b455e` (patch 0256) converts the cursor-placement operator, the first concrete
consumer in the remaining View3D depth-pick family, to an owned kick-then-poll request.
`ViewportDepthPickSession` captures the exact region, dimensions, view matrices, event
coordinate, and one framebuffer-depth ticket spanning Blender's stock 0/2/4-pixel
auto-distance margins. Settlement searches those margins from inner to outer, so a nearer
hit in a wider margin cannot defeat the stock first-success precedence.

Native-ready requests apply during invoke. A browser-pending request resumes through a
240-by-10-ms View3D timer while unrelated input passes through. The continuation retains the
producing scene, View3D, region, window, event coordinate, orientation enum, and complete
cursor snapshot. A newer cursor request supersedes the older one; failure, timeout,
cancellation, context/view drift, or any intervening cursor mutation retires the request
without a late write. A settled request with no hit keeps Blender's view-plane fallback.

## Evidence

- Final source verification rejects 13 independent mutations. Native and wasm32 pass six
  byte-identical contracts covering 12 cases, including progressive-margin precedence,
  pending and native-immediate replay, supersession, no-hit fallback, failure/timeout,
  producing-context drift, viewport-transform drift, and late cursor mutation. Output is
  434 bytes at SHA-256
  `d942710ce5b0cbf104af850093e723424ef660d32a7ad08561d11b85320e649e`;
  the seven-file source receipt is SHA-256
  `603b9aff1319d3aaea90d49865c890ad7e480d513c06ceb989c4a55bc7d53177`:
  `ledger/buildlogs/20260824T185550-361269.log`.
- A clean rebuild compiles both final editor translation units, `view3d_draw.cc` and
  `view3d_edit.cc`, with clang++ 17 natively and em++ 6.0.5 for wasm32:
  `ledger/buildlogs/20260824T185742-363983.log`.
- Numbered patch 0256 applies from its exact three-file predecessor and reverse-applies from
  its postimage at SHA-256
  `708249c2c45931290fa2f55fcf12d4a60a1c1f270eafd3fecf54edc94d79d24e`:
  `ledger/buildlogs/20260824T185537-361099.log`.
- The read-only pin is reconstructed in an isolated source tree. Canonical replay retains
  20,258 entries across 275 paths and 233 active patches at patch SHA-256
  `551a2c756c7cafe4fd700235e4f02085cf8df7e718893339d7e8178fab2f3e33`
  and manifest SHA-256
  `f2a552e28534c72bf73a65814de2091ac093397bf6b8d14d1e06c47a378f3a89`:
  `ledger/buildlogs/20260824T185438-360542.log` and
  `ledger/buildlogs/20260824T185542-361168.log`.
- The broader owned-readback source contract still rejects 28 mutations and reports exactly
  `depth_pick`, `depth_cache`, and `window_capture` as the three open families:
  `ledger/buildlogs/20260824T185608-361659.log`.
- Required M5 remains honestly red only at the missing current
  `blender_browser.deferred.wasm` complete-product boundary:
  `ledger/buildlogs/20260824T185705-362962.log`. Container-backed regression restores M0
  to 6/6 green while M1-M8 retain their existing strict-receipt, browser, split-product,
  hardware, run-label, and release boundaries:
  `ledger/buildlogs/20260824T185712-363072.log`.
- Pinned REUSE 6.2.0 covers the complete checkout, including this record:
  `ledger/buildlogs/20260824T185845-364325.log`.

## Remaining boundary

This is one converted consumer, not closure of the depth-pick family. Navigation,
center-pick, depth eyedropper, painting, zoom-border, and NDOF consumers still reach
synchronous depth paths; full depth-cache and WM window-capture families also remain.
`ledger/deferred.json` therefore stays `partial` with a truthful count of three families.

No adapter, browser profile, split product, live GPU receipt, result promotion, dependency
decision, tolerance, golden, blacklist, or promise changed. Live C1 and aggregate M5
acceptance remain separately deferred by the named blocker
`no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none; Mesa dzn rejected by Dawn)`.
No dzn, Windows interop, or WSL restart path was attempted.

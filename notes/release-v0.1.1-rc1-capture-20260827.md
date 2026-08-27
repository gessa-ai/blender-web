<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# v0.1.1-rc.1 exact CAPTURE handoff — 2026-08-27

## Outcome

The release line is restored to the exact runtime generation that passed the Apple M4 Pro P0-E
acceptance bar. Commit `7ea0093` removes the later unverified frame-ownership experiment and
reconstructs the complete outer source tree of `72dde88`; canonical replay applies 270 patches to
the pinned Blender source. A locked CAPTURE relink reproduces all five Apple-tested product
identities byte-for-byte. The containing source commit is annotated as `v0.1.1-rc.1` for the
driver's exact-generation profile and final-gauntlet run.

## Hardware evidence

The driver identifies this generation by `blender_browser.wasm.orig` SHA-256
`505702dbf41ce0a9552f47e6a78ff9f10562c068c9471a35031835b33e9c062c`. Ten fresh Apple M4 Pro
contexts independently repaint a complete non-flat VIEW_3D scene after a 1280x720 -> 1100x640
shrink with zero post-resize input (10/10, approximately 10.8–11.1 seconds, zero page errors and
WebGPU rejections). Visual inspection confirms grid, shaded selected Cube, camera, light, panels,
and navigation gizmo rather than a threshold-only result. A separate six-cycle shrink/grow stress
run repaints 1100x640, 1280x720, 900x550, 1280x720, 700x500, and 1280x720 without input, then
continues to change semantic pixels after orbit. P0-E is closed.

## Exact CAPTURE generation

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `blender_browser.js` | 707,565 | `52a9a025783071e959daf55d0c07772d9a737220d13b524df9d07abc8ac5f2f0` |
| `blender_browser.wasm` | 120,511,178 | `69b2f10ebac7fe9ae86ad0e230ea8e4ea414e76e0c662a76600128d2b4c53a11` |
| `blender_browser.wasm.orig` | 119,157,853 | `505702dbf41ce0a9552f47e6a78ff9f10562c068c9471a35031835b33e9c062c` |
| `blender_browser.data` | 168,637,598 | `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c` |
| `blender_browser.split-build.json` | 13,251 | `10b181385e609313a07c59f936e34be892cc5cdb9d9a2fb526cd7c1bd2097788` |

The locked relink is `ledger/buildlogs/20260827T183234-2327996.log`; CAPTURE preflight and the
locked no-work check pass immediately afterward.

Focused verification is green at the release boundary:

- resize source and immutable frame-tail trace contracts:
  `20260827T183549-2329831` / `20260827T183549-2329832`;
- hardware acceptance producer and independent receipt-consumer self-checks:
  `20260827T183549-2329836` / `20260827T183549-2329844`;
- native/wasm32 integrated queue and resize recovery:
  `20260827T183549-2329861`;
- deterministic tagged-release contract:
  `20260827T183549-2329855`;
- REUSE 6.2.0: `20260827T183635-2332320`;
- pinned-oracle regression restores M0 to 6/6. M1–M8 retain their named strict manifest,
  unsupported M4 binding, missing deferred APPLY artifact, render/files, and aggregate receipt
  boundaries; none is promoted by the driver handoff alone.

## Boundary

`v0.1.1-rc.1` is an immutable CAPTURE/profile handoff, not a public release archive. The current
accepted success/terminal profile pair predates this original and is hash-incompatible. The
driver must run both capture scenarios against this exact tag and return their accepted profiles;
only their strict union may authorize APPLY. The public staged assembler and deterministic tagged
release packager remain the only route to hostable bytes, and the packager deliberately rejects
this CAPTURE generation. No profile, APPLY shard, public bundle, final `v0.1.1` tag, staged
hardware receipt, milestone result, promise, or launch claim is created here.

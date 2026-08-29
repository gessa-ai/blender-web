<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J async modal event pass-through — 2026-08-29

## Outcome

Commit `8e5df79` and numbered patch 0319 extend the browser modal-handler return-code
correction beyond viewport selection. Five asynchronous continuations now distinguish an event
they own from an event that belongs to a later handler:

- screenshot readback;
- 3D-cursor depth pick;
- view-center depth pick;
- zoom-border depth pick; and
- NDOF depth pick.

For each family, a non-private event returns bare `OPERATOR_PASS_THROUGH`. An owned timer whose
readback is still pending returns `OPERATOR_RUNNING_MODAL`. The 3D-cursor invoke path deliberately
keeps its combined return because that path must permit click-drag while installing its modal
continuation. The separate navigation continuation also keeps its combined queued-event behavior:
it owns and later replays that event, unlike the five non-owned branches changed here.

This closes a source-level sibling audit of the same contradiction already found in browser
selection: `RUNNING_MODAL | PASS_THROUGH` maps to a breaking WM modal-handler result and therefore
does not actually let the next owner handle the event.

## Evidence

- Fail-first focused contract: `ledger/buildlogs/20260829T175900-202890.log`.
- Final focused mutation contract: `ledger/buildlogs/20260829T181212-212855.log`.
- Screenshot, cursor, center, zoom, NDOF, and aggregate async-readback contracts:
  `ledger/buildlogs/20260829T180439-206404.log`,
  `ledger/buildlogs/20260829T180924-211198.log`,
  `ledger/buildlogs/20260829T180650-208141.log`,
  `ledger/buildlogs/20260829T180657-208648.log`,
  `ledger/buildlogs/20260829T180753-210091.log`, and
  `ledger/buildlogs/20260829T180805-210055.log`.
- Five affected production Wasm objects: `ledger/buildlogs/20260829T180830-210917.log`.
- Canonical replay and receipt self-check:
  `ledger/buildlogs/20260829T181212-212856.log` and
  `ledger/buildlogs/20260829T181212-212861.log`; canonical patch SHA-256 is
  `c843a56e668241cb98a8482d2d6ea902df352d69a37b9a96408eee47dd419f13`.
- Locked relink, CAPTURE preflight, locked no-work check, and pinned REUSE:
  `ledger/buildlogs/20260829T181253-213372.log`,
  `ledger/buildlogs/20260829T181358-214450.log`,
  `ledger/buildlogs/20260829T181358-214451.log`, and
  `ledger/buildlogs/20260829T181236-213142.log`.
- Exact isolated-X slow/sparse software control:
  `ledger/buildlogs/20260829T181445-214834.log`; navigation passed through while selection was
  live, Cube selection finished, and the independent recovery orbit completed in
  329/3,936/6,821 ms with zero page or lifecycle errors.

## Product identity and boundary

The relinked CAPTURE inventory at `8e5df79` is JS `bba3f480bb3b`, Wasm
`bc9a997ed19a`, `.wasm.orig` `79c4a0f9edf4` (119,031,231 bytes), data
`095d0ba748c3`, and split manifest `6e3b16ececcb`.

The software-adapter run is diagnostic only. Direct M4 remains red at the Apple browser-pixel
binding (`ledger/buildlogs/20260829T181550-215466.log`), while pinned-oracle regression restores
M0 6/6 and preserves the named M1-M8 boundaries
(`ledger/buildlogs/20260829T181617-215905.log`). P0-I/J remain open until this exact generation
passes the driver's 10/10 slow/sparse Apple series plus the same-generation P0-E and zero-artifact
gauntlet. No hardware receipt, profile, APPLY/public bundle, tag, release, promotion, promise,
tolerance, golden, blacklist, deferral, or launch claim changes here.

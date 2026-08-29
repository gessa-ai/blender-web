<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# P0-I/J browser gesture-selection pass-through — 2026-08-29

## Outcome

The pending-selection WM return-code audit found two siblings of the deterministic click-selection
failure. The browser particle-gesture and bitmap-gesture continuations both returned
`OPERATOR_RUNNING_MODAL | OPERATOR_PASS_THROUGH` for events they did not own. Pinned Blender maps
that pair to `WM_HANDLER_BREAK | WM_HANDLER_MODAL`, so later modal handlers and keymaps never saw
the event. Patch 0318 changes both branches to bare `OPERATOR_PASS_THROUGH`. Because neither branch
returns finish or cancel, each continuation remains installed while WM correctly continues to the
event's owner.

The existing click-selection navigation and unrelated-event corrections are unchanged. The
focused contract now binds all three asynchronous selection continuation families and mutation-
rejects either gesture branch returning the combined status. The broader owned-readback contract
was also reconciled with patch 0314's already-shipping monotonic 30-second viewport-selection
timeout; the stale 240-timer expectation no longer masks this source check.

## Evidence

- Fail-first continuation contract: `ledger/buildlogs/20260829T172428-175910.log`.
- Final 15-mutation continuation contract and affected Wasm object:
  `ledger/buildlogs/20260829T173300-181976.log` and
  `ledger/buildlogs/20260829T172528-176327.log`.
- Adjacent stream, wall-timeout, rotate-retirement, and sync-stage mutation contracts:
  `ledger/buildlogs/20260829T172541-176391.log` through
  `ledger/buildlogs/20260829T172541-176405.log`.
- Canonical clean-pin freeze/replay and receipt self-check:
  `ledger/buildlogs/20260829T172614-177206.log` and
  `ledger/buildlogs/20260829T172658-177753.log`/`177758.log`; canonical patch SHA-256 is
  `447beacd1c93566085287ab605a35ee9f1225ebfcbcf129833db47653aa5d7db`.
- Full owned-readback native/Wasm contract and mutation self-check:
  `ledger/buildlogs/20260829T173031-180067.log` and
  `ledger/buildlogs/20260829T173044-180479.log`.
- Locked relink, no-work, CAPTURE preflight, and REUSE:
  `ledger/buildlogs/20260829T172707-177911.log` and
  `ledger/buildlogs/20260829T173059-180605.log`/`180607.log`/`180613.log`.
- Exact slow/sparse fallback product control:
  `ledger/buildlogs/20260829T172831-178486.log`; the first orbit, selection drain, and independent
  recovery completed in 414/4,643/7,220 ms with no product failure.

### Repeated software stability

The unchanged exact CAPTURE product completed 10/10 fresh slow/sparse software runs. Six ran under
WSLg and four under fresh isolated Xvfb servers. Every accepted run required and observed live
pending-selection navigation pass-through, selected exactly `Cube`, retired both viewport rotates
and the selection continuation, and recorded zero selection-readback, page, or lifecycle errors.
First-orbit drain was 313-437 ms, selection completion was 2,395-5,029 ms, and the independent
recovery orbit completed in 6,862-8,409 ms. Accepted evidence is
`ledger/buildlogs/20260829T173858-186790.log` through
`ledger/buildlogs/20260829T174721-194956.log`.

Four additional WSLg attempts closed their target page/context externally with empty page-error
and selection-failure censuses; they are rejected rather than counted. Their logs are
`20260829T174014-187726`, `20260829T174209-189763`, `20260829T174321-191291`, and
`20260829T174437-192282`. Fresh navigation, stream-continuation, and sync-stage mutation checks are
green at `20260829T174908-196406`, `196407`, and `196412`. Pinned REUSE 6.2.0 covers
2,823/2,823 files at `20260829T174920-196533`. Direct M4 remains red only at the unchanged
Apple/browser-pixel binding (`20260829T175036-196977`); pinned-oracle regression restores M0 6/6
while preserving every named later boundary (`20260829T175044-197079`).

Implementation commit is `7c0971b`. The relinked CAPTURE inventory is JS
`bba3f480bb3b`, Wasm `48ef66fc238d`, `.wasm.orig` `104bc1579a91` (119,031,221 bytes), data
`095d0ba748c3`, and split manifest `059d3bd3a8dd`.

## Boundary

This closes the source/device-free sibling audit, not P0-I/J. The driver-operated Apple M4 Pro must
still pass the exact slow/sparse series 10/10 against this generation, followed by the same-
generation P0-E and zero-artifact interaction gauntlet. Direct M4 remains red at that browser-pixel
boundary; no hardware receipt, profile, APPLY/public bundle, result, release, promotion, promise,
tolerance, golden, blacklist, deferral, or launch claim changed.

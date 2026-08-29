# P0-I/J pending-selection navigation motion order — 2026-08-29

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

The slow/sparse discriminator exposed a concrete FIFO violation after pending viewport selection:
the retained `G` key and confirmation replayed, but the transform's pointer motion passed the
selection continuation immediately and reached Blender before `G`. The eventual replay therefore
invoked and confirmed a zero-delta move. All DOM, GHOST, WM, selection-readback, modal-retirement,
and content-presentation boundaries were complete, but Cube remained at `[0, 0, 0]`.

Patch 0320 initially tracked MMB press/release inside the selection continuation and passed motion
only while that local navigation bit was set. The relinked product falsified that first correction:
the rotate modal installed after MMB press consumes MMB release before the earlier selection modal
observes it. The local bit therefore remained set and later transform motion still overtook its
retained key.

Patch 0321 closes that cross-modal ownership gap. MMB, held-navigation motion, wheel, gesture,
modifier, and NDOF events still pass to their live owner. The first ordinary non-navigation event
also clears stale navigation ownership before entering the selection FIFO. Thus a retained `G`
closes any unobservable rotate tail and its following motion and confirmation remain in the same
FIFO. This is Emscripten-only; native selection, browser readback, timeout, draw retry, and redraw
policy are unchanged.

## Fail-first and source evidence

- The enhanced slow/sparse product run against the first 0320 relink completed selection replay
  but left Cube unmoved with four replayed events:
  `ledger/buildlogs/20260829T190533-252787.log`.
- The 0321 source contract failed before the source/patch existed at
  `ledger/buildlogs/20260829T190933-255538.log`.
- The final 28-mutation navigation/WM census is green at
  `ledger/buildlogs/20260829T191059-256003.log`; rapid-input, selection-stream, and Apple-series
  consumer self-checks are green at `ledger/buildlogs/20260829T191124-256176.log`,
  `ledger/buildlogs/20260829T191124-256171.log`, and
  `ledger/buildlogs/20260829T191124-256189.log`.
- The affected production Wasm object compiled at
  `ledger/buildlogs/20260829T191124-256170.log`.
- Patch 0321 reverses cleanly from the live postimage. The regenerated 20,258-path canonical
  source freeze and receipt self-check are green at
  `ledger/buildlogs/20260829T191244-257457.log` and
  `ledger/buildlogs/20260829T191244-257458.log`; canonical patch SHA-256 is
  `04ba2e6ba8a04ef37bdaf879b10a135736f07114597a908bbbdea8bba244193c`.

## Product verification

The correction is committed as `8e99bc8` after the diagnostic 0320 commit `dc8d538`. Locked relink
and committed-state no-work are green at `ledger/buildlogs/20260829T191339-258049.log` and
`ledger/buildlogs/20260829T191445-259150.log`. CAPTURE product and runtime preflights are green at
`ledger/buildlogs/20260829T191738-261575.log` and
`ledger/buildlogs/20260829T191738-261574.log`.

The first exact slow/sparse served-product run passed at
`ledger/buildlogs/20260829T191451-259194.log`: the selection continuation replayed 13 ordered
events, retired with zero queued events, selected exactly Cube, retired both rotate operators,
cleared both held-button masks, and moved Cube to `[0.33677, 1.14945, 0.42573]`. The ordinary rapid
producer also remains green at `ledger/buildlogs/20260829T191608-259923.log`.

### Repeated software stability

The exact product completed 10/10 accepted slow/sparse software runs: six on the shared display
and four under fresh isolated X servers. Every run required live pending-selection navigation,
exactly 13 replayed FIFO events, two retired rotate operators, exactly Cube selected, cleared
GHOST/WM held-button masks, strict content presentation, and a nonzero native Cube translation.
Action drain was 317-1,412 ms, selection drain was 2,247-4,777 ms, and the final recovery was
6,576-8,205 ms. Page-error and browser-lifecycle censuses were empty across all ten.

Accepted logs are:

- `ledger/buildlogs/20260829T191451-259194.log`;
- `ledger/buildlogs/20260829T191750-261665.log` through
  `ledger/buildlogs/20260829T191944-263034.log`;
- `ledger/buildlogs/20260829T192106-264647.log`;
- `ledger/buildlogs/20260829T192221-265570.log`; and
- `ledger/buildlogs/20260829T192306-266728.log` through
  `ledger/buildlogs/20260829T192423-267686.log`.

Two intervening shared-display target/context closures had empty page-error censuses and were
rejected rather than counted: `ledger/buildlogs/20260829T192022-264138.log` and
`ledger/buildlogs/20260829T192143-265142.log`.

## Exact candidate and boundary

The relinked CAPTURE inventory is JS `bba3f480bb3b`, Wasm `e61b1f4cc5f3`, `.wasm.orig`
`6b0ac5366aef` (119,031,283 bytes), data `095d0ba748c3`, and split manifest `a3569ddfe799`.

This is repeatable software-adapter evidence, not P0-I/J closure. Direct M4 remains red at the
Apple browser-pixel binding, and the regression harness retains its named strict/APPLY/product
boundaries. The driver must pass this exact generation through the immutable Apple slow/sparse
series 10/10 plus the same-generation P0-E and zero-artifact interaction gauntlet before P0-I/J
can close. No hardware receipt, profile, APPLY/public bundle, release tag, promotion, promise,
tolerance, golden, blacklist, deferral, or launch claim changes here.

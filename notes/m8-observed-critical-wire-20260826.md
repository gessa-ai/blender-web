<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 observed critical-wire accounting — 2026-08-26

## Outcome

Commit `88bac1b` closes R13's high-severity false-green path in the 15 MB launch receipt. The
performance producer no longer derives critical transport from `BOOT_CRITICAL_URLS`. It records
every same-origin request and response through the first proven semantic interaction, then requires
each critical request to be a queryless GET with one 200/Brotli response mapped to an exact raw
artifact and `.br` sibling in the served bundle.

The receipt composer independently reconstructs each cold run's observed path set. A known extra
bundle response is counted; unknown, duplicate, queried, unmapped, missing, redirected/error, or
non-Brotli transport fails the receipt. The aggregate is the union of all cold-run sets. The final
M8 verifier recomputes that union and checks each recorded Brotli size and the total against the
exact bundle siblings instead of asserting the former fixed ten-path list.

## False-green proof

The predecessor contract fails first because the composer has no observed-inventory API
(`ledger/buildlogs/20260826T175906-1093257.log`). The final producer and receipt contracts accept a
synthetic early `/extra.js` only when both raw and Brotli artifacts exist and include it in the
total; mutations for an unknown artifact, duplicate request, query, absent response, and omitted
aggregate path all fail (`20260826T181041-1103987.log`, `20260826T181041-1103989.log`). Aggregate
and source-freeze self-checks remain green (`20260826T181041-1103988.log`,
`20260826T181041-1103994.log`). REUSE 6.2.0 remains green
(`20260826T180948-1103549.log`).

The driver-supplied Apple CAPTURE evidence is not a public-wire receipt, but it demonstrates why
the repair matters: `mac-m4pro-success-20260826/requests.json` contains 28 requests for
`/bin/blender_browser.js`. The former unique-file projection silently collapsed this class of
request. The repaired gate rejects that ambiguity; the exact generated public bundle must now show
whether its cache/worker transport satisfies the budget.

## Boundary

No Wasm/data/glue artifact, CAPTURE profile, APPLY product, public bundle, browser or hardware
receipt, result promotion, tolerance, golden, blacklist, dependency, deferral, or milestone promise
changed. The scoped M8 run remains red at the existing missing APPLY/product/browser/tier receipts,
and the canonical container-backed regression restores M0 6/6 while M1–M8 retain their strict
boundaries (`20260826T180825-1101227.log`, `20260826T180915-1101923.log`).

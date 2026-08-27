<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 pthread shared-main HTTP cache — 2026-08-27

## Outcome

Implementation commit `653ebe0` removes the separate public
`blender_browser.worker.js` artifact without restoring per-worker origin requests. The public
assembler now gives the Stage-0-rewritten page glue one immutable URL of the form
`/bin/blender_browser.js?sha256=<decoded-content-sha256>`. The normal script tag and
`pthread-main-loader.js` consume that exact URL. Chromium completes the page script first, then
satisfies the bootstrap fetch from its HTTP cache; the bootstrap independently hashes the decoded
bytes before supplying their Blob through Emscripten's supported `mainScriptUrlOrBlob` seam.

The page factory remains an ordinary same-origin script under the existing strict
`script-src 'self' 'wasm-unsafe-eval'` policy. Only pthread execution uses `worker-src blob:`. No
`script-src blob:`, `unsafe-eval`, generated-glue rewrite, relink, or CAPTURE/APPLY byte mutation was
needed.

## Browser and receipt contract

A source-frozen browser contract serves the exact current CAPTURE product through an in-memory,
explicitly nonreceipt public-shell transform. Pinned Node 22.16.0 / Playwright 1.61.1 Chromium
proves:

- one origin GET for the current page-glue body;
- exactly two Resource Timing consumers for the same content-addressed URL: one `script` and one
  `fetch`;
- exactly one positive transfer size and one zero-byte HTTP-cache hit;
- decoded sizes and the bootstrap SHA-256 equal the exact current glue;
- one Module factory call and all 8/8 configured pthread pool starts as unique same-origin Blob
  dedicated workers;
- `crossOriginIsolated === true`, `WM_main`, strict CSP, and zero page errors.

The shipping performance producer and independent Python composer enforce the same shape before a
semantic interaction. They count the two logical consumers as one critical-path artifact only after
the cache proof shows one transferred body. Per-run origin counts are deltas from a fail-closed
pre-navigation server snapshot, so the three-run receipt cannot confuse cumulative server state
with a duplicate transfer. Missing, queryless, wrong-hash, extra-transfer, wrong-initiator,
wrong-size, duplicate-worker, wrong-origin, late-worker, and multi-factory mutations remain red.

The service-worker precache/cache-first inventory uses the same content-addressed URL, and the exact
static header contract makes `/bin/*.js` immutable. The stable queryless path is not a canonical
public consumer and is rejected by the receipt.

## Exact planning bytes

The canonical assembler and an independent full-tree provenance replay regenerated the current b8
shell/data tree with pinned q11/lgwin-24. They used the already-recorded c9 provisional primary only
as a cross-generation planning component; this is not a current APPLY bundle or receipt.

| component | prior Brotli bytes | shared-main Brotli bytes | delta |
|---|---:|---:|---:|
| Stage-0 data | 2,230,167 | 2,230,167 | 0 |
| page glue | 61,066 | 61,066 | 0 |
| duplicate worker source | 61,066 | 0 | -61,066 |
| all other shell/font/generated controls | 44,825 | 45,039 | +214 |
| **current non-Wasm/control subtotal** | **2,397,124** | **2,336,272** | **-60,852** |
| earlier c9 provisional primary | 12,292,157 | 12,292,157 | 0 |
| **hybrid complete critical wire** | **14,689,281** | **14,628,429** | **-60,852** |

The 214-byte control increase is fully measured: the content-bound loader is 911 Brotli bytes
(+161), the versioned index is 3,054 (+60), the generated worker is 3,613 (-6), and registration is
1,783 (-1). The provisional decimal-budget margin increases from 310,719 to **371,571 bytes**. A
real current primary must be at most **12,663,728 bytes**.

## Evidence and boundary

- exact hybrid assembly and q11 inventory:
  `ledger/buildlogs/20260827T025834-1546320.log`;
- independent Stage-0 derivation and full-tree/generated-control/q11 replay, both bound to cache
  version `8eed2b864d8414d6589d`:
  `ledger/buildlogs/20260827T030454-1549987.log` and
  `ledger/buildlogs/20260827T030505-1550035.log`;
- exact current-product browser cache/Blob-worker proof:
  `ledger/buildlogs/20260827T031515-1557557.log`;
- loader, performance, technical-receipt, transport, server, provenance, assembler, and aggregate
  M8 adversarial self-checks:
  `ledger/buildlogs/20260827T031459-1556989.log`,
  `ledger/buildlogs/20260827T031459-1556986.log`,
  `ledger/buildlogs/20260827T031459-1556998.log`,
  `ledger/buildlogs/20260827T031459-1557091.log`,
  `ledger/buildlogs/20260827T031501-1556991.log`,
  `ledger/buildlogs/20260827T031459-1557007.log`,
  `ledger/buildlogs/20260827T031505-1557000.log`, and
  `ledger/buildlogs/20260827T031515-1557556.log`;
- REUSE and two-root release-freeze self-checks:
  `ledger/buildlogs/20260827T031640-1559474.log` and
  `ledger/buildlogs/20260827T031640-1559475.log`;
- deterministic public dashboard:
  `ledger/buildlogs/20260827T032252-1566940.log` and
  `ledger/buildlogs/20260827T032252-1566939.log`;
- required direct M8 scope, direct regression, and pinned-oracle container regression remain
  honestly red at the named missing APPLY/browser/tier inputs while the container restores M0 to
  6/6:
  `ledger/buildlogs/20260827T032004-1562953.log`,
  `ledger/buildlogs/20260827T032010-1563029.log`, and
  `ledger/buildlogs/20260827T032118-1563738.log`.

No build-tree artifact, profile, APPLY shard, public bundle, hardware receipt, milestone result,
tolerance, golden, blacklist, deferral status, or launch claim changed. The exact current-generation
Apple profiles and APPLY hardware size/latency/pixel receipts remain mandatory.

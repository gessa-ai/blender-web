# M8 pthread single-transfer transport — 2026-08-27

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

## Outcome

Implementation commit `0155397` removes a hidden multiplier from the public critical path. The
unmodified current windowed CAPTURE product reached `WM_main` with zero page errors but started the
page and its pthreads through **34 requests for `/bin/blender_browser.js`**. Browser caching can
reduce transferred bytes, but it cannot turn that request/response ambiguity into the launch
receipt's exact singleton critical-path evidence.

The public assembler now emits one separately inventoried
`/bin/blender_browser.worker.js` whose bytes are exactly the Stage-0-rewritten page glue. A small
bootstrap fetches and hashes that source once, then supplies the resulting Blob through pinned
Emscripten's supported `Module.mainScriptUrlOrBlob` contract. The page glue still loads through a
normal same-origin script tag; every proxied-main/pool/runtime pthread starts from a unique
same-origin Blob URL with no additional HTTP transfer. This is public-bundle-only and does not
rewrite generated glue or change CAPTURE/APPLY Wasm bytes.

The exact relinked CAPTURE generation is:

| artifact | bytes | SHA-256 |
|---|---:|---|
| `blender_browser.js` | 707,441 | `23d9c1b09c2b54cc67d0af4436a53cb6555209b038cedbebdb53dd73b8ea1d31` |
| `blender_browser.wasm` | 120,497,886 | `6aca69e88048a678e78752eefea2e1ffe337d29beff2ae5a5a9b1d6187004d13` |
| `blender_browser.wasm.orig` | 119,144,751 | `b8b2a682ff09e5eb80ba125b3fb85cd4fe65193c3eabd577e8a794c9e6a9fda6` |
| `blender_browser.data` | 168,637,598 | `095d0ba748c3cdc2fcd0956def221e0f0d347d41d95e0a150a28670ab1cea24c` |
| `blender_browser.split-build.json` | 13,218 | `3c75d87e14b043bae9e81e60428493df180912d4a87924ee160a87aa4f738f47` |

## Fail-closed receipt shape

The assembler, exact bundle allowlist, Brotli inventory, service-worker cache, transport server,
staged provenance, M7 fallback freeze, two-root release freeze, and tagged aggregate source closure
all bind the new loader and worker-source artifact. Independent JavaScript and Python consumers
require:

- one queryless GET/200 Brotli response for both page glue and worker source;
- decoded worker-source bytes and SHA-256 equal to the exact public bundle artifact;
- one Module factory call and no bootstrap error;
- at least the proxied main plus eight pool workers before semantic interaction;
- unique `blob:` dedicated-worker objects whose embedded origin equals the measured page origin.

Blob worker startup is a Playwright dedicated-worker event, not a network-request event in current
Chromium. The initial implementation expected Blob request events; the real browser correctly
reported none. The final producer records `page.on("worker")` objects and keeps actual HTTP(S)
requests in the wire union. This makes the distinction explicit without hiding any response.

The loader contract preserves every pinned Emscripten default `INCOMING_MODULE_JS_API` member and
adds exactly `mainScriptUrlOrBlob`; it also proves both pinned libpthread conditional seams. Raw and
deterministically minified loader behavior cover singleton fetch/factory success plus status,
redirect, empty response, network failure, duplicate installation, invalid configuration, and
identity mutations. A fast pre-factory fetch failure is marked handled immediately and is still
re-thrown through the normal factory/boot failure path.

## Evidence

- current-product reproduction, 34 main-glue requests, `WM_main`, zero page errors:
  `ledger/buildlogs/20260827T010142-1458597.log`;
- pre-link byte-equivalent Blob proof, one main plus one worker-source request:
  `ledger/buildlogs/20260827T010243-1459902.log`;
- locked CAPTURE relink: `ledger/buildlogs/20260827T011838-1470750.log`;
- final live current-glue/current-loader browser proof: one main response, one worker-source
  response, 32 unique Blob workers, `WM_main`, zero page errors:
  `ledger/buildlogs/20260827T013501-1487011.log`;
- loader/provenance/assembler/performance/receipt contracts:
  `ledger/buildlogs/20260827T013412-1484711.log`,
  `ledger/buildlogs/20260827T013412-1484712.log`,
  `ledger/buildlogs/20260827T013412-1484716.log`,
  `ledger/buildlogs/20260827T013412-1484723.log`, and
  `ledger/buildlogs/20260827T013412-1484734.log`;
- M8, two-root freeze, final aggregate, M7, and REUSE self-checks:
  `ledger/buildlogs/20260827T013423-1485198.log`,
  `ledger/buildlogs/20260827T013423-1485199.log`,
  `ledger/buildlogs/20260827T013423-1485203.log`,
  `ledger/buildlogs/20260827T013423-1485219.log`, and
  `ledger/buildlogs/20260827T013423-1485210.log`;
- pinned q11/lgwin-24 cost: rewritten worker source 61,066 bytes and minified loader 750 bytes:
  `ledger/buildlogs/20260827T013526-1487482.log`;
- container-backed regression restores M0 6/6 while later tiers retain their named boundaries:
  `ledger/buildlogs/20260827T013125-1482170.log`.

## Budget and boundary

The prior provisional complete-wire shape was approximately 14,616,981 bytes. The exact current
worker source plus bootstrap adds 61,816 bytes, moving the lower-bound projection to approximately
**14,678,797 bytes**, at most 321,203 bytes below the decimal 15 MB ceiling before regenerated
index/service-worker control deltas and the already-named small compressed-Wasm delta are measured.
The duplicate source cost is deliberate: executing the page factory from the same Blob would require
loosening `script-src` to `blob:` (or `unsafe-eval`), which is not an acceptable public security
trade.

This is not an APPLY/public bundle, hardware pixel result, or accepted performance receipt. The
current `b8b2a682ff09` CAPTURE generation still needs fresh accepted Apple success and terminal-error
profiles; the resulting APPLY bundle must then pass the exact <=15,000,000-byte and <=8-second
hardware measurements. No profile, receipt, result, deferral status, tolerance, golden, blacklist,
or launch claim changed here.

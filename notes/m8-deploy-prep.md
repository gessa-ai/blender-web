<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 deploy-prep - bundle + LAUNCH audit (findings)

Date 2026-08-08 · HEAD `5750083` (branch `agent/m2.5-python-boot`) · prepare-only.
Lane deliverables live in `sandbox/m8-deploy/` (bundle assembler, COOP/COEP server,
Playwright boot verify, `_headers`, `LAUNCH_AUDIT.md`, `README.md`).

## Deploy-bundle facts (for whoever wires staged loading / hosting next)

- **Served surface is 5 files**: `index.html` (= `platform_web/shell/windowed.html`),
  `boot-windowed.js`, `bin/blender_browser.{js,wasm,data}`. Plus `_headers`.
- **No `.worker.js`, no separate preinit worker.** pthreads reuse the glue via
  `new Worker(pthreadMainJs)` (same-origin); `wgpu-preinit-worker.js` is a `--post-js`
  compiled INTO `blender_browser.js`. Verified: `grep -c preinitializedWebGPUDevice`
  in the glue = 1; the verify run fetched nothing else. The bundle keeps a provenance
  copy of `wgpu-preinit-worker.js` for auditability only.
- **Paths are absolute from docroot**: `windowed.html` loads `/boot-windowed.js` and
  `/bin/blender_browser.js`; `boot-windowed.js` sets `BIN_PREFIX="/bin/"` and
  `locateFile` resolves wasm/data under it. So docroot MUST be the bundle root (which
  is what Cloudflare Pages does with the bundle as the output dir).
- **COOP/COEP/CORP required** (pthreads => SharedArrayBuffer). `_headers` sets them on
  `/*`; `serve_bundle.py` mirrors them; `verify_boot.mjs` asserts
  `self.crossOriginIsolated`.
- **MIME**: `.wasm` MUST be `application/wasm` (instantiateStreaming + `nosniff`);
  `.data` = `application/octet-stream`; `.js` = `text/javascript`.
- **Payload is symlinked by default** (avoid copying ~200 MiB each assembly);
  `--copy` makes a self-contained uploadable bundle.
- **No favicon by design** (brand art = D-7 human decision; no Blender logo). The
  auto `/favicon.ico` 404 is harmless.

## Boot verdict

PASS on bundle mechanics: served COOP/COEP-isolated, WM_main in 829 ms, `__bwModule`
exposed, `?gate=1280x720` exact-size honored, `presentBackbuffer` fired. **Captured
frame is black** because the current r29 in-flight binary presents one black frame
then idles (splash and workspace alike) - the open solid-cube Bug B, a GPU-lane
state, not a bundle fault. The same capture method produced a non-black image on the
earlier r28 binary. Evidence: `sandbox/m8-deploy/artifacts/bundle_boot_1280x720.png`.

## Latent bug fixed in this lane's own rig

`verify_boot.mjs` (and, for reference, the parity lane's `capture_web.mjs`) called
`page.waitForFunction(fn, { timeout })` - but `{timeout}` there is the *pageFunction
arg*, not the options; the real timeout stayed at Playwright's 30 s default. Harmless
for the opt binary (boots <1 s) but it silently caps slow/degraded boots. Fixed in
this lane's rig to `waitForFunction(fn, null, { timeout })`. (The parity lane's copy
is not this lane's file; flagged, not touched.)

## Wire-size reality vs the 15 MB bar (authoritative: RANKING.md)

- wasm alone: **20.13 MB brotli** = 1.34x the 15 MB bar by itself.
- stage-0 wire-to-interactive: **24.71 MB** = 1.6x over. Monolith today: 49.82 MB.
- To hit 15 MB the wasm must drop to <=~10.4 MB (48% cut). Compiler levers are spent
  (<1%; `-Os`/`-Oz` move the wire the WRONG way). Needs feature-DCE (RANKING top-5:
  name-strip ~1.04, sculpt ~0.67, compositor ~0.34, GP ~0.31, VSE-bundle ~0.29) +
  a JSPI wasm-split (shader compiler ~1 MB, plus importers/exporters/compositor/
  sculpt/Cycles as post-first-pixels modules). Staging (done) + feature-cut + split
  are all three required.
- A live re-measure was attempted but the r29 lane was relinking the binary mid-read
  (raw wasm 123.27 -> 122.80 MB between reads); use RANKING's stable q11 numbers.

## reuse lint - repo-wide status (task 3)

`reuse lint` (v6.2.0) at repo root = **exit 1 / not compliant with REUSE 3.3**, but:

- **Green on the tracked source set (what CI lints).** Tracked non-`upstream` files =
  1001; reuse counts 1080 files with copyright info; used licenses = the intended four
  (GPL-3.0-or-later, GPL-2.0-or-later, Apache-2.0, CC0-1.0); 0 bad / 0 deprecated /
  0 invalid SPDX expressions.
- The exit-1 is **~30k UNTRACKED build-tree files** with no SPDX -
  `build-wasm-windowed-opt/`, `build-wasm-windowed/`, `build-wasm-gpu/`,
  `build-wasm-cycles/` (copied Blender datafiles/shaders) - plus untracked r29 debug
  PNGs under `platform_web/shell/evidence/`. A fresh CI checkout has none of these.
- **Root cause = a `.gitignore` gap**: `build-wasm/` is ignored but the
  `-windowed*/-gpu/-cycles` variants are not, so they are neither committed nor
  skipped by reuse. Fixing that gap makes the local lint match CI green. (Not this
  lane's file to edit - flagged for the config/harness lane.)
- **Only 2 genuinely-tracked gaps:** `platform_web/shell/evidence/m4-r24-final-black-1280x720.png`
  and `.../m4-r24-r23code-black-1280x720.png` lack SPDX (shell lane's evidence, not
  this lane's files).

This lane's own new files all carry SPDX (GPL-3.0-or-later for scripts, CC0-1.0 for
`_headers`/docs) and pass reuse.

## Compliance-file inventory (for the LAUNCH audit)

Present: `LICENSES/{GPL-3.0-or-later,GPL-2.0-or-later,Apache-2.0,CC0-1.0}.txt`,
`NOTICE` (credits Blender Authors + Foundation; nominative-use + trademark
disclaimer), `PROVENANCE.md` (per-file convention + module map, mostly "planned"),
`THIRD-PARTY.md` (deps listed, all rows "pending"), `ledger/deferred.json` (deferral
registry with named blockers), `reports/dashboard.md` (static conformance dashboard).
**Missing:** root `README.md`, `AUTHORS`.

## The launch-gating conflict to escalate (box L7)

Every recent commit carries BOTH `Assisted-by:` AND
`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. LAUNCH.md L7 + D-7 + GOAL.md
require human author + `Assisted-by:` ONLY, no AI `Co-authored-by` (Blender's
contributor policy bans AI commit authorship; this is the fight LAUNCH.md warns not to
re-detonate). HUMAN decision before the public repo is cut: history filter vs policy
change. This lane's commit follows the repo's established trailer convention (both
trailers) rather than freelancing a different history - the fix is a whole-history
call, not a per-commit one.

<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 technical close-out audit

**As of 2026-08-11: RED, fail-closed; no final source freeze or M8 receipt.**

The executable candidate is `sandbox/m8-launch-gate/verify_m8.py`. It has a
non-circular pre-receipt mode (M0–M7 plus exact M8 evidence), an owner-controlled
post-receipt mode (M8 result plus freshly regenerated dashboard), and a launch mode
for signed owner/deployment evidence. Every invocation separates local technical
failures, post-receipt failures, and external blockers in
`sandbox/m8-launch-gate/artifacts/current-m8-preflight.json`.

## Current mechanism state

- M7 now emits a finalizer-owned split inventory with one primary wasm, at least one
  dynamically named deferred shard, and one build-only original. M8 discovers the
  inventory; it does not hardcode shard names. It requires exact role/path/size/hash/
  request-phase values and rejects every unlisted `blender_browser*.wasm*` file.
- The current split bytes are **not released**. The latest strict attempts prove the
  desired request ordering (the first deferred request began 498–505 ms after the
  trusted interaction), but the full runtime receipt remains FAIL: r6 correctly
  rejected a synchronous EEVEE entry, and r7 sampled a transient 0×0 render result
  while a single-threaded local server prevented the worker shard responses from
  completing. Those attempts are diagnostic only.
- All earlier staged, product, browser-matrix, and soak receipts predate the current
  split/artifact set and are stale. None may be carried forward.
- The last accepted pre-split launch measurements remain useful only as historical
  blockers: Stage-0 semantic pixels were absent, eventual product pixels took about
  20.8 seconds locally, and the pinned 1.5 MB/s + 40 ms profile exceeded both the
  8-second and 15,000,000-byte critical budgets. The split must be measured anew;
  no budget is weakened or presumed green.

## Locally actionable closure

After M7 produces a strict mechanism PASS and explicitly closes its browser/server:

1. Freeze all final public shell/file-bridge/capability/first-present/footer/query,
   Stage-1 loader, service-worker, assembler, and legal-payload source changes.
2. Re-run final M4–M7 browser evidence on that frozen shell. The mechanism-release
   receipt is not the final M7 receipt.
3. Assemble one exact copied bundle from the successful split inventory. Copy every
   shipped shard, create/verify every q11 sibling, emit only a sanitized public split
   manifest, precache every logical raw asset, and reject extra files/symlinks/local
   paths. Do not emit the old timestamped `BUNDLE_MANIFEST.txt`.
4. Run canvas-semantic/native-present Stage-0 proof, actual-argv query attacks,
   byte-exact Stage-1 install, exact offline cache/input proof, and three or more cold
   pinned-network samples. A deferred shard requested before the first trusted
   semantic interaction becomes critical and invalidates its manifest classification.
5. Against the unchanged served bundle, run the navigation-clock 30-second skeptic
   and own-file paths, signed current Chrome and Edge rows, then the full 30-minute
   fresh-profile soak even if the launch-time budget is RED.
6. Regenerate factual compliance/milestone evidence and run the default technical
   preflight. Only after the owner ratifies the exact harness SHA may root register M8,
   write its result, regenerate the dashboard, and run post-receipt validation.

Any later build JS/data/wasm/split-manifest change invalidates affected M4–M7 evidence
and every M8 receipt. Any later public-shell/bundle change invalidates final browser
evidence and every M8 receipt. Any later harness change invalidates owner ratification
and the post-receipt result.

## External launch blockers

These cannot be manufactured by local automation and remain RED independently of
technical progress:

- owner-approved independent product/repository/domain/handle naming, logo posture,
  repository description, and a real public source URL;
- human ratification and detached signature over the exact commit, bundle, harness,
  source/demo/dashboard/methodology URLs, production-transport receipt, review date,
  and final-post hash;
- a recorded GPL-literate lawyer review of the repository and final post, including
  the unresolved OpenSubdiv custom-license compatibility/sufficiency decision;
- any required human-authored-history remediation and public AI-assistance disclosure;
- an owner-selected deployable host/package. Unmodified Cloudflare Pages is not a
  valid current target because its 25 MiB per-static-file limit conflicts with the
  raw wasm/data tree and the local `.br` rewrite is not Pages-equivalent;
- an actual deployed-origin receipt proving canonical decoded bytes, compressed wire
  transport, COOP/COEP, isolated browser boot, and offline reload; and
- publication of the source, dashboard, methodology, demo, launch media/post, and
  community messages, followed by completion of every LAUNCH.md checkbox.

Source-preview publication is explicitly excluded from this run and is not counted as
a local technical failure. Public deployment and external posting are likewise outside
local mutation authority, while LAUNCH.md still requires their owner-supplied evidence
before a complete launch claim.

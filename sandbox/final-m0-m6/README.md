<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# Frozen technical closeout

`verify.py` is the final code-release integration gate for M0 through M8. It
re-runs the existing strict milestone verifiers against one immutable run-label,
requires the composite two-root technical source-freeze receipt (top-level
project plus its pinned `upstream/` component), discovers the deferred Wasm name
from the APPLY split inventory, rejects every unlisted matching filesystem
entry, and rechecks every referenced manifest, receipt, verifier, evidence file,
and build artifact after the live comparators finish.

The aggregate also exact-binds the current M8 staged composite receipt, raw
runtime and pinned-network performance proofs, runtime screenshot/license/log,
Chrome+Edge matrix, product proof, 30-minute soak, and compliance receipt. It
then invokes the frozen authoritative `verify_m8.py --post-receipt`, requires
the exact M8 result and byte-exact dashboard bindings, snapshots the newly
generated technical post-receipt preflight, and rechecks every M8 input after
that live verifier returns. Missing, extra, stale, deleted, or concurrently
mutated M8 evidence is therefore release-fatal.

The candidate also binds projected exact-tree inventories for both M8 evidence
roots and the complete staged deploy bundle. The launch-artifact projection
excludes only `current-m8-preflight.json`, because the authoritative verifier
must regenerate that file; its fresh bytes are separately validated and bound.
Every source-build and bundle artifact named by the staged receipt is explicitly
snapshotted before the subprocess, so pathless receipt rows cannot hide a
post-verifier mutation, deletion, symlink, or sibling/tree growth.

The final evidence labels are deliberately derived from one label:

- `<run>.m4`
- `<run>.m5-click`, `<run>.m5-canvas`, `<run>.m5-latency`
- `<run>.m6-workbench`, `<run>.m6-eevee`, `<run>.m6-cycles-smoke`,
  `<run>.m6-cycles-suite`, each accompanied by an exact file/tree digest

This prevents a closeout manifest from silently selecting historical receipts.
The candidate manifest itself must be a non-symlink file inside the repository.
Its composite source-freeze receipt is an exact absolute external file reference
(the freeze output is required to live outside both repositories). Other file
references use strict `{path,bytes,sha256}` repository-relative records; M6
evidence trees use `{path,files,sha256}`.

Fresh closeout evidence is written under the dedicated ignored prefixes listed
in `.gitignore` (including `sandbox/final-m0-m6/evidence/`). The source freeze
captures and later revalidates every non-ignored project source byte; ignored
evidence paths may be created after the freeze and are instead independently
hash-bound here. Existing tracked historical evidence is never overwritten.

The harness-owned `ledger/results/{m0,m1,m2b,m3,m4,m5,m6,m7,m8}.json` files,
the generated `reports/dashboard.md`, and the two exact tracked headed-browser
outputs `sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png{,.license}`
are the complete post-freeze volatile allowlist. Their exact post-run bytes are
mandatory file references in the aggregate candidate and are rechecked after
every live comparator. Fresh run-label evidence under the ignored M0–M8
evidence roots is independently bound as files or complete trees. Every other
non-ignored project path—including adjacent files in those sandboxes—remains
byte-exact to the freeze.

The explicit freeze-critical inventory includes the M3 producer/verifier and
all three WebGPU device-limit creation paths: worker preinitialization, browser
GHOST fallback, and native GHOST. The aggregate independently requires those
project/upstream coverage identities, so a self-consistent receipt that omits
one of them is still release-fatal.

The upstream inventory also names the complete bounded M3 implementation
surface: WebGPU context/framebuffer/texture/shader/cache/compiler/interface
sources; shader registration and GPU tests; draw debug compaction and its
supplemental test; curves resource/compute changes; subdiv evaluation; and the
Metal-only fullscreen scope marker. Omission negatives cover each fix class.
The exact 197-test and 1,003-static-shader identity manifests and Dawn build
recipe are explicit project-root critical inputs as well; the aggregate rejects
their omission independently of a self-consistent freeze coverage count.

The same explicit coverage includes the OpenSubdiv Wasm harvest recipe and
configuration plus upstream CMake/evaluator selection sources. M3 separately
binds the harvested header/archives and their member, symbol, no-OpenGL, and
functional Far+GLSL smoke proofs because generated dependency binaries are not
substitutes for source-freeze coverage.

The Cycles physical-F12 smoke is bound as both its selected manifest and the
complete `cycles-windowed/evidence` tree, so generated render, comparator,
console, screenshot, and license siblings cannot change after the live M6
comparator returns.

M7 is not accepted from its ledger text alone. The aggregate binds the exact
generated file-browser receipt and bundle identity plus the complete fallback,
browser-USD, and native-USD trees selected by `$FINAL_RUN_LABEL`; it then reruns
the strict M7 verifier with `--release-label` before M8. Any evidence mutation,
tree growth, cross-attempt USD pair, or label rebind is therefore red.

Run `verify_m8.py --post-receipt` once before composition if a diagnostic
preflight is desired, but that earlier output is not trusted. The aggregate
always runs the authoritative post-receipt verifier again and binds the fresh
preflight hash in `verification.json`.

After the final source freeze, fresh milestone evidence, harness receipts, and
byte-exact dashboard regeneration, compose and verify the immutable aggregate:

```sh
python3 sandbox/final-m0-m6/compose.py \
  --run-label "$FINAL_RUN_LABEL" \
  --source-freeze "$FINAL_SOURCE_FREEZE/receipt.json" \
  --m0-m3-manifest "sandbox/final-m0-m3/evidence/$FINAL_RUN_LABEL/final-m0-m3.json"
```

The composer requires a `final-` run label, derives every M4–M6 evidence label,
discovers the deferred Wasm name from the exact split inventory, binds the exact
fixed-path M8 evidence set, refuses any existing output directory, writes one
candidate in a private staging directory, invokes `verify.py`, and emits
`verification.json` only after the full aggregate returns PASS. The verifier
returns the candidate byte count/SHA-256 and a complete file/tree verification
closure. The composer rechecks that closure immediately before atomically
renaming the exact five-file output tree to the final selector; PASS stdout
cannot authorize publication after candidate or input mutation.

Run the browser-free contract checks with:

```sh
python3 sandbox/final-m0-m6/selfcheck.py
```

The gate intentionally remains RED until the milestone verifiers accept fresh
receipts. It never relinks a product binary, launches a browser, edits a harness,
or creates evidence on behalf of a test run.

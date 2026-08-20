<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Strict M0–M3 closeout verifier

`verify.py` is an external, read-only gate for the literal `GOAL.md` M0–M3
contracts. It is deliberately stricter than the current milestone harness. It
does not edit `harness/`, run a build, manufacture a receipt, or accept a
threshold merely because an older harness receipt is green.

Run it only after the canonical source freeze and the final M0–M3 evidence run.
The production entry point is `compose.py`; it copies the exact upstream freeze
component into the ignored evidence tree, builds the manifest, invokes this
verifier, and publishes only a verified immutable candidate:

```sh
python3 sandbox/final-m0-m3/compose.py \
  --run-label "$FINAL_RUN_LABEL" \
  --release-freeze /Users/paws/blender-web-final-source-freeze/receipt.json \
  --m0 "sandbox/final-m0-m3/evidence/$FINAL_RUN_LABEL/m0/receipt.json" \
  --m1 "sandbox/final-m0-m3/evidence/$FINAL_RUN_LABEL/m1/receipt.json" \
  --m2 "sandbox/final-m0-m3/evidence/$FINAL_RUN_LABEL/m2/receipt.json" \
  --m2-deps "sandbox/final-m0-m3/evidence/$FINAL_RUN_LABEL/m2-deps/receipt.json" \
  --m3 "sandbox/final-m0-m3/evidence/$FINAL_RUN_LABEL/m3/receipt.json"
```

Only after that strict candidate is green, regenerate the M1, M2b, and M3
harness ledgers from its current receipt graph. These scopes are read-only
adapters: they rerun the complete strict verifier and never launch a historical
test driver or overwrite tracked tier-b output.

```sh
export FINAL_M0_M3_MANIFEST="sandbox/final-m0-m3/evidence/$FINAL_RUN_LABEL/final-m0-m3.json"
bash harness/run.sh --scope m1
bash harness/run.sh --scope m2b
bash harness/run.sh --scope m3
```

Missing environment variables, a noncanonical selector, stale/tampered receipt
bytes, a mismatched run label, a red strict verifier, or receipt-hash drift all
produce an honest red ledger. The adapter contract is tested with:

```sh
python3 sandbox/final-m0-m3/strict_final_adapter_selfcheck.py
```

The container deliberately pins Ubuntu's `openimageio-tools` 2.4.17.0. The
host-side M4/M6 comparator is separately pinned to 3.1.16.0 in its own receipts;
the two identities are not interchangeable.

The candidate manifest and every referenced receipt must be newer than the
source freeze and no more than 24 hours old. Every receipt must carry the exact
candidate `run_label` and source-freeze SHA-256. Changing a label without
changing and rebinding the receipt is rejected. Paths are root-relative, cannot
escape through `..` or symlinks, and use this exact file-reference shape:

```json
{"path": "evidence/file.json", "bytes": 123, "sha256": "<64 lowercase hex>"}
```

Unknown, missing, and duplicate fields/keys fail. There is no permissive
forward-compatible mode; a schema change requires a reviewed verifier change.

## Enforced contracts

- M0: the exact Blender/emsdk/emcc/oracle pins; the required container, wrapper,
  CI, cache, build wrapper, serialized Ninja wrapper, configuration, ledger,
  and REUSE artifacts; a
  digest-pinned container execution proof; both CI caches; pinned actions; and
  zero REUSE violations. Before creating the receipt, the producer hermetically
  proves that nested final evidence—including extensionless transaction markers
  and captured stdout/stderr—is CC0-covered while an unannotated third-party
  browser-cache binary still makes REUSE fail closed.
- Source freeze: the canonical patch, live and replay manifests, byte-exact
  replay checks, exact current upstream path/byte inventory, pristine pinned
  `HEAD`, and an exact current pin file.
- M1: exact current JS/Wasm/result identities; the complete enumerated blenlib
  suite (never fewer than 1,667 tests) and complete bmesh-core suite with zero
  failed and zero crashed; byte-bound native/Wasm test-name manifest equality;
  hash-bound native executables and CMake caches; Release native/Wasm builds
  with `WITH_GMP=OFF`, `WITH_TESTS_SINGLE_BINARY=ON`, and the explicit
  `WITH_TESTS_BMESH_CORE_PARITY=ON` dedicated exact one-test bmesh target;
  recorded and independently repeated exact
  `../scripts/ninja-locked.sh -n` no-work attestations for all four native/Wasm
  BLI and bmesh outputs;
  the exact non-symlink `oracle/bpy.sh` native wrapper, exact non-symlink Node
  22.16.0 executable/version, and canonical
  `build-wasm-m1-parity/bin/blender.{js,wasm}` runtime; plus a separately raw-
  bound and independently repeated
  `../scripts/ninja-locked.sh -n blender` no-work attestation for that complete
  Blender runtime's CMake cache and Ninja graph;
  exact 9/9 main-corpus state equality; and exact versioning counters
  of 12 total, 10 pass, 2 matching oracle refusals, 12 equal.
- M2: CPython 3.13.13 and `import bpy`; the installed-like, cache-pruned base
  scripts tree with the Cycles add-on at the shipping
  `scripts/addons_core/cycles` path; byte-copied, source/staged-inventoried
  `release/datafiles` and bundled `assets`; the stage-0 locale `languages` index; a
  successful `CYCLES` engine assignment; the literal 75-suite keyset; current
  normalized logs; every row without an active, exact suite-scoped deferral
  passing with native/Wasm state equality. A formerly deferred row that now
  passes is accepted and must declare no deferral—the verifier never requires a
  failure. Raw combined logs remain hash-bound. Normalization removes only the
  one exact adjacent, version-pinned allocator/banner pair in each platform log;
  only the Wasm pair's immediately following exact locale startup warning is
  optional. A missing-Cycles startup notice is never normalized: it remains a
  release-input failure. The shared normalizer masks singular or plural
  `unittest` wall timing and only the exact numeric clock prefix on Blender CLG
  records, retaining the subsystem, severity, and complete message. The exact
  `bl_rna_accessors` row additionally removes one known warning for its invalid
  integer-4 denoiser default only when the hash-bound canonical runtime cache is
  exactly `WITH_OPENIMAGEDENOISE:BOOL=OFF`; missing, duplicate, or cross-suite
  occurrences fail or remain visible. The verifier replays
  that pipeline from every raw log and requires byte-for-byte equality, so
  `FAILED`, `AssertionError`, tracebacks, unknown warnings, malformed log clocks,
  moved/duplicated
  envelope lines, unknown build hashes, and near matches remain visible or make
  the receipt fail. Wasm denoising accepts only complete, end-anchored known
  exception terminators; a known prefix with any additional failure text is not
  removed. The `blendfile_io`, `bl_animation_action`, and `blendfile_liblink`
  suites additionally canonicalize only their exact runner-owned absolute
  per-platform scratch roots to `<SUITE_SCRATCH>`: exactly six, one, and 33
  occurrences per side respectively. A missing/extra occurrence, a near-match
  path, or a raw log that already contains the reserved token is release-fatal.
  Four exact structured output classes are canonicalized without hiding unknown
  rows: the two fixed-cardinality keymap set inventories, the named physics
  START/PASSED/result records plus complete contiguous frame censuses, terminal
  GoogleTest millisecond fields, and no others. Three zero-exit rows remain
  honestly `PASS_WITH_DEFERRAL` because their normalized bytes are not equal:
  `bl_rna_paths` binds the exact macOS-versus-browser file-menu blocks to
  `os-shell-affordances`; `bl_animation_action` preserves the exact Wasm
  missing-ObjectData warning pair and its surrounding sequence under
  `wasm32-animation-action-objectdata`; and
  `blendfile_library_overrides` binds the exact, position-stable six-row
  native/Wasm local-ID correspondence delta within its anchored nine-line
  hierarchy-print phase under
  `wasm32-library-override-idname-allocation`. Each status, milestone, evidence,
  marker, line association, position, and cardinality is strict-verifier
  bound. That suite also canonicalizes exactly 66 occurrences of its one
  two-token ID-pointer flag set, accepting only one uniform ordering per raw
  log; mixed, missing, extra, or near-match sets remain visible or fail.
  Relocation, reassignment, a resolved/wrong ledger status, or any
  extra delta fails closed.
  Dependency artifacts must have a one-to-one inventory, current
  hashes, complete ledger metadata, an explicit compatibility boolean and
  license payload for every row, and a green REUSE-bound compliance proof.
  False compatibility rows remain honestly enumerated in
  `unresolved_external_policy`; that external legal-policy classification does
  not turn the local technical-package verdict red. Python, TBB, OpenEXR,
  OpenImageIO, OpenColorIO, and zlib are mandatory.
  The one non-generic active safety state is exactly
  `bl_node_structure_type_inference` → `wasm32-64bit-blend-collision` with
  status `detector-active`; its receipt row must preserve the registry's exact
  ID, status, and evidence, and both its raw and normalized Wasm logs must carry
  the full canonical ADR-004 collision-refusal marker emitted by `readfile.cc`.
  A generic nonzero exit is never sufficient. No other ID or suite may use
  that status. M1 and M2
  must bind byte-identical native-wrapper, Node, JavaScript, and Wasm runtime
  identities.
- M3: the current native test binary, source freeze, M0 toolchain receipt,
  shader cache, and raw evidence are digest-bound. The binary, CMake cache,
  and Ninja graph must be the canonical
  `build-native-gpu/bin/tests/blender_test`,
  `build-native-gpu/CMakeCache.txt`, and `build-native-gpu/build.ninja` files.
  Before any runtime test, the producer records the exact
  `../scripts/ninja-locked.sh -n blender_test` command in `build-native-gpu`,
  with exit zero, literal `ninja: no work to do.` stdout, and empty stderr; the
  verifier repeats that command and requires its bytes to match the receipt and
  both raw result bindings. M3 also binds and independently reparses the native
  GHOST context, browser GHOST fallback, and worker preinitialization sources.
  Each must request the exact same ten adapter-supported WebGPU resource/compute
  ceilings exactly once, including the sampled-texture and sampler pair. The
  canonical cache must enable OpenSubdiv and GPU draw tests. All 197
  `GPUWebGPUTest` tests must pass
  with zero fail/crash. Every primary test row binds its complete raw log; the
  verifier requires one exact RUN/OK pair for that identity, no fail/skip, and
  zero uncaptured WebGPU device errors or leaked-memory reports even when the
  process exits zero. RUN/OK recognition is full-line anchored, so suffixed or
  prefixed aliases cannot satisfy another identity. The raw primary list stdout
  and empty stderr are also bound and reparsed as one sole `GPUWebGPUTest.`
  suite, then compared to the checked-in, fully-qualified, sorted exact
  197-name manifest. The
  static shader census accounts for exactly 1,003
  names with no unexplained failures. The Metal-only `fullscreen_blit` identity
  is absent and the genuine `draw_debug_draw_compact` compute prepass is present;
  the verifier rejects any same-count manifest that does not prove this exact
  substitution. The only possible compiler exclusions are
  active `storage-texture-atomics` or `vertex-stage-rw-storage` registry rows,
  each explicitly scoped and marked non-shipping. Informal blacklist groups do
  not qualify. Cold and warm cache proofs must cover every compiled shader, and
  both complete raw invocations (including text before BEGIN and after END) must
  contain zero native uncaptured-device-error or leaked-memory markers.
  The receipt also binds the cache-marker implementation itself. In census
  mode it must suppress fixture-initialization markers until
  `BW_SHADER_CACHE_DIR` is nonempty and exactly equals
  `BW_SHADER_CACHE_CENSUS_DIR`; this prevents pre-census builtin misses from
  reserving identities and masking the real warm hits.
  A checked-in sorted 1,003-name static manifest is independently compared to
  both cold and warm raw identity sets; coherent same-count substitutions are
  rejected.

  A separate supplemental `DrawWebGPUTest` contract is exactly 2/2 PASS:
  `draw_curves_lib` and `draw_debug_lifetime_rebind`. The producer and verifier
  bind and independently reparse its exact list stdout, empty list stderr, and
  both per-test RUN/OK logs; missing/substituted identities, skipped/failed rows,
  or any uncaptured device error/leaked-memory report are fatal. This does not
  enable WebGPU for the
  generic all-backend `DRAW_TEST` macro.

  OpenSubdiv provenance is content-bound, not inferred from the CMake toggle.
  The receipt pins v3_7_0 and tarball MD5, the build recipe/configuration and
  upstream WebGPU evaluator sources, harvested header plus CPU/GPU archives,
  and the exact Emscripten archive tools. Raw member/defined/undefined-symbol
  proofs must show the GLSL patch-source object and symbol with no OpenGL object
  or API import. A Wasm Far+GLSL smoke must report level-1 vertex count 26 and
  both `OsdPatchParamIsRegular`/`OsdEvaluatePatchBasis` source markers.
  The verifier re-runs the bound `emar`/`emnm` commands and functional smoke
  and requires byte equality with the recorded proof logs. The producer records
  byte-identical pre/post snapshots of the binary, CMake cache, Ninja graph,
  both canonical manifests, marker/device-limit sources, and every OpenSubdiv
  source/header/archive/tool input, followed by a second exact no-work check.

  The exact frozen delta from the prior 196-name receipt is
  `GPUWebGPUTest.select_next_async_replay`. The earlier readback source already
  registered `texture_readback_owned_result` and
  `storage_buffer_readback_owned_result` (the two registrations retained in
  `patches/PREVIEW_SNAPSHOT.patch`); the frozen
  `upstream/source/blender/gpu/tests/readback_test.cc` adds the third test.
  Current exact enumeration is therefore 197, and a self-consistent stale
  196-name manifest is rejected.

## Why the real candidate is currently red

The verifier is intended for the final post-freeze evidence shape; historical
receipts are not silently adapted. At the time this verifier was added, these
required artifacts/fields did not yet exist:

- a final canonical source-freeze output directory and a top-level manifest
  binding every M0–M3 receipt to its receipt SHA-256;
- a digest-pinned, executed oracle-container receipt and a standalone REUSE
  proof in the strict M0 schema;
- fresh all-pass blenlib and bmesh-core raw results. The current M1 harness
  receipt is red/missing artifacts, and its historical 10-failure blenlib
  allowance does not satisfy this verifier's literal zero-failure contract;
- fresh 9-row main-corpus and 12-row versioning receipts containing both native
  and Wasm state identities and exact counters;
- a fresh 75-key M2 receipt with per-row raw and normalized native/Wasm log
  hashes, exact normalization-policy source bindings/replay, and exact
  active-deferral IDs;
- a one-to-one runtime dependency inventory plus a compliance proof bound to
  the exact `ledger/deps.json` and inventory hashes;
- a fresh M3 197-name manifest/result with 197/197 pass and zero crash. The
  existing 189 pass / 6 fail / 1 crash receipt is rejected;
- a named 1,003-shader manifest/result, scoped exclusion rows (if any), and
  cold/warm cache proofs bound to the frozen source and M0 toolchain receipt.

Those are evidence requirements, not hidden deferrals. Until they are produced
from the final bytes, a real invocation should remain red.

## Post-freeze execution DAG

Use one new lowercase label for the entire release attempt. All generated
M0–M3 output is confined to the explicitly ignored
`sandbox/final-m0-m3/evidence/<label>/` prefix. Never point a runner at tracked
historical evidence, ledgers, or the dashboard. Each runner refuses to
overwrite an existing attempt and leaves `INCOMPLETE` on failure.

First create the composite release freeze. The exact upstream pin is also
recorded in `oracle/PIN`:

```sh
export FINAL_RUN_LABEL="final-$(date -u +%Y%m%d-%H%M%S)"
python3 sandbox/final-source-freeze/freeze_release.py \
  --project /Users/paws/blender-web \
  --project-pin "$(git -C /Users/paws/blender-web rev-parse HEAD)" \
  --upstream /Users/paws/blender-web/upstream \
  --upstream-pin fbe6228777e7d9afefcd61a413844e790ae75db7 \
  --upstream-pin-file /Users/paws/blender-web/oracle/PIN \
  --output-dir /Users/paws/blender-web-final-source-freeze
export FREEZE_CHILD=/Users/paws/blender-web-final-source-freeze/upstream/receipt.json
```

After the freeze, run the light M0 and dependency inventory lanes in parallel.
The dependency spec is the freeze-bound technical input
`sandbox/final-m0-m3/m2_dependency_inventory.json`, never an external or
runtime-derived file. It has exact
schema `{"schema":1,"dependencies":{...}}`; its dependency keyset must equal
`ledger/deps.json` `wasm_built`, and each row must contain exactly
`runtime_linked` (boolean), `artifacts` (repository-relative file paths), and
`license_payloads` (nonempty repository-relative file paths).

```sh
python3 sandbox/final-m0-m3/run_m0.py \
  --run-label "$FINAL_RUN_LABEL" --freeze-receipt "$FREEZE_CHILD" &
M0_PID=$!
python3 sandbox/final-m0-m3/run_m2_deps.py \
  --run-label "$FINAL_RUN_LABEL" --freeze-receipt "$FREEZE_CHILD" &
DEPS_PID=$!
wait "$M0_PID"
wait "$DEPS_PID"
```

Build M1 in dedicated parity trees after the freeze. Do not reconfigure either
the immutable product tree or `build-native-gpu`: the M1 native oracle must
match the shipping Wasm feature surface (`WITH_GMP=OFF`). Keep the normal test
mode at `WITH_TESTS_SINGLE_BINARY=ON` so the complete BLI census is emitted as
`BLI_test`, and enable `WITH_TESTS_BMESH_CORE_PARITY=ON` to add a separate
one-source `bmesh_core_test` alongside the normal aggregated bmesh suite. The
technical parity option invokes Blender's existing per-source helper only for
`bmesh_core_test.cc`; it does not relabel or post-filter `blender_test`. The
runner hash-binds both executables, both CMake caches, both Ninja graphs, and
every parsed test-configuration fact. Before enumerating or executing tests it
also records an exact locked dry-run for each target; the independent verifier
repeats all four through `scripts/ninja-locked.sh` and accepts only exit zero,
empty stderr, and the literal `ninja: no work to do.` output. Renaming a
different binary, passing the monolithic `blender_test`, or presenting any
stale link is rejected.

The Wasm BLI target retains the platform `-sMALLOC=mimalloc` setting. The bmesh
dependency closure also pulls CPython's vendored mimalloc API, so its dedicated
target appends `-sMALLOC=dlmalloc`; Emscripten's proven last-setting semantics
make dlmalloc effective without changing Blender or other test targets. The
Ninja provenance check requires the exact `mimalloc,dlmalloc` sequence and
rejects a missing or reversed override.

That full dependency closure has a measured 20,445,328-byte static image with
the pinned Emscripten toolchain, above Emscripten's 16 MiB default. Only the
dedicated Wasm `bmesh_core_test` therefore sets `INITIAL_MEMORY=33554432`.
Memory growth remains enabled for later allocations. Provenance rejects a
missing, smaller, duplicate, legacy `TOTAL_MEMORY`, direct wasm-ld, or late
override; BLI, native parity executables, and the shipping product are unchanged.

```sh
cmake -S upstream -B build-native-m1-parity -G Ninja \
  -C upstream/build_files/cmake/config/blender_lite.cmake \
  -C upstream/build_files/cmake/config/blender_headless.cmake \
  -DLIBDIR="$PWD/lib/macos_arm64" \
  -DCMAKE_BUILD_TYPE=Release -DWITH_GTESTS=ON \
  -DWITH_GMP=OFF -DWITH_TESTS_SINGLE_BINARY=ON \
  -DWITH_TESTS_BMESH_CORE_PARITY=ON
harness/buildwrap.sh scripts/ninja-locked.sh -C build-native-m1-parity \
  BLI_test bmesh_core_test

scripts/build-hosttools.sh
cmake -S upstream -B build-wasm-m1-parity -G Ninja \
  -C patches/blender_web.cmake \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/tools/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake" \
  -DCMAKE_BUILD_TYPE=Release -DWITH_GMP=OFF \
  -DWITH_TESTS_SINGLE_BINARY=ON -DWITH_TESTS_BMESH_CORE_PARITY=ON
harness/buildwrap.sh scripts/ninja-locked.sh -C build-wasm-m1-parity \
  BLI_test bmesh_core_test blender

harness/buildwrap.sh scripts/ninja-locked.sh -C build-native-gpu blender_test
```

The BLI difference previously observed is fully explained by configuration:
the native `WITH_GMP=ON` build had 91 native-only tests—9
`boolean_polymesh`, 9 `boolean_trimesh`, 54 `delaunay_m`, 4
`fixed_width_int`, and 15 `mesh_intersect`—and zero Wasm-only tests. Therefore
the valid gate is an independently built native `WITH_GMP=OFF` oracle with an
exact manifest match, not an intersection filter and not an unplanned Wasm GMP
port. Blender also registers `stack.Peek` twice from distinct source files on
both platforms. The runner preserves that multiplicity as deterministic
`@occurrence=1`/`@occurrence=2` identities in both the list and raw-result
census; unequal multiplicity or malformed occurrence numbering fails.

Run the two large execution lanes serially. They share the Node/Wasm memory
budget; parallel execution adds failure ambiguity without reducing the critical
GPU path. Artifact arguments must name the dedicated frozen-source build
outputs, not historical receipts:

```sh
python3 sandbox/final-m0-m3/run_m1.py \
  --run-label "$FINAL_RUN_LABEL" --freeze-receipt "$FREEZE_CHILD" \
  --native-blenlib build-native-m1-parity/bin/tests/BLI_test \
  --wasm-blenlib-js build-wasm-m1-parity/bin/tests/BLI_test.js \
  --native-bmesh build-native-m1-parity/bin/tests/bmesh_core_test \
  --wasm-bmesh-js build-wasm-m1-parity/bin/tests/bmesh_core_test.js \
  --native-blender oracle/bpy.sh \
  --wasm-blender-js build-wasm-m1-parity/bin/blender.js

python3 sandbox/final-m0-m3/run_m2.py \
  --run-label "$FINAL_RUN_LABEL" --freeze-receipt "$FREEZE_CHILD" \
  --native-blender oracle/bpy.sh \
  --wasm-blender-js build-wasm-m1-parity/bin/blender.js
```

M3 depends on the newly produced M0 toolchain receipt and on a native GPU test
binary rebuilt with the named shader/cache instrumentation:

```sh
python3 sandbox/final-m0-m3/run_m3.py \
  --run-label "$FINAL_RUN_LABEL" --freeze-receipt "$FREEZE_CHILD" \
  --m0-receipt "sandbox/final-m0-m3/evidence/$FINAL_RUN_LABEL/m0/receipt.json" \
  --binary build-native-gpu/bin/tests/blender_test
```

Finally run the composer command at the top of this document. Its successful
output is
`sandbox/final-m0-m3/evidence/<label>/final-m0-m3.json`, which is the sole
M0–M3 input to `sandbox/final-m0-m6/compose.py`. M4 captures may run in
parallel with the non-browser M0 lane, but M4, M5, Workbench, EEVEE, and the
Cycles browser smoke must otherwise be serialized behind the single browser/GPU
lock. The background Cycles suite can overlap a browser-free comparator only
when memory headroom has been checked.

## Reuse, capacity, and current preflight blockers

Frozen shipping artifacts, goldens, corpus inputs, the native oracle, and build
trees may be reused as inputs only if their bytes are unchanged. Source freeze,
all raw M0–M3 receipts, M4 binding, all three M5 browser receipts, all four M6
evidence trees, and both composed manifests must be fresh for the final label.
Historical PASS summaries are never accepted as substitutes.

The latest capacity audit found approximately 33 GiB free. The project/upstream
freeze inventories cover about 0.29/0.37 GiB of files; allow 1.5–2.5 GiB peak
for freeze work and under 1 GiB for final evidence. Existing principal build
trees occupy about 3.3 GiB in aggregate. Budget 0.8–1.5 GiB for the native M1
parity tree, 1.5–2.5 GiB for the Wasm M1 parity tree, and up to 1 GiB transient
headroom for the M3 relink. Expected wall times on this host are 20–45 minutes
native, 60–150 minutes Wasm including the Node runtime link, and 5–15 minutes
for the incremental M3 refresh. Keep at least 10 GiB free before browser
evidence.

Before an expensive final run, resolve these fail-closed preflight items:

- execute the dedicated native/Wasm M1 builds above and prove exact BLI and
  one-test bmesh manifest equality;
- produce and boot the dedicated Node-loadable `blender.js`/`.wasm` pair;
- review and supply the exact dependency inventory specification with a license
  payload for every ledger dependency; OpenSubdiv remains explicitly listed as
  unresolved external policy, not silently relabeled;
- rebuild the M3 native GPU test binary with the current instrumentation and
  make the literal 197-test and 1,003-shader contracts green.

Run the hermetic positive/adversarial suite with:

```sh
python3 sandbox/final-m0-m3/runner_selfcheck.py
python3 sandbox/final-m0-m3/compose_selfcheck.py
python3 sandbox/final-m0-m3/selfcheck.py
python3 sandbox/final-m0-m3/strict_final_adapter_selfcheck.py
```

The self-check creates a temporary pinned Git tree and tests a valid candidate
plus digest tampering, stale time, unknown fields, missing suite keys,
un-deferred failure, nonzero M1/M3 failures, alternate labels, and unscoped
shader exclusions. It never reads build outputs or existing receipts.

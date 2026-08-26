# GPU r26 migration save point — native translation gate closed, Linux replay pending

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

Date: 2026-08-18. This is a stop-work record, not a new milestone claim. The checkout is
moving from macOS arm64 to WSL2 Linux x86-64 and none of the 19 GB of local build state is
authoritative or being transferred.

## Exact source boundary

The outer repository commit contains the port. `upstream/` is deliberately ignored and must be
cloned again at Blender `fbe6228777e7d9afefcd61a413844e790ae75db7`. Apply
`patches/PREVIEW_SNAPSHOT.patch` after cloning. Its SHA-256 at this save point is
`4e8233c5302d48b147ac01a07dbd90d6fb9e95301388e2a182896728aecfa2d0`; reverse-apply checking
against the source tree succeeded. This snapshot includes all 210 modified/untracked upstream
paths, including the complete `source/blender/gpu/webgpu/` backend. The numbered patch series is
useful history, but the preview snapshot is the exact reconstruction authority for the dirty
integration tree.

Other lanes' tracked outer-repository edits are preserved without taking ownership in
`patches/OUTER_WORKTREE_REMAINDER.patch`, SHA-256
`563dfe303d9e401c73938d733e118d3f0e21dbeec5e4216a3b43154031b8e4b1`. This replayable revision
removes private host metadata from the public carrier; apply it after checking out the
migration commit, as described in the migration runbook.

`lib/`, `build-dawn/`, `build-native-gpu/`, and every `build-wasm-*` tree are generated state.
They are not source and are now ignored. Recreate them from the pins and recipes in
`notes/migration-to-ornith-lab.md`.

## Proven on the final macOS build

- Dawn/Tint pin: `36cf1fae0cd8a81a4fb4580751648b80b2e6255c`. The deployment-corrected native
  archive used macOS minimum 11.2; `libwebgpu_dawn.a` SHA-256 began `1f74b0ef`.
- Canonical native test binary:
  `build-native-gpu/bin/tests/blender_test`, SHA-256
  `341b9eb1954c3638e38ff69c5a622fe362cf0c26e84a258afd134e00ebb303c6`.
- Primary WebGPU suite: exactly 197/197 PASS. The checked-in sorted identity set is
  `sandbox/final-m0-m3/gpu_webgpu_tests.txt`, 9,725 bytes, SHA-256
  `fc273708e5d005985fb31c887535c68faca9a22358bdb4d52afdf5bf518f2f93`.
- Supplemental production Draw tests: exactly
  `DrawWebGPUTest.draw_curves_lib` and
  `DrawWebGPUTest.draw_debug_lifetime_rebind`, both PASS.
- Static shader gate: exactly 1,003/1,003 PASS. Cold cache is 1,003 MISS and 1,003 files;
  warm cache is 1,003 HIT and zero MISS. The sorted identity set is
  `sandbox/final-m0-m3/static_shader_identities.txt`, SHA-256
  `30f03de2de606d0ec858e66a0f53efc3148d70b526ec00f59a34764c1afe2989`.
- The honest identity substitution is frozen: Metal-only `fullscreen_blit` is absent and the
  real WebGPU `draw_debug_draw_compact` compute shader is present. This keeps 1,003 without
  count padding.
- OpenSubdiv WebGPU uses the harvested GLSL patch-basis source. The Wasm `libosdGPU.a` is a real
  200,032-byte archive (not the former empty 8-byte archive), contains a defined
  `GetPatchBasisShaderSource` symbol, has no OpenGL imports, and returned a 71,777-byte GLSL
  source containing both required basis markers.
- The device-creation contract binds the same ten adapter-supported limits in native GHOST,
  browser fallback, and `wgpu-preinit-worker.js`.
- Latest proof-only suites before the stop were green: runner 22 positive / 111 negative,
  final M0-M3 verifier 2 positive / 138 negative, source/release freeze, aggregate M0-M6,
  strict adapter, compose, REUSE 6062/6062, syntax and scoped diff checks.
- Final native no-work evidence was exact for `blender_test` and `bf_io_usd`; the last cited
  log is `ledger/buildlogs/20260818T023820.log` with content hash
  `b93ec9603a52c490501b19be5cb1effeb9f3904ac2d92fb01ae5ac8675512a04`.

The useful runtime logs named during closeout are:

- `20260818T020805.log`: crash-isolated 197/197.
- `20260818T020624.log`: DrawWebGPU 2/2 plus the pooled-F16 NaN-preservation test.
- `20260818T020947.log` and `20260818T021002.log`: pre-reporter-fix cold/warm diagnosis.
- `/tmp/blender-web-m3-final-cache.JILO0Y`: final exact cold/warm result. This directory is
  not transferred; the checked-in identities and proof contracts are the durable part.

## What was falsified

- Count-only acceptance is invalid. A coherent 197-name or 1,003-name substitution must fail;
  checked-in exact manifests now close that gap.
- Substring checks for GTest RUN/OK lines are invalid because an identity suffix can alias an
  expected name; primary and supplemental parsers now require full lines.
- The old 1,003 set was not semantically correct: `fullscreen_blit` is Metal-only. It was not
  made WebGPU just to preserve a number.
- Render-pass color clear does not default to NaN in the pinned Dawn C++ wrapper. The actual
  NaN defect came from `DRW_gpu_wrapper::debug_clear()` sending non-finite values into UNORM
  render clears. The backend now uses render clear only for finite values, preserves NaNs for
  floating formats through the upload path, and maps non-representable normalized clears to a
  finite sentinel. The pooled F16 test reads back and proves NaN preservation.
- The 14 apparent warm-cache misses were reporting pollution from GPU fixture startup, not
  missing cache bytes. Reporting now begins only when the active cache directory equals the
  census directory.
- OpenSubdiv could not be enabled in Wasm by source selection alone: its old Wasm GPU archive
  lacked GLSL patch-basis source, the WebGPU define was absent in the OSD target, and a
  backend-agnostic static cache could retain the wrong source across backend reinitialization.
- Simply raising WebGPU limits does not solve the original 18-sampler Metal argument-buffer
  case. The actual WebGPU runtime and static fixes avoid unsupported resource shapes.

## Current red boundaries

- No final M3 or release receipt was produced after these source changes. A new source freeze
  is required on Linux.
- Native proof was on Dawn/Metal. Linux must rebuild the same Dawn commit with Vulkan and rerun
  the exact identity gates; parity is expected, not presumed.
- M2 work was stopped mid-closeout after an exact blendfile-library override canonicalizer
  rewrite. Commit `484219d` is syntactically valid but the final bijection changes did not get
  their full selfcheck run. The last M2 attempt is `INCOMPLETE`; it is not a release input.
- The accepted M4 PASS is historical and immutable. The current `ledger/results/m4.json` is RED
  because later Wasm artifacts differ from that binding. Rebuild and capture a new label.

## Next round attacks, in order

1. Reconstruct the exact source from the preview snapshot and prove its hash before compiling.
2. Port `sandbox/dawn-probe` from its forced Metal options to Linux Vulkan without changing the
   Dawn commit or Tint options. Run the probe on the RTX 4090 and record adapter/backend facts.
3. Build `build-native-gpu`, require exact Ninja no-work, exact 197 identity equality, 197/197,
   DrawWebGPU 2/2, then exact 1,003 cold MISS/files and warm HIT with zero device errors.
4. Attack Linux-only translation deltas: Vulkan adapter limits, resource visibility, depth and
   stencil aspects, shader-cache byte stability, OpenSubdiv source selection, and asynchronous
   validation errors outside the census boundaries. Do not rebaseline either identity manifest
   without a named source-level reason.
5. Rebuild the windowed Wasm product, install the pinned Playwright browser locally, and create a
   new immutable M4 binding. Keep the old 0.204%/0.505% PASS as history, not current evidence.

## Linux follow-up: M2 verifier self-check closed (2026-08-20)

The specific verifier-validation gap recorded above for commit `484219d` is closed. The exact
six-ID `blendfile_library_overrides` bijection implementation passed all four hermetic
positive/adversarial programs under the rebuilt native CPython 3.13.13 host tool:

- `runner_selfcheck.py`: `ledger/buildlogs/20260820T050442.log`
- `compose_selfcheck.py`: `ledger/buildlogs/20260820T050443.log`
- `selfcheck.py`: `ledger/buildlogs/20260820T050405.log`
- `strict_final_adapter_selfcheck.py`: `ledger/buildlogs/20260820T050444.log`

This validates the producer/verifier contract and its tamper controls. It does not promote the
historical interrupted candidate to a release input: `m2b` still requires a fresh strict Linux
runtime receipt, and its harness result remains RED until that evidence exists.

Repository-wide REUSE 3.3 compliance is green at 1,893/1,893 files
(`ledger/buildlogs/20260820T050626.log`). The required `harness/run.sh --scope m2b` and
`--regress` checks were also run; at `2026-08-20T05:06:39Z` they remain honestly RED for the
missing fresh strict-final receipts and the already-recorded M4/M5/M6 artifact/hardware gates.
No receipt, pass flag, deferral status, or promise was changed.

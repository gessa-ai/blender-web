<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M1 wasm floating-point exception deferral closure - 2026-08-24

## Outcome

The `wasm-fp-exception-status` limitation is resolved for Blender's expression evaluator. WebAssembly
still has no floating-point exception status register, but the current canonical source no longer
relies on that register under Emscripten. `BLI_expr_pylike_eval` accumulates explicit
divide-by-zero and invalid-operation status through constant folding and runtime evaluation and
returns the same public status classes as the native evaluator.

No shipping source changed in this reconciliation. The source fix and its regression cases were
already present in the canonical postimage, while the original patch-0004 note, `fix_plan.md`, and
`ledger/deferred.json` still described the initial compile-only state. This unit corrects that
stale accounting and retains the ledger entry as resolved audit history.

## Current contract

The canonical implementation in
`upstream/source/blender/blenlib/intern/expr_pylike_eval.cc` keeps hardware fenv checks on native
platforms and uses a software accumulator on Emscripten. Its operation-specific checks distinguish
true poles and invalid operations from ordinary overflow, cover composite `log`, `lerp`, and
`smoothstep` primitives, preserve quiet-NaN propagation, and detect signaling-NaN input across
ordinary, reduction, comparison, and control-flow opcodes. The portable `fmod` check also closes a
native libm inconsistency without weakening any native result.

The regression cases in
`upstream/source/blender/blenlib/tests/BLI_expr_pylike_eval_test.cc` bind those distinctions:
overflow remains successful, domain errors fail, independent invalid subexpressions are not hidden
by a quiet NaN, signaling NaNs fail on wasm, and non-evaluated short-circuit branches remain clean.
The initial `patches/0004-blenlib-wasm-libc-gaps.patch` remains historical development evidence;
its macro-only fallback is not the complete current implementation.

## Fresh Linux evidence

Both parity targets rebuilt through `scripts/ninja-locked.sh`. The focused native and pinned-Node
wasm runs each pass 144/144 `expr_pylike` cases with zero disabled cases or errors
(`20260824T113128-4106334` and `20260824T113128-4106332`). Complete native and wasm BLI runs each
pass 1,667/1,667, and their ordered test identity/outcome rows are equal
(`20260824T113152-4106507` and `20260824T113153-4106506`).

The canonical freezer then reproduced all 20,258 source entries byte-for-byte. Its receipt is
`sandbox/final-m0-m3/evidence/m1-fenv-closure-ornith-linux-20260824-r2/freeze/receipt.json`,
SHA-256 `551e821a988e9031c69909745f710e2d99f77dca67abf8b0fe14a9cc224907e0`; the replayed source patch
is SHA-256 `cd3eea4e7050f4b19dfcbbb41965d267fd7404946fe0c096c335afc4e0b5eb75`, and both manifests are
SHA-256 `89796b9d8e1d8fc8be0c2e602df5edbd7b5aa02b8c7364baee7152636c0f88ae`
(`20260824T113413-4108577`).

The sealed component producer ran through the digest-pinned, network-disabled Linux oracle and
passed BLI 1,667/1,667, bmesh-core 1/1, main corpus 9/9 exact, and versioning 12/12 exact. Receipt
`sandbox/final-m0-m3/evidence/m1-fenv-closure-ornith-linux-20260824-r3/m1/receipt.json` is SHA-256
`7fc88414e46a6459fd84f17a1a766084f33b80418f52cdbd983229e4383ad9ea`
(`20260824T113519-4109542`). Its native and wasm BLI key-set SHA-256 values are both
`f357896e79de578f2e431b0247b3c6626c17ee1fea91e15aaf7dff88df71e038`.

The first full attempt correctly failed before sealing because the default `oracle/bpy.sh` path
identified the absent retired macOS oracle. The successful run used
`scripts/oracle-container.sh with-env`, the documented ornith-lab route; the failed attempt remains
an incomplete non-receipt.

## Boundary

This closes one stale M1 deferral and changes no harness expectation, result flag, product, source
freeze, dependency decision, tolerance, golden, blacklist, or milestone promise. Required M1
remains red only because its unchanged strict adapter requires a complete fresh M0-M3 candidate,
which cannot be composed inside this WSL instance without the separately recorded conformant
hardware WebGPU receipt. No dzn, browser, adapter, GPU, pixel, profile, or split-product path was
used.

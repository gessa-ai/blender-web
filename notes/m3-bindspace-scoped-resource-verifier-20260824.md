<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3 bind-space scoped-resource verifier repair - 2026-08-24

## Outcome

The device-free bind-space parity driver again extracts and executes the current shipping sampler
and dummy-vertex policies. Patch 0231 moved sampler creation behind `ScopedHandleCache`, and patch
0232 moved dummy-buffer initialization into `dummy_vertex_buffer_create()` with
`mappedAtCreation`. The older extractor still required both retired direct-creation bodies, so the
current suite stopped before compiling any native/Wasm evidence.

Commit `72616c2` binds sampler extraction to the exact scoped-cache call and derives dummy-buffer
initialization from `wgpu_common.hh` while separately requiring the context's scoped-cache call.
The fake WebGPU buffer now models mapped-at-creation access and unmapping, so the extracted helper
runs its actual `{0, 0, 0, 1}` initialization path instead of the retired queue-write path.

## Evidence

- The unchanged verifier rejects the current source before evidence allocation at
  `20260824T120941-2214`; after the sampler boundary alone is repaired, its stale dummy mutation is
  exposed at `20260824T121117-3790`.
- Final pre-commit repository-root and descendant-CWD runs pass seven zero-allocation mutations and
  six byte-identical native/Wasm contracts at 470 bytes, SHA-256 `b5af51dfd967`. The generated
  sampler and dummy-helper SHA-256 values begin `cb26a0afc8ee` and `048b9078e7de`
  (`20260824T121347-5527`, `20260824T121401-5820`, `20260824T121430-6812`,
  `20260824T121434-6795`).
- Post-commit self-check and parity runs remain green at `20260824T121625-9830` and
  `20260824T121629-10096`. The exact native and Wasm result covers default state, texture/image
  bind spaces, sampler descriptors, fence behavior, and one mapped/unmapped dummy-buffer creation
  reused by the second request.
- The canonical source replay retains 225 active patches across 261 paths at patch SHA-256
  `cd3eea4e7050`. The real `blender_browser` graph is locked no-work and OFF preflight binds the
  unchanged 657,928-byte JS, 118,909,416-byte Wasm, and 167,143,248-byte data product
  (`20260824T121636-10409`).

## Boundary

This repairs device-free test coverage only. It changes no shipping GPU/GHOST source, patch,
adapter, browser profile, product mode, receipt verdict, deferral, tolerance, golden, blacklist, or
promise. Required M3 remains red until a conformant hardware adapter can produce its strict live
receipt. The named blocker remains `no conformant hardware Vulkan ICD in WSL2 (NVIDIA ships none;
Mesa dzn rejected by Dawn)`; dzn and Windows were not retried, and WSL was not restarted.

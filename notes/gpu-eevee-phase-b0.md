<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# EEVEE shadow Phase B0 read-only tile-map declaration

Date: 2026-08-09

Status: applied after patches 0138, 0143, and 0144. Locked native and shipping wasm builds
completed. Static and targeted compiler acceptance passed: the tag-update read-write failure is
gone. Full shadow pixel acceptance remains open on the independent Phase B1 image-atomic blocker.

## Root cause

`eevee_shadow_tag_update` uses the generic `TileMaps` resource table from
`eevee_shadow_page_ops.bsl.hh`. That table declares binding 8 as read-write because later compute
page operations modify it. The tag-update graphics pipeline only reads that binding in both vertex
and fragment stages. Reusing the generic declaration therefore emits a vertex-stage read-write
storage binding even though the vertex algorithm performs no write or atomic operation.

The WebGPU bind-group-layout visibility repair cannot legalize a shader declaration that still
requires read-write storage in the vertex stage. The correct repair is at the declaration site.

## Patch 0146

`patches/0146-gpu-eevee-shadow-tag-readonly.patch` changes only
`eevee_shadow_tag_update.bsl.hh`. It adds a local slot-8 `TileMapsRead` table with a read-only array
and uses that table for `tag_update_vert` and `tag_update_frag`.

The compute `tag_propagate` entry point continues to use the generic read-write `TileMaps` table.
The fragment `Tiles` table and its `atomicOr` are unchanged. Resource slots, data layout, indexing,
and shadow behavior are unchanged.

## Boundaries

This is Phase B0 only. It does not begin Phase B1 and does not alter the distinct
`MADefault_Surface_shadow_mesh` `OpImageTexelPointer` storage-texture atomic failure. It does not
disable shadows, demote a genuinely writable resource, change backend policy, or touch build,
harness, oracle, golden, threshold, deferral, ledger, results, dashboard, series, or readback code.

No native build, wasm build, or browser run is part of the frozen preparation. Those acceptance
gates must wait for the dependency order `0138 -> 0143-A -> 0144`, then run from a stable committed
source and shipping binary as specified in `sandbox/gpu-eevee-phase-b0/probe-plan.md`.

## Static verification

- Patch 0146 forward-applies cleanly against baseline
  `5631379defb51b4beb92e284edaba655400f4803` without modifying the live source.
- An isolated forward, reverse, and forward replay reproduces the baseline and patched source
  hashes exactly.
- The patch contains one source path and changes only the two graphics entry-point table types plus
  the local read-only declaration.
- At freeze time, the live source remained unapplied and no build was run.
- The owned artifacts contain no authored U+2014 character.

## Live stacked evidence, 2026-08-10

Patch 0146 is applied after 0144 in the live source. It still names exactly one source path and
reports 6 insertions and 2 deletions. Its SHA-256 remains
`986f95b9d3645c4fffc1cfc65e1d0b7fcce09ca7ef7605b991e2e54ba4613899`. A disposable-copy replay
reversed `0146` then `0144`, applied `0144` then `0146` with
`--whitespace=error-all`, and reproduced all 13 stacked source hashes exactly.

The locked native build regenerated the tag-update shader and reached the final `blender_test`
link. The locked shipping wasm build regenerated the same shader and reached the final
`blender_browser.js` link. The unchanged census measured 164 PASS / 7 FAIL / 2 CRASH / 173 and
static shaders 971 / 987. Relative to the 0144-only receipt, 0146 raises static coverage by exactly
one shader, from 970 to 971, without changing the test census.

The targeted `principled_bsdf_default` browser run reached `OK BLENDER_EEVEE`, did not crash or
become unresponsive, and recorded zero Dawn validation errors. The
`eevee_shadow_tag_update` vertex read-write compiler failure present in the 0144-only console is
absent. The only retained shadow compiler failure in this targeted run is the independent
`MADefault_Surface_shadow_mesh` `OpImageTexelPointer` path owned by Phase B1.

This is not a shadow pixel pass. The run recorded zero readback kicks, zero completions, and no
device-byte capture, and its 128 by 128 render-operator PNG is constant black. The deferred probe
plan still requires a shadowed scene, at least two frames, a caster or light mutation, and an
unchanged-golden comparison after Phase B1 permits the render to reach Film readback.

Exact logs, manifests, image hashes, source hashes, and artifact hashes are recorded in
`sandbox/gpu-eevee-phase-b0/0146-final-receipt.txt` and
`sandbox/gpu-eevee-phase-b0/0146-final-integrity.txt`.

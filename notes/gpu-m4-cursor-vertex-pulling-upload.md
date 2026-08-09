<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: GPL-2.0-or-later -->

# M4 cursor vertex pulling upload and binding chronology

## Premise correction

The selected-cube artifact is the 3D cursor draw, not triangle-fan expansion. The
origin capture shows a small white L in place of Blender's red and white cursor,
the moved-cursor capture expands into viewport-scale white spikes, and the same
workspace with `show_cursor = false` has no artifact. All three accepted controls
completed with zero WebGPU validation errors.

Temporary runtime instrumentation then identified the direct draw shader as
`gpu_shader_3D_polyline_flat_color`. The circle VBO has 13 vertices and the line
VBO has 24 vertices. Both use the expected 24-byte interleaved layout with position
at offset 0 and color at offset 12. The decisive log is
`sandbox/gpu-m4-cursor-upload/cursor_diag3_runtime.log`.

For each cursor draw, the bind-group builder emitted stale `StorageBuf` entries at
dense bindings 0 and 1 before the correct position and color VBO entries at those
same bindings. `create_bind_group_checked` retained the first duplicate, so the
polyline shader read unrelated storage bytes as vertex data. This explains both
the finite origin artifact and the large moved-cursor spikes.

## Patch 0135: upload before vertex pulling

`WGPUVertexBuffer::bind_as_ssbo` and `bind_as_texture` now acquire the active
context before any upload work, soft-return if no context exists, and call
`upload_data()` on every bind. This covers both first use and later host-side DIRTY
updates while preserving DEVICE_ONLY allocation behavior. Acquiring the context
first also leaves DIRTY data available for a later retry instead of dereferencing
a missing active context during `update_sub`.

Patch 0135 is necessary upload correctness, but the origin and moved controls prove
that upload alone does not repair the visible cursor.

## Patch 0137: native chronological storage binding

The context now records one monotonic serial across `StorageBuf`, VBO/IBO storage,
and buffer-texture binds. Buffer records are tagged as either `Storage` or
`Sampler`, so equal raw slot numbers remain distinct frontend namespaces and remap
through the correct shader interface map.

Within each mapped or fallback pass, valid storage candidates are reduced by dense
binding and only the newest serial is emitted. The existing mapped-first policy is
preserved: a mapped candidate claims its binding before identity fallbacks are
considered. This gives native last-bind-wins behavior without assigning permanent
priority to geometry buffers.

Same-slot storage rebinding also erases the displaced record across the
`StorageBuf` and VBO/IBO maps. Unbinding or destroying the newer object therefore
cannot resurrect an older raw-slot binding. Sampler-tagged buffer records remain
independent, and two differently typed raw slots can coexist when shader remapping
places them at different dense bindings.

## Evidence and verification status

Accepted pre-fix controls:

- `sandbox/gpu-m4-cursor-upload/cursor_origin_1280x720.png`
- `sandbox/gpu-m4-cursor-upload/cursor_moved_1280x720.png`
- `sandbox/gpu-m4-cursor-upload/cursor_hidden_1280x720.png`
- `sandbox/gpu-m4-cursor-upload/cursor_diag3_runtime.log`

Temporary `[BW-CURSOR-DIAG]` instrumentation was removed from production source.
Patches 0135 and 0137 pass reverse checks and an isolated reverse-then-forward
round trip restores the exact four production-source hashes.

Final verification after static WIP audit:

- locked native production build: PASS;
- temporary actual-WebGPU backend probes: 2/2 PASS, covering later VBO, reversed
  later StorageBuf, typed Sampler/Storage raw-slot coexistence, and DIRTY re-upload;
- temporary test hunks fully reverted and original test-source hashes restored;
- locked optimized shipping wasm build: PASS;
- fresh 75-second origin, moved `(3, 0, 0)`, and hidden controls: zero GPU errors,
  zero page errors, and stable shipping binary hashes across all three captures;
- origin and moved images show finite native cursor geometry with a red and white
  circle plus colored axes; the hidden control removes it;
- preliminary fresh splash is wedge-free and passes the unchanged comparator with
  4,069 pixels, 0.442 percent, over 0.016;
- M3 census remains the established 149 PASS / 7 FAIL / 2 CRASH of 158 plus
  `static_shaders` 956/973. The gate reports only the known human-owned I10
  un-defer candidate.

Selected receipts:

- `sandbox/gpu-m4-cursor-upload/0135-0137-final-receipt.txt`
- `sandbox/gpu-m4-cursor-upload/0135-0137-native-backend-probes.patch`
- `sandbox/gpu-m4-cursor-upload/0135-0137-native-backend-probes.log`
- `sandbox/gpu-m4-cursor-upload/cursor_origin_final_1280x720.png`
- `sandbox/gpu-m4-cursor-upload/cursor_moved_final_1280x720.png`
- `sandbox/gpu-m4-cursor-upload/cursor_hidden_final_1280x720.png`

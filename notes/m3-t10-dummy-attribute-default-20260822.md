<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T10 dummy-attribute default parity — 2026-08-22

## Outcome

Patch 0166 initializes WebGPU's shared zero-stride dummy vertex buffer to
`(0.0f, 0.0f, 0.0f, 1.0f)`. This matches the pinned Vulkan backend's missing-
attribute policy and restores the fourth component required by Blender's
generated-coordinate/orco path. The old WebGPU path relied on zero-initialized
buffer storage and therefore supplied `(0,0,0,0)`.

The correction is queue ordered: the buffer is created with `Vertex | CopyDst`,
then the one 16-byte write is submitted on the same context queue before any later
draw submission. The zero-stride binding from patch 0159 remains unchanged, so
all vertex and instance indices read this one initialized value.

## Experiment and contract

The integrated bind-space smoke now extracts the exact shipping
`WGPUContext::dummy_vertex_buffer` method and runs it against a device-free
create/write boundary in both native and wasm32. It proves one allocation, one
write, stable handle reuse, the exact usage/size, xyz zero bits, and
`w = 0x3f800000`. The expected bytes are independently bound to
`source/blender/gpu/vulkan/vk_device.cc`, whose pinned policy explicitly sets the
fourth float to one for missing orcos.

The first test-only extraction attempt rewrote its generated function name and
stopped at compile before reaching a product assertion
(`ledger/buildlogs/20260822T045749-1028148.log`). After that checker-only fix, the
unchanged canonical source failed exactly at `dummy vertex initialized once`
(`ledger/buildlogs/20260822T045815-1028510.log`).

Final native and Node 22.16.0 stdout are byte-identical at 463 bytes,
SHA-256 `7d817b7b39eddc8d89b7c91971d23b3f58c38bf4ace7599f6686fdc4c442117b`;
the extracted shipping method is bound at SHA-256
`69cf811791fb8266728b92994071c2edacd79e9761008144611e69e30acd1e24`
(`ledger/buildlogs/20260822T050118-1031317.log`). Malformed sampler and dummy-
vertex sources plus wrong Dawn, Node, and fmt identities all reject without
allocating evidence (`ledger/buildlogs/20260822T050503-1035672.log`).

## Integration evidence and boundary

- The final-source freezer reproduced 257 paths and 20,258 manifest entries. The
  canonical patch is 1,548,011 bytes at SHA-256
  `31832021c9d755a70e03c7f895ebc77793431fac192de1fde53f56fc43b4c4e5`;
  both manifests are SHA-256
  `a7af5d5008b634b86bc7eed7182ce78a919d3deb2fdcaa2da3a4e5190bbf3e7e`
  (`ledger/buildlogs/20260822T050036-1030758.log`). Canonical replay is green with
  143 active numbered patches (`ledger/buildlogs/20260822T050728-1038665.log`).
- The correct windowed `blender_browser` target recompiles `wgpu_context.cc`,
  links, and then reports exact locked no-work
  (`ledger/buildlogs/20260822T050234-1033413.log`,
  `ledger/buildlogs/20260822T050314-1033747.log`). An earlier invocation selected
  the intentional Node `blender` target and consequently exposed its NODERAWFS
  profile against the browser-only OPFS imports
  (`ledger/buildlogs/20260822T050147-1032855.log`); no source change resulted.
- Exact REUSE 6.2.0 is green for 2,040/2,040 files
  (`ledger/buildlogs/20260822T050728-1038666.log`).
- Required M3 remains red at `2026-08-22T05:05:43Z` only because there is no fresh
  strict candidate. Container-backed regression restores M0 to 6/6 green and
  leaves M1-M8 red at their existing receipt/APPLY/artifact/browser/run-label/
  hardware boundaries.

No real WebGPU instance, adapter, device, buffer, pipeline, draw, browser receipt,
result promotion, dependency decision, deferral, tolerance, golden, or blacklist
was created or changed. Live proof remains owned by `M3-LINUX-REPLAY` and blocked
by s7's software-only adapter.

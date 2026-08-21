<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M3.T6 integrated buffer Linux reconciliation — 2026-08-21

## Outcome

The canonical in-tree WebGPU common-buffer and readback-registry postimages now have a
checkout-relative, device-free native/Wasm parity contract. The native leg reuses pinned Dawn's
target graph; the Wasm leg uses emdawnwebgpu's matching C/C++ value types. Both compile the
shipping `wgpu_buffer`, `wgpu_common`, and `wgpu_readback` inputs directly instead of substituting
the earlier standalone T6.pre prototype. Before allocating evidence, the driver requires a clean
Dawn `36cf1fae` checkout, canonical clean-pin replay, host CMake 4.0.3, emcc 6.0.5, and Node
22.16.0.

Five contracts cover the evolved shipping behavior:

- eight alignment cases, the 64 KiB staging threshold, and both index formats;
- all 32 buffer-kind/usage/readability combinations, including Uniform+Storage and unconditional
  `CopyDst` for device-only buffers;
- fail-closed update/read behavior on an uncreated buffer;
- move construction, move assignment, and self-move lifetime through the real source-forgetting
  path;
- the real registry's invalid cache/exact readback lifecycle, including failed-ticket retirement
  and zero pending work.

Root and descendant runs are green at `20260821T201129-535621` and
`20260821T201308-540710`. Native and Node emit identical 348-byte evidence
(`sha256:270af15eff07`); the five canonical source/header inputs have combined identity
`sha256:a323ceb1ad84`. Both targets finish at locked-Ninja no-work. The wrong-Dawn control rejects
before evidence allocation (`20260821T201335-541152`). Canonical replay remains 257 paths at
`sha256:e03f140fe3f3`, shell/diff checks pass, and the existing windowed product is exact no-work
(`20260821T201414-541852/541854`). Final REUSE 6.2.0 is 1,960/1,960 green
(`20260821T201600-543678`).

## Boundary

The contract creates no Dawn instance, adapter, device, live GPU buffer, or M3 receipt. It does
not replace the historical 5/5 live Dawn/Metal copy/readback proof, and a fresh Linux live replay
remains owned by `M3-LINUX-REPLAY` after s7 exposes an accepted hardware adapter. Required M3 is
still red for the absent strict candidate. Container-backed regression at
`2026-08-21T20:14:51Z` keeps M0 6/6 green and M1–M8 honestly red on their existing
strict-manifest, APPLY/artifact, browser, run-label, and hardware boundaries. No product,
upstream/GPU implementation, receipt, result flag, dependency record, deferral, tolerance,
golden, blacklist, or promise changed.

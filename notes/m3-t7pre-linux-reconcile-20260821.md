<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M3.T7.pre shader-compiler Linux reconciliation — 2026-08-21

## Outcome

The device-free T7.pre compiler/interface contract is reproducible on ornith-lab. Six of six
contracts pass through exact shaderc v2025.4, SPIR-V 1.3, and Dawn/Tint
`36cf1fae0cd8a81a4fb4580751648b80b2e6255c`. The deterministic output is 249 bytes with
SHA-256 `db4b0c2fe03ecfe9629fca978b1002c65420d0df4f0d15fcaddc7736f52cded5`.

The live half remains correctly blocked. Dawn identifies the only Vulkan adapter as
`llvmpipe (LLVM 21.1.8, 256 bits)`, adapter type CPU. The harness exits 5 with exactly one
`PROBE_BLOCKED` before requesting a device, creating a pipeline, or allocating any receipt.
The historical Apple M4 Pro / Metal 4/4 pipeline proof remains valid; this iteration does not
adapt it into Linux evidence.

## Finding and repair

The retained driver was macOS-only: it defaulted to the absent `lib/macos_arm64` shaderc package,
forced Dawn Metal, used raw Ninja, and requested a device before exercising any compiler logic.
The pre-fix Linux reproduction fails on that absent package
(`20260821T192440-491001`).

The reconciled driver now:

- rejects any Dawn checkout other than the exact pin before build/evidence allocation;
- checksum-binds the shaderc v2025.4 archive and compares its extracted source byte-for-byte;
- builds the shared native shaderc library and the T7.pre target only through
  `scripts/ninja-locked.sh`, avoiding the stale Linux v2023.8 package and the static
  shaderc/Tint SPIRV-Tools collision;
- selects Metal on macOS and Vulkan on Linux while sharing the strict adapter classifier;
- runs six device-free contracts covering the mapped bindmap, sampler qualifier types,
  compute SSBO atomics, default-Tint negative semantics, exact sampler-array rejection, and
  interface bounds/type inference; and
- makes live expectations explicit: `hardware` requires the historical four pipeline gates,
  while `blocked` requires exact rc 5 and one non-hardware rejection with no live PASS. The
  build driver has no live-skip mode.

## Evidence and boundary

- First Linux build: `20260821T192916-493199`; final root confirmation:
  `20260821T193442-504989`. Both pass 6/6 device-free contracts, strict llvmpipe rejection,
  and final locked no-work.
- Final descendant-CWD replay: `20260821T193454-505246`, identical evidence and both graphs
  no-work.
- Wrong-Dawn and invalid-mode pre-allocation controls:
  `20260821T193125-502026` and `20260821T193442-504990`; the latter also proves there is no
  live-skip mode.
- Required M3 scope: `20260821T193232-502650`, honestly RED only for the absent fresh strict
  M0-M3 candidate.
- Group-scoped regression: `20260821T193237-503510`, M0 remains 6/6 GREEN; M1-M8 retain the
  existing strict-manifest, APPLY/artifact, browser, run-label, and hardware boundaries.
- Exact REUSE 6.2.0: `20260821T193342-504520`, 1,951/1,951 files licensed.

This work changes no product/upstream/GPU source, shader policy, dependency archive, harness,
receipt, adapter acceptance, result flag, deferral, tolerance, golden, blacklist, or milestone
promise. A fresh Linux M3 receipt still requires the exact 197/1,003 replay on a non-fallback
hardware Vulkan adapter under **M3-LINUX-REPLAY**.

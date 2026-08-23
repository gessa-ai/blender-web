<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M3.T1 — Dawn + Tint native toolchain probe

Proves the WebGPU shader chain runs natively on macOS/Metal or Linux/Vulkan,
in-process:

```
GLSL 450 (hand-written vert+frag)
  -> glslangValidator --target-env vulkan1.1   -> .spv  (Vulkan-1.1 / SPIR-V 1.3)
  -> tint::spirv::reader::ReadIR               -> tint::core::ir::Module
  -> tint::wgsl::writer::ProgramFromIR         -> tint::Program
  -> tint::wgsl::writer::Generate              -> WGSL text
  -> wgpuDeviceCreateShaderModule(WGSL)        -> validated on a hardware Dawn device
```

This is the T1 de-risk for **R2** (Dawn/Tint native build + SPIR-V reader) and it
prints the translated WGSL — the binding-map evidence seed for **T2** (R1,
combined-sampler split). See `notes/gpu-webgpu-architecture.md` §3, §6 and
`notes/gpu-dawn-probe.md` for the findings and API deltas.

## Dawn pin

| | |
|---|---|
| Repo | `https://dawn.googlesource.com/dawn` |
| Branch | `chromium/7989` (release branch) |
| Commit | `36cf1fae0cd8a81a4fb4580751648b80b2e6255c` |

Tint is **not** a separate dependency — it lives inside Dawn's tree
(`src/tint/`) and is built from the same checkout.

## Prerequisites

- CMake ≥ 3.16, Ninja, and a C++20 compiler (Xcode CLT or Linux clang/GCC).
- `glslangValidator` (`brew install glslang` or the distro package) for the
  offline GLSL→SPIR-V step.
- Python 3 + git on `PATH` (for Dawn's `DAWN_FETCH_DEPENDENCIES` fetcher).
- Network access the first time (the fetcher git-clones Dawn's third-party deps).
- A hardware adapter exposed through Metal on macOS or Vulkan on Linux. CPU/software
  adapters are rejected and cannot produce a probe receipt.

## Build & run

```sh
# 1. Clone the pinned Dawn (shallow is fine) into the gitignored build area:
git clone --depth 1 --branch chromium/7989 \
  https://dawn.googlesource.com/dawn /path/to/blender-web/build-dawn/dawn

# 2. Build + run (through the harness so logs stay off-context):
harness/buildwrap.sh bash sandbox/dawn-probe/build.sh
```

`build.sh` writes SPIR-V and the probe binary under `build-dawn/probe-build/`
(gitignored). Override with the `DAWN_SRC` / `BUILD` env vars.

## Success criterion

The probe prints the vertex + fragment WGSL, creates both shader modules on a
hardware Dawn device, and exits **0** iff both validate with zero validation
errors. Distinct non-zero exit codes mark which stage failed (2 load, 3 tint,
4–6 device bring-up, 7 module validation). Exit 5 with `PROBE_BLOCKED` means the
host exposed only a software/CPU adapter; that result is not a receipt.

## Files

- `shaders/probe.vert`, `shaders/probe.frag` — trivial GLSL 450; the fragment
  uses a combined `sampler2D` on purpose (the R1 hazard).
- `probe.cc` — the in-process chain + headless Dawn device + validation.
- `probe_error_handles.cc` — an audit-only software-adapter control proving that
  validation failures return non-null Dawn error objects. It also runs the shipping
  GHOST scope helper and the shipping GPU ordered-command helper against rejected/accepted
  command/submission paths, proving an error command buffer never reaches the queue and a new
  frame epoch can retry. It also proves the shipping scoped-handle cache rejects a real non-null
  sampler error object before publishing a clean retry, and repeats that rejection/retry with the
  exact mapped dummy-vertex-buffer factory and the persistent buffer wrapper's composite
  handle/metadata value. The short-lived buffer control then proves the shipping ordered resource
  gate blocks dependent work after a real non-null buffer error object and releases a clean
  next-epoch retry. Matching bind-group, texture, and texture-view controls prove the same ordered
  gate blocks their non-null error objects, while composite texture/view and
  bind-group/pipeline-layout caches prove pair rejection is atomic and clean replacements publish
  on retry. Its output is explicitly non-receipt evidence and cannot satisfy the hardware success
  criterion above.
- `probe_platform.hh` — exact host backend selection + hardware-adapter gate.
- `CMakeLists.txt` — consumes Dawn via `add_subdirectory` (minimal target set).
- `build.sh` — the three-step driver above.
- `ghost-wgpu/build_verify.sh` — requires patches 0149, 0167, 0171, and 0172's
  canonical integrated postimage, then stages the pinned GHOST context outside
  `upstream/` through the same locked Dawn graph. Its device-free
  contract exhausts all 1,024 masks across ten optional features and requires
  guarded `Float32Filterable`, `TextureComponentSwizzle`, and
  `TextureCompressionBC` selection before either a hardware T3 pass or an explicit
  software-block control. `parser-selfcheck` rejects eight malformed selector
  shapes, including missing, mismatched, and duplicated BC selectors, plus missing,
  duplicated, blocked, and nonzero hardware transcripts. Hardware mode independently
  classifies the adapter retained by the real context and requires one exact
  adapter/PASS transcript.

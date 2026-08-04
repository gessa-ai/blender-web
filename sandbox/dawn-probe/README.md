<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->
# M3.T1 — Dawn + Tint native toolchain probe

Proves the WebGPU shader chain runs natively on arm64 macOS, in-process:

```
GLSL 450 (hand-written vert+frag)
  -> glslangValidator --target-env vulkan1.1   -> .spv  (Vulkan-1.1 / SPIR-V 1.3)
  -> tint::spirv::reader::ReadIR               -> tint::core::ir::Module
  -> tint::wgsl::writer::ProgramFromIR         -> tint::Program
  -> tint::wgsl::writer::Generate              -> WGSL text
  -> wgpuDeviceCreateShaderModule(WGSL)        -> validated on a real Dawn/Metal device
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

- CMake ≥ 3.16, Ninja, a C++17 clang (Xcode CLT).
- `glslangValidator` (`brew install glslang`) for the offline GLSL→SPIR-V step.
- Python 3 + git on `PATH` (for Dawn's `DAWN_FETCH_DEPENDENCIES` fetcher).
- Network access the first time (the fetcher git-clones Dawn's third-party deps).

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
live Dawn/Metal device, and exits **0** iff both validate with zero validation
errors. Distinct non-zero exit codes mark which stage failed (2 load, 3 tint,
4–6 device bring-up, 7 module validation).

## Files

- `shaders/probe.vert`, `shaders/probe.frag` — trivial GLSL 450; the fragment
  uses a combined `sampler2D` on purpose (the R1 hazard).
- `probe.cc` — the in-process chain + headless Dawn device + validation.
- `CMakeLists.txt` — consumes Dawn via `add_subdirectory` (minimal target set).
- `build.sh` — the three-step driver above.

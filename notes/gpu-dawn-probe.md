<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->
# M3.T1 — Dawn+Tint native toolchain probe (findings)

Uncommitted worker notes for orchestrator review. Companion to the committed
`sandbox/dawn-probe/`. Pin: Blender 5.2 `fbe6228777e7`; this file is about the
**Dawn/Tint** dependency, not Blender.

Task: prove GLSL → SPIR-V → Tint(SPV reader → WGSL writer) → `wgpuDeviceCreate
ShaderModule` runs natively on this Mac (arm64 macOS), de-risking **R2** and
seeding **R1/T2** with real WGSL binding output.

---

## 1. Dawn pin (RECORDED)

| | |
|---|---|
| Repo | `https://dawn.googlesource.com/dawn` |
| Branch | `chromium/7989` (newest release branch at probe time) |
| Commit | `36cf1fae0cd8a81a4fb4580751648b80b2e6255c` |
| Clone | `--depth 1 --branch chromium/7989`, 24 s, 590 MB |

Rationale: a `chromium/NNNN` release branch head is more stable than `main`.
7989 was the highest-numbered release branch at clone time (main HEAD was
`2f060868016d44530fe1343b81cf6ff4fa42470c`). **M4 alignment caveat:** the M4
browser path uses `--use-port=emdawnwebgpu` (≥4.0.10). For M3↔M4 WGSL agreement
the native Tint here should track the same Dawn/Tint generation as the pinned
emdawnwebgpu port; revisit the exact commit when the M4 port is pinned
(open question 3 in `notes/gpu-shader-chain.md` §5).

## 2. Toolchain on this host

- glslangValidator 16.4.0 (`brew install glslang`; pulled spirv-tools 1.4.357.0
  too → `spirv-val`/`spirv-dis` available). Recorded in `ledger/deps.json`? — no,
  glslang is a *build-time host tool* for the probe, not a runtime/browser dep.
- CMake 4.0.3, Ninja 1.13.1, Apple clang 17.0.0 (Xcode 26.2).
- Dawn fetcher used Python 3.14.6 (Homebrew), git — no depot_tools needed.

## 3. CMake flags (as required by the task)

```
-DDAWN_FETCH_DEPENDENCIES=ON
-DTINT_BUILD_SPV_READER=ON
-DTINT_BUILD_WGSL_WRITER=ON
-DDAWN_ENABLE_METAL=ON
-DDAWN_BUILD_SAMPLES=OFF
-DTINT_BUILD_TESTS=OFF
-DTINT_BUILD_CMD_TOOLS=ON
```
Plus, for a lean macOS link surface: `DAWN_ENABLE_VULKAN/OPENGLES/DESKTOP_GL=OFF`,
`DAWN_USE_GLFW=OFF`, `DAWN_BUILD_PROTOBUF=OFF`. Consumed via `add_subdirectory`
+ `EXCLUDE_FROM_ALL` so ninja builds only the probe's link closure.

Probe links: `webgpu_cpp`, `dawn::dawn_native`, `dawn::dawn_proc`,
`tint_lang_spirv_reader`, `tint_lang_wgsl_writer`, `tint_api`.

## 4. API DELTAS vs the architecture doc (the important part)

The architect's doc (`gpu-webgpu-architecture.md` §3b, `gpu-shader-chain.md` §1)
was written from web knowledge and assumed the **AST-era Tint API**:
`tint::spirv::reader::Read(words) -> tint::Program`, then
`tint::wgsl::writer::Generate(program)`. **That entry point is gone at this pin.**
The real API at `36cf1fae` is **IR-based**:

| Doc assumed | Actual at chromium/7989 |
|---|---|
| `spirv::reader::Read(words, opts) -> tint::Program` | `spirv::reader::ReadIR(std::vector<uint32_t>, spirv::reader::Options) -> tint::Result<tint::core::ir::Module>` |
| `wgsl::writer::Generate(program)` directly on reader output | must first `wgsl::writer::ProgramFromIR(module&, wgsl::writer::Options) -> Result<Program>`, then `wgsl::writer::Generate(program, opts) -> Result<Output>` |
| — | `Output.wgsl` (std::string) holds the WGSL |

Ground truth mirrored: `src/tint/cmd/common/helper.cc::ReadSpirv` does exactly
`ReadIR → ProgramFromIR`. `Result<T>` API: compare `!= tint::Success`, `.Get()`
for the value ref, `.Move()` to move out, `.Failure()` streams the error.

Other API facts confirmed by reading the pin's headers/samples:
- **Combined-sampler split is built into the SPIR-V reader.** `spirv::reader::
  Options::sampler_mappings` (a `map<BindingPoint,BindingPoint>`); when **empty**
  Tint "auto-resolves binding conflicts by incrementing binding numbers until
  unique" (`src/tint/lang/spirv/reader/common/options.h:38-51`). This is the
  exact R1 knob T2 must pin — see §6 for the observed numbering.
- Dawn native device creation is the modern webgpu.h async API driven
  synchronously: `dawnProcSetProcs(&dawn::native::GetProcs())` →
  `wgpu::CreateInstance` (with `InstanceFeatureName::TimedWaitAny`) →
  `instance.WaitAny(instance.RequestAdapter(..., CallbackMode::WaitAnyOnly, cb),
  UINT64_MAX)` → same for `RequestDevice`. No surface needed (headless).
  (`src/dawn/samples/SampleUtils.cpp:161-343`.)
- WGSL module: `wgpu::ShaderSourceWGSL` (NOT the old `ShaderModuleWGSLDescriptor`)
  chained via `descriptor.nextInChain`. Validation surfaced via
  `PushErrorScope(ErrorFilter::Validation)` / `PopErrorScope(WaitAnyOnly, cb)` +
  `SetUncapturedErrorCallback`. `wgpu::StringView` (`.data`/`.length`, sentinel
  `WGPU_STRLEN`) replaces `const char*` message params throughout.

Implication for the backend (`wgpu_shader_compiler.cc`, arch §5): code against
the **IR path** (`ReadIR`/`ProgramFromIR`/`Generate`), not the AST path the doc
sketched. Everything else in §3 holds.

### 4a. NEW CONSTRAINT — Tint reads only Vulkan-1.1 / SPIR-V 1.3

Tint's IR SPIR-V reader **hardcodes** its spirv-tools target env:
`constexpr auto kTargetEnv = SPV_ENV_VULKAN_1_1;`
(`src/tint/lang/spirv/reader/parser/parser.cc:95`). It is **not** exposed through
`spirv::reader::Options`. Feeding it Vulkan-1.2 SPIR-V (version 1.5, which
`glslangValidator --target-env vulkan1.2` and shaderc `vulkan_1_2` both emit) is
rejected outright:

```
spirv:1:1 error: Invalid SPIR-V binary version 1.5 for target environment
SPIR-V 1.3 (under Vulkan 1.1 semantics).
```

The probe only passes once SPIR-V is generated at **`--target-env vulkan1.1`
(SPIR-V 1.3)**. But arch §3a records that Blender's Vulkan backend compiles with
`shaderc_env_version_vulkan_1_2` (`vk_shader_compiler.cc:211`). **Therefore the
WebGPU shader compiler must target `shaderc_env_version_vulkan_1_1` (SPIR-V 1.3),
NOT 1.2**, or Tint will reject every module. This is a concrete, load-bearing
spec item for T7 that the architecture doc did not have. Risk it introduces:
any Blender shader that needs a SPIR-V >1.3 capability (some 1.2-era decorations,
`PhysicalStorageBuffer` addresses, certain subgroup ops) won't survive the 1.1
target — enumerate those before T7 (the M3 compute corpus is expected clean).

### 4b. Build-integration gotchas (each cost an attempt; all resolved)

1. **Host Python `pyexpat` breakage.** Dawn auto-picked Homebrew CPython 3.14.6
   whose `pyexpat` fails to `dlopen` (`Symbol not found:
   _XML_SetAllocTrackerActivationThreshold` — a libexpat ABI skew), aborting
   SPIRV-Tools codegen. Fix: pass `-DPython3_EXECUTABLE` pointing at an
   interpreter whose `import pyexpat` works (3.13.13 here). `build.sh` now
   auto-selects one.
2. **`webgpu_cpp` target is not add_subdirectory-consumable.** Linking the
   `webgpu_cpp` alias (→ `dawncpp_headers`) across directory scopes makes CMake
   attribute a generated header as a missing source of the consumer and fail at
   generate time. Fix: link the **monolithic `dawn::webgpu_dawn`** static lib
   (Dawn's documented external target, `docs/quickstart-cmake.md`) — it provides
   the real `wgpu*` impl + C++ headers with no `dawnProcSetProcs`/`DawnNative.h`
   wiring. The SPIR-V reader is NOT bundled in it (Dawn never consumes SPIR-V),
   so `tint_lang_spirv_reader` is linked explicitly alongside it (writer/api
   resolve lazily, no duplicate symbols).
3. **C++20 required.** Dawn's generated `webgpu_cpp.h` and the Tint headers use
   `std::span`/`std::type_identity`/`std::to_array`/concepts. The probe target
   must be C++20 (Dawn sets this on its own TUs but the consumer does not inherit
   it).
4. **`tint` CLI not built.** `TINT_BUILD_CMD_TOOLS=ON` was set, but with
   `EXCLUDE_FROM_ALL` the `tint` CLI target isn't pulled unless depended on. The
   in-process C++ Tint API was sufficient, so the CLI bonus was skipped (build
   `ninja tint_cmd` if wanted).

## 5. Build metrics

- Clone: 24 s, 590 MB (shallow, `--branch chromium/7989`).
- `fetch_dawn_dependencies` + configure (cold): 57.8 s; Dawn checkout grows to
  **1.3 GB** (source + fetched third_party: abseil, spirv-tools/headers,
  glslang, emdawnwebgpu, etc.). Reconfigure (warm): ~3 s.
- Build: **minimal target set = ~693 ninja edges** (`dawn::webgpu_dawn`
  monolithic + `tint_lang_spirv_reader`/`_wgsl_writer`/`_api` + probe).
  `dawn_probe` binary = **13 MB**; probe build tree = **118 MB**. Warm no-op
  build + probe run = 4 s.
  NOTE: cold wall-time not cleanly captured — two host restarts interrupted the
  build, which resumed incrementally (ninja). 693 edges on 14 cores ⇒ order a
  few minutes cold; the interruptions cost sessions, not correctness.
- Disk floor: start 46 GB; low ~37 GB mid-build; 88 GB at end (other fleet
  workers freed space). **Never near the 8 GB floor.**

## 6. RESULTS — PROBE PASS (exit 0)

Reproduced by the committed `sandbox/dawn-probe/build.sh`
(`ledger/buildlogs/20260804T033247.log`). Device: **"Apple M4 Pro", Metal,
headless (no surface)**.

| Stage | Result |
|---|---|
| dawn-build (Dawn native + Tint, native arm64 macOS) | **PASS** |
| spirv-gen (glslang GLSL 450 → SPIR-V 1.3) | **PASS** |
| tint-translate (ReadIR → ProgramFromIR → Generate → WGSL) | **PASS** (both stages) |
| module-validate (`CreateShaderModule` on Dawn/Metal, validation error scope clean) | **PASS** (both stages) |

### Fragment WGSL (verbatim — the T2 / R1 binding-map seed)

```wgsl
var<private> out_color : vec4<f32>;

@group(0u) @binding(2u) var image_sampler : sampler;

@group(0u) @binding(1u) var image_image : texture_2d<f32>;

struct Material {
  tint : vec4<f32>,
}

@group(0u) @binding(3u) var<uniform> material : Material;

fn main_inner(v_uv : vec2<f32>) {
  out_color = (textureSample(image_image, image_sampler, v_uv) * material.tint);
}

@fragment
fn main(@location(0u) v_uv : vec2<f32>) -> @location(0u) vec4<f32> {
  main_inner(v_uv);
  return out_color;
}
```

### R1 combined-sampler split — OBSERVED numbering (the key T2 evidence)

Input GLSL bindings → Tint WGSL output (empty `sampler_mappings`, auto-resolve):

| GLSL declaration | GLSL `binding` | WGSL result |
|---|---|---|
| `sampler2D image` (texture half) | 1 | `@group(0) @binding(1) texture_2d<f32>` (kept) |
| `sampler2D image` (sampler half) | — (invented) | `@group(0) @binding(2) sampler` (**new**) |
| `Material` UBO | 2 | `@group(0) @binding(3) uniform` (**BUMPED 2→3**) |

This is R1 made concrete: splitting the combined sampler invents a sampler
binding (2) that **collides** with the Material UBO's declared binding (2), and
Tint's auto-conflict-resolution then **increments the UBO to 3**. So Tint's WGSL
binding numbers do **not** match Blender's `shader_interface` expectations
(which still think Material lives at binding 2). Left unmanaged this is a silent
mis-bind. The vertex WGSL also surfaces `gl_PointSize`/`gl_ClipDistance` in the
emitted `gl_PerVertex` struct (arch hazards §3c.6), unused here but visible.

### Tint API surprises encountered

- The whole AST→IR reader migration (§4): `Read`→`ReadIR`, plus the mandatory
  `ProgramFromIR` hop before `Generate`.
- The hardcoded Vulkan-1.1 input env (§4a) — the single most important finding.
- `spirv::reader::Options::sampler_mappings` is the exact, documented knob for
  controlling the split-sampler numbering — so R1 is *tunable*, not just
  observable (see §7).

## 7. Confidence read for T2 — HIGH

The R1 mechanism is fully characterised and, crucially, **controllable**:
`spirv::reader::Options::sampler_mappings` (`map<BindingPoint,BindingPoint>`)
lets T2/T7 assign each split sampler an explicit WGSL binding instead of letting
Tint invent+bump. The strategy for `wgpu_shader_interface`: derive the
bind-group layout from Blender's create-info reflection, then hand Tint a
`sampler_mappings` that pins every combined sampler's sampler-half to a chosen
binding, and lay out the bind-group to match Tint's deterministic output. T2's
job is now a well-scoped mapping exercise with a proven API — not an open risk.
The bigger cross-cutting item for T7 is §4a (compile at SPIR-V 1.3, not 1.2).

## 8. Deliverable pointers

- Committed: `sandbox/dawn-probe/{probe.cc,CMakeLists.txt,build.sh,README.md,
  shaders/probe.{vert,frag}}`.
- Build area (gitignored): `build-dawn/dawn` (checkout @ 36cf1fae),
  `build-dawn/probe-build` (binary + spv + Dawn/Tint objects).

<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Porting patterns — the fleet's stdlib (append-only)

Read this before fighting a familiar-looking wasm build error. Each entry: the
error signature, the root cause, and the fix pattern with a citation.

## Class 1 — wasm32 ILP32 pointer-size assumptions
`static_assert(sizeof(X) == <LP64 constant>)` fails because wasm32 pointers are
4 bytes (LP64 = 8). Fix: guard the assert by ABI — assert the wasm32 value under
`#ifdef __EMSCRIPTEN__`, keep the LP64 value in `#else`. Do NOT delete the assert
(it's a regression guard). See `patches/0005-*`, `notes/m1-blenlib.md`
(BLI_resource_scope.hh 16→8). Also DNA scalar alignment: makesdna uses the i386
model (8-byte scalars aligned to 4 when ptr=4); wasm32 keeps 8-byte scalars at
8-align with 4-byte pointers — `patches/0002-*`, `notes/m1-dna-align.md`.

## Class 2 — libc gaps under Emscripten
- `<fenv.h>`: wasm has no FP-exception status register. Emscripten sets
  `FE_ALL_EXCEPT 0` and omits `FE_DIVBYZERO`/`FE_INVALID`. `#define` the missing
  macros to 0 under `#ifdef __EMSCRIPTEN__`; the post-eval FP check becomes a
  no-op (honest deferral, flag for `ledger/deferred.json`). `patches/0004-*`.
- `struct statfs`: incomplete under Emscripten (not `__linux__`, not BSD/Apple).
  Emscripten implements POSIX `statvfs()` — route to the existing statvfs path via
  `#ifdef __EMSCRIPTEN__` + `<sys/statvfs.h>` + `USE_STATFS_STATVFS`. `patches/0004-*`.
- DNA `enum X : char` narrowing: Emscripten `char` is SIGNED; native platforms set
  `-funsigned-char`. platform_wasm now adds `-funsigned-char` (+ `-fno-strict-aliasing
  -ffp-contract=off`). `notes/m1-integrate.md`.

## Class 3 — build-time host codegen tools under wasm
Blender compiles small C++ programs (makesdna, makesrna, shader_tool, datatoc,
msgfmt) and EXECUTES them mid-build to generate sources. Cross-compiled to wasm,
the "executable" is `tool.js`+`tool.wasm`.
- **Symptom A: rc=126 "Permission denied"** — CMake invokes via `$<TARGET_FILE:tool>`
  (a file path, not a bare target), so the node `CMAKE_CROSSCOMPILING_EMULATOR` is
  never auto-applied. Fix (BOTH halves): (1) prepend `${CMAKE_CROSSCOMPILING_EMULATOR}`
  before `"$<TARGET_FILE:tool>"` in the `add_custom_command` (no-op on native); (2)
  call `blender_web_host_tool(tool)` after `add_executable` to overwrite the link
  flags with a node-runnable profile (`-pthread -sNODERAWFS -sEXIT_RUNTIME=1
  -sALLOW_MEMORY_GROWTH -sWASM_BIGINT -sPROXY_TO_PTHREAD=0`). Proven for makesdna/
  makesrna (`patches/0003-*`, `notes/m1-hosttools.md`) and shader_tool/datatoc
  (`patches/wip-0007-*`). This wiring is IDENTICAL for every such tool.
- **Symptom B: the tool runs under node but MISCOMPUTES / hangs.** A wasm host tool
  can run fine yet be wrong. Two sub-classes seen:
  - ABI-baking tools (makesdna): wrong struct offsets — a real ABI bug, owned by the
    tool's C++ (Class 1). `notes/m1-dna-align.md`.
  - SIMD/vectorized tools (shader_tool `lexit`): SSE4.2/NEON with no correct scalar
    fallback → scalar path hangs/mis-tokenizes under wasm. Enable Emscripten's
    SSE4.2→wasm-SIMD (`-msse4.2 -msimd128` + widen the arch guard to accept
    `__EMSCRIPTEN__`) to reuse the native vectorized path. Fixes most; a residual
    tokenization discrepancy on complex EEVEE shaders remains **UNRESOLVED** (deep,
    GPU/M3). See `notes/m1-shader-codegen-wasm.md`. LESSON: text-codegen host tools
    (shader_tool, datatoc — output is target-independent) are better run as NATIVE
    host binaries; only ABI-baking tools (makesdna/makesrna) must be wasm.
- **`WITH_ASSERT_RELEASE=ON` caveat**: the M1 config keeps NDEBUG OFF so BLI_assert/
  `assert()` stay live for tier-(a) runtime correctness. This ALSO activates asserts
  inside build-time host tools, where native Release (NDEBUG on) would skip them.
  Do NOT paper over a host-tool assert with NDEBUG — it can convert a fast, precise
  abort into an infinite loop (observed in shader_tool). Fix the underlying tool bug.

## Meta — order-only object dependencies pull in unrelated codegen
`ninja bf_<lib>` builds a lib's `.cc.o` files only after all order-only
`cmake_object_order_depends_target_*` succeed. Those are derived from the lib's real
LINK deps (e.g. blenkernel PRIVATE-links `bf::draw`/`bf::gpu` → their shader codegen
becomes an order-only gate on every blenkernel object), NOT from the lib's own
`#include`s. So a lib with zero GPU includes can still be blocked by broken GPU
shader codegen, and it cannot be severed without dropping genuine link edges. Query
with `ninja -C build-wasm -t query cmake_object_order_depends_target_<lib>`.

## Class 3b — build-time HOST PYTHON scripts (discover_nodes.py etc.)
Some codegen is a Python script run on the build host (node registration:
`add_node_discovery()` -> `${PYTHON_EXECUTABLE} discover_nodes.py`). The script has
no shebang and is not executable, so if `PYTHON_EXECUTABLE` is empty the command
collapses to running the `.py` directly -> `/bin/sh: ...py: Permission denied`
(rc 126). Emscripten sets no host interpreter and WITH_PYTHON=OFF skips find(Python).
Fix: platform_wasm.cmake sets a HOST `PYTHON_EXECUTABLE` (prefer the emsdk-bundled
python; else find_program(... NO_CMAKE_FIND_ROOT_PATH) to bypass the emscripten
sysroot re-root). This is the build-host interpreter, unrelated to the embedded
CPython. See notes/m1-shader-codegen-wasm.md.

## Class 3c — ADR-002: NATIVE host tools for target-independent text codegen
shader_tool + datatoc emit target-INDEPENDENT text; their wasm builds can be buggy
(shader_tool's SIMD/scalar lexer mis-tokenizes under wasm). Build them NATIVELY
(scripts/build-hosttools.sh -> build-hosttools/bin-native/) and point the custom
commands at ${BLENDER_WEB_HOST_TOOLS_DIR}/<tool> when cross-compiling (patch 0007 +
platform_wasm.cmake). ONLY for text codegen — makesdna/makesrna bake target ABI and
MUST stay wasm-under-node (Class 3). Byte-identity of native-vs-wasm output MUST be
audited before trusting this (it was: identical wherever the wasm tool functions).
Cold rebuild scripts commonly retain `CXX=em++` from the dependency harvest; override it
explicitly with the recorded host compiler before invoking `scripts/build-hosttools.sh`.
The native `msgfmt` closure also links the host zlib/zstd libraries even though its headers
come from `lib/wasm`, so the cold-host package list must provide both development libraries.
Native host-tool binaries are explicit Ninja inputs to thousands of generated shader/datafile
edges. Rebuilding `shader_tool` or `datatoc` after a windowed product link therefore makes that
product stale even when the tools emit byte-identical output: on ornith-lab a later audit rebuild
of `shader_tool` scheduled 3,587 edges. Always order host-tool construction before product builds;
after any host-tool rebuild, rebuild the affected product through `scripts/ninja-locked.sh` and
retain an exact `-n` no-work proof.

## Class 1 (recurring) — LP64 shift/width assumptions beyond sizeof-asserts
Not just `static_assert(sizeof==const)`: watch for `size_t(1) << 32` and similar
64-bit-width assumptions. blenkernel image.cc uses `size_t(1) << 32` as a cache-key
collision-avoidance base; on wasm32 `size_t` is 32-bit so it overflows AND can't hold
the value. Fix: widen the specific value/field to a fixed 64-bit type under
__EMSCRIPTEN__ (LP64 unchanged). Check the field isn't DNA-serialized first; if it is,
STOP (that's an ABI-layout change). IDCacheKey is pure-runtime, so widening was safe.
Patch 0008.

## Class 4 — JSPI (`-sJSPI`) suspends are ILLEGAL during C++ static ctors under PROXY_TO_PTHREAD
Signature: `SuspendError: trying to suspend without WebAssembly.promising`, stack
originating from `__wasm_call_ctors` → a C++ global-init function (`_GLOBAL__I_*`) →
a static ctor (observed: `std::ios_base::Init::Init()`), i.e. BEFORE `main()` and
before `onRuntimeInitialized` even fires — the boot dies during `initRuntime()` with no
app output. Root cause: Emscripten's `-sJSPI` wraps only `main`/`__main_argc_argv`
(exportPattern) and the pthread entry (`invokeEntryPoint`, via `WebAssembly.promising`)
as suspendable; but `initRuntime()` calls `wasmExports["__wasm_call_ctors"]()` RAW on
the MAIN thread (guarded `if (ENVIRONMENT_IS_PTHREAD) return`), so any op a static ctor
performs that `-sJSPI` lowered to a suspend has no Suspender on the stack → abort. Fix:
when `main()` runs on a `-sPROXY_TO_PTHREAD` WORKER, that worker can block
(`Atomics.wait`), so blocking `WaitAny`/futex waits work there WITHOUT JSPI — drop
`-sJSPI` and keep the device await as a blocking `WaitAny` on the worker; the cross-thread
device-ready future is signalled from the browser main thread. A main-thread suspend, if
ever genuinely needed, must be reached from a promising-wrapped export, never from ctors.
See `notes/m4-integration.md` T9, `patches/platform_wasm.cmake` (browser arm).

## Class 5 — direct Linux build-tree tests need Blender's bundled-library environment
Signature: a freshly linked native test exits before enumeration with
`error while loading shared libraries: libOpenEXR.so.*` (or another transitive
precompiled dependency), even though its direct RUNPATH is present. Linux
`DT_RUNPATH` is not transitive. CTest and Blender's code-generator commands apply
`PLATFORM_ENV_BUILD`; a standalone evidence runner must do the same. Prepend the
canonical `lib/linux_<arch>/*/lib` package directories to `LD_LIBRARY_PATH`, retain
the caller's path only as a fallback, and apply that environment to both list and
run phases. Do not copy libraries into the build tree or substitute system packages.

## Class 6 — container-backed test shims must freeze the launch mount across child `cwd` changes
Signature: a host path exists, but the containerized oracle reports that the same Python test
file cannot be opened as soon as a matrix runner gives each suite its own scratch `cwd`.
A shim that derives its bind mount from every invocation's current directory mounts only that
scratch leaf, so absolute repository arguments cannot translate into `/work/...`. Freeze the
`with-env` launch directory in an inherited variable, mount that stable root for each shim call,
and map descendant caller directories to their exact container workdir. Keep direct wrapper
calls on their existing current-directory-only contract and reject shim calls from outside the
frozen root.
When the shim substitutes for an existing launcher, it must also preserve arguments exactly;
do not inject convenience flags already supplied by that launcher, or startup metadata can be
emitted twice and break exact normalized parity.

## Class 7 — combined stdout/stderr can fragment unittest progress without changing results
Signature: native and Wasm both exit zero with the same `Ran N tests`/`OK` tail, but one combined
log groups adjacent progress dots while the other writes one dot per line. This is descriptor
buffering/interleaving, not operator behavior. Canonicalize only a suite-scoped, whole-output
grammar with the exact dot cardinality and exact normalized result tail; reject missing/extra dots,
changed test counts, or any additional output. Do not add a general punctuation filter.

Containerized oracle logs also spell repository paths under the fixed `/work` mount while the
Wasm runtime prints the host checkout root. Normalize only those exact roots followed by `/`,
reject a log that mixes both roots or already contains the reserved token, and perform the more
specific per-suite scratch-root mapping first. Arbitrary paths remain visible parity evidence.
The same buffering can prefix progress dots directly onto a later stdout launcher-envelope line.
Recognize only a dot-only prefix immediately before the exact allocator text and pinned adjacent
banner, preserve the dots plus their newline, and reject every other prefix.
A dot-only prefix is not sufficient when that envelope interrupts an unterminated multi-dot run:
replacing the prefix with `prefix + newline` can turn an otherwise identical `..` into two `.`
lines. Do not rebaseline or flatten punctuation. First add adversarial fixtures for both a split
multi-dot run and a split verbose test-status line, then reconstruct only the exact interrupted
progress grammar while preserving every non-envelope byte.
For suites that intentionally emit diagnostics during unittest progress, canonicalize only a
whole-output grammar: bind the exact ordered diagnostics and exact `Ran N tests`/`OK` tail, allow
dot/newline bytes only around that block, and require the total dot count to equal `N`.
When one platform moves a progress dot across an exact diagnostic boundary, enumerate the complete
anchored layout and restore that single dot before comparing streams. Keep platform null-pointer
spellings as an explicit finite set; do not mask arbitrary pointer-value text.
If a dot can land at any boundary inside a short, exact ordered diagnostic sequence, bind the
records and dot cardinality instead of enumerating incidental offsets. A final diagnostic may also
flush immediately before or after the exact result tail, or between its exact `Ran N tests` prefix
and final `OK`. Accept only observed complete layouts, canonicalize them to one order, and reject
missing, duplicated, near-match, or differently placed diagnostics.
If a test-completion dot normally trails such a diagnostic phase but can flush back inside it,
include that trailing boundary in each observed complete layout and preserve the exact total dot
cardinality. Matching only the diagnostic lines can otherwise mistake a two-dot phase for a
one-dot phase while leaving an unbound dot attached to the following record.
Expected-failure progress markers can be interrupted by the launcher envelope too. Bind a marker
such as `x` only as an exact observed prefix for the named suite and platform, then byte-splice the
envelope so the complete status sequence must still equal the peer log. Never add `x` to the
general dot-prefix grammar.

## Class 8 — current evidence producers must not inherit paths from retained legacy rigs

Signature: a current producer imports or transforms a retained historical rig successfully on its
original host, but fails before its self-check on a new checkout because source, artifact, output,
or Node module paths are absolute. Derive the repository root from the producer file, not the
caller's current directory. Keep the historical rig immutable; replace each load-bearing legacy
declaration exactly once and fail if its seam drifts. Resolve browser modules through explicit,
documented local roots and confine evidence output to one validated child of the canonical run
directory. Self-check mode may use unmistakable non-evidence artifact placeholders so it can run
before a shipping artifact exists, but a real producer invocation must still open and hash-bind
every required product artifact before browser launch.

## Class 9 — Emscripten WebGPU value types must come from the emdawnwebgpu port

Signature: a device-free Wasm target includes Dawn's native `include/webgpu/webgpu_cpp.h`, reaches
the generated `dawn/webgpu_cpp.h`, and fails with “Do not include this header. Use the headers
provided by Emdawnwebgpu instead.” Native Dawn deliberately rejects those generated headers under
`__EMSCRIPTEN__`, even when the target only constructs bind-group descriptor values and never
requests a device. Pass `--use-port=emdawnwebgpu` to both compile and link so Emscripten supplies
the matching C/C++ header set; do not add a native Dawn generated-include directory to the Wasm
target. See `sandbox/wgpu-shader-integrated-smoke/`.

## Class 10 — device-free backend objects can still require Blender's allocator closure

Signature: a device-free test stack-constructs a backend class and links fail only at its virtual
deleting destructor with unresolved `mem_guarded::internal::mem_freeN_ex`. A class carrying
`MEM_CXX_CLASS_ALLOC_FUNCS` emits allocator-backed deleting/new paths even when the test never
heap-allocates it. Link the canonical guardedalloc source closure in both native and Wasm legs;
do not mask the product dependency with a test-only allocator symbol. Private GPU headers can also
reach fmt through `BLI_string_ref.hh`, so bind the pinned native and Wasm fmt include roots and
require their directly consumed headers to be byte-identical. See
`sandbox/wgpu-buffer-integrated-smoke/`.

## Class 11 — device-free functions can share a translation unit with live-device code

Signature: a parity test needs pure enum/layout helpers from a shipping backend `.cc`, but linking
that object also reports unresolved shader, cache, or device methods that the test never calls.
Compile the canonical translation unit with function/data sections and link with section garbage
collection; do not copy the helpers into a test module or satisfy the live half with fake symbols.
Blender's `BLI_assert_unreachable()` still prints in Release builds even though it does not abort,
so an intentionally exercised fail-visible fallback must link the canonical `BLI_assert.cc` and
bind the exact native/Wasm diagnostic instead of suppressing stderr. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

When the needed pure helper has internal linkage, include its canonical shipping `.cc` exactly
once from the shared test translation unit; do not copy the helper or add a test-only production
API. Link the real dependent translation units, then section-collect the uncalled device half.
File-scope objects can keep a narrow runtime edge alive even when every device function is
collected: `CLG_LogRef` registers itself from a global constructor, so a directly included GPU
translation unit still needs the canonical `clog.cc` plus guardedalloc closure. Link those real
sources in both native and Wasm legs; do not replace the registration function with a test stub.
Modern enum wrappers can still collapse through a legacy accessor: vertex `SNORM_10_10_10_2` and
`UNORM_10_10_10_2` both report normalized `GPU_COMP_I10`, while the pinned vertex call sites and
all established backends use that legacy arm for signed packed normals. Check the pinned call-site
census before assigning semantics from the newer enum spelling. See
`sandbox/wgpu-vertex-integrated-smoke/` and
`sandbox/wgpu-shader-frontend-integrated-smoke/`.

## Class 12 — shader text fast paths need the same token boundary as their rewrite

Signature: a GLSL source rewriter correctly protects its replacement loop from longer identifiers,
but its earlier `find()`-based fast path still treats `myisnan(` as `isnan(` and injects otherwise
unused declarations. Require the identifier boundary before deciding that a rewrite is needed;
then reuse that discriminator for the actual replacement. This keeps unrelated source and cache
keys byte-identical and makes the no-op control explicit in the native/Wasm contract. See
`sandbox/wgpu-shader-frontend-integrated-smoke/`.

## Class 13 — constructing a polymorphic backend object retains its live-device vtable

Signature: a device-free test includes a backend translation unit successfully, but the first
stack construction of its polymorphic class retains every virtual entry and exposes unresolved
device/compiler edges that section garbage collection previously removed. Do not satisfy those
dead paths with test stubs. When the contract needs one non-virtual member method, extract that
method byte-for-byte from the canonical source with unique, fail-closed boundaries, rename only
the class qualifier, and compile it against a minimal state carrier. Bind the canonical replay and
the extracted payload digest, and add a malformed-source zero-allocation control. See
`sandbox/wgpu-shader-frontend-integrated-smoke/`.

## Class 14 — per-axis resource limits do not validate linear host copies

Signature: texture creation rejects dimensions above the adapter limits, but a later upload,
readback, or fallback clear multiplies individually valid width, height, depth, row pitch, and
texel size into a wrapped `size_t` before allocating host memory. Resolve the complete linear
geometry atomically before allocation or caller reads, and drive every later loop bound, byte
count, and WebGPU layout field from that one result. Exercise the same boundary contract on native
and wasm32 because their `size_t` overflow points differ. See
`sandbox/wgpu-texture-integrated-smoke/`.

## Class 15 — framebuffer readback belongs to the attached subresource

Signature: a backend calls `texture->read(0, ...)`, sizes each destination row from the texture's
whole-mip byte count, and then crops on the host. This silently reads array layer zero, ignores the
framebuffer attachment's mip, and writes the texture's full component count even when the caller
requested fewer channels. Resolve the exact attachment mip/layer before reading; validate source
and destination row geometry separately; then crop, apply the backend's Y convention, and
truncate or extend channels without exceeding the caller-visible payload. Native framebuffer
reads define missing color channels as zero and a requested missing alpha channel as one. Exercise
layer selection, leading-channel truncation, R/RG extension, bounds, and native/wasm32 overflow
before trusting pixels. See `sandbox/wgpu-framebuffer-subresource-oracle/` and
`sandbox/wgpu-texture-integrated-smoke/`.

## Class 16 — layered framebuffer clear passes exhaust attachments independently

Signature: a framebuffer clear emulates an all-layer native attachment with one WebGPU render pass
per layer, chooses the maximum layer count globally, and aborts when a shorter sibling has no view
for a later pass. Earlier layers clear, but the longer attachment's remaining layers stay stale.
Classify every attachment on every pass as active, exhausted, or invalid: omit only exhausted
all-layer attachments, keep fixed-layer behavior unchanged, and fail invalid selections before
submitting that pass. Exercise unequal color-layer counts plus invalid and integer-boundary cases
in native and wasm32. See `sandbox/wgpu-framebuffer-completeness-oracle/` and
`sandbox/wgpu-texture-integrated-smoke/`.

## Class 17 — layered draw counts follow attachment selections, not backing textures

Signature: pass-per-layer emulation asks the first bound texture for its complete array size and
then forces that pass number onto every attachment. A frontend-fixed attachment is moved away from
its selected layer, and mismatched all-layer attachments can draw a prefix before a later view
fails. Accumulate pass counts only from attachments whose frontend layer is negative, require all
such counts to agree before encoding, validate fixed selections without letting them drive the
loop, and preserve fixed layers when resolving each pass view. Exercise fixed/all-layer mixtures,
mismatched counts, invalid selections, and signed-boundary cases in native and wasm32. See
`sandbox/wgpu-texture-integrated-smoke/`.

## Class 18 — one-shot load clears do not span WebGPU array-layer passes

Signature: an explicit framebuffer `CLEAR` action is changed to `LOAD` by the first render pass,
but a native all-layer attachment was split into one WebGPU pass per array layer. Only the first
layer is initialized; later layer/viewport passes load stale contents. Before assembling any draw
pass, classify pending clears by frontend layer selection and physical layer count. Keep fixed and
single-layer actions in the render pass, but materialize multi-layer all-layer actions through the
backend's complete layered-clear path and consume them only after that operation. Validate the
whole pending set before clearing any attachment. Exercise fixed, all-layer, invalid, and signed
boundary scopes in native and wasm32. See `sandbox/wgpu-framebuffer-loadclear-oracle/` and
`sandbox/wgpu-texture-integrated-smoke/`.

## Class 19 — transfer alignment does not enlarge caller-owned payloads

Signature: a WebGPU buffer update rounds its byte count to the required four-byte transfer
alignment and passes that larger count with the original frontend pointer. Allocation bounds can
still be valid while the final one to three transfer bytes lie beyond the caller's logical
payload. Validate the aligned size against the device allocation, retain the original pointer for
already aligned data, and otherwise copy only the logical bytes into owned zero-filled transfer
storage. Exercise native/wasm32 boundary parity and an ASan odd-size caller; do not infer source
padding from destination alignment. Callers must also branch on the transfer result before
freeing a static host payload or clearing dirty state; otherwise a rejected upload becomes
permanent silent data loss. See `sandbox/wgpu-storage-update-padding-repro/`,
`sandbox/wgpu-buffer-integrated-smoke/`, and `sandbox/wgpu-vertex-integrated-smoke/`.

## Class 20 — raw sRGB uploads do not perform render-attachment encoding

Signature: a texture clear normally relies on the render attachment to encode linear RGB into
sRGB storage, but a non-renderable texture dimension falls back to a repeated host texel and
`WriteTexture`. That copy stores its bytes verbatim, so linearly quantizing the clear color makes
the later sRGB sample decode it a second time. Apply the sRGB output transfer function to only the
RGB components before quantization on the raw-copy path; alpha stays linear. Bind both the stored
bytes and a native clear-then-sample round trip, because either check alone can miss a transfer
direction error. See `sandbox/wgpu-texture-srgb-clear-oracle/` and
`sandbox/wgpu-texture-integrated-smoke/`.

## Class 21 — emulated multi-draw needs one atomic indirect byte span

Signature: a backend expands one signed multi-draw request into individual WebGPU indirect calls
and computes `offset + i * stride` inside the active render pass. Negative frontend values become
large unsigned offsets, zero stride repeats one command instead of selecting tightly packed
commands, and a late range or multiplication failure is discovered only after earlier calls were
issued. Before pipeline or pass work, normalize zero stride to the indexed/non-indexed command
size, require four-byte alignment, reserve the final command, and bound the remaining
`(count - 1) * stride` with subtraction and division. Feed every call from that single proven span
and leave the result untouched on rejection. Exercise both 16/20-byte shapes, overlapping legal
strides, signed boundaries, alignment, exact-fit and one-byte-short allocations, and large-count
arithmetic in native and wasm32. See `sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 22 — signed dispatch geometry must be resolved before unsigned WebGPU calls

Signature: a backend receives signed compute workgroup counts, casts them directly into WebGPU's
unsigned dispatch API, and relies on one frontend binding that checks only upper bounds. Negative
values can therefore become huge dispatches, while other callers can exceed the per-axis limits
published by the backend. The indirect sibling can likewise issue its fixed three-word command
without proving that the buffer contains all 12 bytes. Resolve direct counts atomically against
the published per-axis capabilities before shader or pipeline work, preserving zero-count no-op
semantics, and validate an aligned indirect span with subtraction before opening a compute pass.
Exercise negative and exact-limit axes, zero dimensions, invalid capabilities, exact-fit and
undersized indirect buffers, alignment, and 64-bit boundary arithmetic in native and wasm32. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 23 — normalized direct-draw inputs are still signed at the backend boundary

Signature: a frontend uses zero draw counts as defaults, resolves them before backend dispatch,
but leaves every draw parameter signed. A backend then casts negative first/count values at each
unsigned graphics-API call after context, upload, pipeline, or pass work. Resolve the four values
once at method entry: require nonnegative first values and positive normalized counts, preserve the
full positive `int` domain, and leave the output unchanged on rejection. Reuse that one plan for
fan expansion plus indexed, non-indexed, single-pass, and layered calls. Do not add geometry bounds
the public API explicitly leaves to the graphics backend. Exercise each negative/zero field and
`INT_MIN`/`INT_MAX` boundaries on native and wasm32. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 24 — signed viewports need a distinct unsigned WebGPU scissor

Signature: multi-viewport emulation forwards Blender's signed viewport rectangle to both
`SetViewport` and `SetScissorRect`. WebGPU permits a bounded negative viewport origin, but its
scissor fields are unsigned and Dawn requires the complete scissor inside the render area;
casting a negative origin wraps, while an overshooting extent invalidates the command encoder.
Preserve the original viewport so clipping does not change the raster transform and intersect a
separate scissor with the framebuffer using widened arithmetic. Reject negative extents and
device-limit-invalid rectangles atomically, but retain legal zero extents and canonicalize fully
clipped rectangles to a contained zero scissor. This lets a no-fragment pass consume pending
attachment load actions instead of leaving stale pixels for a later read. Exercise negative and
partial edges, complete clipping, exact bounds, device limits, and `INT_MIN`/`INT_MAX` in native
and wasm32. Apply the same plan to direct and indirect multi-viewport paths. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 25 — clamped 2x2 mip kernels discard odd-axis edge texels

Signature: a render fallback downsamples every mip with a fixed 2x2 box and clamps each load to
the source bounds. For an odd source axis, the destination has floor(size/2) pixels, so no
destination footprint reaches the final texel; clamping never repairs the omission. Match
Blender's pinned native separable kernel instead: one tap for size one, two equal taps for even
sizes, and three position-dependent weights over odd sizes. Keep the complete production WGSL in
one callable helper, compile its axis plan for native and wasm32, and parse the exact shader with
the pinned Tint reader. Exercise first/middle/last odd footprints and a ramp whose final texel
changes the result. See `sandbox/wgpu-texture-integrated-smoke/`.

## Class 26 — bottom-origin window rectangles must preflight before a render pass

Signature: a framebuffer path converts `H - (y + height)` in signed `int`, clips the
viewport itself, and opens the render pass before deciding whether the rectangle is usable.
Negative origins then change the raster transform when clamped, integer-boundary state can
overflow during Y conversion, and skipping `SetViewport` after pass creation silently selects
WebGPU's whole-target default. Convert the bottom-origin coordinate with widened arithmetic,
preserve the signed viewport under Dawn's published bounds, and clip an enabled frontend scissor
independently into unsigned framebuffer space. Validate malformed rectangles atomically before
any pass allocation, but preserve a legal zero or fully clipped raster state when the pass owns
pending attachment load actions: encode a contained zero scissor so the pass consumes its clear
without producing fragments. A disabled scissor must remain disabled. Exercise partially visible
edges, fully clipped rectangles, target/device limits, oversized-but-clippable scissors, null
input, `INT_MIN`/`INT_MAX`, and pending load clears on native and wasm32. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 27 — ordinary offscreen passes must apply stored raster state

Signature: a backend fixes window viewport handling inside a shared render-pass constructor but
leaves ordinary offscreen passes on WebGPU's implicit whole-target viewport and disabled scissor.
First pin the offscreen coordinate convention with a native pixel oracle, then compose it with
the backend readback contract: when WebGPU physical row zero is read back as Blender's last row,
the rectangle itself still needs `top = H - y - height`. Clip-space Y reflection only changes
content inside a viewport and cannot relocate that viewport. Preserve the signed viewport
transform, clip an enabled scissor independently into the unsigned render area, and validate the
complete plan before any layered clear or pass allocation. Keep multi-viewport
emulation under its per-pass owner. Draw-pass raster state does not prove scissored framebuffer
clear semantics; audit and test clear paths separately. See
`sandbox/wgpu-offscreen-viewport-oracle/` and `sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 28 — attachment load clears cannot implement a scissored clear

Signature: a backend maps every framebuffer clear to render-pass `loadOp=Clear`, even though
Blender specifies that an enabled scissor clips color, depth, and stencil clears. WebGPU load
operations always clear the complete attachment and cannot consume dynamic scissor state. Pin the
logical lower-left footprint with a native pixel oracle, then select exactly one policy before
device work: disabled or exact-full scissor keeps the load-op fast path, an empty intersection is
a no-op, and a proper rectangle uses a typed fullscreen draw over `loadOp=Load` attachments.
Preserve integer color output types, use depth output plus stencil replace state, and carry the
same rectangle across every guarded array-layer pass. Explicit attachment load-action clears are
different: they remain full-subresource operations even when frontend scissor state is enabled.
Parse the exact shipping WGSL variants with pinned Tint and exercise window conversion, clipping,
aspects, integer boundaries, and layer exhaustion on native and wasm32. See
`sandbox/wgpu-framebuffer-scissored-clear-oracle/` and
`sandbox/wgpu-texture-integrated-smoke/`.

## Class 29 — aligned copy size does not imply an aligned buffer offset

Signature: a buffer read rounds its byte count to WebGPU's four-byte copy granularity and proves
the aligned range fits, but forwards the original source offset unchanged. Dawn validates source
and destination offsets independently, so a contained read at offset two still invalidates the
command encoder. Use one checked copy-span decision after size alignment: require nonzero aligned
size, aligned source and destination offsets, and subtraction-form containment for both buffers.
Bind the pure misalignment case to the shipping read seam before any encoder or asynchronous
ticket work. See `sandbox/wgpu-buffer-integrated-smoke/`.

## Class 30 — fallible creation must precede ownership commit

Signature: a backend creates a device resource with caller-owned initial data, ignores the
creation result, then frees the only host payload and marks the resource uploaded. An allocation
or mapped-range failure therefore becomes permanent data loss instead of a retryable condition.
Treat resource creation and ownership transfer as one transaction: return on failure, and mutate
the host pointer/uploaded state only after success. Exercise the exact shipping state machine with
a deterministic failure followed by retry, plus subrange, existing-resource, no-context, and
device-built branches on native and wasm32. See `sandbox/wgpu-buffer-integrated-smoke/`.

## Class 31 — a non-null error handle does not prove a mapped range

Signature: a mapped-at-creation staging buffer is checked for a null handle, but its
`GetMappedRange()` result is passed directly to `memcpy`. WebGPU implementations can retain an
error handle while exposing no mapped range, turning a recoverable update failure into a null
write before command validation can report it. Store and check the mapped pointer before copying,
unmapping, allocating an encoder, or submitting; return failure so callers retain retryable state.
Exercise the exact extracted shipping method with deterministic allocation failure, map failure,
the direct-write threshold, successful byte preservation, and exact operation ordering on native
and wasm32. See `sandbox/wgpu-buffer-integrated-smoke/`.

## Class 32 — transient resource creation must guard stateful GPU work

Signature: a backend allocates a short-lived buffer for an expanded draw path, assumes creation
succeeded, then flushes state or reaches `Queue::WriteBuffer`, command encoding, and pass assembly
with a null handle. Treat descriptor creation and handle publication as one transaction: create a
local candidate, reject null without mutating the output, then let the caller proceed only after
success. Bind every duplicated shipping path to the same transaction and require the guards to
precede their first queue operation. Exercise deterministic failure, exact descriptor fields,
atomic output preservation, and successful publication on native and wasm32. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 33 — cache publication is an ownership commit

Signature: a backend creates a sampler or pipeline, inserts its handle into a map or appends it to
a specialization-keyed sequence, and only then checks whether creation returned null. One
transient failure permanently poisons that key: later callers find the cached null and never retry
creation. Keep the candidate local, reject null first, and publish only a usable handle. When this
appears once, census every cache for the same create/publish order; framebuffer-local,
context-local, process-wide, and per-shader pools can duplicate it independently. Bind every
publication site to one source-order contract and exercise fail-once/succeed-once behavior with a
device-free handle/cache seam. See
`sandbox/wgpu-texture-integrated-smoke/` and `sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 34 — transient render helpers must guard every created handle

Signature: a render fallback checks its inputs and cached pipeline, but assumes its lazy shader
module, short-lived uniform buffer, and bind group all succeed. A failed module reaches pipeline
creation, a failed buffer reaches `Queue::WriteBuffer`, or a failed bind group reaches pass work,
turning a recoverable resource failure into validation errors or a null-handle call. Reject each
handle before the first dependent operation. Use one device-free buffer-creation transaction so
failure cannot overwrite the caller's handle, and bind the remaining guards to the exact shipping
source order. See `sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 35 — multi-pass resource failure must discard the whole command encoder

Signature: a dependent mipmap loop encodes earlier passes, then continues past a missing view or
uses another null transient handle and still finishes and submits the command buffer. That can
publish a holey mip chain whose later levels depend on absent intermediate results. Guard the
module and encoder before dependent work; return, rather than continue, on every failed view,
bind-group, or pass allocation so the local encoder and all prior passes are abandoned; and
validate the finished command buffer before the only queue submission. Exercise each failure
boundary, including a later pass after earlier encoding, against the exact extracted shipping
method on native and wasm32. See `sandbox/wgpu-texture-integrated-smoke/`.

## Class 36 — reserved asynchronous readback must fail terminal before mapping

Signature: a readback registry reserves in-flight capacity and a ticket, creates its staging
buffer, then assumes both command-encoder creation and `Finish()` succeeded. A null encoder is
dereferenced immediately; a null finished command buffer can still be submitted and followed by
`MapAsync`, leaving registry work pending for a copy that never existed. Encode the copy through
one checked transaction: reject a null encoder before copy work, reject a null command buffer
before submit, and submit exactly once only on success. On either failure, settle the reservation
with a specific terminal error, release every pinned backend handle, and install no map callback.
Exercise encoder failure, finished-buffer failure, and exact successful ordering with a
device-free native/wasm32 seam, then bind every texture and buffer kick to it. See
`sandbox/wgpu-buffer-integrated-smoke/`.

## Class 37 — pass creation is part of the command submission transaction

Signature: a compute or render path validates its pipeline, then assumes command-encoder,
pass-encoder, and finished-command-buffer creation all succeed. A null encoder is dereferenced, a
null pass receives dependent work, or a null finished buffer reaches queue submission. Treat the
complete sequence as one transaction: validate the encoder before beginning a pass, validate the
pass before invoking its body, end only a valid pass, validate `Finish()` before submission, and
submit exactly once only on success. Exercise deterministic failure at every handle boundary and
exact successful ordering with device-free native/wasm32 probes, then bind every duplicated
shipping caller to that transaction. See `sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 38 — a sanitizing resource builder is still a fallible factory

Signature: a shared bind-group builder filters null inputs before calling WebGPU, but its callers
assume the returned bind group is valid and pass it directly into compute, batch, or immediate
pass work. Input sanitation prevents a JavaScript-marshalling failure; it does not make the final
resource allocation infallible. Publish the transient candidate only after a non-null result, and
abort before the first dependent pass operation on failure. If an empty resource list is valid,
keep that state distinct from a required group whose creation failed. Census every caller of the
shared builder, exercise atomic failure/success on native and wasm32, and bind each caller to the
tested transaction with exact source-order checks. See `sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 39 — a caller-side null check cannot repair factory-internal use

Signature: a helper returns a pass handle and every caller checks it, but the helper applies
viewport or scissor state to the result of `BeginRenderPass()` before returning. A failed pass is
therefore used before the caller can observe null. Treat the helper itself as the publication
boundary: keep the candidate local, publish only a non-null handle, then perform dependent state
changes. Exercise atomic failure/success through the shared device-free handle contract and bind
the shipping factory's exact create/guard/state/return order. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 40 — a pipeline vertex plan is an all-or-nothing resource set

Signature: pipeline assembly declares one WebGPU vertex-buffer slot for every real source and
missing-attribute dummy, but draw encoding silently skips any slot whose allocation is absent.
Dawn requires every pipeline-declared slot at draw time, so the skipped binding converts a
recoverable allocation failure into command validation failure. Resolve the complete plan into a
temporary ordered handle list before creating an encoder or pass; reject the whole draw on the
first missing real or dummy buffer; publish the handle list only after every slot resolves; and
bind the proven list without nullable branches. Preserve an empty plan for procedural draws.
Exercise fail-fast, atomic-output, ordered-success, and empty-plan behavior device-free, then bind
direct batch, indirect batch, and immediate paths to the same helper. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 41 — index allocation failure must not change draw semantics

Signature: an indexed batch uploads its deferred index data, then derives `indexed` from whether
the resulting backend handle is valid. Allocation failure consequently falls through to a
non-indexed draw (and, for indirect draws, reinterprets a 20-byte indexed command as a 16-byte
non-indexed command), while other paths reach `SetIndexBuffer` through unchecked transient
handles. Resolve the required index handle before pipeline selection or command encoding; reject
a missing required handle without changing caller-owned state; make the non-indexed case explicit;
and bind only the resolved handle in direct, indirect, triangle-fan, and immediate paths. Exercise
missing-required, valid-required, and non-indexed cases device-free, then bind the exact shipping
source order. See `sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 42 — semantic fallback must not absorb resource-creation failure

Signature: a shader intentionally permits automatic pipeline-layout inference when its reflected
interface cannot describe a surviving binding, but the same helper also falls back after
`CreateBindGroupLayout` or `CreatePipelineLayout` returns null. The semantic fallback is valid;
the resource failure is not. Conflating them can silently restore the depth-texture and
unfilterable-float inference defects that required an explicit layout in the first place. Return
success only for the intentional uncovered-binding branch. Create both layout handles into local
candidates, preserve caller outputs on either failure, publish the pair only after both succeed,
and make a null resource fail shader finalization. Exercise first-handle failure, second-handle
failure, and ordered pair publication device-free on native and wasm32. See
`sandbox/wgpu-shader-frontend-integrated-smoke/`.

## Class 43 — compositor liveness begins at successful submission

Signature: a browser compositor directly replaces its persistent resize texture, publishes a
bind-group layout before the dependent present pipeline exists, then logs first pixels before
unchecked views, bind groups, encoders, passes, and command buffers reach the queue. A transient
failure can discard the last usable resize texture, leave mismatched dimensions or partial cached
state, dereference a null handle, and falsely release the loading UI. Keep the prior texture and
extent until replacement succeeds; publish reusable layout/pipeline state only as a complete pair;
encode every per-frame dependency inside one abortable transaction; and advance first-pixels and
present counters only after the complete command buffer is submitted. Exercise each allocation and
command boundary device-free on native and wasm32. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 44 — child initialization failure must stop parent publication

Signature: a platform window invokes `setDrawingContextType()` but ignores its status, keeps its
default validity flag set, and is then registered with the system's window manager and event queue.
The base class has already replaced the failed context with `GHOST_ContextNone`, so later code sees
a non-null window and context even though the requested drawing backend never initialized. Derive
window validity from the exact context-setter result, then validate the complete window before any
active-window assignment, callback registration, manager insertion, or initial event publication.
Destroy an invalid candidate without publishing its pointer. Exercise rejected/accepted context
statuses plus null, invalid, and valid window candidates device-free on native and wasm32, and bind
both shipping publication sites to the tested transaction. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 45 — one-shot state commits only after its GPU work is submitted

Signature: an explicit all-layer framebuffer load clear invokes a checked per-layer command
transaction but unconditionally changes the pending load action to `LOAD` after the void wrapper
returns. A failed view, encoder, pass, or finished command buffer therefore suppresses every retry,
and the next draw loads an attachment that was never cleared. Propagate success through the nested
clear helpers; retain the pending action on any failure; and commit it only after every selected
layer reached the queue. Exercise fail-first retention followed by a successful retry on native and
wasm32, then source-bind the materializer to the exact commit helper. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 46 — non-null WebGPU handles can still be validation-error objects

Signature: a resource or command helper treats `handle != nullptr` as successful creation,
publishes the object, submits the finished command buffer, or advances one-shot state. Dawn and
browser WebGPU instead return opaque non-null error objects for validation failures; the error is
observable only through a completed error scope. Wrap creation and command encoding in validation,
OOM, and internal scopes, retain candidates locally until all scopes settle cleanly, validate a
finished command before submitting it under a second scope, and commit liveness/state only after
that submit scope succeeds. Browser callbacks are asynchronous, so pending publication must be an
explicit state rather than a synchronous boolean. Command scopes introduce an additional ordering
hazard: if submission waits for a callback while a later direct queue write executes immediately,
the queue chronology changes. Reserve every command, `WriteBuffer`, and `WriteTexture` mutation in
one FIFO before starting validation; poison and cancel the remainder of the failed frame epoch,
then allow a later epoch to retry. Never let an asynchronous callback retain a stack reference;
copy upload bytes and capture reference-counted state. Exercise non-null rejected and clean
accepted objects plus pre-submit rejection on pinned Dawn, and preserve a device-free
native/wasm32 model. See `sandbox/dawn-probe/probe_error_handles.cc` and
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 47 — an asynchronous resource cache needs a durable pending state

Signature: a browser-side resource factory creates a non-null handle under an error scope, but
the cache either publishes it before `PopErrorScope` resolves or returns a provisional handle to
dependent command work. A synchronous bool cannot represent browser validation because the
callback runs only after the creating stack returns. Give each cache key one explicit pending
state, deduplicate repeated misses, retain the candidate in callback-owned storage, and publish
only after validation, out-of-memory, and internal scopes all settle cleanly. Rejection must erase
only the pending marker so the same key can retry; accepted old entries must remain untouched.
Callback state must outlive the owning context without capturing it. Exercise pending
deduplication, a non-null rejected object, clean retry, and cache-hit preservation device-free on
native and wasm32, then prove the exact helper against pinned Dawn. See
`sandbox/wgpu-pipeline-integrated-smoke/` and `sandbox/dawn-probe/probe_error_handles.cc`.
For a reusable resource with fixed initial bytes, initialize the local candidate through
`mappedAtCreation` before popping its creation scopes. A separate queued write can otherwise run
before validation settles or require publishing the provisional handle merely to initialize it.

## Class 48 — persistent resource metadata shares the handle's publication boundary

Signature: a persistent buffer stores its handle, allocated size, requested size, usage kind, and
readback capability in separate members immediately after `CreateBuffer`, or frees caller-owned
initial bytes merely because creation returned non-null. A browser callback can later reject that
error object, leaving published metadata without a valid resource and destroying the only retry
payload. Cache one composite allocation under a durable fixed key, retain the candidate and all
metadata until validation/OOM/internal scopes settle, and expose only the accepted composite.
Pending calls must deduplicate, rejected calls must retry, and a moved-from wrapper must remain a
safe empty object. When initial bytes are caller-owned, preserve them until the accepted composite
is observable, including a callback that settles between frames. Exercise pending metadata
invisibility, non-null rejection, clean retry, exact mapped bytes, and delayed ownership commit
against the byte-extracted shipping methods on native and wasm32, then use pinned Dawn only as a
software error-object control. See `sandbox/wgpu-buffer-integrated-smoke/` and
`sandbox/dawn-probe/probe_error_handles.cc`.

## Class 49 — transient resource validation must reserve queue chronology first

Signature: a short-lived buffer is created for one batch/immediate draw, its non-null candidate is
used to encode dependent work, and the browser reports only later that the candidate was a
validation/OOM/internal error object. A persistent cache is the wrong lifetime, while waiting
synchronously would deadlock the browser worker. Reserve an ordered frame-epoch gate before
creation, keep the candidate callback-owned through scope completion, and permit its provisional
handle only for CPU encoding whose submission is queued behind that gate. Rejection poisons the
current epoch and cancels every dependent queue mutation; the next frame may recreate and retry.
Support both completion orders: the scope can settle while its gate is active, or before an earlier
queue entry releases it. Never capture the stack-owned wrapper from the callback. Exercise literal
null, a non-null rejected object, clean next-epoch retry, both completion orders, native/wasm32
parity, and the exact helper on pinned Dawn as explicitly software-only non-receipt evidence. See
`sandbox/wgpu-pipeline-integrated-smoke/` and `sandbox/dawn-probe/probe_error_handles.cc`.

## Class 50 — texture validity has two publication shapes

Signature: a root texture or view returns a non-null Dawn error object, and callers immediately
encode work or publish a related handle before browser error scopes settle. A root Blender texture
cannot wait for an asynchronous callback without changing the frontend API, so reserve the ordered
queue gate first, keep shared accepted/rejected state in every copied subresource range, and allow
the provisional handle only for CPU encoding behind that gate. A standalone view uses the same
gate; a view created inside `command_encode_submit_scoped` must instead remain inside that one
enclosing scope so the complete command is rejected before submission. A private replacement that
owns both a texture and its view has a different boundary: cache and publish the composite pair
atomically, preserving the accepted old pair while a resize is pending and clearing only pending
state after rejection. Never capture a stack-owned texture wrapper in a scope callback. Exercise
pending queue order, non-null root/view rejection, clean retry, and pair-level atomic publication
on native and wasm32, then confirm the exact factories against pinned Dawn as explicitly
software-only non-receipt evidence. See `sandbox/wgpu-texture-integrated-smoke/` and
`sandbox/dawn-probe/probe_error_handles.cc`.

## Class 51 — explicit layout coverage and validation readiness are separate states

Signature: a shader has complete interface-map coverage, creates a non-null bind-group layout and
pipeline layout, and immediately exposes the pair. Browser validation resolves later, so an error
pair can be consumed by pipeline creation; treating the still-pending pair as `has_layout=false`
also silently selects Dawn auto layout even though the shader requires the explicit resource
types. Retain the CPU layout entries, mark covered layouts as required independently of readiness,
and publish the two handles atomically through one validation/OOM/internal scoped cache. Pipeline
lookup must stop while the required pair is pending and retry creation after rejection; only an
actually uncovered shader may use auto layout. Bind groups created before an enclosing command
scope need their own ordered resource gate, while bind groups created inside that command scope are
already rejected with the complete command before submission. Exercise pending deduplication,
non-null pair rejection, atomic clean retry, and same-epoch dependent-work cancellation on native
and wasm32, then confirm the exact generic gates against pinned Dawn as software-only non-receipt
evidence. See `sandbox/wgpu-shader-frontend-integrated-smoke/`,
`sandbox/wgpu-pipeline-integrated-smoke/`, and `sandbox/dawn-probe/probe_error_handles.cc`.

## Class 52 — shader compilation and WebGPU resource readiness are separate stages

Signature: shaderc/Tint returns valid WGSL, `CreateShaderModule` and pipeline factories return
non-null handles, and finalize or a cache miss immediately publishes them. Browser validation can
still reject any handle asynchronously, so a shader that discards its WGSL cannot retry and a
pipeline cache can permanently retain an error object. Preserve the final WGSL as CPU retry state,
scope the complete required module set as one atomic cache value, and let draw/dispatch lookup stop
while that set is pending. Only an accepted module set may enter a separately scoped render- or
specialization-keyed compute-pipeline cache. Keep accepted keys stable while failed keys retry. A
one-shot module/pipeline chain instead reserves an ordered transient resource gate before any
dependent command transaction, so rejection cancels the current frame epoch. Exercise pending,
non-null rejection, atomic clean retry, stable accepted entries, and distinct pipeline keys on
native and wasm32; use pinned Dawn only as explicitly software-control non-receipt evidence. See
`sandbox/wgpu-pipeline-integrated-smoke/` and `sandbox/dawn-probe/probe_error_handles.cc`.

## Class 53 — sanitized bind entries are not a complete shader resource set

Signature: the bind-group assembler drops absent, stale, invalid, or wrong-kind resources, then a
draw or dispatch treats the resulting empty list as proof that the shader has an empty group-0
layout. A partial non-empty list is equally unsafe: WebGPU requires every binding retained by the
final WGSL, including backend-injected push-constant and multi-viewport uniforms. Retain the exact
sorted surviving binding IDs during shader finalization, collect the unique IDs of entries that
carry live resources, and require the sets to be equal before allocating an encoder or pass. Only
an expected-empty and assembled-empty pair may skip bind-group creation. Exercise genuinely empty,
complete, required-but-empty, partial, extra, and duplicate-assembled cases on native and wasm32,
then source-bind compute, direct/indirect batch, multi-viewport, and immediate callers to the same
pre-command guard. See `sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 54 — render-pass load actions are submission transactions

Signature: framebuffer pass assembly changes an attachment from `CLEAR` to `LOAD` before a later
attachment view, bind group, finished command buffer, or queue submission can fail. The retry then
loads pooled contents that the rejected command never cleared. Reserve each logical clear in a
command-owned transaction, make later same-epoch passes encode `LOAD` behind that reservation, and
consume the action only after completed encoding and submission scopes accept the command. A
failed command releases its reservations; the ordered scheduler cancels later same-epoch work, so
the next epoch safely retries `CLEAR`. Bind each reservation to the load-store generation so a
stale callback cannot consume a newer frontend bind, and keep the shared tracker alive without
capturing the framebuffer. Exercise failure at a later attachment view and bind group, same-epoch
load behavior, clean retry, and generation replacement on native and wasm32. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 55 — resize requests and configured extents are different state

Signature: a browser resize immediately publishes new authoritative dimensions and configures the
surface, then asynchronously validates the matching persistent backbuffer. Rejection preserves only
the old texture, leaving a new surface paired with stale source dimensions; a fullscreen
`textureLoad` can then read beyond the old allocation. Store the latest requested extent separately
from the last complete configured surface/backbuffer state. Allocate and validate the candidate
first, discard a superseded candidate, and configure plus publish every size-bound field only for
the current accepted candidate. Presentation may continue on the old state only while the acquired
surface and backbuffer both exactly match its authoritative extent. Retry rejected requests from
the next present tick, so recovery does not depend on a duplicate browser resize event. Exercise
rejection preservation, supersession, atomic commit, exact present coherence, and no-event retry on
native and wasm32, then pass a real non-null texture error object through the same helper on pinned
Dawn as explicitly software-only non-receipt evidence. See
`sandbox/wgpu-pipeline-integrated-smoke/` and `sandbox/dawn-probe/probe_error_handles.cc`.

## Class 56 — synchronous window publication needs an asynchronously validated preflight

Signature: a synchronous platform-window constructor imports a pre-acquired browser GPU device,
then treats an unresolved canvas or merely scheduled surface/backbuffer setup as a successful
drawing context. Browser validation arrives through promises after the constructor returns, so a
window with no present path reaches the manager and event queue. Use the pre-main worker interval,
where the event loop is still available, to await canvas-context configuration and initial
backbuffer error scopes. Publish one complete import bundle only after every stage succeeds, carry
an exact failure-stage status into the synchronous constructor, and reject the child context before
parent window publication. Keep device-only offscreen contexts as an explicit mode whose success
does not imply a surface. Exercise every partial stage, non-null error-object cleanup, single entry
forwarding, and complete publication under the pinned JavaScript runtime; separately compile the
same status decision for native and wasm32. See `platform_web/shell/wgpu-preinit-worker.js` and
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 57 — surface acquisition status is part of the present transaction

Signature: a present path calls `GetCurrentTexture()`, checks only whether the returned texture
handle is null, discards every early-return result, and then reports swap success unconditionally.
The browser binding converts a `GPUCanvasContext.getCurrentTexture()` exception into an explicit
`Error` status plus a null texture. Treat only optimal/suboptimal success with a live texture as
presentable; retry `Timeout` without changing configuration, force `Outdated`/`Error` through a
fresh configuration, and recreate a `Lost` surface. A suboptimal texture may present once but must
request reconfiguration after its transaction settles. Return whether command validation was
actually scheduled so the synchronous GHOST boundary does not manufacture success for an
acquisition that never began. Exercise every status with both valid and malformed texture presence
on native and wasm32. See `platform_web/ghost/GHOST_WGPUTransaction.hh` and
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 58 — imported browser devices need an owned terminal-loss signal

Signature: a browser worker creates a native `GPUDevice`, emdawnwebgpu later imports it into C++,
and presentation relies on surface status plus handle truthiness after the device has been lost.
The port explicitly rejects `GetLostFuture()` on an imported device, while Dawn may retain non-null
error objects after loss; logging `device.lost` therefore does not give the GHOST context a usable
terminal state. In the device-creation realm, publish a monotonic generation-bound loss record
before publishing the device and update it from the browser promise only if that exact record is
still current. Sample the record before acquire or present work, treat missing/replaced/settled
records as terminal, disable outstanding callbacks, and clear every context-owned GPU handle once.
For devices created through the C++ fallback, install the descriptor callback at creation and let
it capture only shared atomic state, never the context pointer. Exercise pre-entry and post-entry
loss, stale promise order, sticky terminal state, and callback lifetime on native and wasm32; a
real forced-loss software-Dawn control may prove non-null error-object behavior but remains a
non-receipt. See `platform_web/shell/wgpu-preinit-worker.js`,
`platform_web/ghost/GHOST_WGPUTransaction.hh`, and
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 59 — pending persistent allocation must own one-shot frontend payloads

Signature: a persistent buffer correctly withholds its non-null candidate until browser error
scopes settle, but `StorageBuf::update()` or `UniformBuf::update()` returns when allocation is
pending and drops the caller's only byte copy. Creation later publishes an empty buffer, while a
rejected candidate also loses the initialization needed by a clean retry. Open an owned payload
queue before resource creation, copy every aligned update and clear in frontend order, leave the
queue retryable on rejection, and drain it exactly once from callback-owned state after the
composite allocation publishes. Deferred UBO ownership may be released only after that queue has
accepted the bytes; binding still waits for the allocation itself. Exercise a single actual
frontend create/update call, multiple pending update/clear operations, non-null rejection plus
resource-only retry, and exact sentinel ordering on native and wasm32. Use pinned Dawn only as an
explicit software error-object control. See `sandbox/wgpu-buffer-integrated-smoke/` and
`sandbox/dawn-probe/probe_error_handles.cc`.

## Class 60 — nested prerequisite commands cannot reserve behind their consumer

Signature: an ordered draw transaction reserves its FIFO ticket before invoking its encode
callback, while framebuffer pass assembly inside that callback discovers an all-layer clear and
opens a second command transaction. The draw therefore submits first even though its staged load
action encodes `LOAD`; the later clear reads as a prerequisite in source but behaves as a
post-draw overwrite on the queue. Preflight the complete load pass, reserve every materialized
clear before reserving the dependent draw, and join their asynchronous results in one idempotent
completion group. Commit the shared load-action generation only when all clears and the draw
validate; any rejected or canceled member rolls the generation back for a later epoch, and a stale
group cannot consume a replacement bind. Exercise clear failure, draw failure, clean order, and
generation replacement through the real FIFO on native and wasm32, then source-bind every direct,
indirect, multi-viewport, and immediate caller to preparation-before-command order. See
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 61 — scheduling an upload is not an ownership commit

Signature: `Queue::WriteBuffer` or a mapped staging copy returns normally, so a VBO clears its dirty
range or a deferred UBO frees its attached CPU data before the surrounding browser implementation
error scope settles. A later validation, out-of-memory, or internal error then leaves no exact bytes
for retry; Emscripten is especially exposed because the scope callback cannot complete within the
synchronous frontend call. Give every upload a durable pending/accepted/rejected transaction, copy
its exact byte range into callback-owned queue state, and release that copy only on accepted scope
completion. Rejection retains the entry for a new scheduler epoch, while frontend dirty/attached
ownership remains live until the retry accepts. Exercise delayed direct writes, direct rejection,
staged encoding and submission rejection, caller-buffer mutation after scheduling, deferred UBO
cleanup, and clean retry on native and wasm32. Use a real non-null pinned-Dawn validation error only
as explicitly software-control non-receipt evidence. See `sandbox/wgpu-buffer-integrated-smoke/`
and `sandbox/dawn-probe/probe_error_handles.cc`.

A durable payload is still insufficient when its owner leaves a one-bit dirty flag set while the
transaction is pending. A later CPU mutation cannot raise an already-set bit, so acceptance of the
older snapshot can clear the newer work and free its host bytes. Consume the dirty bit only after
the queue retains the exact snapshot; acceptance may release ownership only when the bit remains
clear. Apply the same rule to derived buffer-texture expansions. Regress the exact stock frontend
setter followed by A/B acceptance order, not a copied state machine. See
`notes/m3-gpu-upload-generation-r8-20260824.md`.

## Class 62 — a command scope cannot capture an earlier resource error

Signature: compute assembles a bind group before opening the dispatch command's implementation
error scopes, accepts Dawn's non-null validation-error object as a usable handle, and only then
encodes the pass. The later command scope cannot retroactively capture the resource-creation error,
so it reaches the device's uncaptured callback even if command submission eventually fails. Reserve
an ordered transient resource gate, push validation/out-of-memory/internal scopes around
`CreateBindGroup`, and place the dependent command behind that gate. A rejected group cancels only
its frame epoch; a clean later epoch recreates the group and may publish the dispatch. Exercise
direct and indirect paths with non-null error objects, an uncaptured-error counter, cancellation,
and clean retry on native and wasm32; use pinned software Dawn only as explicit non-receipt control.
See `sandbox/wgpu-pipeline-integrated-smoke/` and `sandbox/dawn-probe/probe_error_handles.cc`.

## Class 63 — spontaneous acquisition callbacks cannot own a raw platform context

Signature: an asynchronous browser adapter or device request captures a raw platform-context
pointer, while context destruction invalidates only later error-scope callbacks. Delivering either
request after destruction dereferences freed state; an adapter success can also start a device
request and a device success can publish readiness after the owner is gone. Give both request
callbacks one shared owner-lifetime gate, invalidate it first in the context destructor, and route
all owner access, completion, and follow-on acquisition through the gate. A delayed callback then
discards its returned WebGPU handle without touching the owner. Exercise delayed adapter and device
delivery after destruction under AddressSanitizer, retain an unsafe raw-owner control that ASan
must reject, and compile the accepted contract for native and wasm32. See
`platform_web/ghost/GHOST_WGPUTransaction.hh` and `sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 64 — terminal device state must gate already-scheduled callback work

Signature: a device-lost callback publishes only shared terminal state, while owner cleanup and
callback-lifetime invalidation wait for the next public platform entry. Resize, pipeline, and
present callbacks already queued before the loss can therefore configure a surface, publish GPU
handles, submit work, or record a present during that interval if they check only owner lifetime.
Capture the shared device state in every fallible completion and consult it immediately before
Configure, handle publication, queue submission, and present bookkeeping. Keep separate guards at
each nested asynchronous stage: a creation check cannot protect a later configuration completion,
and a command-validation check cannot protect submission or its final commit. Exercise closures
created under an active state, signal loss before delivery, and require zero post-loss operations
while retaining an active-state control. See `platform_web/ghost/GHOST_WGPUTransaction.hh` and
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 65 — a poisoned asynchronous FIFO must drain iteratively and forget unreachable epochs

Signature: one rejected queue transaction marks its frame epoch failed, and every already-ready
follower cancels by calling the same completion path recursively. A product-sized burst can then
consume one native or wasm stack frame per follower, while a separate failed-epoch set retains one
entry forever for every bad frame. Give the drain one mutex-protected owner flag: synchronous
completion merely releases the active entry and the existing owner continues its loop; a truly
asynchronous completion reacquires ownership after the old drain returns. Count queued references
per epoch, retain a failed epoch while it remains current so newly reserved same-frame work still
cancels, and prune it once a later epoch is current and no queued entry can carry it. Exercise a
failed head plus 100,000 resolved followers, then 100,000 distinct failed epochs and a clean retry
on native and wasm32. See `sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 66 — callback validity must exclude in-flight owner access

Signature: a delayed completion loads a non-null owner from a shared atomic gate, context
destruction clears that gate and frees the owner, and the completion then dereferences the pointer
it loaded before invalidation. A check-then-use token prevents new delivery but does not synchronize
an already-running callback. Register each delivery while holding the lifetime gate, stop acceptance
and clear the owner before destruction, and wait for deliveries running on other threads before
releasing owner storage. Destruction from inside a callback must exclude the caller's active delivery
from that wait so a reentrant completion cannot deadlock. Exercise concurrent destruction, delayed
post-invalidation delivery, reentrant self-destruction, and an unsafe AddressSanitizer control; bind
every asynchronous shipping completion to the same gate and require native/wasm32 parity. See
`sandbox/audit-r8/`.

## Class 67 — imported device loss belongs in callback-owned state

Signature: JavaScript owns an imported browser device's `GPUDevice.lost` promise, while C++ copies
only an initially active atomic state. The owner polls the JavaScript signal at public entry points,
but callbacks already queued between those polls see the stale atomic and may still configure,
publish, or submit. Give the shared callback state the exact imported generation and a loss observer;
every completion samples the observer before work and makes missing, replaced, or settled signals a
sticky terminal transition. Fallback devices retain the same state object without an imported
observer. Exercise pending, settled, sticky, and replacement observations on native and wasm32, and
source-bind every configuration/publication/submission completion to the callback-owned state. See
`platform_web/ghost/GHOST_WGPUTransaction.hh` and `sandbox/audit-r8/`.

## Class 68 — lifetime-safe callbacks may still race their shared owner

Signature: a callback lifetime gate registers concurrent deliveries and makes destruction wait,
but releases its mutex before invoking either completion. `AllowSpontaneous` explicitly permits
delivery on arbitrary threads, so two resize, pipeline, or present completions can concurrently
read and mutate the same non-atomic GHOST context fields even though neither can outlive the owner.
Serialize owner access for the whole delivery with a recursive mutex: invalidation from another
thread waits for the active callback, while nested delivery and self-destruction on the callback
thread remain reentrant. Keep cancellation as a state-only operation so terminal loss can reject
future deliveries without waiting for one already running. Exercise two held concurrent callbacks,
require peak owner access of one, then require nested delivery and concurrent destruction to finish
on native and wasm32. See `platform_web/ghost/GHOST_WGPUTransaction.hh` and `sandbox/audit-r8/`.

## Class 69 — callback serialization must be the owner's execution boundary

Signature: spontaneous callbacks share a recursive mutex, but public platform methods and terminal
cleanup access the same non-atomic owner fields without that mutex. Callback-to-callback delivery
is serialized while callback-to-owner mutation still races. Destruction has a companion admission
hole when invalidation waits for the execution mutex before setting its terminal state: an active
callback can re-enter, or a queued callback can win the mutex, after destruction has begun. Give
callbacks and every stateful public owner method one shared reentrant execution token. Terminal
cleanup takes that token before clearing fields, then closes admission without waiting. Destruction
closes admission before it waits for the token and never holds the state mutex during that wait, so
an already-admitted callback can finish or destroy its own owner without lock inversion. Retain a
shared gate reference until each token releases. Exercise callback-vs-owner and callback-vs-cleanup
barriers, active-callback destruction, late nested and queued delivery, self-destruction, and an
unsafe AddressSanitizer control in native and wasm32. See
`platform_web/ghost/GHOST_WGPUTransaction.hh` and `sandbox/audit-r8/`.

## Class 70 — durable FIFO payloads still need one reservation owner

Signature: a replay call marks an ordered deque snapshot in flight, releases its mutex, and
reserves one scheduler ticket per entry. A concurrent caller can retain a newer payload, skip the
older in-flight entries, and reserve its ticket between two entries of the earlier snapshot. The
scheduler then faithfully executes the wrong reservation order, so overlapping writes publish an
older value last. Give replay one mutex-protected drainer flag and let that owner repeatedly select
and reserve every available deque entry before releasing ownership; completion remains asynchronous
and independently synchronized. Stamp each entry with the current drain generation so a synchronous
rejection stays retryable without being selected repeatedly by the same drainer. A concurrent
retain/replay call returns to the active drainer,
which observes the new tail on its next selection pass. Exercise barriers after the first ticket to
force E1/E3/E2 overtaking in the broken control, then require E1/E2/E3 reservation and execution
plus E3 final bytes on native and wasm32. See `sandbox/wgpu-buffer-integrated-smoke/`.

## Class 71 — fallback device loss must settle pending asynchronous initialization

Signature: a fallback device-lost callback marks callback-owned terminal state while backbuffer
creation or surface configuration is pending, and those later completions return when they observe
loss. Neither path clears its pending flag or invokes the ready callback, so startup remains gated
forever without another public owner boundary. Capture only the shared device state and synchronized
owner-lifetime gate in the loss callback, publish loss before owner delivery, then route one
idempotent terminal transition through that gate. The transition cancels future delivery, clears
all pending work and GPU handles, and invokes failed initialization settlement exactly once as its
final owner action. Exercise independent loss during both pending stages, duplicate loss, and late
completion delivery on native and wasm32; retain a source binding that forbids a raw owner capture.
See `sandbox/audit-r8/`.

## Class 72 — a self-destroying callback cannot execute from owner member storage

Signature: an initialization settlement calls a `std::function` member directly, and the callable
deletes the context that owns that member. Destruction frees the active callable storage while its
`operator()` is still executing, so even a final callback with no later owner-field access has a
heap-use-after-free. Move the callback into a local, explicitly clear the member, and invoke the
local as the settlement path's final action. Exercise a production-shaped callback that deletes
its owner, continues inside its own callable storage, and rejects later owner delivery under native
AddressSanitizer and wasm32; retain the direct member invocation as an unsafe ASan control. See
`sandbox/audit-r8/`.

## Class 73 — transient staging creation needs an earlier queue reservation

Signature: a large buffer upload creates a mapped staging buffer before the dependent command
helper pushes implementation scopes. WebGPU may return a non-null validation, OOM, or internal
error object, so checking only the handle and mapped pointer leaves creation uncaptured and lets
dependent command validation stand in for the wrong operation. Reserve an ordered transient
resource gate before staging creation, retain its provisional handle through scope settlement, and
reserve the command ticket behind it. A rejected resource poisons the current frame epoch and
cancels the dependent command; a later epoch retries from the payload queue's owned bytes. Exercise
a non-null error object with an uncaptured-error counter, same-epoch cancellation, exact retained
bytes, and clean retry on native and wasm32. See `sandbox/wgpu-buffer-integrated-smoke/`.

## Class 74 — callback source counts can certify dead text instead of ownership structure

Signature: a source gate counts a delivery spelling and rejects one narrow raw-owner capture, so a
comment can replace a removed delivery while an alias, implicit outer capture, or added callback
evades the intended census. Lex the source with comments and literals excluded, locate every
callback by enclosing method, callee, argument position, and balanced lambda structure, then require
its exact explicit captures, owner-gate call, and callback-time terminal-state check. Keep mutation
controls that preserve the retired raw count while removing a real gate, replace an explicit capture
with a default, and add a callback; all must fail. Pair that source manifest with a device-free
production-shaped matrix covering every named callback before loss and after loss/destruction on
native and wasm32. See `sandbox/audit-r8/`.

## Class 75 — wasm32 memory layout is not Blender's historical 32-bit file layout

Signature: a Wasm build can load a native `.blend` and save it successfully, but stock native
Blender rejects the Wasm output with `unexpected data size` or reads shifted fields such as a null
Scene root collection. Both ABIs use four-byte pointers, yet wasm32 naturally aligns 64-bit
scalars to eight bytes while Blender's canonical 32-bit file layout is the historical i386
four-byte-alignment model. SDNA records type sizes and members, not member offsets, so emitting
wasm32's compiled type lengths does not make its raw struct bytes portable. Keep the generated
runtime SDNA for live memory and undo memfiles, emit a second canonical `size_32` SDNA for regular
files, force comparison when either member offsets or tail padding diverge, and reconstruct each
struct field-by-field before remapping its pointers. Use makesdna's verified runtime-offset table
on the memory side only; the file side retains SDNA's sequential historical walk. Tag parsed undo
SDNA as runtime-layout and use the same table for recursive pointer traversal, because offsets are
otherwise absent there too. Preserve native generated output byte-for-byte and prove stock-native
reload, an old BHead4 corpus round-trip, and global undo. See
`patches/0248-wasm32-canonical-blend-write.patch`,
`notes/m7-wasm32-write-cross-abi-20260824.md`, and
`sandbox/m7-wasm32-write-cross-abi/`.

## Class 76 — an owner-callback census must begin at the asynchronous API registration

Signature: a structural source gate manifests every known owner delivery and rejects raw `this`,
but it discovers callbacks only by the expected lifetime-gate call inside their bodies. A new
`AllowSpontaneous` callback can capture an alias assigned from `this`, access the owner directly,
and leave the old role count unchanged. Inventory every literal spontaneous mode occurrence as one
complete call argument, then bind its enclosing method, exact callee, mode/callback argument
positions, and callback form. Classify shared owner-neutral dispatchers explicitly and tie every
owner-affine registration back to a role whose continuation enters the shared lifetime gate. Keep
an in-memory mutation that adds a differently named raw-owner alias at a new registration; it must
fail even though the original delivery-role manifest is otherwise unchanged. See
`sandbox/audit-r8/callback_census.py` and
`notes/m4-ghost-callback-registration-census-r9-20260824.md`.

## Class 77 — missing wasm fenv status needs a software exception contract, not a permanent no-op

Correction to the initial Class 2 compile-only guidance above: defining absent Emscripten
`FE_DIVBYZERO`/`FE_INVALID` macros to zero is sufficient only to compile and leaves Blender's
expression error contract wrong. Keep native hardware fenv checks, but on wasm accumulate explicit
divide-by-zero and invalid-operation status at every evaluated opcode and during constant folding.
Classify exact poles separately from overflow, do not turn propagated quiet NaNs into new invalid
operations, inspect signaling-NaN bits before arithmetic quiets them, and cover composite helpers
at their primitive operations so an unrelated NaN cannot hide an invalid branch. Regression-control
ordinary, reduction, comparison, and short-circuit opcodes on both native and wasm. The current
canonical implementation passes the same 144 focused cases and all 1,667 BLI tests on both.
See `notes/m1-fenv-deferral-closure-20260824.md` and the current canonical diff for
`source/blender/blenlib/intern/expr_pylike_eval.cc`.

## Class 78 — an asynchronous child must retain the parent operator's terminal input

Signature: a generic stroke handler owns an opaque mode-specific handle and destroys it as soon as
mouse release or keyboard confirmation finishes the stroke, while that handle now owns a pending
GPU request. Returning to the event loop without intercepting the finish event either frees the
request too early or loses the exact input needed to complete stock teardown. Propagate an explicit
complete/pending/failed result through the opaque interface, retain only a custom-data-free copy of
the exact terminal event in the parent operation, and replay a sanitized copy through the original
modal dispatcher after a bounded timer observes settlement. New motion may supersede the pending
request, but finish remains single-owner; context or protected-state drift, unsafe event payloads,
timeout, failure, and cancellation all converge on cleanup that removes the timer before destroying
the child handle. Exercise native-immediate completion, pending finish replay, supersession, drift,
timeout, failure, and cancellation with byte-identical native/wasm32 output. See
`patches/0261-m5-painting-depth-continuation.patch` and `sandbox/m5-painting-depth/`.

## Class 79 — generic gestures discard pending operator custom data before returning

Signature: a generic box gesture calls an operator's `exec`, treats every result other than
`OPERATOR_FINISHED` as cancellation, and frees its gesture-owned `op->customdata` before returning
to the operator's modal wrapper. An asynchronous `exec` therefore cannot replace custom data with
its readback state, and returning `OPERATOR_RUNNING_MODAL` alone loses the continuation. Keep the
request in an operator-keyed owner list while the gesture is live; after the generic modal helper
has ended the gesture, the wrapper finds that exact request, installs its bounded timer state, and
continues. Direct execution may attach immediately, while native-ready requests still finish inside
the original gesture call. New same-window/region requests supersede older owners, and context
drift, Escape, gesture cancellation, timeout, backend failure, and external cancellation all remove
the timer, unlink the request, and cancel its GPU ticket before freeing state. Exercise native-ready,
pending handoff, exact timer identity, newest-wins, and every terminal path on native and wasm32.
See `patches/0262-m5-zoom-border-depth-continuation.patch` and
`sandbox/m5-zoom-border-depth/`.

## Class 80 — asynchronous device input must own and replay its custom payload FIFO

Signature: an input operator reads a typed motion structure through `event->customdata`, performs
a synchronous depth fallback during its starting event, and then applies every later device delta
to accumulated view state. A shallow `wmEvent` copy leaves the continuation pointing at
window-manager-owned memory, while retaining only the latest event drops non-commutative motion.
Copy the typed payload beside every retained event, repoint each event at its owned copy, and queue
the exact bounded FIFO while the producing depth request settles. Preserve bounds-first behavior
and native-immediate completion; after settlement, replay the starting motion and each queued delta
in order through the stock handler. A queued new starting motion may transfer the remaining FIFO
to a successor request, but no event may be applied twice. Producing-view drift, timeout, backend
failure, queue overflow, Escape, and external cancellation must remove the exact timer and cancel
the GPU ticket before freeing any payload. Exercise deep-copy ownership, FIFO ordering, queue
bounds, chained starting events, and every terminal path on native and wasm32. See
`patches/0263-m5-ndof-depth-continuation.patch` and `sandbox/m5-ndof-depth/`.

## Class 81 — a reusable depth cache needs an owned transfer before caller continuations

Signature: point and rectangle depth consumers use owned requests, but tools that reuse the full
viewport depth cache still call a synchronous texture read. Converting those callers directly
without a shared primitive either duplicates byte-layout logic or retains caller memory while the
browser map callback is pending. Start one exact full-texture request, validate both allocation
arithmetic and the signed indexing range used by `ViewDepths`, and retain the producing region,
dimensions, and view/projection matrices. Transfer one cache only after exact-size settlement and
only while that producing view still matches; reset, backend failure, size mismatch, drift, and
destruction all cancel the owned request. Keep the native synchronous helper until every cache
consumer has its own bounded continuation—the primitive alone does not close the family. Exercise
pending and immediate completion, consume failure, replacement, invalid geometry, and producing-
view drift on native and wasm32. See `patches/0264-m5-depth-cache-readback-primitive.patch` and
`sandbox/m5-depth-cache-readback/`.

## Class 82 — an already-overridden depth pass needs an explicit asynchronous prepare path

Signature: a modal drawing tool asks the shared View3D helper for a full depth cache, but the helper
returns early when its override flag is already set unless a synchronous output pointer forces a
redraw. Replacing only the read with an owned request therefore risks sampling an old texture, while
keeping the output pointer blocks the browser event loop. Factor the stock depth pass behind an
explicit force flag and expose a draw-only prepare call that never allocates or reads a cache. Start
the owned request immediately afterward. If it is pending, retain the producing context and a
bounded, custom-data-free event FIFO, poll on one identified timer, then transfer the cache and
replay through the unmodified modal dispatcher. Preserve native-immediate execution and the stock
initial-failure fallback; context drift, unsafe payloads, overflow, timeout, backend failure,
Escape, and external cancellation must retire timer, FIFO, and request together. Exercise both
wait-for-input and immediate-start operators on native and wasm32. See
`patches/0265-m5-curve-depth-cache-continuation.patch` and
`sandbox/m5-curve-depth-cache/`.

## Class 83 — replay must resume after any state transition already performed

Signature: a modal event starts a stroke and only then discovers that its first point needs an
asynchronous depth cache. Replaying that mouse press through the whole modal dispatcher after
settlement repeats the already-completed idle-to-painting transition; the dispatcher now sees an
active stroke and interprets the same press as its terminal button event. Retain an explicit resume
disposition beside the queued initiating event. After cache transfer, resume that event at the exact
post-transition apply seam, while later events still enter the stock modal dispatcher in FIFO order.
If one replayed event invalidates the cache and starts a successor request, transfer every remaining
event to the successor FIFO without applying or dropping it. Preserve immediate-ready execution on
the original stack, and make context drift, unsafe payloads, overflow, timeout, backend failure, and
external cancellation retire the timer, request, FIFO, and uncommitted stroke together. Exercise
the initiating-event seam separately from ordinary replay on native and wasm32. See
`patches/0266-m5-annotation-depth-cache-continuation.patch` and
`sandbox/m5-annotation-depth-cache/`.

## Class 84 — a recorded operator can become modal only after snapshotting its consumed input

Signature: an operator's `exec` callback iterates an RNA collection and performs synchronous GPU
reads between points or stroke boundaries. A pending browser read cannot retain borrowed RNA
iteration state, and restarting `exec` would repeat already-applied points. Snapshot only the exact
fields consumed by stock replay into owned storage, retain an explicit point cursor, and advance
that cursor only after the point has been applied. Preserve the original boundary order: acquire
the cache required to finish the preceding stroke, finish it, initialize the next stroke, then
resume the same unconsumed point. Let an immediately ready request finish on the original `exec`
stack; install the existing bounded modal poller only when a request is genuinely pending, and
swallow unrelated events while owned recorded input is authoritative. Backend failure, context
drift, timeout, Escape, and external cancellation must release the request, timer, cache, and
snapshot together. Exercise native-ready, chained pending generations, input-snapshot isolation,
non-depth and eraser modes, exact boundaries, and every terminal guard under native and wasm32.
See `patches/0267-m5-annotation-recorded-depth-cache-continuation.patch` and
`sandbox/m5-annotation-depth-cache/`.

## Class 85 — a shared modal dispatcher owns both processed samples and terminal semantics

Signature: a paint operator creates a placement helper during its first processed sample, but
surface or stroke projection needs an asynchronous full-viewport depth cache. Retaining only the
raw initiating event is insufficient once the shared paint dispatcher has already converted that
event into an `InputSample`; retaining only samples is also insufficient because release and
confirm events perform dispatcher-owned line or anchored-brush finalization. Let the operation own
the placement request, exact first sample, and bounded FIFO of already-processed generated samples,
while the modal stroke owner owns the one identified timer and a custom-data-free copy of the
terminal event. Preserve immediately ready and non-depth execution on the original stack. After
settlement, apply the first sample exactly once, replay generated samples FIFO, then feed the
sanitized terminal event back through the stock dispatcher rather than calling the operation's
finish hook directly. Producing manager/window/screen/area/region/view/scene/object drift, backend
failure, timeout, sample overflow, Escape, and external cancellation must retire the timer, request,
placement cache, FIFO, and terminal event together. Exercise terminal line-end replay separately
from sample replay, because both paths can otherwise look complete while losing different stock
semantics. See `patches/0268-m5-grease-pencil-depth-cache-continuation.patch` and
`sandbox/m5-grease-pencil-depth-cache/`.

## Class 86 — an invoke continuation needs a pre-initialized modal teardown

Signature: one shared operator invoke blocks for a full viewport depth cache before it projects its
first control point, creates navigation state, mutates editable geometry, or installs its preview
callback. Move the entire post-cache tail into one ready-only helper and snapshot the invoke-time
operator properties and start coordinates before starting the owned request. A pending request must
still own the modal cursor, one identified timer, and a bounded custom-data-free event FIFO, but it
must not expose navigation, drawing, preview, or control-point state until settlement. Validate the
producing manager/window/screen/area/region/view/depsgraph/scene/object/layer/drawing/paint/brush
identity on every owned tick, then initialize exactly once and replay retained events through the
stock modal dispatcher. Preserve the synchronous helper's initial read-failure projection fallback;
a later backend failure, view drift, timeout, unsafe payload, overflow, Escape, or external cancel
uses an uninitialized exit branch that retires the timer, request, FIFO, and cursor without touching
draw handles or geometry that do not yet exist. Exercise every operator sharing the invoke, initial
fallback, pre-projection suspension, FIFO/navigation replay, and both pre/post-initialization
teardown on native and wasm32. See
`patches/0269-m5-grease-pencil-primitive-depth-cache-continuation.patch` and
`sandbox/m5-grease-pencil-primitive-depth-cache/`.

## Class 87 — an atomic result helper needs its asynchronous prerequisite hoisted to the owner

Signature: a modal operator calls one of several library helpers, and each helper performs the same
synchronous full-viewport depth read immediately before expensive or irreversible result work.
Starting a continuation inside the helper is too late: its borrowed arguments and partially built
image or triangulation result cannot survive a browser tick. Construct the shared placement in the
operator before any editable-data mutation, start its owned request there, and pass the ready
placement explicitly through every helper signature. Retain only the exact triggering event when
the stock operator would have completed on that event; unrelated events are swallowed rather than
replayed into an operation that should already be terminal. Preserve non-depth, immediately ready,
and initial-read-failure fallback on the original stack. A pending request uses one identified,
bounded timer plus producing manager/window/screen/area/region/view/depsgraph/scene/view-layer/
object/data/layer/frame/paint/brush guards; later failure, drift, timeout, Escape, or external
cancellation retires the timer, event, placement, and request before any result helper runs.
Exercise each result algorithm separately and prove that fit inputs, boundary mask, fill point, and
solver choice remain exact across settlement. See
`patches/0270-m5-grease-pencil-fill-depth-cache-continuation.patch` and
`sandbox/m5-grease-pencil-fill-depth-cache/`.

## Class 88 — a virtual initializer needs one shared post-initialize first-event seam

Signature: a shared modal base invokes a subclass initializer and then immediately consumes the
initiating event through a file-local helper. One subclass needs to suspend initialization for an
asynchronous prerequisite, but returning `RUNNING_MODAL` from the virtual initializer skips both
the base's modal-handler registration and its first-event work; replaying the whole base invoke
would instead reread properties and repeat pre-initialize state. Expose one narrow base method that
contains only the existing post-initialize first-event helper. The pending subclass installs the
modal handler once, snapshots a custom-data-free initiating event plus a bounded safe FIFO, and
calls that seam exactly once after its prerequisite and ready-only tail settle. Replay later events
through the unchanged base modal method. Keep non-depth, immediately ready, and initial-read-failure
paths on the original stack; context drift, backend failure, timer-allocation failure, timeout,
unsafe payload, overflow, Escape, external cancellation, and destruction must retire the request,
timer, initiating event, and FIFO before any keyframe, drawing, transform, or other mutable tail is
captured. Exercise immediate/deferred first-event identity and a queued terminal event separately.
See `patches/0271-m5-grease-pencil-pen-depth-cache-continuation.patch` and
`sandbox/m5-grease-pencil-pen-depth-cache/`.

## Class 89 — a temporary render override must end before an invoke continuation suspends

Signature: an invoke callback temporarily changes viewport render state, synchronously reads a
full depth cache, restores the viewport, then captures selected objects and transform backups for
modal use. Replacing only the read can leak the temporary render state across browser ticks or
capture mutable state before the cache is valid. Allocate the operation owner first, constrain the
override to a draw-only prepare call, and restore it before readback initialization or any return.
If the request is pending, retain a custom-data-free initiating event plus a bounded safe FIFO and
do not collect selection or backups. After exact producing-context settlement, transfer the cache,
run one ready-only stock initialization tail, then replay the FIFO through the unchanged modal
dispatcher. Track whether initialization occurred so pending cancellation never restores backups
that were not created. Exercise pass-through, immediate ready, initial no-depth cancellation,
queued terminal events, backend/consume failure, drift, timeout, queue bounds, and external cancel
on native and wasm32. See
`patches/0272-m5-object-axis-target-depth-cache-continuation.patch` and
`sandbox/m5-object-axis-target-depth-cache/`.

## Class 90 — a shared stack-data initializer needs ownership lifted into every caller shape

Signature: click, linked-pick, generic gesture, persistent circle, and brush operators all create
stack-local traversal data through one helper that synchronously fills a full depth cache. The
helper cannot suspend because its output aliases the caller's stack, while no single operator
owner covers direct `exec`, invoked modal, generic-gesture handoff, and persistent custom data.
Split the helper into an opaque one-shot prepare/consume session and a ready-only stack-data fill.
Lift session ownership into each caller shape: extend the existing click owner, give linked-pick an
identified timer, attach box/lasso to the generic gesture owner, retain circle state for both
persistent and direct execution, and delay brush initialization before random generators or stroke
state exist. Snapshot exact operator inputs and queue only custom-data-free events behind bounded
FIFOs. Validate manager/window/screen/area/region/view/depsgraph/scene/view-layer/object/edit and
mode identity before transfer, including the XRAY decision that bypassed depth at preparation.
Consume once, enter the unchanged traversal or modal dispatcher, and retire every timer/session/
FIFO on drift, failure, timeout, overflow, Escape, external cancel, or destruction. Exercise each
caller shape independently on native and wasm32; a single generic modal model will miss direct and
persistent-owner lifetime bugs. See
`patches/0273-m5-particle-edit-depth-cache-continuation.patch` and
`sandbox/m5-particle-edit-depth-cache/`.

## Class 91 — optional GPU telemetry cannot validate a presentation transaction

Signature: a browser preflight configures a WebGPU canvas, acquires its first texture, waits one
event-loop turn for `uncapturederror`, and publishes the surface when no event arrives. The WebGPU
error event is optional and may be delayed or omitted, so its absence is not a completion signal.
For non-fallback adapters, put configuration, texture/view acquisition, command encoding, and the
first surface submission inside validation/OOM/internal scopes, then await queue-work completion
before publication. Chromium's fallback adapter has a separate platform defect: any WebGPU promise
after `OffscreenCanvas.configure()` cancels because its external Instance is dropped. Admit that
compatibility path only when the current `GPUAdapterInfo.isFallbackAdapter` (or exact legacy
fallback) reports `true`, label it diagnostic-only, and let it bind no receipt; missing or false
status stays on the strict path. Exercise synchronous, delayed, and omitted telemetry independently
from scope results, exact current-spec fallback selection, strict completion, cleanup, and partial
publication. See `platform_web/shell/wgpu-preinit-worker.js` and
`sandbox/wgpu-pipeline-integrated-smoke/preinit_worker_test.mjs`.

## Class 92 — entering WM_main is not a browser liveness receipt

Signature: a headed browser verifier waits for the shell's `running` marker, sleeps once, and
accepts any nonzero WM tick. The marker is published when WM_main is entered, before the first
software-rendered iteration has completed, so a one-tick dead loop passes. On Linux test Chromium,
an uninitialized software GPU service can also destroy a forced SwiftShader device immediately
after OffscreenCanvas configuration, confusing harness setup with a product failure. Bind this
diagnostic explicitly to Chromium's software adapter plus `--use-gpu-in-tests`, require current
fallback status, and label the result nonreceipt. Bound startup by a second real WM tick; then take
two further bounded samples with a positive tick delta. Finally send trusted canvas input and
require both another tick and a presentation delta, while rejecting any device loss, page error,
stage-1 failure, or import failure. Keep the classifier device-free and mutation-tested so a
single sample, missing input, hardware adapter, or presentation-free response cannot silently
restore the false green. See `sandbox/wgpu-pipeline-integrated-smoke/live_preinit_boot.mjs` and
`live_preinit_contract_test.mjs`.

## Class 93 — pointer identity does not freeze mutable producer state

Signature: a deferred GPU read retains manager, viewport, depsgraph, scene, view-layer, and active-
object pointers, then creates its selection list and transform backups only after settlement. A
frame step, selection change, or in-place transform edit can preserve every pointer while pairing
old pixels with new operation state. Before suspension, retain a producer-only snapshot of the
exact frame, selected target identities/session IDs, local transform channels, parent/data
identities, and evaluated transform matrices. Re-enumerate and compare that state on every pending
event before transferring the readback; deletion or replacement is handled by comparing stored raw
identities only against currently valid objects. Keep modal backups delayed until settlement so a
failed guard has nothing to restore. Exercise same-pointer frame, same-size selection replacement,
and transform drift separately on native and wasm32, and mutate the source guard in the aggregate
census. See `patches/0276-m5-axis-target-producer-state.patch` and
`sandbox/m5-object-axis-target-depth-cache/`.

## Class 94 — large mutable producer state belongs at the readiness boundary

Signature: a deferred viewport read retains a particle-edit pointer, but the same edit allocation
can change frame, object transform, point/key topology, coordinates, visibility/selection flags,
or particle-system state while depth is pending. Pointer identity and a coarse `edited` boolean do
not describe the pixels that produced the request. Capture the exact frame and evaluated object
matrices plus a short-lived 128-bit token over storage identities and the values used by traversal
before starting the readback. Recompute that potentially linear token only after the backend reports
Ready, immediately before the one-shot `take`; pending mouse events keep the cheap identity guard and
never pay an O(points + keys) scan. Fail closed before caller initialization on any mismatch, and
exercise click, gesture, and brush owners separately because they retain different inputs and FIFOs.
See `patches/0277-m5-particle-producer-state.patch` and
`sandbox/m5-particle-edit-depth-cache/`.

## Class 95 — a surface error scope cannot precede same-turn submission

Signature: a frame acquires a browser canvas texture, encodes a command buffer under WebGPU error
scopes, waits for those scopes to settle, and only then submits. The handles and command buffer can
all be non-null, yet the browser destroys the transient surface texture when that event-loop turn
yields; the delayed queue call therefore rejects a destroyed texture forever. Treat immediate
handle validity and asynchronous error validation as separate boundaries. After encoding a
complete command buffer, push the submission scopes and call `Queue::Submit` synchronously in the
acquisition turn. Pop the nested submission scopes and then the encoding scopes, retain every
dependency behind one thread-safe two-result join, and publish the present only when both groups
accept. A null partial handle still stops before submission. Exercise encoding-first and
submission-first callback delivery, each scope's failure, exact same-turn submit count, and a live
trusted-input presentation with zero rejected submissions; software evidence remains explicitly
nonreceipt. See `platform_web/ghost/GHOST_WGPUTransaction.hh` and
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 96 — normalized adapter fixtures can hide browser API shape drift

Signature: a browser receipt producer extracts adapter fields inside `page.evaluate()`, but its
self-check bypasses that callback and returns an already-normalized
`{isFallbackAdapter: false, info: ...}` record. A browser API property move can therefore make
every live adapter fail closed while the classifier fixtures remain green. Exercise the actual
page callback by installing current-spec, legacy, and conflicting raw adapter objects behind a
fake `navigator.gpu.requestAdapter()`. Prefer a boolean
`GPUAdapterInfo.isFallbackAdapter`, use `GPUAdapter.isFallbackAdapter` only as a compatibility
fallback, and require the current location to win conflicts. Keep true, absent, malformed,
masked, and software identities rejected; the fix is extraction, not classifier relaxation. See
`sandbox/m8-wasm-split/capture_blender_profile.mjs` and
`sandbox/m8-launch-gate/runtime_evidence.mjs`. Apply the same raw current/legacy/conflicting/
unknown fixture matrix to product-owned acquisition callbacks; the WM-worker preinit additionally
mutates legacy-only extraction, legacy-first precedence, and unknown-as-fallback behavior in
`sandbox/wgpu-pipeline-integrated-smoke/preinit_worker_test.mjs`.

## Class 97 — overlapping contexts need one owner-tracked backend handle snapshot

Signature: each GPU context copies its instance, device, and queue into independent process-static
fields for an asynchronous worker, then every context destructor clears all three fields. With two
live contexts, destroying an older owner erases the newer owner's device; separately reading the
three fields can also combine different generations during publication. Store complete handle
tuples in one locked latest-live-owner registry. Republishing an owner replaces and moves its tuple
atomically, forgetting an older owner preserves the current tuple, forgetting the newest owner
restores the previous live owner, and forgetting the last owner returns one empty tuple. Workers
copy the whole tuple under the same lock before using any member. Exercise coherent republish, both
teardown orders, previous-owner restoration, last-owner cleanup, and duplicate cleanup on native
and wasm32. See `patches/0279-gpu-webgpu-context-handle-registry.patch` and
`sandbox/wgpu-pipeline-integrated-smoke/`.

## Class 98 — a platform-window override must preserve context activation

Signature: a custom platform window overrides `activateDrawingContext()` during bring-up and
leaves an unconditional failure stub after its real drawing context begins shipping. Blender's
window manager activates through `GHOST_IWindow`, so the override bypasses the stock
`GHOST_Window` delegation even though the owned context implements device-aware activation.
Delegate to `GHOST_Window::activateDrawingContext()` and propagate its exact result; do not replace
the failure stub with unconditional success. Bind both the web override and the stock
window-to-context call in a source contract, with hard-coded success/failure mutations, then rebuild
the product translation unit. See `platform_web/ghost/GHOST_WindowWeb.cc` and
`sandbox/wgpu-pipeline-integrated-smoke/window_activation_contract.py`.

## Class 99 — a platform capability bit is a runtime routing promise

Signature: a browser GPU backend implements a nominally synchronous read by kicking an owned
request, consuming a prior settled request when available, and otherwise returning a conservative
interim buffer, while its platform layer advertises synchronous front-buffer support. Blender uses
that flag to choose a front-buffer helper whose void call is promoted to unconditional success, so
the interim bytes escape and the owned pending/ready continuation is never entered. Mask the
synchronous capability at the platform boundary; do not weaken the async request or manufacture a
synchronous wait on the WM worker. Bind the flag to both the stock capability-controlled branch and
the browser kick/take implementation, and mutate the routing, pending fallback, settlement, and
interim initialization independently. See `platform_web/ghost/GHOST_SystemWeb.cc` and
`sandbox/wgpu-pipeline-integrated-smoke/frontbuffer_capability_contract.py`.

## Class 100 — capability defaults must be audited when a platform is added

Signature: a platform starts from `GHOST_CAPABILITY_FLAG_ALL` and masks its obvious unsupported
methods, but newer or less visible capability bits remain enabled by omission. The method bodies can
still look correct while Blender takes a platform-specific branch based on a promise the backend
cannot fulfill. Audit every bit in the current pinned enum against the actual event and window
surfaces, not against an older backend's exclusion list. In a browser, DOM wheel deltas are already
adjusted by system scrolling preferences, so they cannot expose raw physical trackpad direction; a
canvas also has no server-owned window frame. Mask both facts while retaining independently proven
IME and RGBA cursor support. Bind exclusions to the event/window implementations and mutate each
unsupported and implemented bit separately. See `platform_web/ghost/GHOST_SystemWeb.cc` and
`sandbox/wgpu-pipeline-integrated-smoke/web_capability_contract.py`.

## Class 101 — deferred browser acceptance is not active platform state

Signature: a synchronous platform API returns success after queuing a user-activation-gated
browser request, so the platform-independent base immediately publishes the requested state even
though the browser has neither accepted nor completed it. Track Inactive, Pending, and Active
separately; publish the active GHOST state only from the browser's matching change callback, and
route relative input only while Active. Error, external loss, focus loss, application release, and
window disposal must cancel both the browser's deferred request and the platform state. Exercise
the accepted-but-pending interval, success, error, external loss, blur, disposal, absolute-motion
recovery, and a real product loss/reacquire cycle. See
`platform_web/ghost/GHOST_WindowWeb.cc` and
`platform_web/ghost/harness/pointer_lock_test.mjs`.

## Class 102 — callback userdata must identify the listener registration

Signature: browser listeners all receive the owning platform-system pointer as userdata. Removal
prevents new callbacks but cannot retract work already queued for a worker; if a replacement window
re-registers the same system pointer before that work runs, the old callback passes a pointer-based
owner gate and targets the replacement. Give every listener set unique durable userdata carrying a
registration epoch/token, retire that exact token before listener removal, and never recycle or
free it while queued delivery remains possible. Use the same userdata for exact removal and admit a
callback only when both its record and epoch are current. In a real worker harness, retain listener
closures from two successive registrations, replace twice, deliver both under a third registration,
require no stale input, then prove current input still works. See
`platform_web/ghost/GHOST_SystemWeb.cc` and
`platform_web/ghost/harness/window_lifecycle_test.mjs`.

## Class 103 — a listener set must publish as one transaction

Signature: a platform registers several browser listeners, ignores individual return values, and
marks the set active after the last call. A selector or API failure can leave a successful prefix
installed while the owner claims complete registration; later replacement and disposal then reason
from a false all-or-nothing flag. Register in a fixed order, stop at the first failure, remove the
exact successful prefix in reverse order, and keep owner userdata, epoch, and registered state
unpublished until every result succeeds. If initial or replacement registration fails, destroy the
candidate window before a manager or event observes it. Exercise all failure positions plus a
failed replacement followed by a clean retry on native and wasm32, then retain a real worker
dispose/recreate/input regression. See `platform_web/ghost/GHOST_SystemWeb.cc`,
`platform_web/ghost/GHOST_WGPUTransaction.hh`, and
`sandbox/wgpu-pipeline-integrated-smoke/window_lifecycle_contract.py`.

## Class 104 — monotonic process counters need per-owner epochs

Signature: bounded startup work stops after a process-global counter reaches a fixed value. The
first owner behaves correctly, but a replacement inherits the already-completed count and skips
its own initialization. Keep the global counter monotonic, capture its value when each owner is
published, and decide completion from the unsigned delta relative to that baseline. Reset the
owner's bounded tick state in the same publication transaction. Exercise initial and replacement
epochs, first/second completions, terminal and timeout behavior, and counter wrap on native and
wasm32. See `platform_web/ghost/GHOST_WebDisplayState.hh`,
`platform_web/ghost/GHOST_SystemWeb.cc`, and
`sandbox/wgpu-pipeline-integrated-smoke/first_pixel_settle_test.cc`.

## Class 105 — DOM listener targets are input-ownership boundaries

Signature: a canvas application registers keyboard callbacks on `window` so shortcuts keep working,
but the callback also receives keys after canvas blur and while a hidden IME input owns focus. The
same physical keystroke can then enter both the browser text/composition path and GHOST, while an
unrelated page control still drives Blender. Canvas-only listeners solve the external-control leak
but drop ordinary ASCII/control keys once an application-owned IME textarea takes focus. Treat all
application-owned focus elements as one admission domain, route non-composing keys from each owned
element, and prevent duplicate raw/composition delivery. Register only genuinely global events such
as resize on `window`, remove every listener from its exact registration target, and retain epoch
gating because changing the DOM target does not retract queued worker deliveries. Exercise focused
canvas input, unrelated-control suppression, trusted ordinary textarea keys, active composition
nonduplication, and delayed replacement callbacks. See `platform_web/ghost/GHOST_SystemWeb.cc`,
`sandbox/m4-keyboard-focus/`, and
`platform_web/ghost/harness/window_lifecycle_test.mjs`.

## Class 106 — terminal pointer events outlive the canvas but not their owner

Signature: mouse-down and mouse-up are both registered on a canvas. A drag that leaves the element
then releases over the page produces no canvas mouse-up and no focus loss, so platform button state
remains held forever. Register the terminal release on a target that outlives the interaction, but
admit it only when the platform still owns a matching press; an unrelated page release must neither
enter the application nor lose its browser default. A window-targeted event also changes the origin
of Emscripten `targetX/Y`, so translate viewport coordinates back to the canvas before delivery and
remove the listener from the exact registration target. Exercise outside release, unchanged canvas
focus, unowned suppression, coordinate routing, and replacement/disposal epochs. See
`platform_web/ghost/GHOST_SystemWeb.cc`, `sandbox/m4-mouse-release-ownership/`, and
`sandbox/wgpu-pipeline-integrated-smoke/window_lifecycle_contract.py`.

## Class 107 — continuous pointer ownership outlives the canvas during a drag

Signature: terminal mouse-up is captured at `window`, but mouse-move remains registered only on
the canvas. A canvas-owned drag that crosses onto another page element therefore freezes at its
last in-canvas position until the correctly delivered release. Capture motion at `window` too, but
admit an outside point only while GHOST owns at least one pressed button or Pointer Lock is active;
ordinary page motion must stay unconsumed. Current Emscripten does not populate the deprecated
`canvasX/Y` fields, and synchronously querying DOM geometry on every motion adds a main-thread
round trip. Instead, take one coherent DOM rectangle snapshot at listener registration and resize,
then translate `clientX/Y` locally on the WM worker. Exercise fail-first outside motion, canvas-
relative coordinates, outside release, unowned motion/release suppression, focus loss, Pointer
Lock, and listener replacement/removal. See `platform_web/ghost/GHOST_SystemWeb.cc` and
`sandbox/m4-mouse-release-ownership/`.

## Class 108 — one logical window can span several DOM focus elements

Signature: a canvas application focuses its own hidden textarea for IME composition, and the
canvas blur listener mistakes that internal handoff for application deactivation. Model browser
focus as a domain containing the canvas and the enabled, focused IME textarea; publish only state
changes at the domain boundary. A canvas blur may be suppressed when the domain still owns focus,
but browser-window blur must always deactivate because `activeElement` can remain the textarea
after the tab or window loses focus. Register both element- and window-level listeners in the same
rollback transaction and deduplicate overlapping delivery. Exercise canvas-to-textarea and
textarea-to-canvas handoffs, an ordinary page control, browser-window loss/recovery while IME owns
`activeElement`, and exact listener retirement. See `platform_web/ghost/GHOST_SystemWeb.cc`,
`sandbox/m4-ime-focus-ownership/`, and
`platform_web/ghost/harness/ime_composition_test.mjs`.

## Class 109 — proxied callbacks cannot reconstruct an intermediate DOM edge

Signature: a DOM callback is proxied to a worker and decides whether a blur still matters by
querying `activeElement` when the worker eventually runs. A same-task canvas-to-control-to-canvas
transition has already restored the final state, so the blur is suppressed and held application
input survives a real focus-domain boundary. Publish a monotonic loss generation synchronously in
the capturing DOM event, then have the worker retire input before reconciling the live final state.
That preserves the boundary's existence but is insufficient if later proxied input can enqueue
before the worker polls: stamp input with its event-time generation or put both facts into one
ordered queue, and reconcile every preceding loss before mutating held state.
When an ordinary proxied blur handles the loss first, acknowledge the generation so a later poll
does not manufacture a duplicate deactivate/activate pair. Mark application-owned IME focus moves
as explicit internal handoffs rather than inferring them from delayed DOM state. Exercise held
modifier/button retirement under same-task blur/refocus, exact boundary ordering before an immediate
post-refocus key/button Down, ordinary single-pair transitions,
synthetic blur terminal behavior, and canvas/IME handoffs in the real worker topology. See
`platform_web/ghost/GHOST_SystemWeb.cc` and `sandbox/m4-focus-transition-order/`.

## Class 110 — exact resource completeness must distinguish absence from validation latency

Signature: an exact bind-group check is correct for WebGPU's explicit layout, but backend-created
push buffers and samplers publish only after browser error scopes settle. Returning null while a
persistent resource is merely pending turns a validation-safety mechanism into a one-shot draw
drop; startup overlays may never be redrawn, leaving a healthy presenting canvas blank. Diagnose
first by printing sorted expected, assembled, missing, and extra IDs. Keep exact equality for real
absence. Start persistent shader-owned resources before later shader readiness gates, and expose a
provisional shared handle only when every observing queue epoch is reserved behind the same
validation result. Acceptance publishes normally; rejection must cancel all epochs that could
have encoded the error object and leave a clean retry. Exercise same-epoch reuse, cross-epoch reuse,
multi-epoch rejection, and a real windowed warning scanner. See
`upstream/source/blender/gpu/webgpu/wgpu_common.hh`,
`upstream/source/blender/gpu/webgpu/wgpu_shader.cc`, and
`notes/p0-bind-group-readiness-20260826.md`.

## Class 111 — a capped log is not a liveness counter

Signature: a frame path prints only its first few successful calls to bound console noise, and
receipts later interpret the exact number of printed lines as the number of frames produced. The
same output then describes both a frozen application and a 60 Hz application. Keep the diagnostic
cap, but prove liveness with an uncapped exported counter or semantic pixel deltas across trusted
input. Record which signal a receipt consumes and mutation-test the consumer; never infer sustained
presentation from the first-two-frame `presentBackbuffer` messages. See
`platform_web/ghost/GHOST_ContextWGPUWeb.cc` and
`sandbox/wgpu-pipeline-integrated-smoke/live_preinit_boot.mjs`.

## Class 112 — mutable attachment wrappers leave identity-keyed framebuffer caches stale

Signature: a persistent backend texture wrapper adopts a replacement native handle and new extent
in place, while a framebuffer caches dimensions derived from that wrapper. Reattaching the same
pointer is correctly an identity no-op, so it does not dirty the derived cache; viewport/scissor
planning then uses the old dimensions against the new render attachment and validation rejects the
draw. Trace both the platform resize and application relayout before changing event ordering. At
the wrapper-adoption seam, explicitly refresh every framebuffer cache derived from mutable fields,
and exercise shrink plus restoration against the real product. See
`upstream/source/blender/gpu/webgpu/wgpu_context.cc`,
`upstream/source/blender/gpu/intern/gpu_framebuffer.cc`, and
`sandbox/m4-resize-recovery/`.

## Class 113 — asynchronous readiness must invalidate the draw it made provisional

Signature: a browser GPU cache returns pending on first use, the caller correctly abandons that
draw, and the cache later publishes a valid module, layout, or pipeline without invalidating the
owning UI region. Presentation can continue while whichever region lost its first draw remains
black forever, so frame submission and idle logs cannot reveal the defect. Publish accepted async
readiness into the platform's ordinary full-screen update path, and keep an incomplete-draw signal
separate: accepted readiness may rearm a completed bounded episode, while repeated drops and failed
publications must never extend its ceiling. Start one bounded boot episode to discover visible lazy
variants, but do not terminate it from a fixed presentation count because surface presents can
precede shader settlement. Exercise late acceptance, active-episode acceptance, repeated-drop
bounding, terminal rearming, and counter wrap on native and wasm32; closure still requires idle
semantic pixels on hardware. See `platform_web/ghost/GHOST_WebDisplayState.hh`,
`upstream/source/blender/gpu/webgpu/wgpu_shader.cc`,
`upstream/source/blender/gpu/webgpu/wgpu_pipeline.cc`, and
`notes/p0-redraw-recovery-20260826.md`.

## Class 114 — delayed callback safety needs bounded, non-recycled identity

Signature: browser listener removal prevents new events but cannot retract callbacks already
proxied to a worker. Retaining one heap record per registration makes stale userdata safe, yet
failed prefix transactions and repeated replacement grow process-lifetime metadata without limit.
Use opaque addresses from a fixed token pool: never dereference, free, or reuse a token; compare it
with the active token before loading the owner; publish the owner before the token; and retire the
token and owner before removing listeners. Budget every attempt, including rolled-back prefixes,
and fail closed at exhaustion. Soak real failed registrations and replacement windows while
holding an old callback, require exact token accounting and listener balance, then prove stale
delivery is rejected and fresh input survives. See `platform_web/ghost/GHOST_SystemWeb.cc` and
`sandbox/m8-callback-registration-soak/`.

## Class 115 — ignored browser capability promises escape synchronous C contracts

Signature: a pinned browser shim treats a user-sensitive DOM method as a synchronous `void`
operation, while current browsers return a Promise. The C-facing helper reports immediate success
and discards that Promise; a routine policy/document rejection then becomes a global page error
even when the platform already owns an error-event fallback. Wrap the exact element method before
the runtime loads, invoke the native method synchronously in the same activation stack, and attach
the rejection handler immediately. Route rejection through the existing platform lifecycle, emit
only a bounded diagnostic, and leave unrelated `unhandledrejection` events observable—never
globally `preventDefault()` them. Exercise repeated Promise-only rejection in the real worker
topology and require inactive platform state, one diagnostic, and zero page errors. See
`platform_web/shell/diagnostics-bootstrap.js`,
`platform_web/ghost/harness/pointer_lock_test.mjs`, and
`sandbox/wgpu-pipeline-integrated-smoke/pointer_lock_contract.py`.

## Class 116 — define fragment outputs as one complete value across shader translators

Signature: native UI expects a constant RGB plus computed alpha, the browser receives valid WGSL
and a valid alpha-blend pipeline, and hardware preserves the intended geometry/falloff while RGB
appears as stale bright data. A source pattern that initializes a stage-global output vector and
later replaces only one component has to survive GLSL preprocessing, SPIR-V generation, Tint's
SPIR-V reader, WGSL optimization, Dawn's backend translation, and the native shader compiler.
When every other resource and blend invariant is measured, collapse that result to one full-vector
assignment so no backend must preserve a partial write across those passes. Verify the final WGSL
at the browser API, not just the input GLSL, and keep pixel closure hardware-gated. See
`upstream/source/blender/gpu/shaders/gpu_shader_2D_widget_shadow_frag.glsl` and
`notes/p0-widget-shadow-defined-rgb-20260826.md`.

## Class 117 — runtime-ready is not first-pixel-ready

Signature: a long-lived browser runtime resolves its module and enters the application main loop
before Python startup, shader translation, and the first surface submission finish. A wall-clock
"settle" fallback tied to that runtime marker hides the loader while the uncapped presentation
counter is still zero, exposing seconds of black or partial warmup even though the primary
first-pixel signal is correct. Keep the real presentation signal primary; if its log text can
drift, poll an uncapped successful-presentation counter, require a finite positive value, and stop
at a hard ceiling without hiding on timeout. Exercise the rejected timer, the real marker, and a
masked-marker counter fallback against the same product. See
`platform_web/shell/boot-windowed.js` and
`sandbox/m4-frame-coherence/`.

## Class 118 — virtual filesystem rename atomicity stops at backend boundaries

Signature: a staged loader writes complete files under a writable temporary mount and renames
them into a read-only preloaded tree, assuming POSIX rename semantics span both paths. WasmFS
routes those directories through different backends, so every cross-directory publication fails
even though streaming, byte accounting, and temporary writes succeed. Validate publication in the
real runtime, not a permissive mock. Temporarily add only owner write/search permission to each
already-created destination parent, stage a sibling temporary file, rename within that directory,
and restore every original mode on success, fetch failure, cleanup failure, and retry. Bind safe
manifest paths, duplicate rejection, same-parent rename, mode restoration, and exact post-publish
bytes with mutations. See `sandbox/m8-staged-deploy/stage1-loader.js` and
`sandbox/m8-stage0-ui-font/probe_candidate.mjs`.

## Class 119 — request-time invalidation can expire before an asynchronous drawable commit

Signature: a browser resize queues a size event and redraw immediately, while the matching surface
and persistent backbuffer validate asynchronously. If an older bounded redraw episode is still
active, that request does not reset its ceiling; the update can run against the old drawable on the
last available tick, and the later coherent commit publishes no new invalidation. Identical resizes
then alternate between a complete frame, stale overdraw, and black depending on callback timing.
Keep ordinary readiness signals unable to extend an active hard ceiling, but give a newly committed
drawable its own monotonic generation that always starts one fresh bounded episode. Publish it only
after the complete extent-bound state commits, not when the resize is merely requested. Exercise
the final-old-tick/late-commit schedule on native and wasm32, expose a read-only live commit counter,
and still require repeated idle semantic pixels on hardware. See
`platform_web/ghost/GHOST_WebDisplayState.hh`,
`platform_web/ghost/GHOST_ContextWGPUWeb.cc`, and `sandbox/m4-resize-recovery/`.

## Class 120 — repeated presents do not prove fresh region content

Signature: a resize recovery episode produces many validated surface presents, yet hardware shows
the same stale rectangle on every frame. Presentation counts prove compositor activity but cannot
distinguish freshly encoded Blender regions from repeated blits of a retained backbuffer. Before
changing invalidation or draw ordering again, correlate each successful present with a bounded
single-worker snapshot of cumulative draw sequence plus the exact target, resolved viewport, and
scissor for the suspect scene-background and display-composite shaders. An unchanged shader
sequence across presents identifies retained-content reuse; an advancing sequence with a stable
wrong target identifies a stale geometry source; correct advancing plans point at submission or
composition order. Keep the trace episode-scoped and capped, and require semantic hardware pixels
for closure. See `platform_web/ghost/GHOST_WebDisplayState.hh`,
`upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc`, and
`sandbox/m4-resize-recovery/verify_resize_trace.py`.

## Class 121 — replaceable window backbuffers require guaranteed context reactivation

Signature: a browser surface validates and commits a replacement backbuffer, bounded invalidation
drives many real presents, and every present still contains the same stale region. A persistent
texture wrapper can adopt the replacement only when its GPU context activates, but a single-window
WM considers the already-current window drawable and skips activation indefinitely. Clearing the
cached drawable identity before the draw loop forces the ordinary activation path to synchronize
the latest backbuffer before region encoding. Scope this to backends with replaceable drawable
attachments; Blender's Metal path already establishes the rule, and Emscripten WebGPU shares it.
Bind the activation/adoption order device-free, retain bounded per-present diagnostics, and require
semantic hardware pixels for closure. See
`upstream/source/blender/windowmanager/intern/wm_draw.cc`,
`upstream/source/blender/gpu/webgpu/wgpu_context.cc`, and
`sandbox/m4-resize-recovery/verify_source.py`.

## Class 122 — a synchronous window swap cannot become an asynchronous backend callback

Signature: frame submissions validate asynchronously, so routing the final surface blit through
their FIFO appears to restore GPU order. The platform swap then reports success before it acquires,
encodes, or submits anything; later WM frame epochs can begin while the prior swap is still a
backend-owned callback. Device-free queue-order tests stay green, but the hardware product can
hard-abort in unrelated-looking Blender allocation code because the platform lifetime contract has
already been crossed. Keep surface acquire, blit, submit, and result propagation inside GHOST's
synchronous `swapBufferRelease()` browser turn. Solve earlier submission ordering without moving
that boundary, and require a real-hardware boot before accepting any replacement. Preserve rejected
experiments in numbered history, but add an explicit rollback patch and forbid their callback seam
in the live source contract. See `platform_web/ghost/GHOST_ContextWGPUWeb.cc`,
`patches/0289-gpu-webgpu-restore-synchronous-window-present.patch`, and
`notes/p0-boot-crash-ordered-present-rollback-20260827.md`.

## Class 123 — separately lifetime-gated getters do not form a coherent drawable snapshot

Signature: a browser resize replaces a persistent backbuffer and increments its redraw generation
under an owner callback gate, while frame activation reads the texture, format, extent, and later
the generation through separate individually guarded calls. Every read is race-free in isolation,
but an `AllowSpontaneous` completion can commit between calls. The frame may then adopt the old
texture while carrying the new generation, so a queue-tail barrier treats old-drawable work as the
completed replacement frame and presents the untouched new backbuffer without any validation
error. Return the complete drawable identity and its committed generation from one lifetime-gated
snapshot, publish the generation in the same callback that commits the replacement handle, and
carry that snapshot value through frame completion. Device-free contracts can bind the atomic
read/publication and reject split getters; only repeated semantic pixels on conformant hardware
can close the race. See `platform_web/ghost/GHOST_ContextWGPUWeb.hh`,
`upstream/source/blender/gpu/webgpu/wgpu_context.cc`, and
`sandbox/m4-resize-recovery/verify_source.py`.

## Class 124 — a queue barrier must snapshot diagnostics at the boundary it proves

Signature: a completed-frame barrier correctly holds later GPU submissions, but its diagnostic
samples mutable draw state only when the later synthetic presentation update runs. CPU encoding
for that later frame has already advanced the live counters even though its queue work is still
behind the barrier, so the log attributes unpresented plans to the older backbuffer actually being
copied. Capture the complete draw-plan snapshot when `end_frame()` schedules the barrier, retain
it unchanged through queue arrival, and consume that snapshot before completing the synchronous
present. Duplicate same-episode scheduling must not replace it; supersession may replace it only
with the newer episode's frame-tail snapshot; completion and cancellation clear it. Exercise the
snapshot lifetime on native and wasm32, while leaving semantic closure to hardware pixels. See
`platform_web/ghost/GHOST_WebDisplayState.hh`,
`upstream/source/blender/gpu/webgpu/wgpu_context.cc`, and
`sandbox/wgpu-pipeline-integrated-smoke/first_pixel_settle_test.cc`.

## Class 125 — replacement commit must retire an older ready present barrier

Signature: a resize barrier reaches ready after its frame submissions settle, then a newer
drawable commits before GHOST enters the synchronous present. If the commit leaves that older
barrier ready, GHOST samples the current backbuffer rather than the barrier's former texture and
can copy the newly committed, untouched backbuffer under the obsolete episode. Publish and store
the replacement episode on the new backbuffer first, then atomically cancel any scheduled or
ready barrier for another episode; only after that binding is visible may cancellation release the
ordered queue. Exercise both the state transition and the exact commit ordering on native and
wasm32, while retaining repeated hardware semantic pixels as the closure bar. See
`platform_web/ghost/GHOST_WebDisplayState.hh`,
`platform_web/ghost/GHOST_ContextWGPUWeb.cc`, and
`sandbox/wgpu-pipeline-integrated-smoke/first_pixel_settle_test.cc`.

## Class 126 — episode-wide draw history cannot authorize a replacement frame

Signature: a coherent resize commits during the tail of an older drawable's frame. The new
episode correctly prevents that old frame from scheduling a present barrier, but its remaining
draws still populate an episode-wide trace. If the first adopted replacement frame is empty or
window-only, its barrier can inherit those plausible counts and present an untouched backbuffer
without any validation error. Bind the episode at the exact atomic backbuffer-adoption boundary,
then reset semantic trace facts once at the real window-frame begin while retaining cumulative
episode counters only for diagnostics. Keep the barrier scheduled for incomplete frames so
synchronous swap remains
suppressed; once it reaches ready, admit only a frame with the visible 3D region's offscreen
background, its later direct-window display composite, and a final window-target draw. Generic
offscreen/window activity can be chrome-only and is not sufficient. Complete rejected frames as
invalid to release later-epoch work and re-arm the same bounded retry. Bind reset, snapshot,
rejection, and retry on native and wasm32, but leave repeated semantic pixel closure to conformant
hardware. See
`platform_web/ghost/GHOST_WebDisplayState.hh`,
`platform_web/ghost/GHOST_ContextWGPUWeb.hh`, and
`sandbox/m4-resize-recovery/verify_source.py`.

## Class 127 — context activation is not a window-frame boundary

Signature: a frame-local completeness trace sees hundreds of advancing draw sequences, but every
tail snapshot retains only the same final 23–25 commands and permanently lacks an early region
pass. A GPU context can reactivate several times while Blender encodes one WM window frame; using
activation or backbuffer synchronization as the trace reset boundary erases earlier region draws
each time. Keep activation responsible for atomically adopting the drawable and its episode, but
reset semantic frame facts exactly once in the backend's real `begin_frame()`. Later activations
may synchronize resources without changing frame ownership. Require `end_frame()` to admit only a
complete same-episode snapshot, and withhold unbarriered surface copies while the bounded resize
episode is still seeking that frame. A mutation contract must reject both an activation-time reset
and a missing begin-frame reset; a real fallback run can prove scheduling and error freedom, but
only repeated conformant-hardware pixels close visual recovery. See
`upstream/source/blender/gpu/webgpu/wgpu_context.cc`,
`platform_web/ghost/GHOST_ContextWGPUWeb.cc`, and
`sandbox/m4-resize-recovery/verify_source.py`.

## Class 128 — a validated surface present is not semantic region readiness

Signature: the browser surface submits successfully and the surrounding application chrome is
visible, but one lazily validated editor region still contains only its clear/background pass.
Neither a runtime marker nor an uncapped present counter proves that region's meaningful content
encoded. Define a frame-local semantic predicate from successful draw-encoding call sites, carry
that exact snapshot through the queue-tail barrier, and publish readiness only after the matching
surface submission validates. Do not invent ordering between passes that render into separate
offscreen targets: the exact browser product encodes `overlay_grid_next` immediately before
`overlay_background`, even though both feed the later direct-window `OCIO_Display` composite.
For Blender's default VIEW_3D boot, require both successfully encoded offscreen passes and require
the display composite after each. Keep the loader visible if the marker is absent or invalid;
never infer it from elapsed time or a generic present. Prove the shell rejects generic presents,
bind the measured live order in native/wasm behavior tests, and retain conformant-hardware
cold-boot pixels as the closure bar. See
`platform_web/ghost/GHOST_WebDisplayState.hh`,
`upstream/source/blender/gpu/webgpu/wgpu_context.cc`, and
`sandbox/m4-viewport-content-loader/verify.py`.

## Class 129 — a shader-name receipt allowlist turns new draw drops invisible

Signature: a backend-wide completeness diagnostic prints every shader and exact expected/assembled
binding sets, but the hardware receipt recognizes only the few shader names known when the gate was
written. A later compute, text, icon, or geometry variant can then hit the identical hard draw-drop
path while the receipt remains green. Match the invariant diagnostic rather than a shader allowlist,
parse and preserve its shader plus surviving/assembled/missing/extra sets, aggregate identical
signatures with counts, and fail closed on malformed matching lines. Self-check both the historical
names and arbitrary future names. A zero-warning receipt does not prove pixels by itself, but a
nonzero warning can never be compatible with a complete frame while every caller abandons the draw.
See `upstream/source/blender/gpu/webgpu/wgpu_shader.cc` and
`sandbox/m8-wasm-split/capture_blender_profile.mjs`.

## Class 130 — typed buffer frontends can discard pending bind intent independently

Signature: a general storage/uniform binding path correctly records a slot while browser buffer
allocation is pending, yet a polyline or geometry shader still reports every vertex/index storage
binding missing and only its push constant assembled. Vertex and index wrappers may each implement
their own upload-then-bind frontend; a post-upload `valid()` return repeats the same intent-loss
bug outside the generic buffer path. Treat pending allocation as an exact resource state, record
the typed binding ID before handle publication, and let resource assembly distinguish exact
pending IDs from genuinely unbound or extra resources. Do not weaken set completeness: a pending
draw may retry, while any unaccounted missing/extra ID remains a hard draw drop and receipt failure.
Bind the source predicate with mutation checks, census every shader at runtime, and retain
conformant-hardware pixels as closure. See
`upstream/source/blender/gpu/webgpu/wgpu_vertex_buffer.cc`,
`upstream/source/blender/gpu/webgpu/wgpu_index_buffer.cc`, and
`sandbox/p0-interaction-stress/`.

## Class 131 — ordinary input may need bounded recovery without owning a drawable episode

Signature: boot recovery and resource-readiness retries are bounded correctly, but an interaction
first exposes a lazy browser resource after that budget has ended. The input event reaches Blender
and requests its normal redraw; that one frame drops, and no later input-driven full-window retry
exists to repair the retained region. Route accepted move, supported button, nonzero wheel, and key
events into a dedicated input-tail generation while also advancing the aggregate diagnostic retry.
Do not start a resize episode: ordinary input has no replacement drawable and must not acquire
resize's completed-frame barrier semantics. A generic readiness generation is insufficient: if the
last accepted input lands on tick 179 of 180, it otherwise consumes the old burst's final tick and
can leave its dropped frame stale. Sampling the input generation once per WM poll coalesces queued
callbacks, then resets one complete trailing budget after the most recent real input. This remains
bounded after input stops, while unrelated shader-readiness signals still cannot extend an active
ceiling. Bind unsupported/zero events, mutation-test every bridge, prove the tick-179 schedule and
native/Wasm coalescing parity, and retain trusted hardware pixels as the closure bar. See
`platform_web/ghost/GHOST_EventBridgeWeb.cc`,
`platform_web/ghost/GHOST_WebDisplayState.hh`, and `sandbox/p0-interaction-stress/`.

## Class 132 — a pending bind may depend on a different eventual resource

Signature: a typed frontend preserves ordinary SSBO intent during asynchronous allocation, but its
buffer-texture variant still drops the slot or binds the wrong backing. Some texture-buffer formats
require expansion before binding (for example float1-3 sources represented by float4 storage), so
the allocation currently pending and the resource that must eventually enter the bind group are
not necessarily the same object. Preserve both identities: record the eventual correctly shaped
resource and a separate pending dependency. Resource assembly may classify the exact mapped ID as
pending while the dependency is retryable, but it must require the eventual resource to be valid
before emitting a live entry. Never substitute the unexpanded source just to make the set complete;
rejection or an absent final backing remains a hard incomplete draw. Prove the primary-pending and
expanded-publication transition in exact native/Wasm behavior, then retain hardware pixels as the
closure bar. See `upstream/source/blender/gpu/webgpu/wgpu_vertex_buffer.cc`,
`upstream/source/blender/gpu/webgpu/wgpu_context.cc`, and
`sandbox/wgpu-buffer-integrated-smoke/`.

## Class 133 — browser same-turn submission and native validation ordering are distinct contracts

Signature: a shared command helper validates before queue submission on native Dawn, but its
browser branch must submit a finished command buffer in the JavaScript calling turn so synchronous
presentation cannot overtake frame work. A byte-identical test that expects native submit counts
from Wasm then fails even though both runtime policies are deliberate. Encode the policy pair in
one contract: native suppresses submit after an encoding-scope failure; browser submits any valid
finished buffer before that asynchronous diagnostic arrives; both suppress null encoder/command
handles, report a failed completion for either scope error, balance every pushed scope, and invoke
completion exactly once. Keep native/Wasm evidence text identical by naming both policies rather
than pretending their raw submit counts match. See
`upstream/source/blender/gpu/webgpu/wgpu_common.hh` and
`sandbox/wgpu-buffer-integrated-smoke/integrated_buffer_test.cc`.

## Class 134 — same-turn commands must join separately validated transient resources

Signature: browser command buffers must submit in the calling turn, but a staging resource used by
that command was created under its own asynchronous error scope and scheduler gate. Ignoring the
gate preserves queue order yet disconnects the payload transaction from resource rejection: clean
command scopes can falsely commit bytes whose non-null staging handle later proves to be an error
object. Keep the same-turn submission, but join the resource-creation and command-validation
completions. Publish success exactly once only after both legs accept; either rejection retains the
owned payload for a clean-epoch retry. Null creation or mapping remains a synchronous setup failure
and must abandon the join before the caller's ordinary failure path runs. Exercise native's
validation-ordered cancellation and browser's already-submitted path in one native/Wasm contract.
See `upstream/source/blender/gpu/webgpu/wgpu_buffer.cc` and
`sandbox/wgpu-buffer-integrated-smoke/integrated_buffer_update_test.cc`.

## Class 135 — every accepted lazy helper needs a redraw-readiness edge

Signature: a persistent cache returns no handle while browser validation is pending, so the
calling draw abandons a clear, blit, upload, compatibility attachment, dummy buffer, or topology
helper. Validation later accepts and caches the handle, but no ordinary input or window event is
required to arrive afterward. A comment that the caller will retry on a later frame is therefore
not a scheduling guarantee: the accepted helper can remain invisible indefinitely. Attach one
publication callback to every such cache producer and coalesce a bounded redraw retry only for a
new non-null accepted handle. Pending creation, rejection, null publication, and cache hits must
emit no edge, preventing an unavailable helper or hot cache from extending the retry ceiling.
Freeze the full producer census rather than patching only the shader family seen in one capture,
and keep hardware pixels as the closure authority. See
`upstream/source/blender/gpu/webgpu/wgpu_context.cc`,
`upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc`,
`upstream/source/blender/gpu/webgpu/wgpu_batch.cc`, and
`sandbox/p0-interaction-stress/verify_auxiliary_cache_redraw.py`.

## Class 136 — readback-backed bindings have a separate readiness dependency

Signature: a typed sampler-buffer frontend has a valid primary GPU buffer, but formats requiring
expansion cannot construct their eventual binding until an asynchronous browser readback settles.
An empty first `MapAsync` result is neither a synchronous absence nor proof that Blender failed to
bind the slot. Report that exact readback as pending, retain the eventual expanded resource plus
its external dependency in the context, and publish one coalescible redraw edge only when the
cache entry settles successfully. Default cache consumers and exact ticket owners must not inherit
that edge; failure, cancellation, and repeated cache hits emit none. Keep the hard completeness
gate for genuinely absent resources, and diagnose every distinct pending shader/set signature so
repeated boot traffic cannot hide an interaction-only variant. Prove the pending-to-ready
transition with the real frontend extraction on native and wasm32, while leaving pixel closure to
repeated conformant-hardware runs. See
`upstream/source/blender/gpu/webgpu/wgpu_buffer.cc`,
`upstream/source/blender/gpu/webgpu/wgpu_readback.cc`,
`upstream/source/blender/gpu/webgpu/wgpu_vertex_buffer.cc`, and
`sandbox/p0-interaction-stress/verify_buffer_texture_readback_pending.py`.

## Class 137 — asynchronous present settlement must re-enter through WM

Signature: a surface transaction samples the persistent backbuffer and then waits for browser
validation. Later WM frames update that backbuffer, but their swaps coalesce behind the in-flight
transaction. Calling the surface-present routine directly from the validation callback appears to
replay the newest content and can pass several runs, yet it acquires outside the ordinary WM draw
boundary and may still expose a retained partial frame. Publish a distinct monotonic replay
generation instead. The WM loop must consume that generation only after its `WindowUpdate` passes
any resize barrier, and the resulting ordinary frame must own surface acquire/encode/submit. Do not
route this through the generic bounded-readiness heartbeat: a terminal heartbeat can discard the
one update settlement exists to guarantee. Bind the seam with positive suppression/replay deltas,
an exact draw-stage witness, and repeated same-native-state pixels; aggregate present counts alone
cannot distinguish a stale replay. See `platform_web/ghost/GHOST_ContextWGPUWeb.cc`,
`platform_web/ghost/GHOST_SystemWeb.cc`, `platform_web/ghost/GHOST_WebDisplayState.hh`, and
`sandbox/p0-interaction-stress/`.

## Class 138 — validation callback latency must not suppress later WM presents

Signature: one surface copy has already popped its WebGPU error scopes, but their asynchronous
result callbacks lag several complete WM frames. Treating that callback latency as exclusive
ownership of the entire presentation path discards every newer swap; a single eventual replay then
has to publish an arbitrarily long run of changed backbuffer content and can retain a stale frame.
Keep one transaction as the diagnostic-scope owner, but let overlapping WM frames acquire, encode,
and submit unscoped surface copies synchronously in their own browser turns. Record those overlaps
on the same coalesced latch and request one final scoped WM replay when the owner settles. Never
acquire a surface texture from the callback, never nest error scopes under the pending owner, and
prove the seam with same-native-state pixel canaries rather than aggregate present counts. See
`platform_web/ghost/GHOST_ContextWGPUWeb.cc`,
`platform_web/ghost/GHOST_WGPUTransaction.hh`, and `sandbox/p0-interaction-stress/`.

## Class 139 — rapid screenshots are not a worker-queue drain verdict

Signature: several trusted actions sampled a few hundred milliseconds apart retain the same canvas
image, while a proxied Wasm worker may still be draining earlier GPU validation or WM work. Pixel
identity across those immediate samples is a real observation but cannot distinguish permanent
input/presentation loss from bounded backlog. Preserve the filed cadence, then add a bounded drain
phase that requires one sample to change pixels while WM ticks, validated presentations, and the
input-redraw generation all advance. Follow it with a new independent interaction and require the
same predicate again. On timeout retain every rapid sample, final counters, pointer-lock outcome,
and native event tail; otherwise the next hardware pass still cannot localize the loss. Reject
fallback or incompletely identified adapters before labeling a run as hardware, and never let this
focused diagnostic replace the immutable semantic-pixel receipt. See
`sandbox/p0-interaction-stress/rapid_freeze_repro.mjs`.

## Class 140 — bind input-drain claims to the terminal native edge

Signature: an exact rapid sequence includes several actions after the first visibly changed frame,
but the diagnostic accepts any earlier post-baseline pixel change as proof that the whole sequence
drained. DOM capture proves only browser generation, while a pass-through Blender modal handler can
miss releases consumed by an earlier modal operator. Count state-changing press/release callbacks
at the GHOST worker boundary instead, retain a held-button mask, and compare against a baseline
taken immediately before the rapid sequence. Require every terminal action's expected edges, a
cleared mask, a clean Blender modal stack, pixels, WM progress, presentation, and redraw ownership
in the same bounded sample. Then require a separately baselined recovery action. Keep the counters
diagnostic-only and transition-based so duplicate/synthetic releases do not manufacture delivery.
See `platform_web/ghost/GHOST_WebDisplayState.hh`, `platform_web/ghost/GHOST_SystemWeb.cc`, and
`sandbox/p0-interaction-stress/rapid_freeze_repro.mjs`.

## Class 141 — input activity and resource readiness need separate retry ownership

Signature: every proxied mouse-motion sample advances an input generation and the aggregate redraw
generation, while the recovery consumer treats the aggregate edge as new asynchronous GPU-resource
readiness. A drag can then inject one synthetic full-screen update and reset the full recovery tail
for every motion event, building a render queue behind the native interaction events that already
own immediate redraw. Preserve both counters, but compare their per-poll unsigned deltas: paired
input/aggregate increments are input activity, while an unmatched aggregate increment is genuine
resource or resize readiness. Inside an active burst, acknowledge nonterminal input without
injecting another synthetic update or extending the hard ceiling. Let the first input after idle
open a bounded burst, and let a separately recorded button/key/wheel terminal edge restart exactly
one complete tail. This keeps ordinary input outside the replacement-drawable barrier while making
continuous motion bounded. See `platform_web/ghost/GHOST_WebDisplayState.hh`,
`platform_web/ghost/GHOST_SystemWeb.cc`, and
`sandbox/wgpu-pipeline-integrated-smoke/first_pixel_settle_test.cc`.

## Class 142 — bind late presentation evidence to the frame producer

Signature: a monotonic process-global generation is sampled when an asynchronous or barrier-delayed
surface transaction begins, after the persistent backbuffer frame being copied was encoded. A newer
input can advance the global counter without contributing to that frame, so a clean present can
falsely certify the newer input. Snapshot causal provenance at the producer boundary immediately
before frame encoding, carry it inside any immutable completed-frame/barrier record, and publish
only that captured generation after validation. Test three distinct transitions: later dispatch
cannot relabel an already-begun frame, a delayed barrier keeps its completed-frame generation, and
the next producer frame adopts the new generation. This is an evidence fix, not authorization to
change redraw policy or promote software-adapter pixels. See
`platform_web/ghost/GHOST_WebDisplayState.hh`, `platform_web/ghost/GHOST_ContextWGPUWeb.cc`, and
`sandbox/wgpu-pipeline-integrated-smoke/first_pixel_settle_test.cc`.

## Class 143 — frame-bound presentation is not post-input content evidence

Signature: a validated surface transaction carries the exact dispatched input generation captured
when its WM frame began, yet it can still copy a persistent backbuffer whose intended 3D region did
not encode. Generic chrome draws or retained bytes make the surface transaction valid without
proving the user's orbit, selection, or transform reached a complete viewport frame. Keep a
separate bounded semantic trace for the pending terminal generation, record only successfully
encoded background, stock-grid, and final-display work, snapshot it with the frame, and advance a
monotonic content-presented edge only after that exact surface submission validates. Do not use
the edge as a substitute for hardware pixels: it localizes a failure above or below content-bearing
presentation but cannot establish visual correctness. See
`platform_web/ghost/GHOST_WebDisplayState.hh`, `platform_web/ghost/GHOST_ContextWGPUWeb.cc`,
`upstream/source/blender/gpu/webgpu/wgpu_context.cc`,
`upstream/source/blender/gpu/webgpu/wgpu_framebuffer.cc`, and
`sandbox/p0-interaction-stress/rapid_freeze_repro.mjs`.

## Class 144 — retire input-owned recovery after exact content success

Signature: terminal input correctly starts a bounded synthetic full-screen retry tail, but the
tail always consumes its entire tick budget even after that exact input generation has already
encoded and presented a complete semantic viewport frame. The redundant updates can build a queue
ahead of the next sparse user action and make a healthy worker look frozen. Track explicit
input-tail ownership and retire it only when the frame-bound content-presented generation reaches
the target. Clear that ownership instead of retiring the shared burst when a resize episode,
asynchronous resource-readiness edge, or dropped draw appears: those signals may cover other
regions and retain their original bounded recovery contract. Prove early retirement, later-input
rearming, and unchanged generic/resize ceilings in native and wasm32 behavior; hardware pixels
remain the closure authority. See `platform_web/ghost/GHOST_WebDisplayState.hh`,
`platform_web/ghost/GHOST_SystemWeb.cc`, and
`sandbox/wgpu-pipeline-integrated-smoke/first_pixel_settle_test.cc`.

## Class 145 — draw encoding is not selection-result admission

Signature: a selection output begins from a known clear, every required batch reaches a real
`Draw*` command, and the frontend immediately starts its ordered readback. Browser command error
scopes settle later; a rejected draw can therefore leave the clear readable even though the
synchronous pre-encode guard was correctly disarmed. Give every selection command a balanced
validation ticket, snapshot a selection-specific failure generation at attempt start, and keep the
mapped bytes private until all tickets settle. A late rejection cancels only that attempt and
retries after its settled validation edge; unrelated UI draw failures must not invalidate a valid
pick. Exercise rejection after readback begins, multiple outstanding draws, and a clean genuine
miss in native/wasm32 models. See `platform_web/ghost/GHOST_WebDisplayState.hh`,
`upstream/source/blender/gpu/intern/gpu_select_next.cc`,
`upstream/source/blender/gpu/webgpu/wgpu_batch.cc`, and
`sandbox/p0-interaction-stress/verify_select_draw_validation.py`.

## Class 146 — canceled modal continuations must not report backend failures through operator UI

Signature: an asynchronous browser operator correctly replays retained input and returns
`OPERATOR_CANCELLED`, yet every later action appears frozen. Blender's window manager opens a popup
for any entry in the completed operator's report list, regardless of report severity, so the popup
can immediately capture the replayed input and masquerade as a dead input/render loop. Keep backend
failure diagnostics bounded and fail-visible in the browser console, leave the operator report list
empty, replay retained input before teardown, and make the hardware producer reject the diagnostic
so graceful degradation cannot manufacture a pass. Preserve native reports. See
`upstream/source/blender/editors/space_view3d/view3d_select.cc`,
`upstream/source/blender/windowmanager/intern/wm_event_system.cc`, and
`sandbox/p0-interaction-stress/verify_select_stream_continuation.py`.

## Class 147 — every modal-continuation teardown must preserve its retained input

Signature: an asynchronous browser operator replays its FIFO on success, timeout, explicit Escape,
and backend failure, but its registered external `cancel` callback frees the continuation directly.
Window/area teardown or another WM-owned cancellation can then silently discard every ordinary
event captured while the request was pending, even though the GPU and event loop remain healthy.
Route external cancellation through the same replay-before-free ordering as other terminal paths;
reuse the continuation's manager/window identity guard so context drift never requeues input into a
replacement window. Mutation coverage must remove this one teardown replay independently of the
normal modal exits. See `upstream/source/blender/editors/space_view3d/view3d_select.cc` and
`sandbox/p0-interaction-stress/verify_select_stream_continuation.py`.

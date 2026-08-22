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

Signature: a backend creates a sampler or pipeline, inserts its handle into a cache, and only
then checks whether creation returned null. One transient failure permanently poisons that key:
later callers find the cached null and never retry creation. Keep the candidate local, reject
null first, and publish only a usable handle. When this appears once, census every cache for the
same create/publish order; framebuffer-local, context-local, and process-wide pools can duplicate
it independently. Bind every publication site to one source-order contract and exercise
fail-once/succeed-once behavior with a device-free handle/cache seam. See
`sandbox/wgpu-texture-integrated-smoke/` and `sandbox/wgpu-pipeline-integrated-smoke/`.

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
For suites that intentionally emit diagnostics during unittest progress, canonicalize only a
whole-output grammar: bind the exact ordered diagnostics and exact `Ran N tests`/`OK` tail, allow
dot/newline bytes only around that block, and require the total dot count to equal `N`.
When one platform moves a progress dot across an exact diagnostic boundary, enumerate the complete
anchored layout and restore that single dot before comparing streams. Keep platform null-pointer
spellings as an explicit finite set; do not mask arbitrary pointer-value text.

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

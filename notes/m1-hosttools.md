<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# Host codegen tools under node — the reusable build pattern

Date: 2026-08-03. Owner: build-deps worker.
Deliverable: `patches/0003-hosttools-node.patch` + `blender_web_host_tool()` in
`patches/platform_wasm.cmake`.

TL;DR: **Blender's build-time host codegen tools now run automatically under node
when cross-compiled to wasm — no manual relink, no manual invocation.** DNA
generation is proven end-to-end from a clean configure (5 files, sizes below).
Every later milestone that adds a "compile a tool, then run it during the build"
step hits the SAME wall and must reuse this pattern.

## The wall (why native execution fails under Emscripten)

Blender compiles small C++ programs (`makesdna`, `makesrna`, and later glsl/datatoc
codegen, icon generation, locale/`msgfmt`) and EXECUTES them mid-build to generate
source. Native, that's `add_custom_command(COMMAND $<TARGET_FILE:tool> ...)`. Under
Emscripten the "executable" is `tool.js` + `tool.wasm`, so invoking it directly is
`permission denied`. Two coupled causes:

1. **Invocation.** The tool must be launched as `node tool.js ...`. The Emscripten
   toolchain already sets `CMAKE_CROSSCOMPILING_EMULATOR` to node
   (`tools/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake`
   L373-378). CMake auto-applies that emulator to a custom command ONLY when the
   `COMMAND` is a **bare target name**. Blender invokes via
   `cmake -E env "$<TARGET_FILE:tool>"` — a file path, not a target name — so the
   emulator is never applied. **The `$<TARGET_FILE:>` form is the trap.**
2. **Link profile.** Host tools inherit the browser `PLATFORM_LINKFLAGS`:
   `-sPROXY_TO_PTHREAD` (runs `main()` off on a worker — wrong for a synchronous
   CLI) and no host filesystem (can't read/write the argv paths).

## The fix (both halves — you need both)

### Half A — invocation: prepend the emulator
In each tool's `add_custom_command`, insert `${CMAKE_CROSSCOMPILING_EMULATOR}`
immediately before `"$<TARGET_FILE:tool>"`. On native builds the variable is empty,
so the prefix is a no-op — the patch is portable. Result baked into `build.ninja`:

    cmake -E env <...> /…/tools/emsdk/node/22.16.0_64bit/bin/node /…/bin/makesdna.js <args>

### Half B — link profile: `blender_web_host_tool(<target>)`
Defined once in `patches/platform_wasm.cmake` (top-level scope, so it's visible in
every subdirectory's CMakeLists). Call it right after the tool's
`add_executable` / `setup_platform_linker_flags` block. It **overwrites** the
target's `LINK_FLAGS` (does not append) with a node-runnable profile:

    -pthread -sNODERAWFS -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH -sWASM_BIGINT -sPROXY_TO_PTHREAD=0

  * `-sPROXY_TO_PTHREAD=0` — `main()` runs on the main thread, synchronous CLI.
  * `-sNODERAWFS` — argv absolute paths map straight to node's real filesystem
    (no MEMFS mounting), so the generated files land on disk directly.
  * `-sEXIT_RUNTIME=1` — the process actually exits (0) so ninja sees success.
  * `-pthread` stays — the tool's objects were compiled `-pthread`; the
    shared-memory ABI must match at link.

Overwrite (not append) matters: appending would leave the inherited
`-sPROXY_TO_PTHREAD` and the `-sERROR_ON_WASM_CHANGES_AFTER_LINK` dev-guard on the
line. `set_target_properties(... LINK_FLAGS ...)` replaces the string that
`setup_platform_linker_flags()` appended.

## How to reuse for the next tool (shader codegen, icons, locale)

1. Wherever the tool is declared: `add_executable(<tool> ...)` →
   `if(COMMAND blender_web_host_tool) blender_web_host_tool(<tool>) endif()`.
2. In its `add_custom_command`, prepend `${CMAKE_CROSSCOMPILING_EMULATOR}` before
   `"$<TARGET_FILE:<tool>>"`.
3. If the tool reads/writes files by RELATIVE path or via cwd tricks, NODERAWFS is
   still correct (it's the real FS); only watch for tools that `chdir` or expect a
   specific working directory — set it via the custom command's `WORKING_DIRECTORY`.
4. Fold the CMake edit into a `patches/000N-*.patch` so the harness apply→configure
   →build stays one command. (This round: 0001 platform, 0002 makesdna wasm32
   alignment [source-correctness, other worker], 0003 host-tools-under-node [this].)

Note: a wasm host tool that must emit **target-ABI-correct** data (makesdna emits
struct offsets) can be wrong even when it runs fine — that's a separate class of
bug (wasm32 layout), owned by the tool's C++ source, not by this build wiring.

## Proof (this round)

Clean configure: `emcmake cmake -S upstream -B build-hosttools -G Ninja
-C patches/blender_web.cmake -DCMAKE_BUILD_TYPE=Release` → Configuring done (48 s).
`ninja -C build-hosttools source/blender/makesdna/intern/dna.cc` → BUILD OK: linked
`bin/makesdna.js` and ran it under node with ZERO manual steps, generating:

| file | bytes |
|---|---|
| dna.cc | 576896 |
| dna_defaults.cc | 594947 |
| dna_struct_ids.cc | 102505 |
| dna_type_offsets.h | 37372 |
| dna_verify.cc | 1062527 |

**RNA** (`makesrna`) is wired identically — the node prefix and the node-runnable
link profile are both present in `build.ninja` for `bin/makesrna.js` (verified) — but
`makesrna` links `bf_dna`, which compiles the generated `dna_verify.cc`. That
compile is gated on the makesdna wasm32-alignment fix (BLOCKER #2 in
`notes/m1-integrate.md`, owned by the makesdna-source worker). Once that lands and
`bf_dna` compiles, `ninja … rna_*_gen.cc` generates the RNA sources through this
same path with no further build-integration work.

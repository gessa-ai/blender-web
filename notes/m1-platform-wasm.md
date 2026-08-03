# M1 — Emscripten platform layer (platform_wasm.cmake)

## What the patch does

`patches/0001-platform-wasm.patch` adds an `if(EMSCRIPTEN)` branch to the "Main
Platform Checks" block in `upstream/CMakeLists.txt` (~L1541). It is checked
**before** the `UNIX AND NOT APPLE` branch because Emscripten sets `UNIX=TRUE`,
so without reordering it would wrongly pull in `platform_unix.cmake`. The branch:

1. Optionally appends `${BLENDER_WEB_PATCH_DIR}` to `CMAKE_MODULE_PATH` so
   `include(platform_wasm)` resolves (the file lives in the port's `patches/`, not
   in upstream's `build_files/cmake/platform/`).
2. `include(platform_wasm)`.

`patches/platform_wasm.cmake` is the wasm equivalent of `platform_unix.cmake`:

- **Lib discovery stub.** No `lib/wasm` harvest exists until M2, so it points
  `LIBDIR` at `${CMAKE_SOURCE_DIR}/lib/wasm` only if populated; otherwise forces
  `WITH_LIBS_PRECOMPILED OFF` and unsets `LIBDIR` (no glibc-ABI glob like unix).
  `WITH_STATIC_LIBS ON` (mono-wasm, no shared objects).
- **Compiler flags:** `-pthread` on C and C++ (atomics + bulk-memory + shared mem).
- **Linker flags (PLATFORM_LINKFLAGS):** `-pthread -sPROXY_TO_PTHREAD
  -sMALLOC=mimalloc -sWASM_BIGINT -sALLOW_MEMORY_GROWTH`, plus
  `-sERROR_ON_WASM_CHANGES_AFTER_LINK` on non-Release builds (dev fast-path guard).
- **LTO:** `WITH_COMPILER_LTO OFF` forced (fast incremental dev links).
- **Reserved, commented out:** `--use-port=emdawnwebgpu` (GPU, M3/M4) and `-sJSPI`
  (event loop, M4+). Not enabled for headless M1.

## How to apply

The diff is rooted at the upstream tree (`a/CMakeLists.txt`). From repo root:

    git apply --directory=upstream patches/0001-platform-wasm.patch

or from inside `upstream/`:

    git -C upstream apply ../patches/0001-platform-wasm.patch

Then make `platform_wasm.cmake` discoverable, either:

    emcmake cmake -DBLENDER_WEB_PATCH_DIR=$(pwd)/patches \
      -C patches/blender_web.cmake -S upstream -B build/wasm

or copy `patches/platform_wasm.cmake` into
`upstream/build_files/cmake/platform/` before configure (avoid: dirties the
read-only upstream tree — prefer the `-D` route).

## Open decisions (for the configure-attempt worker)

- **Module-path plumbing:** `-DBLENDER_WEB_PATCH_DIR` vs copying the file into the
  platform dir. Chosen the `-D` route to keep upstream pristine; confirm emcmake
  passes it through cleanly.
- **C++ exceptions:** not forced here. Emscripten defaults to no exceptions;
  OIIO / CPython (M2) likely need `-fexceptions` or `-sWASM_EXCEPTIONS`. Decide
  when those deps land — left off to keep the M1 surface minimal.
- **Memory sizing:** `INITIAL_MEMORY`, `STACK_SIZE`, `PTHREAD_POOL_SIZE` deferred
  to the runtime launcher, not baked into link flags.
- **`-sERROR_ON_WASM_CHANGES_AFTER_LINK`** gated on non-Release; verify it does not
  collide with any post-link pass the harness runs.
- **`WITH_CYCLES ON`** in `blender_web.cmake` may drag Embree/OSL-shaped find calls
  through the (now empty) LIBDIR — a configure attempt will confirm whether the
  CPU-only forcing is sufficient or Cycles must be OFF for M1 core-boots.

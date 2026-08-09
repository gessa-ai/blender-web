# SPDX-FileCopyrightText: 2016 Blender Authors
# SPDX-FileCopyrightText: 2026 blender-web contributors
#
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Ported for the web from build_files/cmake/platform/platform_unix.cmake @ fbe6228777e7
#
# Emscripten / WebAssembly platform layer for the blender-web port (Blender 5.2
# LTS, pin fbe6228777e7). This is the wasm equivalent of platform_unix.cmake /
# platform_apple.cmake: it stubs out the native lib/<platform> precompiled-library
# discovery (which has no wasm equivalent yet) and sets the Emscripten compiler /
# linker flags mandated by GOAL.md's "Emscripten posture" standing decision.
#
# Included from upstream/CMakeLists.txt's "Main Platform Checks" block via the
# `if(EMSCRIPTEN)` branch added by patches/0001-platform-wasm.patch. It runs in the
# top-level CMake scope, so it appends to the CMAKE_*_FLAGS / PLATFORM_LINKFLAGS
# variables initialised there (root CMakeLists.txt ~L1455-1464).

if(NOT EMSCRIPTEN)
  message(FATAL_ERROR "platform_wasm.cmake included on a non-Emscripten toolchain")
endif()

# find_package_wrapper is defined by platform_unix.cmake, which this file replaces
# for the Emscripten branch. A handful of downstream listfiles still reference it
# (e.g. tests/python/CMakeLists.txt, gated behind WITH_ALEMBIC). Provide the same
# thin shim so those paths don't hit an undefined-macro error.
macro(find_package_wrapper)
  find_package(${ARGV})
endmacro()

# check_freetype_for_brotli() is defined in platform_unix.cmake, which this file
# replaces for the Emscripten branch. Reproduced verbatim (per
# platform_unix.cmake @ fbe6228777e7, L173-191): the Freetype-with-brotli assert
# is run against our own cross-compiled FreeType (built FT_REQUIRE_BROTLI=ON).
function(check_freetype_for_brotli)
  if((DEFINED HAVE_BROTLI) AND (DEFINED HAVE_BROTLI_INC))
    if(HAVE_BROTLI AND ("${HAVE_BROTLI_INC}" STREQUAL "${FREETYPE_INCLUDE_DIRS}"))
      # Pass, the includes didn't change, use the cached value.
      return()
    endif()
  endif()

  unset(HAVE_BROTLI CACHE)
  include(CheckSymbolExists)
  set(CMAKE_REQUIRED_INCLUDES ${FREETYPE_INCLUDE_DIRS})
  check_symbol_exists(FT_CONFIG_OPTION_USE_BROTLI "freetype/config/ftconfig.h" HAVE_BROTLI)
  unset(CMAKE_REQUIRED_INCLUDES)
  if(NOT HAVE_BROTLI)
    unset(HAVE_BROTLI CACHE)
    message(FATAL_ERROR "Freetype needs to be compiled with brotli support!")
  endif()
  set(HAVE_BROTLI_INC "${FREETYPE_INCLUDE_DIRS}" CACHE INTERNAL "")
endfunction()

# -----------------------------------------------------------------------------
# Host codegen tools (makesdna / makesrna / ...) — run under node at build time
#
# Blender's build compiles several C++ "host tools" and then EXECUTES them during
# the build to GENERATE source (DNA structs, RNA bindings; later milestones: glsl
# datatoc, icons, locale). Under Emscripten those tools are .wasm/.js, not native
# binaries, so two things must change versus the browser link profile:
#
#   1. Invocation. The tool's add_custom_command must run `node <tool>.js ...`, not
#      the .js file directly (which fails "permission denied"). The Emscripten
#      toolchain sets CMAKE_CROSSCOMPILING_EMULATOR to node (Emscripten.cmake
#      @ L373-378). CMake applies that emulator automatically ONLY when a custom
#      command's COMMAND is a bare target name; Blender invokes the tool via
#      `cmake -E env "$<TARGET_FILE:tool>"`, which bypasses that path. So each such
#      custom_command is patched to prepend ${CMAKE_CROSSCOMPILING_EMULATOR} before
#      the tool path (patches/0002-hosttools-node.patch). On native builds the var
#      is empty, so the prefix is a no-op.
#
#   2. Link profile. The default browser profile (PLATFORM_LINKFLAGS) proxies main()
#      to a worker (-sPROXY_TO_PTHREAD) and gives the module no host filesystem —
#      both wrong for a build-time CLI. blender_web_host_tool() below overwrites the
#      target's LINK_FLAGS with a node-runnable profile: main() on the main thread,
#      -sEXIT_RUNTIME so the process exits, -sNODERAWFS so the absolute host paths
#      passed as argv read/write the real filesystem. This is the exact mechanism
#      proven manually in notes/m1-integrate.md (blocker #1, "FIX PATH PROVEN").
#
# Later milestones that add host tools (shader/glsl codegen, icon and locale
# generation) MUST reuse BOTH halves — see notes/m1-hosttools.md.
function(blender_web_host_tool target)
  if(NOT EMSCRIPTEN)
    return()
  endif()
  # OVERWRITE (not append) the LINK_FLAGS that setup_platform_linker_flags() set
  # from PLATFORM_LINKFLAGS: -sPROXY_TO_PTHREAD, -sMALLOC=mimalloc and the
  # changes-after-link guard are all wrong for a node CLI. -pthread stays — the
  # tool's objects were compiled with it (shared-memory ABI must match).
  set_target_properties(${target} PROPERTIES
    LINK_FLAGS
      "-pthread -sNODERAWFS -sEXIT_RUNTIME=1 -sALLOW_MEMORY_GROWTH -sWASM_BIGINT -sPROXY_TO_PTHREAD=0")
endfunction()

# -----------------------------------------------------------------------------
# The main `blender` executable — node-runnable headless profile (M2.3/M2.5)
#
# This is DELIBERATELY a separate function from blender_web_host_tool(), not a
# reuse of it (the two profiles differ on the load-bearing PROXY_TO_PTHREAD axis).
# Called from source/creator/CMakeLists.txt via patches/0010-* right after
# add_executable(blender ...).
#
# Profile rationale (explicit, per the M2.3 link-profile decision):
#   * -sPROXY_TO_PTHREAD (ON) — main() runs on a pthread, the browser/node main
#     thread stays free to service the event loop. This is what lets a multithreaded
#     (TBB) binary block on pthread_join / TBB barriers WITHOUT deadlocking on
#     on-demand worker creation. It is the SAME profile the tier-(a) gtest binaries
#     (bmesh_core_test, ~200 archives incl. TBB) linked and RAN under node with
#     (proven: M1.11). The host-tool profile uses PROXY_TO_PTHREAD=0 because those
#     tools are single-threaded CLIs; blender is not. ADR-001's "Python runs
#     synchronously on the (proxied) main thread" explicitly assumes this proxied
#     posture (M2 uses NO -sJSPI, so there is no suspension and no setjmp/JSPI
#     hazard — ADR-003). EXIT_RUNTIME=1 makes the proxied process still exit with
#     main()'s return code instead of keeping node's worker pool alive.
#   * -sNODERAWFS — argv paths + PYTHONHOME/BLENDER_SYSTEM_* map straight onto
#     node's real filesystem, so the harvested stdlib (lib/wasm/lib/python3.13) and
#     the upstream scripts tree load from real absolute paths.
#   * -sEXIT_RUNTIME=1 — process exits (headless verification / harness).
#   * -sSTACK_SIZE — Blender has dynamic-size alloca sites (recon: 6 in blenkernel)
#     and deep recursion; emscripten's default 64 KiB main stack is far too small.
#     Raise to 8 MiB (matches a typical native main-thread stack).
#   * -sTOTAL_MEMORY left to grow (ALLOW_MEMORY_GROWTH); big scenes are unbounded.
# OVERWRITE the target LINK_FLAGS so blender is node-runnable INDEPENDENT of
# WITH_GTESTS (whose block also happens to add NODERAWFS/EXIT_RUNTIME globally —
# we do not want blender's runnability to silently depend on that).
function(blender_web_node_binary target)
  if(NOT EMSCRIPTEN)
    return()
  endif()
  # -sMALLOC=dlmalloc (NOT mimalloc) for the blender binary specifically:
  # CPython 3.13 VENDORS its own mimalloc (libpython3.13.a(obmalloc.o) defines the
  # full public mi_* API, 276 globals) for PyObject allocation. Linking emscripten's
  # -sMALLOC=mimalloc (libmimalloc-mt.a) alongside it is a hard duplicate-symbol
  # link error (mi_malloc/mi_free/mi_new/...). We keep CPython's internal mimalloc
  # (the perf-critical Python-object path GOAL's mimalloc decision cares about) and
  # give the C heap emscripten's dlmalloc, which is thread-safe under -pthread and
  # is exactly the allocator the M2.0b libpython-embed probe ran clean on. The
  # gtest / host-tool binaries keep -sMALLOC=mimalloc (they don't link libpython,
  # so no clash) — this override is isolated to the target that embeds CPython.
  # -sINITIAL_MEMORY: the linked module's static data (RNA/DNA tables, the frozen
  # stdlib, string pools) exceeds emscripten's 16 MiB default, so wasm-ld errors
  # "initial memory too small". 512 MiB is a generous initial reservation; growth
  # (ALLOW_MEMORY_GROWTH, bounded by the default 2 GiB maximum) handles scenes.
  # --profiling-funcs: preserve the wasm name section through wasm-opt so node
  # stack traces symbolicate to real function names — essential while iterating the
  # headless boot (a bare -O2 build strips names, leaving only function indices).
  # Cheap (link-time only, no recompile); revisit for the eventual shipping profile.
  # --pre-js node-fstat-shim.js: work around an emscripten NODEFS.fstat bug that
  # only affects the NODERAWFS (node headless) build — it dereferences stream.node
  # without guarding it, so fstat() on a NODERAWFS standard stream (fd 0/1/2, no
  # virtual node) throws instead of falling through to fs.fstatSync(stream.nfd).
  # CPython fstat()s stdio during init, so this is the Python-boot blocker. NODE-ONLY;
  # the browser/WASMFS build has no NODEFS.fstat and does not get this --pre-js. See
  # the shim file for the exact bug + upstream-fix note.
  set(_bw_node_flags
    "-pthread -fexceptions -sMALLOC=dlmalloc -sWASM_BIGINT -sALLOW_MEMORY_GROWTH \
-sINITIAL_MEMORY=536870912 -sPROXY_TO_PTHREAD -sNODERAWFS -sEXIT_RUNTIME=1 -sSTACK_SIZE=8388608 \
--profiling-funcs --pre-js ${BLENDER_WEB_PATCH_DIR}/node-fstat-shim.js")
  if(NOT CMAKE_BUILD_TYPE STREQUAL "Release")
    string(APPEND _bw_node_flags " -sERROR_ON_WASM_CHANGES_AFTER_LINK")
  endif()
  set_target_properties(${target} PROPERTIES LINK_FLAGS "${_bw_node_flags}")
endfunction()

# =============================================================================
# BEGIN BLENDER-WEB BROWSER TARGET SECTION (M4.pre — browser boot shell)
# -----------------------------------------------------------------------------
# Owned by the ghost-web shell round. Everything between the BEGIN/END markers is
# the browser-side link profile; no other worker edits this section.
#
# `blender_browser` is byte-for-byte the SAME compiled Blender as the node
# `blender` target (identical object archives), relinked for a real browser tab:
#
#   node `blender`            browser `blender_browser`
#   ----------------------    ------------------------------------------------
#   -sNODERAWFS               (none) — browsers have no host filesystem
#   (classic FS)              -sWASMFS — filesystem in SHARED linear memory, so
#                             the preloaded payload is visible on the
#                             PROXY_TO_PTHREAD worker that runs main() (classic
#                             MEMFS keeps its dir tree as per-thread JS objects the
#                             proxied main thread never sees). Also GOAL.md's
#                             standing FS decision (WasmFS + OPFS).
#   BLENDER_SYSTEM_* = host   BLENDER_SYSTEM_* = /bw/... WasmFS mounts populated by
#   absolute paths            --preload-file packages (boot.js echoes the mounts
#                             into ENV; see platform_web/shell/).
#   runs immediately          -sMODULARIZE + EXPORT_NAME — boot.js owns the Module
#                             config (arguments / ENV / print / printErr / onExit).
#
# Everything else (dlmalloc for the CPython-mimalloc clash, PROXY_TO_PTHREAD for
# TBB, 512 MiB + growth, 8 MiB stack, WASM_BIGINT, JS-EH) matches the node profile
# so behaviour is identical — reproducing the known layer_utils.cc:205 startup
# abort in the tab proves the whole browser layer, and `import bpy` goes green the
# moment the in-flight DNA-reconstruct fix lands.
#
# Gated behind WITH_BLENDER_WEB_BROWSER (default OFF) *and* EXCLUDE_FROM_ALL so it
# never burdens the node/gtest iteration builds other workers run in this shared
# tree — it is built ONLY on an explicit `ninja blender_browser`.
option(WITH_BLENDER_WEB_BROWSER
  "blender-web: also emit the browser-linked `blender_browser` executable (M4.pre shell)"
  OFF)

# Port repo root (parent of the patches/ dir). Anchors the preload payload roots.
if(NOT DEFINED BLENDER_WEB_REPO_ROOT)
  if(DEFINED BLENDER_WEB_PATCH_DIR)
    get_filename_component(BLENDER_WEB_REPO_ROOT "${BLENDER_WEB_PATCH_DIR}/.." ABSOLUTE)
  else()
    get_filename_component(BLENDER_WEB_REPO_ROOT "${CMAKE_SOURCE_DIR}/.." ABSOLUTE)
  endif()
endif()

# Registered via cmake_language(DEFER) from this file (top-level scope) so it runs
# at the END of the top-level CMakeLists — AFTER add_subdirectory(source/creator)
# has fully defined `blender` (sources, link libraries, include dirs). We do NOT
# patch source/creator/CMakeLists.txt: upstream is harness-protected, and a numbered
# creator hook is unnecessary — DEFER + a full property clone gets the same result
# with zero upstream surface.
#
# The one wrinkle of cloning outside creator's directory scope: directory-level
# add_definitions()/include_directories() (e.g. creator's -DWITH_PYTHON, USD paths)
# do NOT auto-apply to a target created in the top-level scope, so we harvest the
# creator directory's COMPILE_DEFINITIONS / INCLUDE_DIRECTORIES / COMPILE_OPTIONS
# and merge them in. (The global -pthread/-fexceptions/-funsigned-char flags live in
# CMAKE_CXX_FLAGS, which applies in every scope, so those need no harvesting.)
function(blender_web_browser_binary src_target)
  if(NOT EMSCRIPTEN OR NOT WITH_BLENDER_WEB_BROWSER)
    return()
  endif()
  if(NOT TARGET ${src_target})
    message(FATAL_ERROR "blender-web browser: source target `${src_target}` does not exist")
  endif()
  set(_new blender_browser)
  if(TARGET ${_new})
    return()
  endif()

  # ---- clone the compiled Blender: same sources / libs / includes / defs -------
  get_target_property(_srcs ${src_target} SOURCES)
  get_target_property(_sdir ${src_target} SOURCE_DIR)
  set(_abs_srcs "")
  foreach(_s IN LISTS _srcs)
    if(IS_ABSOLUTE "${_s}")
      list(APPEND _abs_srcs "${_s}")
    else()
      list(APPEND _abs_srcs "${_sdir}/${_s}")
    endif()
  endforeach()

  add_executable(${_new} EXCLUDE_FROM_ALL ${_abs_srcs})
  add_dependencies(${_new} makesdna)

  # Target-level properties carried across verbatim.
  foreach(_prop LINK_LIBRARIES COMPILE_FEATURES)
    get_target_property(_val ${src_target} ${_prop})
    if(_val)
      set_target_properties(${_new} PROPERTIES ${_prop} "${_val}")
    endif()
  endforeach()

  # Definitions / includes / options = target-level  +  creator directory-level.
  foreach(_prop COMPILE_DEFINITIONS INCLUDE_DIRECTORIES COMPILE_OPTIONS)
    set(_merged "")
    get_target_property(_tv ${src_target} ${_prop})
    if(_tv)
      list(APPEND _merged ${_tv})
    endif()
    get_directory_property(_dv DIRECTORY "${_sdir}" ${_prop})
    if(_dv)
      list(APPEND _merged ${_dv})
    endif()
    if(_merged)
      list(REMOVE_DUPLICATES _merged)
      set_target_properties(${_new} PROPERTIES ${_prop} "${_merged}")
    endif()
  endforeach()

  # ---- browser link profile ----------------------------------------------------
  # NOTE: no -sERROR_ON_WASM_CHANGES_AFTER_LINK here (unlike the node profile): the
  # incremental-link fast-path guard is irrelevant for this one-off artifact and a
  # false trip would waste an iteration. --profiling-funcs keeps named stack traces
  # in the browser console while iterating the boot.
  # -sEXPORTED_RUNTIME_METHODS=ENV — expose the runtime ENV object on the module so
  # the shell's boot.js can set BLENDER_SYSTEM_PYTHON/SCRIPTS/DATAFILES to the WasmFS
  # mounts in preRun (the browser equivalent of the node recipe's env triad). FS is
  # exported too so the shell / node verifier can sanity-check the preloaded tree.
  set(_bw_browser_flags
    "-pthread -fexceptions -sMALLOC=dlmalloc -sWASM_BIGINT -sALLOW_MEMORY_GROWTH \
-sINITIAL_MEMORY=536870912 -sPROXY_TO_PTHREAD -sEXIT_RUNTIME=1 -sSTACK_SIZE=8388608 \
-sPTHREAD_POOL_SIZE=8 -sWASMFS -sFORCE_FILESYSTEM=1 \
-sMODULARIZE=1 -sEXPORT_NAME=createBlenderModule -sEXPORTED_RUNTIME_METHODS=ENV,FS,callMain")

  # BEGIN BLENDER-WEB NAME-SECTION STRIP (M8 size lane; reverse-appliable block)
  # The wasm `name` section is ~1 MB brotli of pure function-name debug metadata
  # (sandbox/m8-dce-ranking/RANKING.md item 1: ~23 MB raw -> ~1.1 MB brotli in the
  # shipped module) and serves ONLY debugging/profiling. It exists here solely
  # because --profiling-funcs sets emscripten's EMIT_NAME_SECTION=1
  # (tools/emsdk/upstream/emscripten/tools/cmdline.py:417). So gate it on the build
  # type instead of emitting it unconditionally:
  #   * Release (the SHIPPED browser binary) -> append -g0, which forces
  #     EMIT_NAME_SECTION=0 (cmdline.py:362-366), order-independent -> the name
  #     section is dropped. ~1 MB brotli saved, ZERO feature risk, no patch, no
  #     recompile (link-flag only). This is RANKING.md's item-1 "-sno-name-section"
  #     lever (there is no literal -s NO_NAME_SECTION in emcc 6.0.5; -g0 is the
  #     supported spelling).
  #   * non-Release (RelWithDebInfo / Debug dev + iteration builds) -> keep
  #     --profiling-funcs so named stack traces AND the DCE census survive. The
  #     census (llvm-nm --print-size --demangle for per-subsystem byte attribution)
  #     now runs on the RelWithDebInfo twin `build-wasm-windowed`, which is the SAME
  #     -O2 objects as the Release tree, so per-function CODE sizes are identical to
  #     the shipped module -- the census loses nothing. See
  #     notes/m8-soak-and-namestrip.md for the before/after measurement + rationale.
  if(CMAKE_BUILD_TYPE STREQUAL "Release")
    string(APPEND _bw_browser_flags " -g0")
  else()
    string(APPEND _bw_browser_flags " --profiling-funcs")
  endif()
  # END BLENDER-WEB NAME-SECTION STRIP

  # ---- preload payload (host path @ WasmFS mount) ------------------------------
  # Mirrors the node boot recipe's BLENDER_SYSTEM_* triad (notes/m2-python-boot.md).
  # Wholesale dirs for the SIMPLEST-that-boots profile; M7 replaces this with staged
  # lazy fetch + stdlib tree-shaking (documented in notes/m4-browser-shell.md).
  set(_py_home   "${BLENDER_WEB_REPO_ROOT}/lib/wasm/lib/python3.13")
  set(_scripts   "${BLENDER_WEB_REPO_ROOT}/upstream/scripts")
  set(_datafiles "${BLENDER_WEB_REPO_ROOT}/upstream/release/datafiles")
  foreach(_p "${_py_home}" "${_scripts}" "${_datafiles}")
    if(NOT EXISTS "${_p}")
      message(FATAL_ERROR "blender-web browser: preload root missing: ${_p}")
    endif()
  endforeach()
  string(APPEND _bw_browser_flags
    " --preload-file ${_py_home}@/bw/python/lib/python3.13"
    " --preload-file ${_scripts}@/bw/scripts"
    " --preload-file ${_datafiles}@/bw/datafiles")

  # blender-web / D-10 (WITH_INTERNATIONAL): the compiled .mo catalogs + the `languages`
  # index live in a repo-owned tree (scripts/build-locale-datafiles.sh -> build-hosttools/
  # locale), NOT in the read-only upstream datafiles, so they ride their own preload root
  # mounted under /bw/datafiles at /bw/datafiles/locale (where BKE_appdir resolves
  # BLENDER_DATAFILES + "locale"). The stager (stage_pack.py) keeps `languages` in stage-0
  # and defers the 49 .mo to stage-1 with the CJK fonts. See notes/i18n-restore-r45.md.
  if(WITH_INTERNATIONAL)
    set(_locale "${BLENDER_WEB_REPO_ROOT}/build-hosttools/locale")
    if(NOT EXISTS "${_locale}/languages")
      message(FATAL_ERROR
        "blender-web browser: WITH_INTERNATIONAL is ON but the locale payload is missing "
        "at ${_locale}. Run scripts/build-locale-datafiles.sh before configuring.")
    endif()
    string(APPEND _bw_browser_flags
      " --preload-file ${_locale}@/bw/datafiles/locale")
  endif()

  # ---- M4 windowed (WITH_WEBGPU_BACKEND) link additions ------------------------
  # The base flags above OVERWRITE LINK_FLAGS, so the WebGPU arm's PLATFORM_LINKFLAGS
  # (--use-port=emdawnwebgpu) are dropped for this target — re-add them here, plus:
  #   * -sSTACK_SIZE=32MB (+ DEFAULT_PTHREAD_STACK_SIZE): the runtime shader chain
  #     (glslang/Tint recursion) blows emscripten's 64 KB default; deps-shader-chain.md
  #     finding 3. Later -s wins, so this overrides the 8 MB above.
  # NO -sJSPI (M4 T9 empirical finding, notes/m4-integration.md T9): -sJSPI was added
  # for GHOST_ContextWGPUWeb::initializeDrawingContext()'s WaitAny device await, but
  # (a) it is UNNEEDED — the device is acquired ASYNC on the PROXY_TO_PTHREAD WM worker
  # BEFORE main() runs (see the --post-js below; M4.T11/ADR-007), so initializeDrawing-
  # Context() imports it synchronously and never blocks, and
  # (b) it is HARMFUL — Emscripten wraps only `main`/the pthread entry with
  # WebAssembly.promising; `__wasm_call_ctors` runs raw on the MAIN thread in
  # initRuntime() BEFORE main, so any -sJSPI suspend reached from a C++ static ctor
  # (observed: std::ios_base::Init::Init during _GLOBAL__I) throws
  # "trying to suspend without WebAssembly.promising" and aborts boot before the banner.
  # WGPU_TINT_LIBS (shaderc+Tint archives) are linked via bf_gpu's LINK_LIBRARIES,
  # cloned into this target — no extra flag needed here.
  #
  # --post-js wgpu-preinit-worker.js (M4.T11 / ADR-007): the emdawnwebgpu WebGPU device
  # cannot be acquired synchronously without asyncify and cannot cross Worker realms
  # (notes/m4-integration.md "M4.T11" probe), so it must be acquired ASYNC on the WM
  # worker itself, pre-main. This post-js runs in every pthread worker and, for the
  # proxied application-main thread only, awaits navigator.gpu.request{Adapter,Device}()
  # and stashes the device in Module.preinitializedWebGPUDevice before dispatching the
  # cmd:2 entry message. initializeDrawingContext() then pulls it via
  # emscripten_webgpu_get_device().
  if(WITH_WEBGPU_BACKEND)
    string(APPEND _bw_browser_flags
      " --use-port=emdawnwebgpu"
      " -sSTACK_SIZE=33554432 -sDEFAULT_PTHREAD_STACK_SIZE=33554432"
      # M4.T12 first-window pixels: transfer the DOM `#canvas` to the proxied-main
      # (WM) worker as an OffscreenCanvas so emdawnwebgpu's CreateSurface ->
      # findCanvasEventTarget('#canvas') resolves THERE (the worker has no `document`;
      # without the transfer the selector is unresolvable and the surface is deferred,
      # leaving the window framebuffer attachmentless -> Dawn "Render pass has no
      # attachments"). PROXY_TO_PTHREAD's crt1 already requests the transfer
      # (crt1_proxy_main.c:48 settransferredcanvases(-1)); these two flags provide the
      # OffscreenCanvas support + name the canvas to hand over. See
      # notes/m4-integration.md "M4.T11" surface section + ADR-007. Single-quote the
      # selector so ninja's `sh -c` does not treat `#canvas` as a comment.
      " -sOFFSCREENCANVAS_SUPPORT -sOFFSCREENCANVASES_TO_PTHREAD='#canvas'"
      " --post-js ${BLENDER_WEB_REPO_ROOT}/platform_web/shell/wgpu-preinit-worker.js")
  endif()

  set_target_properties(${_new} PROPERTIES LINK_FLAGS "${_bw_browser_flags}")

  # ---- strip triplicate __pycache__ from the preload payload -------------------
  # BEGIN BLENDER-WEB PYCACHE PRUNE (M8 size lane; reverse-appliable block)
  # Emscripten --preload-file / file_packager has NO exclude globs, so without this
  # the .data packs every stdlib + script .py PLUS its .pyc at 3 optimisation levels
  # (plain/opt-1/opt-2) -- ~46 MiB of pure redundancy measured on this tree. Keeping
  # .py only is import-safe (CPython recompiles to memory on first import; the harvest
  # side does the same drop in scripts/deps/python.sh). This PRE_LINK step guarantees
  # a clean .data regardless of how a local tree accumulated __pycache__ (e.g. a native
  # oracle run leaving .pyc under upstream/scripts, which ships .py only at the pin).
  # It runs ONLY when blender_browser actually links (EXCLUDE_FROM_ALL target), so the
  # node/gtest iteration builds other lanes run in this shared tree are untouched.
  # Idempotent -> safe to re-run; see notes/m8-pycache-strip.md.
  add_custom_command(TARGET ${_new} PRE_LINK
    COMMAND bash
      "${BLENDER_WEB_REPO_ROOT}/scripts/deps/prune-preload-pycache.sh"
      "${_py_home}" "${_scripts}" "${_datafiles}"
    COMMENT "blender-web: pruning __pycache__ from preload roots (py-only .data)"
    VERBATIM)
  # END BLENDER-WEB PYCACHE PRUNE

  message(STATUS
    "blender-web: browser target `blender_browser` enabled "
    "(WasmFS + preload, virtual root /bw). Build: ninja blender_browser")
endfunction()

# Defer the clone to the end of this (top-level) directory scope, once the `blender`
# target from source/creator has been fully defined. No-op unless the browser target
# is explicitly requested (-DWITH_BLENDER_WEB_BROWSER=ON).
if(EMSCRIPTEN AND WITH_BLENDER_WEB_BROWSER)
  cmake_language(DEFER CALL blender_web_browser_binary blender)
endif()
# END BLENDER-WEB BROWSER TARGET SECTION
# =============================================================================

# -----------------------------------------------------------------------------
# Native host codegen tools (ADR-002)
#
# shader_tool and datatoc emit target-INDEPENDENT text (byte-identity verified,
# native == wasm wherever the wasm tool functions — notes/m1-shader-codegen-wasm.md).
# The wasm build of shader_tool mis-tokenizes some shaders (silent corruption /
# hangs), so per ADR-002 these two tools run as NATIVE host binaries built with the
# host compiler into build-hosttools/bin-native/. macros.cmake's data_to_c* and
# shader-info custom commands pick these up via BLENDER_WEB_HOST_TOOLS_DIR. (Unlike
# makesdna/makesrna, which bake target ABI and MUST stay wasm-under-node.)
if(NOT DEFINED BLENDER_WEB_HOST_TOOLS_DIR)
  get_filename_component(BLENDER_WEB_HOST_TOOLS_DIR
    "${BLENDER_WEB_PATCH_DIR}/../build-hosttools/bin-native" ABSOLUTE)
  set(BLENDER_WEB_HOST_TOOLS_DIR "${BLENDER_WEB_HOST_TOOLS_DIR}" CACHE PATH
    "Directory of native host codegen tools (shader_tool, datatoc) per ADR-002")
endif()
if(NOT EXISTS "${BLENDER_WEB_HOST_TOOLS_DIR}/shader_tool"
   OR NOT EXISTS "${BLENDER_WEB_HOST_TOOLS_DIR}/datatoc")
  message(FATAL_ERROR
    "blender-web ADR-002: native host tools not found in "
    "${BLENDER_WEB_HOST_TOOLS_DIR} (need shader_tool + datatoc). "
    "Build them first: see notes/m1-shader-codegen-wasm.md.")
endif()

# Host Python interpreter for build-time codegen SCRIPTS (e.g. discover_nodes.py,
# which generates the node-registration .cc). These are pure-Python and run on the
# BUILD host — unrelated to the embedded interpreter (WITH_PYTHON=OFF for M1). The
# Emscripten toolchain does not set PYTHON_EXECUTABLE, and discover_nodes.py is not
# executable / has no shebang, so Blender's add_node_discovery() would invoke it
# directly and fail with rc 126 ("Permission denied"). Prefer the emsdk-bundled
# python (pinned with the toolchain); else fall back to a host python3, bypassing the
# Emscripten find-root so we resolve a HOST (not target) binary.
if(NOT PYTHON_EXECUTABLE)
  file(GLOB _bw_host_python "${BLENDER_WEB_PATCH_DIR}/../tools/emsdk/python/*/bin/python3")
  if(_bw_host_python)
    list(GET _bw_host_python 0 PYTHON_EXECUTABLE)
  else()
    find_program(PYTHON_EXECUTABLE NAMES python3 python NO_CMAKE_FIND_ROOT_PATH)
  endif()
  set(PYTHON_EXECUTABLE "${PYTHON_EXECUTABLE}" CACHE FILEPATH
    "Host Python for blender-web build-time codegen scripts")
  unset(_bw_host_python)
  message(STATUS "blender-web: host PYTHON_EXECUTABLE = ${PYTHON_EXECUTABLE}")
endif()

# -----------------------------------------------------------------------------
# Precompiled library discovery
#
# There is no `lib/wasm` harvest until M2 (the build_environment superbuild has
# not been cross-compiled yet). Unlike platform_unix.cmake we do NOT glob a
# glibc-ABI LIBDIR; instead we point LIBDIR at lib/wasm only if it has been
# populated, and otherwise disable precompiled libs entirely so find_package()
# falls through cleanly during headless core bring-up.

if(NOT DEFINED LIBDIR)
  # The wasm harvest prefix lives at the PORT repo root (lib/wasm), which is the
  # PARENT of the upstream Blender tree passed as -S. CMAKE_SOURCE_DIR is that
  # upstream tree, so anchor LIBDIR on BLENDER_WEB_PATCH_DIR (the port's patches/
  # dir, set by blender_web.cmake) whose parent is the repo root. Fall back to the
  # CMAKE_SOURCE_DIR sibling if the patch dir var is somehow unset.
  if(DEFINED BLENDER_WEB_PATCH_DIR)
    get_filename_component(LIBDIR "${BLENDER_WEB_PATCH_DIR}/../lib/wasm" ABSOLUTE)
  else()
    get_filename_component(LIBDIR "${CMAKE_SOURCE_DIR}/../lib/wasm" ABSOLUTE)
  endif()
endif()

file(GLOB _wasm_libdir_contents "${LIBDIR}/*")
if(_wasm_libdir_contents)
  set(WITH_LIBS_PRECOMPILED ON)
  set(CMAKE_PREFIX_PATH "${LIBDIR}" ${CMAKE_PREFIX_PATH})
  # The Emscripten toolchain re-roots find_library()/find_path()/find_package()
  # at its own sysroot (CMAKE_FIND_ROOT_PATH_MODE_{LIBRARY,INCLUDE}=ONLY), so a
  # bare find_* cannot see lib/wasm. Appending LIBDIR to CMAKE_FIND_ROOT_PATH
  # makes the wasm prefix a first-class search root — the same remedy the dep
  # cross-build scripts used (e.g. opencolorio.sh passes -DCMAKE_FIND_ROOT_PATH).
  # Belt-and-suspenders: the resolution block below also seeds explicit
  # <Pkg>_DIR / <PKG>_LIBRARY hint vars so every find is deterministic.
  list(APPEND CMAKE_FIND_ROOT_PATH "${LIBDIR}")
  if(FIRST_RUN)
    message(STATUS "blender-web: using wasm LIBDIR: ${LIBDIR}")
  endif()
else()
  # M1 headless-core bring-up: no harvested deps yet.
  set(WITH_LIBS_PRECOMPILED OFF)
  unset(LIBDIR)
  if(FIRST_RUN)
    message(STATUS "blender-web: no wasm LIBDIR populated yet (pre-M2); "
                   "WITH_LIBS_PRECOMPILED forced OFF.")
  endif()
endif()
unset(_wasm_libdir_contents)

# Prefer static libraries (there is no shared-object loading in mono-wasm).
set(WITH_STATIC_LIBS ON)

# -----------------------------------------------------------------------------
# GPU backend selection — WebGPU only (no GL, no Vulkan, no Epoxy)
#
# On non-Apple platforms upstream defaults WITH_OPENGL_BACKEND=ON and
# WITH_VULKAN_BACKEND=ON (root CMakeLists.txt L933/L941), and platform_unix.cmake
# then `find_package_wrapper(Epoxy REQUIRED)` (GL loader) and, under Vulkan,
# `find_package_wrapper(ShaderC REQUIRED)` / FindVulkan. This port bypasses
# platform_unix, so those REQUIRED finds never run — but the option defaults would
# still switch on the GL and Vulkan backend code in source/blender/gpu. The port
# ships its own `gpu/webgpu/` backend instead, so force both legacy backends OFF:
#
#   * OpenGL OFF  -> drops the Epoxy dependency entirely (its only REQUIRED find
#                    lived in platform_unix; no WebGPU consumer of GL exists).
#   * Vulkan OFF  -> drops Vulkan + ShaderC. The BSL->SPIR-V->WGSL shader chain
#                    (M3) will re-introduce shaderc/Tint through the WebGPU backend,
#                    not through WITH_VULKAN_BACKEND.
#
# These run after the option() declarations (root L933/L941) but before the gpu
# subdirectory is added, so FORCE wins.
set(WITH_OPENGL_BACKEND OFF CACHE BOOL "" FORCE)  # no GL in a WebGPU-only build (drops Epoxy)
set(WITH_VULKAN_BACKEND OFF CACHE BOOL "" FORCE)  # WebGPU backend replaces Vulkan/ShaderC

# Neutralize Epoxy so nothing downstream can hard-require it. dependency_targets.cmake
# still builds an INTERFACE bf_deps_epoxy from these vars (harmless when empty); the
# only find_package(Epoxy REQUIRED) was in platform_unix, which we do not include.
set(EPOXY_INCLUDE_DIRS "" CACHE STRING "" FORCE)
set(EPOXY_LIBRARIES    "" CACHE STRING "" FORCE)

# -----------------------------------------------------------------------------
# WebGPU backend for wasm (cycle-6) — emdawnwebgpu port + wasm Tint/shaderc harvest
#
# ADDITIVE + DEFAULT OFF. WITH_WEBGPU_BACKEND defaults OFF (root CMakeLists.txt:961)
# and is declared BEFORE this file is included (:1555), so this arm is INERT in the
# shared headless build-wasm — that configure is untouched. A dedicated WebGPU
# compile tree opts in with `-DWITH_WEBGPU_BACKEND=ON` (WITH_HEADLESS stays ON: this
# is the GPU-backend arm ONLY; it does NOT pull the windowed GHOST/UI stack the way
# WITH_BLENDER_WEB_WINDOWED does — that is a separate, heavier profile).
#
# gpu/CMakeLists.txt's WITH_WEBGPU_BACKEND arm (:476) consumes DAWN_INCLUDE_DIRS /
# TINT_INCLUDE_DIRS / SHADERC_INCLUDE_DIR (INC_SYS) + DAWN_LIBRARIES / WGPU_TINT_LIBS
# (LIB). build-native-gpu points those at a native Dawn checkout. The wasm mapping:
#   * webgpu.h / webgpu_cpp.h come from the emdawnwebgpu PORT via --use-port (NOT a
#     Dawn include dir): the port tracks the same chromium/7989 C++ spelling the
#     backend TUs were written against — verified, all 18 webgpu TUs compile clean
#     with ZERO source changes (notes/gpu-wasm-compile.md). So DAWN_INCLUDE_DIRS is
#     empty; the port include is added to the COMPILE flags globally instead.
#   * Tint headers = the pinned Dawn source (src/tint/...), same as native.
#   * shaderc headers = the cross-compiled harvest lib/wasm/shaderc/include.
#   * WGPU_TINT_LIBS (the archive set) is a LINK-time concern (the later full-binary
#     step, not this compile round); wired from the harvested ordered lists so the
#     eventual link is ready. emdawnwebgpu provides the device at link, so
#     DAWN_LIBRARIES stays empty.
if(WITH_WEBGPU_BACKEND)
  get_filename_component(_bw_repo "${BLENDER_WEB_PATCH_DIR}/.." ABSOLUTE)
  set(_bw_dawn "${_bw_repo}/build-dawn/dawn")
  if(NOT EXISTS "${_bw_dawn}/src/tint/lang/spirv/reader/reader.h")
    message(FATAL_ERROR
      "blender-web: WITH_WEBGPU_BACKEND=ON but the pinned Dawn/Tint source is missing "
      "at ${_bw_dawn} (needed for Tint headers). See notes/gpu-dawn-probe.md.")
  endif()
  if(NOT EXISTS "${LIBDIR}/shaderc/include/shaderc/shaderc.hpp")
    message(FATAL_ERROR
      "blender-web: WITH_WEBGPU_BACKEND=ON but the wasm shaderc harvest is missing at "
      "${LIBDIR}/shaderc. Build it: scripts/deps/shaderc.sh (notes/deps-shader-chain.md).")
  endif()

  # emdawnwebgpu port: webgpu/webgpu{,_cpp}.h at COMPILE (and the JS/wasm binding at
  # LINK). MUST be on the compile flags so the backend TUs resolve the header.
  string(APPEND CMAKE_C_FLAGS       " --use-port=emdawnwebgpu")
  string(APPEND CMAKE_CXX_FLAGS     " --use-port=emdawnwebgpu")
  string(APPEND PLATFORM_CFLAGS     " --use-port=emdawnwebgpu")
  string(APPEND PLATFORM_LINKFLAGS  " --use-port=emdawnwebgpu")

  set(DAWN_INCLUDE_DIRS   ""                          CACHE STRING "" FORCE)
  set(TINT_INCLUDE_DIRS   "${_bw_dawn}"               CACHE STRING "" FORCE)
  set(SHADERC_INCLUDE_DIR "${LIBDIR}/shaderc/include" CACHE PATH   "" FORCE)

  # The browser GHOST context (GHOST_ContextWGPUWeb.hh) lives in platform_web/ghost.
  # wgpu_context.cc includes it under __EMSCRIPTEN__ (patches/0035-gpu-webgpu-context-web.patch),
  # so put that dir on the include path. Gated on WITH_WEBGPU_BACKEND -> inert in the
  # shared headless build. (notes/gpu-wasm-render-harness.md §seam.)
  include_directories("${_bw_repo}/platform_web/ghost")

  # LINK-time archive set (later step): shaderc bundle first, then tint (which
  # carries the single shared SPIRV-Tools). Read from the harvested ordered lists.
  set(DAWN_LIBRARIES "" CACHE STRING "" FORCE)
  set(_wgpu_libs "")
  if(EXISTS "${LIBDIR}/shaderc/shaderc-archives.txt")
    file(STRINGS "${LIBDIR}/shaderc/shaderc-archives.txt" _bw_sc)
    foreach(_a IN LISTS _bw_sc)
      list(APPEND _wgpu_libs "${LIBDIR}/shaderc/lib/${_a}")
    endforeach()
  endif()
  if(EXISTS "${LIBDIR}/tint/tint-archives.txt")
    file(STRINGS "${LIBDIR}/tint/tint-archives.txt" _bw_tn)
    foreach(_a IN LISTS _bw_tn)
      list(APPEND _wgpu_libs "${LIBDIR}/tint/lib/${_a}")
    endforeach()
  endif()
  set(WGPU_TINT_LIBS "${_wgpu_libs}" CACHE STRING "" FORCE)
  unset(_wgpu_libs)

  if(FIRST_RUN)
    message(STATUS "blender-web: WebGPU backend ON — emdawnwebgpu port + "
                   "Tint(${_bw_dawn}) + shaderc(${LIBDIR}/shaderc/include)")
  endif()
endif()

# -----------------------------------------------------------------------------
# Dependency resolution against the real lib/wasm prefix (M1.8)
#
# This file REPLACES platform_unix.cmake for the Emscripten branch, so none of
# platform_unix's find_package_wrapper() calls run. We reproduce here exactly the
# subset that the M1 headless core needs — the mandatory, non-optional deps that
# dependency_targets.cmake wires into bf::dependencies::* aliases and that
# blenlib PUBLIC-links (OpenImageIO -> OpenColorIO -> OpenEXR/Imath, fmt, TBB,
# Eigen3, zlib/zstd, plus the JPEG/PNG/Freetype/Brotli mandated finds).
#
# The hint-var set below is the proven consumer contract from the dep cross-build
# scripts (see notes/deps-oiio.md): CONFIG packages get an explicit <Pkg>_DIR;
# module-found libs (ZLIB/JPEG/PNG/Zstd/Freetype/Brotli) get <PKG>_LIBRARY +
# include hints so the emscripten-rerooted find_library() is a deterministic
# no-op. OpenColorIO's installed config chases pystring/minizip-ng through its
# OWN bundled Find modules — those need *_INCLUDE_DIR/_LIBRARY (NOT *_ROOT for
# minizip-ng: the ROOT path hits a get_target_property trap).
#
# Optional/gated deps (Python, Cycles/OSL/Embree, USD, OpenVDB, audio, ...) are
# resolved by their own WITH_-guarded blocks in Blender's tree and are forced OFF
# in patches/blender_web.cmake, so they need nothing here.
if(WITH_LIBS_PRECOMPILED)
  # ---- CONFIG-package location hints ----------------------------------------
  set(fmt_DIR            "${LIBDIR}/lib/cmake/fmt")
  set(Imath_DIR          "${LIBDIR}/lib/cmake/Imath")
  set(OpenEXR_DIR        "${LIBDIR}/lib/cmake/OpenEXR")
  set(libdeflate_DIR     "${LIBDIR}/lib/cmake/libdeflate")   # OpenEXR core find_dependency
  set(openjph_DIR        "${LIBDIR}/lib/cmake/openjph")      # OpenEXR core find_dependency
  set(OpenColorIO_DIR    "${LIBDIR}/lib/cmake/OpenColorIO")
  set(OpenImageIO_DIR    "${LIBDIR}/lib/cmake/OpenImageIO")
  set(TBB_DIR            "${LIBDIR}/lib/cmake/TBB")
  set(Eigen3_DIR         "${LIBDIR}/share/eigen3/cmake")
  set(yaml-cpp_DIR       "${LIBDIR}/lib/cmake/yaml-cpp")     # OCIO find_dependency
  set(yaml-cpp_VERSION   "0.8.0")
  set(tsl-robin-map_DIR  "${LIBDIR}/share/cmake/tsl-robin-map")
  set(TIFF_DIR           "${LIBDIR}/lib/cmake/tiff")
  set(PNG_DIR            "${LIBDIR}/lib/cmake/PNG")
  set(libjpeg-turbo_DIR  "${LIBDIR}/lib/cmake/libjpeg-turbo")
  # expat ships its config under lib/cmake/expat-<version>/ (version-suffixed dir).
  file(GLOB _bw_expat_cfg_dir "${LIBDIR}/lib/cmake/expat-*")
  if(_bw_expat_cfg_dir)
    set(expat_DIR "${_bw_expat_cfg_dir}")
  endif()
  unset(_bw_expat_cfg_dir)

  # ---- Module-found libraries: seed the search results so find_* is a no-op --
  set(ZLIB_ROOT          "${LIBDIR}")
  set(ZLIB_INCLUDE_DIR   "${LIBDIR}/include")
  set(ZLIB_LIBRARY       "${LIBDIR}/lib/libz.a")
  set(JPEG_ROOT          "${LIBDIR}")
  set(JPEG_INCLUDE_DIR   "${LIBDIR}/include")
  set(JPEG_LIBRARY       "${LIBDIR}/lib/libjpeg.a")
  set(PNG_ROOT           "${LIBDIR}")
  set(PNG_PNG_INCLUDE_DIR "${LIBDIR}/include")
  set(PNG_LIBRARY        "${LIBDIR}/lib/libpng16.a")
  set(TIFF_INCLUDE_DIR   "${LIBDIR}/include")
  set(TIFF_LIBRARY       "${LIBDIR}/lib/libtiff.a")
  set(ZSTD_ROOT_DIR      "${LIBDIR}")
  set(ZSTD_INCLUDE_DIR   "${LIBDIR}/include")
  set(ZSTD_LIBRARY       "${LIBDIR}/lib/libzstd.a")
  set(BROTLI_ROOT_DIR    "${LIBDIR}")
  set(FREETYPE_LIBRARY              "${LIBDIR}/lib/libfreetype.a")
  set(FREETYPE_INCLUDE_DIR_ft2build "${LIBDIR}/include/freetype2")
  set(FREETYPE_INCLUDE_DIR_freetype2 "${LIBDIR}/include/freetype2")
  # OCIO bundled Find modules for pystring / minizip-ng (module mode, no config).
  set(pystring_ROOT        "${LIBDIR}")
  set(pystring_INCLUDE_DIR "${LIBDIR}/include")
  set(pystring_LIBRARY     "${LIBDIR}/lib/libpystring.a")
  set(minizip-ng_INCLUDE_DIR "${LIBDIR}/include/minizip-ng/minizip")
  set(minizip-ng_LIBRARY     "${LIBDIR}/lib/libminizip.a")

  # ---- Resolve, leaves first so downstream find_dependency() sees the targets -
  find_package(Threads REQUIRED)
  find_package(fmt REQUIRED)                       # -> fmt::fmt
  find_package(Imath REQUIRED)                     # -> Imath::Imath
  find_package(OpenEXR REQUIRED)                   # -> OpenEXR::OpenEXR
  find_package(ZLIB REQUIRED)                      # -> ZLIB_INCLUDE_DIRS/ZLIB_LIBRARIES
  find_package(Zstd REQUIRED)                      # Blender module -> ZSTD_*
  find_package(JPEG REQUIRED)                      # -> JPEG_INCLUDE_DIR/JPEG_LIBRARIES
  find_package(PNG REQUIRED)                       # -> PNG_INCLUDE_DIRS/PNG_LIBRARIES
  find_package(TIFF REQUIRED)                      # OIIO find_dependency
  find_package(TBB REQUIRED)                       # -> TBB::tbb
  find_package(OpenColorIO 2.0.0 REQUIRED)         # -> OpenColorIO::OpenColorIO
  find_package(OpenImageIO REQUIRED)               # -> OpenImageIO::OpenImageIO
  find_package(Eigen3 REQUIRED)                    # -> Eigen3::Eigen
  find_package(Freetype REQUIRED)                  # -> FREETYPE_INCLUDE_DIRS/FREETYPE_LIBRARIES
  find_package(Brotli REQUIRED)                    # -> BROTLI_LIBRARIES
  check_freetype_for_brotli()

  # ---- Derive the raw vars dependency_targets.cmake consumes ----------------
  # It reads ${TBB_LIBRARIES}/${TBB_INCLUDE_DIRS} (not the TBB::tbb target),
  # mirroring platform_unix.cmake's TBB block.
  if(WITH_TBB AND TARGET TBB::tbb)
    get_target_property(TBB_LIBRARIES    TBB::tbb LOCATION)
    get_target_property(TBB_INCLUDE_DIRS TBB::tbb INTERFACE_INCLUDE_DIRECTORIES)
  endif()

  # OpenImageIO was cross-built with OIIO_BUILD_TOOLS=OFF, so its config does NOT
  # export the OpenImageIO::oiiotool target. dependency_targets.cmake:144 reads its
  # LOCATION unconditionally (a build-time datafiles/icon generator that M1 never
  # runs; a wasm oiiotool could not run on the host anyway). Provide the imported
  # executable so the configure-time get_target_property() resolves. M2 supplies a
  # real NATIVE oiiotool here when it wires up the datafiles generation step.
  if(NOT TARGET OpenImageIO::oiiotool)
    add_executable(OpenImageIO::oiiotool IMPORTED GLOBAL)
    set_target_properties(OpenImageIO::oiiotool PROPERTIES
      IMPORTED_LOCATION "${CMAKE_BINARY_DIR}/bw_no_wasm_oiiotool")
  endif()

  if(FIRST_RUN)
    message(STATUS "blender-web: resolved wasm deps from ${LIBDIR} "
                   "(OIIO/OCIO/OpenEXR/Imath/fmt/TBB/Eigen3/JPEG/PNG/TIFF/zlib/zstd/Freetype/Brotli)")
  endif()
else()
  # ---------------------------------------------------------------------------
  # Pre-M2 fallback ONLY (lib/wasm empty): empty INTERFACE placeholders so a bare
  # CMake spine still configures for regression-checking. This branch is DEAD once
  # the superbuild has populated lib/wasm (WITH_LIBS_PRECOMPILED flips ON above).
  # Not parity theater: fenced behind an empty prefix, builds nothing.
  foreach(_bw_iface
      OpenColorIO::OpenColorIO
      OpenImageIO::OpenImageIO
      OpenEXR::OpenEXR
      fmt::fmt
      Eigen3::Eigen
      TBB::tbb)
    if(NOT TARGET ${_bw_iface})
      add_library(${_bw_iface} INTERFACE IMPORTED GLOBAL)
    endif()
  endforeach()
  unset(_bw_iface)
  if(NOT TARGET OpenImageIO::oiiotool)
    add_executable(OpenImageIO::oiiotool IMPORTED GLOBAL)
    set_target_properties(OpenImageIO::oiiotool PROPERTIES
      IMPORTED_LOCATION "${CMAKE_BINARY_DIR}/bw_m1_placeholder/oiiotool")
  endif()
  set(TBB_LIBRARIES    "${CMAKE_BINARY_DIR}/bw_m1_placeholder/libtbb.a" CACHE STRING "" FORCE)
  set(TBB_INCLUDE_DIRS "${CMAKE_BINARY_DIR}/bw_m1_placeholder"          CACHE PATH   "" FORCE)
  if(FIRST_RUN)
    message(STATUS "blender-web: lib/wasm empty — empty placeholder dep targets (pre-M2).")
  endif()
endif()

# -----------------------------------------------------------------------------
# Embedded CPython 3.13 resolution (M2.3) — resolve to the wasm harvest, NOT host
#
# platform_wasm.cmake REPLACES platform_unix.cmake, whose WITH_PYTHON branch does
# `find_package(PythonLibsUnix REQUIRED)` (build_files/.../platform_unix.cmake:234).
# Under the Emscripten toolchain a bare find_library/find_path is re-rooted into the
# emscripten sysroot (CMAKE_FIND_ROOT_PATH_MODE_*=ONLY) and would never see lib/wasm,
# and worse could resolve the *host* python. So instead of running the finder we set
# the PYTHON_* cache vars DIRECTLY to the harvested cross-compiled interpreter
# (scripts/deps/python.sh: libpython3.13.a JS-EH + include/python3.13 + stdlib).
# FindPythonLibsUnix itself is written to be short-circuited exactly this way (it
# skips its find_* when PYTHON_INCLUDE_DIR / PYTHON_LIBRARY are already DEFINED,
# module lines 62-73), so setting the vars is the sanctioned override, not a hack.
#
# The load-bearing consumers (verified at the pin):
#   * dependency_targets.cmake:243-250 builds bf::dependencies::optional::python from
#     ${PYTHON_INCLUDE_DIR} (SYSTEM include), ${PYTHON_LINKFLAGS}, ${PYTHON_LIBRARIES}.
#   * root CMakeLists.txt:2276 asserts ${PYTHON_INCLUDE_DIR}/Python.h exists.
#   * root CMakeLists.txt:1414 version-guards ${PYTHON_VERSION} >= 3.13.
# These four vars (+ the LIBRARY/LIBPATH/DIRS aliases for completeness) are all that
# the headless, non-module, no-install configuration touches. The HOST interpreter
# for build-time codegen scripts (discover_nodes.py) is the separate, native
# PYTHON_EXECUTABLE set above — do NOT conflate the two.
if(WITH_PYTHON)
  if(NOT WITH_LIBS_PRECOMPILED OR NOT DEFINED LIBDIR)
    message(FATAL_ERROR
      "blender-web: WITH_PYTHON=ON but lib/wasm is not populated. Harvest CPython "
      "first: scripts/deps/python.sh (see notes/adr/ADR-001-cpython-emcc-6.0.5.md).")
  endif()
  set(_bw_py_inc "${LIBDIR}/include/python3.13")
  set(_bw_py_lib "${LIBDIR}/lib/libpython3.13.a")
  if(NOT EXISTS "${_bw_py_inc}/Python.h")
    message(FATAL_ERROR "blender-web: missing ${_bw_py_inc}/Python.h (broken python harvest).")
  endif()
  if(NOT EXISTS "${_bw_py_lib}")
    message(FATAL_ERROR "blender-web: missing ${_bw_py_lib} (broken python harvest).")
  endif()
  # NumPy 2.3.4 static archive (13 production PyInit_* registered as builtins in
  # bpy_interface.cc under __EMSCRIPTEN__; scripts/deps/numpy.sh, notes/deps-numpy.md).
  # Linked into the SAME python link (the only target that embeds CPython is `blender`).
  # ORDER IS LOAD-BEARING: libnumpy must precede libpython3.13 on the link line — the
  # numpy modules reference CPython C-API symbols (Py_*) resolved FROM libpython, and
  # nothing in libpython references numpy, so the strict chain is
  # bpy_interface.o -> libnumpy.a (PyInit_*) -> libpython3.13.a (Py_*). This is the exact
  # order the standalone import-gate embed proved (notes/deps-numpy.md "Verification").
  set(_bw_numpy_lib "${LIBDIR}/lib/libnumpy.a")
  if(NOT EXISTS "${_bw_numpy_lib}")
    message(FATAL_ERROR
      "blender-web: WITH_PYTHON=ON but ${_bw_numpy_lib} is missing. Harvest numpy: "
      "scripts/deps/numpy.sh (see notes/deps-numpy.md).")
  endif()
  # Version (major.minor only, as FindPythonLibsUnix reports it).
  set(PYTHON_VERSION "3.13" CACHE STRING "Python Version (major and minor only)" FORCE)
  # Include dirs — Python.h and pyconfig.h are co-located in the harvest, so the
  # config dir equals the include dir.
  set(PYTHON_INCLUDE_DIR         "${_bw_py_inc}" CACHE PATH "" FORCE)
  set(PYTHON_INCLUDE_CONFIG_DIR  "${_bw_py_inc}" CACHE PATH "" FORCE)
  set(PYTHON_INCLUDE_DIRS        "${_bw_py_inc}" CACHE STRING "" FORCE)
  # Static library — mono-wasm links libpython3.13.a directly into the executable.
  # PYTHON_LIBRARY (singular) stays the interpreter archive alone (find-module semantics);
  # PYTHON_LIBRARIES (the link list, consumed by dependency_targets.cmake:243-250) also
  # carries libnumpy, numpy-first per the ordering note above.
  set(PYTHON_LIBRARY             "${_bw_py_lib}" CACHE FILEPATH "" FORCE)
  set(PYTHON_LIBRARIES           "${_bw_numpy_lib};${_bw_py_lib}" CACHE STRING "" FORCE)
  set(PYTHON_LIBPATH             "${LIBDIR}/lib" CACHE PATH "" FORCE)
  # No -export-dynamic: bpy's C modules are compiled INTO the mono-wasm module and
  # registered via PyImport builtins, not dlopen'd, so the Unix embedding link flag
  # is unnecessary (and emscripten does not want it). Keep empty but DEFINED so
  # dependency_targets.cmake:246 target_link_libraries(... ${PYTHON_LINKFLAGS}) is a
  # clean no-op.
  set(PYTHON_LINKFLAGS           "" CACHE STRING "" FORCE)
  set(PYTHONLIBSUNIX_FOUND TRUE)
  if(FIRST_RUN)
    message(STATUS "blender-web: embedded CPython ${PYTHON_VERSION} -> ${_bw_py_lib} "
                   "(include ${_bw_py_inc})")
  endif()
  unset(_bw_py_inc)
  unset(_bw_py_lib)
  unset(_bw_numpy_lib)
endif()

# -----------------------------------------------------------------------------
# Toolchain sanity: mono-wasm, no LTO on dev/iteration builds
#
# GOAL.md: "mono-wasm (no dynamic linking ... kills DCE)"; "Dev links at -O0/-O1,
# never LTO on iteration builds". The -O level is driven by CMAKE_BUILD_TYPE; here
# we only guarantee LTO stays off so incremental links stay fast. Flip these to a
# release profile in a later ADR, not by hand.

set(WITH_COMPILER_LTO OFF CACHE BOOL "" FORCE)

# -----------------------------------------------------------------------------
# Compiler flags (C and C++)
#
# -pthread enables atomics + bulk-memory and shared-memory codegen; it must be
# present at BOTH compile and link. Everything else memory/GPU-related is a
# link-time -s option (below).

# -funsigned-char is MANDATORY, not stylistic: Blender's DNA declares fixed
# underlying-type enums like `enum X : char { ... = 1 << 7 }` (== 128) that only
# compile where `char` is unsigned. Every native platform sets it (platform_unix
# L895, platform_apple L161, platform_win32 via /clang:); Emscripten defaults
# `char` to SIGNED, so without this makesdna.cc et al. fail -Wc++11-narrowing.
# -fno-strict-aliasing and -ffp-contract=off match native for correctness + FP
# determinism (tier-(a) parity depends on the latter). -pthread: atomics + shared
# memory, required at compile and link.
# -fexceptions (emscripten JS-based EH) is MANDATORY, not optional: TBB, OpenImageIO
# and gflags all throw C++ exceptions, and gtest itself throws on assertion in some
# modes. Emscripten DISABLES exception catching by default, so a throw calls abort()
# instead of unwinding -> the gtest runner aborts at startup (verified: ___cxa_throw
# -> Aborted). Must be uniform across every object AND the link (see notes/deps-tbb.md
# "consume TBB under wasm" table). Whole-build commit to -fwasm-exceptions is the
# faster later alternative once every dep is rebuilt with it uniformly.
set(_WASM_COMPILE_FLAGS "-pthread -fexceptions -funsigned-char -fno-strict-aliasing -ffp-contract=off")
string(APPEND CMAKE_C_FLAGS   " ${_WASM_COMPILE_FLAGS}")
string(APPEND CMAKE_CXX_FLAGS " ${_WASM_COMPILE_FLAGS}")
string(APPEND PLATFORM_CFLAGS " ${_WASM_COMPILE_FLAGS}")
unset(_WASM_COMPILE_FLAGS)

# -----------------------------------------------------------------------------
# Linker flags
#
# Per GOAL.md "Emscripten posture". Applied to every linked target through the
# root CMakeLists.txt's setup_platform_linker_flags (PLATFORM_LINKFLAGS ->
# CMAKE_EXE_LINKER_FLAGS).
#
#   -pthread                         threads (must match compile side)
#   -sPROXY_TO_PTHREAD               run main() off the browser main thread
#   -sMALLOC=mimalloc                thread-scalable allocator (TBB malloc proxy OFF)
#   -sWASM_BIGINT                    i64 <-> BigInt at the JS boundary, no legalization
#   -sALLOW_MEMORY_GROWTH            growable heap (Blender scenes are unbounded)
#
# Note: `-pthread` on the link line is what pulls in the shared-memory + worker
# runtime; PTHREAD_POOL_SIZE / INITIAL_MEMORY tuning is deferred to the runtime
# launcher, not baked here.

string(APPEND PLATFORM_LINKFLAGS
  " -pthread"
  " -fexceptions"
  " -sPROXY_TO_PTHREAD"
  " -sMALLOC=mimalloc"
  " -sWASM_BIGINT"
  " -sALLOW_MEMORY_GROWTH"
)

# Fast-path guard for dev/iteration links only: fail loudly if a post-link pass
# would rewrite the wasm (which would silently invalidate the incremental cache).
# Not safe for optimized release links, so gate it on non-Release build types.
if(NOT CMAKE_BUILD_TYPE STREQUAL "Release")
  string(APPEND PLATFORM_LINKFLAGS " -sERROR_ON_WASM_CHANGES_AFTER_LINK")
endif()

# ---- M1 tier-(a) test-runner profile (gtest builds only) -------------------
# The blenlib/bmesh gtest binaries run under node, not a browser, and must:
#   * -sNODERAWFS      map argv paths straight to node's real filesystem, so the
#                      fstream/fileops suites can open the real UTF-8 asset files
#                      under `--test-assets-dir` (verified: fileops.fstream_open_*
#                      go RED->GREEN with NODERAWFS + a real assets dir). Native
#                      CI likewise requires --test-assets-dir; this is faithful,
#                      not a weakening.
#   * -sEXIT_RUNTIME=1 make the process exit with RUN_ALL_TESTS()'s return code
#                      (a PROXY_TO_PTHREAD runner otherwise keeps node's worker
#                      pool alive after main returns -> the harness would hang).
# Gated on WITH_GTESTS so the eventual browser `blender` target never inherits
# NODERAWFS. Host codegen tools (makesdna/makesrna) set their own LINK_FLAGS via
# blender_web_host_tool() and already carry both flags, so this is a harmless
# duplicate for them.
if(WITH_GTESTS)
  string(APPEND PLATFORM_LINKFLAGS " -sNODERAWFS -sEXIT_RUNTIME=1")
endif()

# -----------------------------------------------------------------------------
# Reserved for later milestones (intentionally NOT enabled yet)
#
#   --use-port=emdawnwebgpu   GPU backend (M3/M4). webgpu_cpp.h is unstable; the
#                             port version is pinned when the WebGPU backend lands.
#   -sJSPI                    JS Promise Integration for the event loop (M4+),
#                             replacing Asyncify's ~50% size tax. Chrome 137 floor.
#
# string(APPEND PLATFORM_LINKFLAGS " --use-port=emdawnwebgpu -sJSPI")

# No system link libraries on wasm (everything is static or a -s runtime option).
# PLATFORM_LINKLIBS is left as initialised (empty) by the root CMakeLists.txt.

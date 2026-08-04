<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M2.3 + M2.5 — WITH_PYTHON flip, bf_python, link `blender`, boot bpy headless

Status (2026-08-04): **M2.3 COMPLETE** (configure + bf_python + `blender` link all GREEN).
**M2.5 BLOCKED** at a DNA/readfile layout smell during factory-startup `.blend` load —
handed to driver per the "DNA/RNA layout smells → STOP" rule. The C core boots, prints its
version banner, and runs to the factory-startup scene setup before aborting; Python init is
NOT yet reached (the blocker is pre-Python).

## Per-stage result

| stage | result | evidence |
|---|---|---|
| configure (WITH_PYTHON ON, python→lib/wasm) | **PASS** | buildlog 20260804T033253; cache WITH_PYTHON=ON, PYTHON_LIBRARIES→lib/wasm/lib/libpython3.13.a |
| bf_python (+bmesh/ext/gpu/mathutils) | **PASS** (0 source fixes) | buildlog 20260804T032630 (83 s); 5 archives in build-wasm/lib/ |
| link `bin/blender.js` | **PASS** | buildlog 20260804T064947; blender.wasm 102 MB (82 MB without --profiling-funcs), blender.js 227 KB |
| boot `import bpy` | **FAIL** (DNA read smell, pre-Python) | see blocker below |
| operator smoke | not reached | blocked-by boot |

## Deliverables

- `patches/blender_web.cmake` — `WITH_PYTHON ON`; `WITH_PYTHON_INSTALL/_MODULE OFF` +
  `_INSTALL_NUMPY/_REQUESTS/_ZSTANDARD OFF` (hygiene).
- `patches/platform_wasm.cmake` — `if(WITH_PYTHON)` block sets `PYTHON_*` cache vars DIRECTLY
  to the lib/wasm harvest (no `find_package(PythonLibsUnix)`; avoids emscripten find-root
  re-rooting + host-python leakage); new `blender_web_node_binary()` function (the blender
  node link profile).
- `patches/0010-creator-blender-node-profile.patch` — calls `blender_web_node_binary(blender)`
  AFTER `setup_platform_linker_flags(blender)` in creator/CMakeLists.txt.
- `scripts/deps/python.sh` — libpython rebuild recipe changes (atomics + module disables +
  companion merge; see seam #4).
- New harvested `lib/wasm/lib/libpython3.13.a` (self-contained, 42.9 MB, atomics-enabled).

## Seams fixed (with root cause)

1. **Python discovery (M2.3 wiring).** platform_wasm.cmake REPLACES platform_unix.cmake, whose
   `find_package(PythonLibsUnix)` would re-root into the emscripten sysroot / resolve the HOST
   python. Fix: set `PYTHON_VERSION/PYTHON_INCLUDE_DIR/PYTHON_LIBRARIES/PYTHON_LINKFLAGS` (+
   aliases) directly to lib/wasm. The load-bearing consumers are `dependency_targets.cmake:243-250`
   (`bf::dependencies::optional::python` reads `PYTHON_INCLUDE_DIR`/`PYTHON_LINKFLAGS`/
   `PYTHON_LIBRARIES`) and root `CMakeLists.txt:2276` (`${PYTHON_INCLUDE_DIR}/Python.h`). Host
   PYTHON_EXECUTABLE (native emsdk python, for build-time codegen scripts) is unchanged/separate.
   `PYTHON_LINKFLAGS=""` (no `-Xlinker -export-dynamic`; bpy C modules are static builtins, not
   dlopen'd).

2. **mimalloc duplicate-symbol clash (link).** CPython 3.13 VENDORS mimalloc
   (`libpython3.13.a(obmalloc.o)` defines the full public `mi_*` API, 276 globals). Linking
   emscripten's `-sMALLOC=mimalloc` (libmimalloc-mt.a) alongside is a hard duplicate-symbol
   error. Fix: the `blender` binary uses `-sMALLOC=dlmalloc` (thread-safe under -pthread; the
   allocator the M2.0b libpython embed probe ran clean on). CPython keeps its OWN internal
   mimalloc for PyObject allocation. Isolated to the blender target (gtests/host-tools keep
   mimalloc — no libpython there). This required placing `blender_web_node_binary()` AFTER
   `setup_platform_linker_flags(blender)` (creator:1961), which APPENDS the global
   PLATFORM_LINKFLAGS (mimalloc) — my function OVERWRITES LINK_FLAGS so dlmalloc wins.

3. **libpython not shared-memory-link-compatible (link).** The M2.2 harvest was compiled
   single-threaded (`-fexceptions` only), so its objects lack the atomics/bulk-memory wasm
   features; wasm-ld refuses them in Blender's `--shared-memory` (-pthread) link
   ("--shared-memory is disallowed by abstract.o …"). Fix (scripts/deps/python.sh): add
   `-matomics -mbulk-memory` to CFLAGS/CPPFLAGS. This gives the features WITHOUT emscripten's
   full `-pthread` runtime (no `__EMSCRIPTEN_PTHREADS__`), so CPython stays single-threaded
   (ADR-001 posture) yet every object links into the threaded host.

4. **Missing companion static libs (link).** libpython referenced `mpd_*` (libmpdec/_decimal,
   114 syms), `python_hashlib_Hacl_*` (31, hashlib SHA), `sqlite3_*` (85), `BZ2_*` (6) — the
   standalone python.js resolved sqlite/bz2 via emscripten PORTS and linked separate
   libmpdec/libHacl archives; the mono-wasm link has none of these. Fix (python.sh): disable the
   optional C-extensions whose only unmet deps are external/companion libs and which are NOT
   needed for `import bpy` (each has a fallback): `py_cv_module__sqlite3/_bz2/_decimal/_md5/
   _sha1/_sha2/_sha3/_blake2/pyexpat/_elementtree=n/a`. Result: a SELF-CONTAINED libpython whose
   only external symbols are zlib's (14 refs), resolved by lib/wasm's libz.a already on the
   Blender link. Verified: 0 companion-lib undefined refs post-rebuild. (`decimal` → pure-python
   `_pydecimal`; `hashlib` degrades gracefully — re-add with proper deps at M2.6 if a suite
   needs them.) The python.sh harvest also now merges any remaining in-tree companion `*.a`
   into libpython (belt-and-suspenders; currently a no-op after the disables).

5. **initial memory too small (link).** Static data (RNA/DNA tables, stdlib) exceeds
   emscripten's 16 MiB default → `-sINITIAL_MEMORY=536870912` (512 MiB) in the node profile;
   growth handles scenes.

## `blender` link profile decision (explicit, per task)

`blender_web_node_binary()` OVERWRITES the blender target LINK_FLAGS with:
```
-pthread -fexceptions -sMALLOC=dlmalloc -sWASM_BIGINT -sALLOW_MEMORY_GROWTH
-sINITIAL_MEMORY=536870912 -sPROXY_TO_PTHREAD -sNODERAWFS -sEXIT_RUNTIME=1
-sSTACK_SIZE=8388608 --profiling-funcs   (+ -sERROR_ON_WASM_CHANGES_AFTER_LINK on non-Release)
```
- **PROXY_TO_PTHREAD kept ON** (NOT =0). Rationale: this is the exact profile the tier-(a)
  gtest binaries (bmesh_core_test, ~200 archives incl. TBB) linked and RAN under node with
  (M1.11), so it is proven to run a multithreaded TBB binary headless; it also avoids the
  on-demand-pthread-creation deadlock that PROXY_TO_PTHREAD=0 risks for TBB. ADR-001's "Python
  runs synchronously on the (proxied) main thread" explicitly assumes this proxied posture. M2
  uses NO `-sJSPI`, so there is no suspension / setjmp×JSPI hazard (ADR-003). EXIT_RUNTIME=1
  still makes the proxied process exit with main()'s code. This is a DELIBERATE, documented
  deviation from the task's suggested "=0 for now" (the host-tool profile uses =0 because those
  are single-threaded CLIs; blender is not — it mirrors the gtest profile, not the host-tool one).
- **--profiling-funcs**: kept as a bring-up aid (named node stack traces; +~20 MB name section).
  Drop it for the shipping profile.

## Boot recipe (exact)

emsdk node: `tools/emsdk/node/22.16.0_64bit/bin/node`. Command:
```
BLENDER_SYSTEM_PYTHON=/Users/paws/blender-web/lib/wasm \
BLENDER_SYSTEM_SCRIPTS=/Users/paws/blender-web/upstream/scripts \
BLENDER_SYSTEM_DATAFILES=/Users/paws/blender-web/upstream/release/datafiles \
tools/emsdk/node/22.16.0_64bit/bin/node build-wasm/bin/blender.js \
  --background --factory-startup \
  --python-expr "import bpy; print('BPY_OK', bpy.app.version_string, len(bpy.data.objects))"
```
Env rationale (verified against code):
- `BLENDER_SYSTEM_PYTHON=lib/wasm` → `BKE_appdir_folder_id(BLENDER_SYSTEM_PYTHON)`
  (bpy_interface.cc:544) → `config.home` (bpy_interface.cc:559) → CPython finds the stdlib at
  `<home>/lib/python3.13` (= lib/wasm/lib/python3.13, our harvest).
- `BLENDER_SYSTEM_SCRIPTS=upstream/scripts` → appdir case (appdir.cc:712) for bpy's
  startup/modules (bl_ui/bl_operators). `BLENDER_SYSTEM_DATAFILES=upstream/release/datafiles`
  (appdir.cc:682). NODERAWFS makes these absolute host paths resolve directly.
- (Boot did not reach Python, so the python-side of this recipe is not yet runtime-verified;
  it is code-derived and expected-correct.)

## THE BLOCKER (M2.5) — DNA/readfile layout smell, handed to driver

**Signature:** deterministic abort during factory-startup `.blend` read, BEFORE Python init:
```
Blender 5.2.0 LTS
BLI_assert failed: source/blender/blenkernel/intern/layer_utils.cc:205,
  BKE_view_layer_object_bases_get(), at '(view_layer->flag & VIEW_LAYER_OUT_OF_SYNC) == 0'
```
Stack: `main → wm_homefile_read_ex → BKE_blendfile_read_setup_readfile →
BKE_scene_set_background → BKE_view_layer_object_bases_get`.

**Root cause (instrumented, not guessed):**
- `BKE_scene_set_background` (scene.cc:2199) calls `BKE_view_layer_synced_ensure` and then
  asserts the layer is synced. The sync (`BKE_layer_collection_sync`, layer.cc:1370) returns
  false at its `if (!scene->master_collection) return false;` guard (layer.cc:1376) → the
  OUT_OF_SYNC flag is never cleared → the very next line asserts.
- Instrumented state at that call: `no_resync=0` (resync NOT forbidden — the read-path
  forbid/allow are perfectly balanced, 79/79), `master_collection=NULL`, `oos=8`
  (VIEW_LAYER_OUT_OF_SYNC set), the view_layer's `layer_collections` NON-empty and iterable.
- **`Scene.master_collection` (DNA `struct Collection *`, DNA_scene_types.h:2905) reads NULL
  raw, BEFORE any pointer resolution** — confirmed because the "invalid root collection" report
  at readfile.cc:2078 is NOT emitted (that path fires only when the RESOLVED pointer is bad);
  the `if (scene->master_collection != nullptr)` at readfile.cc:2073 was FALSE, i.e. the field
  read null straight out of struct reconstruction. So this is NOT a `newdataadr`/oldnewmap
  resolution failure — it is the struct field itself reading null.

**Why this is a DNA smell (STOP → driver):** `master_collection` sits immediately AFTER
`ListBaseT<ViewLayer> view_layers` (a C++ template-wrapped ListBase) in the Scene struct
(DNA_scene_types.h:2903-2905). `view_layers` and its ViewLayer contents read FINE, but
`master_collection` (next field) reads null — the classic signature of a RUNTIME-SDNA offset
for `master_collection` that disagrees with its actual compiled `offsetof` (DNA_struct_reconstruct
writes the field's value to the makesdna offset; if that ≠ the real C++ offset, `scene->
master_collection` reads its zero-init). This is the FIRST real `.blend` read on wasm32 (the
tier-(a) gtests never reconstruct a full Scene), so it is the first place a Scene-struct
makesdna offset error (patch-0002 alignment territory) or a 64-bit-file→wasm32 pointer-field
reconstruction bug can surface. `startup.blend` uses the modern (v2) header with 64-bit
pointers; wasm32 is 32-bit → the cross-pointer-size reconstruction path is exercised here.

**Prime suspect + the definitive test for the driver:** compare makesdna's computed SDNA offset
of `Scene.master_collection` against the actual compiled `offsetof(Scene, master_collection)`
under the wasm32 toolchain (and the same for `view_layers`). A mismatch confirms a makesdna
layout bug for fields following the `ListBaseT<...>` template under the patch-0002 wasm32
alignment model. Candidate directions: (a) fix makesdna's sizing/alignment of `ListBaseT<>`
templates on wasm32; (b) audit DNA_struct_reconstruct's 64→32 pointer-field handling; (c) the
wasm64 escape hatch (GOAL: "wasm32 first; wasm64 later behind a flag") if 32-bit .blend read
proves too costly. NOTE: because it is field-offset-localized (view_layers OK, master_collection
null), other post-template pointer fields across many DNA structs may be SILENTLY misread even
where they don't abort — a broad correctness risk, not just this one field. Driver call.

## Reproduce / diagnostics

Boot logs: scratchpad `boot_final.log` (clean repro). Diagnostic patches (temporary, reverted;
upstream is back to the clean 0001-0010 + 0120 series) confirmed each step: `no_resync=1` during
forbidden windows (benign), forbid/allow balanced 79/79, `master_coll=0` at scene_set_background.

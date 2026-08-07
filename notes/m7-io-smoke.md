<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: GPL-2.0-or-later
-->

# M7-io — launch-tier IO export smoke test (glTF + OBJ) on wasm

## Verdicts (outcome first)

- **OBJ export (native C++ `wm.obj_export`): BLOCKED — operator not in this
  binary.** The whole native IO export suite is compiled OUT. Called at runtime
  it raises `AttributeError: ... "bpy.ops.wm.obj_export" ... could not be found`;
  `get_rna_type()` → `KeyError`. Cause: `patches/blender_web.cmake:176-180`
  force-disables `WITH_IO_WAVEFRONT_OBJ / WITH_IO_PLY / WITH_IO_STL / WITH_IO_FBX
  / WITH_IO_GREASE_PENCIL`, and `WITH_USD=OFF` (build cache). Empirically all of
  `wm.obj_export, wm.usd_export, wm.ply_export, wm.stl_export` are **ABSENT**.
  The launch-tier "OBJ/USD IO" C++ exporters are simply not in the M6 binary.
- **glTF export (Python addon `io_scene_gltf2`, `export_scene.gltf`): BLOCKED —
  numpy aborts.** The operator EXISTS, the addon auto-enables under
  `--factory-startup`, `execute()` runs and reaches the real mesh gather, then
  the process **aborts** inside numpy on the first array allocation:
  `Aborted(Assertion failed: PyGILState_Check(), at:
  numpy-2.3.4/numpy/_core/src/multiarray/alloc.c,130,_npy_alloc_cache)`.
  Isolated to the payload: a bare `np.zeros(5)` aborts identically — this is
  **not** glTF-specific.
- **OBJ import round-trip (bonus): N/A** — `wm.obj_import` is absent (same build
  config), so there is nothing to round-trip on this binary.

Neither blocker is in this worker's file ownership: OBJ is a build-config flag
(build trees read-only, no rebuild), glTF's blocker is the numpy build in
`lib/wasm` (Python payload, another session). Both are precisely characterized
below, and the comparison harness + native oracle references are turnkey so the
verdicts flip to a parity check the moment either upstream is fixed.

## glTF failure — the full peel (3 layers, first two worked around)

The default GLB export path was driven far enough to expose the real blocker.
All workarounds are runtime shims injected from the sandbox script — **zero
upstream edits, zero rebuild** — and none touch the actual export logic or fake
a result (the produced `.glb` is validated against the native oracle):

1. **`_ctypes` C-extension absent from the wasm CPython payload.** The addon
   unconditionally imports its draco module at `execute()`
   (`__init__.py:1120 execute` → `blender/exp/export.py:14
   from ...io.exp import draco` → `io/exp/draco.py:5 from ctypes import *` →
   `ctypes/__init__.py:10 from _ctypes import ...` → `ModuleNotFoundError:
   _ctypes`). draco/meshopt use ctypes only *inside* functions the default
   uncompressed export never calls, so a stub `ctypes`/`_ctypes` in `sys.modules`
   (installed only when the real import fails) satisfies the import and lets the
   real code run. *Proper fix:* build `_ctypes` (libffi) into the payload, or make
   the addon's draco import lazy (upstream).
2. **Upstream platform bug on `sys.platform=='emscripten'`.** `io/com/library.py`
   `dll_path()` maps only win32/linux/darwin → returns `None` for emscripten →
   `dll_exists()` dereferences `None.absolute()` (`library.py:48`), which
   `is_draco_available()`/`is_meshopt_available()` call on *every* export. The
   correct wasm answer is "unavailable" (no bridge `.so`, no libffi), asserted
   directly on the cached flags. *Proper fix:* one-line upstream guard for a
   `None` path (or an `emscripten` map entry returning `None`).
3. **HARD BLOCKER — numpy aborts on all array allocation** (see verdict). Root
   cause: the `lib/wasm` numpy 2.3.4 was built **with assertions enabled**
   (not `-DNDEBUG`), and its `assert(PyGILState_Check())` in `alloc.c` fires
   under Emscripten's pthread GIL/TLS model. This is very likely a *false*
   assertion (the GIL is effectively held; `PyGILState_Check()` is unreliable
   under `-sPROXY_TO_PTHREAD`). *Recommended fix for the python-wasm session:*
   rebuild numpy **release (`-DNDEBUG`)** to compile the assert out; if it still
   misbehaves at runtime, it is a genuine GIL/TLS integration bug to fix in the
   Python-boot layer. The glTF addon is numpy-heavy (mesh extraction via
   `foreach_get` + `np.unique`), so it cannot run until numpy allocates.

## Native oracle references (parity is turnkey once unblocked)

`export_scene.py` runs **identically** on the wasm binary and the native pin
oracle (`oracle/bpy.sh`). On the oracle it produced the references cleanly
(`CTYPES_SHIM False`, no platform workaround, `OBJ_EXPORT_OK`, `GLTF_EXPORT_OK`)
— proving the script and comparators are correct. The default-cube contract the
wasm side must match:

- **`out/native/cube.glb`** (1936 B): magic `glTF` v2; chunks JSON=1068 / BIN=840;
  1 scene / 1 node / 1 mesh / 1 primitive; **4 accessors** — POSITION VEC3×24,
  NORMAL VEC3×24, TEXCOORD_0 VEC2×24, indices SCALAR/USHORT×36 (12 tris); 1
  material; total buffer 840 B. generator `Khronos glTF Blender I/O v5.2.39`.
- **`out/native/cube.obj`** (943 B) + `cube.mtl`: v=8, vt=14, vn=6, f=6 (all
  quads), 1 object, 1 material. Source mesh (both sides): verts=8 edges=12
  polys=6 loops=24.

Comparators (stdlib only, no new deps): `parse_glb.py a.glb b.glb` compares a
generator-independent structural digest (meshes/primitives/accessor
type+comp+count/attrs/buffer bytes) — exit 0 = PASS; `parse_obj.py a.obj b.obj`
compares v/vt/vn/f + face degrees. Chosen mode is **semantic** (not byte): the
GLB `generator` string embeds the version and buffer byte-layout ordering is not
contractual; OBJ float formatting may differ. When the wasm side produces files,
`parse_glb.py out/native/cube.glb out/wasm/cube.glb` is the one-shot verdict.

## Reproduce

```
# wasm (both exports; OBJ fails absent, glTF aborts in numpy):
BLENDER_SYSTEM_RESOURCES=$PWD/upstream BLENDER_SYSTEM_PYTHON=$PWD/lib/wasm \
BLENDER_SYSTEM_DATAFILES=$PWD/upstream/release/datafiles \
M7_OBJ=$PWD/sandbox/m7-io-smoke/out/wasm/cube.obj \
M7_GLB=$PWD/sandbox/m7-io-smoke/out/wasm/cube.glb \
tools/emsdk/node/22.16.0_64bit/bin/node build-wasm-cycles/bin/blender.js \
  --background --factory-startup --python sandbox/m7-io-smoke/export_scene.py

# native oracle references (both succeed):
BLENDER_BIN="$PWD/oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender" \
M7_OBJ=$PWD/sandbox/m7-io-smoke/out/native/cube.obj \
M7_GLB=$PWD/sandbox/m7-io-smoke/out/native/cube.glb \
oracle/bpy.sh --python sandbox/m7-io-smoke/export_scene.py
```

## Evidence

- `sandbox/m7-io-smoke/export_scene.py` — shared exporter (OBJ + GLB) + the two
  runtime shims (guarded, wasm-only).
- `sandbox/m7-io-smoke/probe_ops.py` — operator/addon availability probe.
- `sandbox/m7-io-smoke/parse_glb.py`, `parse_obj.py` — stdlib validators/comparators.
- `sandbox/m7-io-smoke/out/native/cube.{glb,obj,mtl}` — oracle references.
- `sandbox/m7-io-smoke/out/{wasm,native}_run.log` — captured runs (the numpy
  abort stack; the clean native run).

## What flips these to PASS

1. **OBJ:** set `WITH_IO_WAVEFRONT_OBJ=ON` (and `WITH_USD=ON` for USD) in the web
   config and relink; then `parse_obj.py` self-compare vs the oracle (byte-compare
   plausible first, semantic fallback). Round-trip via `wm.obj_import` becomes
   possible too.
2. **glTF:** rebuild `lib/wasm` numpy release (`-DNDEBUG`); the two runtime shims
   here already carry the export past the payload's `_ctypes` gap and the
   upstream emscripten `dll_path` bug, so the export should then complete and
   `parse_glb.py out/native/cube.glb out/wasm/cube.glb` is the verdict.

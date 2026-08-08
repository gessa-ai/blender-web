<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# python-trim-restore: the "dis.py trim gap" is a MISDIAGNOSIS, not a defect

**Date:** 2026-08-08 · **Lane:** python-trim · **Ports:** 8130 (boot verify), 8127 (scratch).
Charter: fix a CPython stdlib trim that (per `notes/m8-staged-deploy.md` sec "Benign boot
debts", lines 171-180 + residual 5, and `ledger/progress.txt` lines 393-394) supposedly
dropped `dis.py` from the shipped payload, breaking `inspect -> dis` and logging caught
tracebacks during `pose_library` / `bl_pkg` boot registration.

## Headline (truth pass)

**There is no `dis.py` trim, and there is no `dis`-related boot failure.** The charter's
premise is false. Every artifact and every live boot contradicts it:

- `dis.py` is present in the shipped `.data` (40962 bytes, byte-for-byte the on-disk
  harvest), and its only C-extension dep `_opcode` is a builtin in the linked libpython.
- On the ACTUAL browser build, `import dis`, `import inspect`, `inspect.getsource(...)`,
  `dis.dis(...)`, `import pydoc`, `pydoc.render_doc(len)` and all hash algorithms SUCCEED,
  with ZERO import/traceback lines in the boot console.
- The two addons the note named as failing (`bl_pkg`, `pose_library`) are BOTH in the
  live enabled-addons list; the exact `dataclasses -> inspect -> dis -> opcode -> _opcode`
  chain imports cleanly.

**No payload change was made. No relink was performed. The windowed-opt `.data` is
untouched (85,203,093 bytes, unchanged). Size delta = 0.** Fabricating a "restore" of a
module that is already present would be parity theater (GOAL.md forbids it), so the
deliverable is this refutation with evidence, not a code change.

## Deliverable 1: the trim mechanism (precisely: NONE excludes dis.py)

All three candidate mechanisms were audited; none excludes `dis.py`:

| candidate | verdict |
|---|---|
| `platform_wasm.cmake` payload assembly (L319-334) | Wholesale `--preload-file ${_py_home}@/bw/python/lib/python3.13`. No exclude globs, no per-file list. Packs the entire harvested stdlib, `dis.py` included. NOT a trim. |
| PYCACHE PRUNE block (`platform_wasm.cmake` L383-401 -> `scripts/deps/prune-preload-pycache.sh`) | Deletes only `-type d -name '__pycache__'` (the `.pyc` at plain/opt-1/opt-2). Never touches a `.py` file. No scope creep. NOT a trim of `dis.py`. |
| `scripts/deps/python.sh` harvest | L32-33: "We harvest the FULL unzipped stdlib for correctness/parity now." `make libinstall` -> full `Lib/`; `dis.py` lands at `lib/wasm/lib/python3.13/dis.py`. NOT a trim. |

`rg` over the repo (excluding `upstream/`, `build-*/`, `sandbox/`, `lib/`) for any stdlib
trim / exclude list / `dis.py` removal found NOTHING except the note's own claim and
aspirational future-work ("trim `bl_ui`", `notes/m8-size-probe.md`). **No mechanism
excludes `dis.py`. It has never been trimmed.**

### What the note actually saw (root cause of the misdiagnosis)

The git history explains the real prior gap. Commit `c1f6477` (2026-08-06,
"M4.python-debt: enable _sha3(+md5/sha1/blake2) hash exts; thread-backed _multiprocessing
shim") is the fix. BEFORE it, the harvested libpython did not build the Hacl hash
C-extensions, so boot logged real caught tracebacks:

```
ERROR:root:code for hash md5 was not found.  ValueError: unsupported hash type md5
ERROR:root:code for hash sha1 / blake2b / blake2s / sha3_* was not found.
```

(reproduced verbatim on the stale pre-`c1f6477` binary `build-wasm/bin/blender.js`, Aug 4,
which predates the Aug 6 libpython re-harvest). The note author observed caught
registration tracebacks and attributed them to `inspect -> dis`, but the failing import
was the hash modules (and, separately, the documented urllib3/Pyodide `js` debt, ledger
L322/L327), never `dis`. `dis.py` was a red herring; the hash gap was already closed by
`c1f6477` two days before the note was written.

## Deliverable 2: full missing-module sweep (the whole class, not just dis)

Boot battery on the current target (node proxy `build-wasm-cycles/bin/blender.js`, linked
against the current libpython, cross-checked on the actual browser build). Every import
the charter names is present and working; the only absences are deliberately-cut
C-extensions, each documented in `scripts/deps/python.sh` and none imported on the
`--factory-startup` boot path.

### Present and working (no action needed)

| module | probe result |
|---|---|
| `dis`, `opcode`, `_opcode` | IMPORT_OK; `dis.dis()` -> 204 chars |
| `inspect` | IMPORT_OK; `inspect.getsource(inspect.getsource)` -> 363 chars |
| `pydoc` | IMPORT_OK; `pydoc.render_doc(len)` -> 131 chars (the `help(len)` path) |
| `dataclasses`, `typing`, `enum`, `importlib` | IMPORT_OK |
| `hashlib` + `md5`/`sha1`/`sha256`/`sha3_256`/`blake2b`/`blake2s` | all HASH_OK (builtin Hacl exts) |
| `decimal` | IMPORT_OK (pure-python `_pydecimal` fallback; `_decimal` C-ext intentionally off) |
| `xml`, `unittest`, `asyncio` | IMPORT_OK |

### Absent, by deliberate documented decision (NOT a boot gap, NOT to be restored)

| import | missing C-ext | rationale (python.sh / config.site) | boot-imported? | restore cost if forced |
|---|---|---|---|---|
| `sqlite3` | `_sqlite3` | `py_cv_module__sqlite3=n/a` (needs emscripten sqlite3 PORT) | no | + sqlite3 native lib |
| `decimal` fast path | `_decimal` | `py_cv_module__decimal=n/a` (pure-py fallback works) | no (fallback used) | + libmpdec |
| `xml.parsers.expat` | `pyexpat`,`_elementtree` | `py_cv_module_pyexpat=n/a`,`_elementtree=n/a` (would dup lib/wasm libexpat) | no | + expat dup |
| `bz2` | `_bz2` | `py_cv_module__bz2=n/a` (emscripten bzip2 PORT) | no | + bzip2 |
| `ssl` | `_ssl` | not built (needs OpenSSL cross-build) | no | + OpenSSL (MB-scale) |
| `ctypes` | `_ctypes` | not built (needs libffi; no dlopen in mono-wasm) | no | + libffi |
| `lzma` | `_lzma` | not built (needs xz) | no | + xz |
| `curses` | `_curses` | not built (needs ncurses; no TTY in a tab) | no | + ncurses |
| `readline` | `readline` | not built (no interactive TTY) | no | + readline |
| `uuid` (C accel) | `_uuid` | not built (pure-py `uuid` path works) | no | negligible, but unused |

**Honest cut line:** none of the absent modules is imported on the boot path (the boot
enabled 7 addons with zero tracebacks), and every one that could conceivably be wanted
later drags in a megabyte-scale external native library. Restoring any of them now would
add wire weight for a module nothing imports. The existing `python.sh` cut line is
correct; hold it. (Re-enable individually behind a future milestone's real need, per
python.sh L148-150.)

## Deliverable 3-4: restore + rebuild (NOT performed, correctly)

Nothing was restored and no relink was run, because the module the charter targets is
already present. `patches/platform_wasm.cmake` was NOT edited (the trim it hypothesised
does not exist there or anywhere). The shared `build-wasm-windowed-opt/bin` tree was read
read-only and left byte-identical (`.data` 85,203,093 bytes, unchanged) so concurrent
lanes reading it were never perturbed. **Size delta: 0 raw / 0 brotli.**

## Deliverable 5: proof (live browser boot of the actual build)

Served the monolith windowed-opt browser build (`sandbox/m8-staged-deploy/bundle-mono`,
the exact frozen artifact the note A/B-tested and wrongly called dis-less; `dis.py`
verified at 40962 bytes in its baked `loadPackage` manifest) COOP/COEP-isolated on port
8130, booted headed bundled Chromium, ran the battery inside the WM-worker.

```
crossOriginIsolated=true SAB=true ; WM_main reached in 246 ms
IMPORT_OK dis / inspect / pydoc / dataclasses / opcode / _opcode
GETSOURCE_OK len=363 ; DIS_OK chars=204 ; PYDOC_OK len=131 ; HASH_OK
console lines total=7 ; import/traceback-suspect lines=0
```

Registration-chain probe (second boot):

```
CHAIN_OK dataclasses / inspect / dis / opcode / _opcode
ADDON_IMPORT_OK bl_pkg / pose_library / _bpy_internal
NET_OK requests / urllib3
ENABLED_ADDONS ['bl_pkg','io_anim_bvh','io_curve_svg','io_mesh_uv_layout',
                'io_scene_fbx','io_scene_gltf2','pose_library']
boot-console suspect lines: 0
```

The two addons the note said fail to register (`bl_pkg`, `pose_library`) are live-enabled.
The boot console captures Blender's own `printErr` (the known OIIO `physical_memory`
assertion and the multiprocessing "no Python binary" line both appear), so any
`inspect -> dis` traceback WOULD surface here; none does.

Screenshot evidence (full UI + genuine 5.2.0 LTS splash + Quick Setup, crisp Latin fonts):
`sandbox/m8-python-trim/artifacts/battery_boot_mono_1280x720.png` (+ `.license`, CC0-1.0).

## Deliverable 6: size before/after

No payload change. `blender_browser.data` before = after = 85,203,093 bytes (raw), brotli
35.28 MB (unchanged). The `dis.py`+`opcode.py` bytes it would supposedly "restore" are
already inside that figure (dis.py 40962 + opcode.py 2825 = 43787 bytes, present).

## Residual flagged (separate, NOT a stdlib trim, already documented)

`ledger/progress.txt` L322/L327 records a genuine open item: `urllib3.contrib.emscripten.
fetch` unconditionally runs `inject_into_urllib3()` when `sys.platform=='emscripten'` and
imports Pyodide's `js` module, which a non-Pyodide CPython lacks -> a `ModuleNotFoundError:
No module named 'js'` was seen during `bl_pkg` register on an earlier build. On the current
build `import requests`/`urllib3` both return NET_OK and `bl_pkg` is enabled, so it did not
surface here; regardless it is a networking-transport decision, not a stdlib trim, and is
out of this lane's scope. Left with its existing owner.

## Reproduce

```
# node proxy sweep (fast; reads lib/wasm directly via NODERAWFS):
NODE=tools/emsdk/node/22.16.0_64bit/bin/node
export BLENDER_SYSTEM_RESOURCES="$PWD/upstream" \
       BLENDER_SYSTEM_PYTHON="$PWD/lib/wasm" \
       BLENDER_SYSTEM_DATAFILES="$PWD/upstream/release/datafiles"
"$NODE" build-wasm-cycles/bin/blender.js --background --factory-startup \
  --python-expr "import dis,inspect,pydoc; print('OK', inspect.getsource(len.__class__.__len__.__doc__ and inspect.getsource or inspect.getsource))" 2>&1 | tail

# actual browser build (COOP/COEP, bundled Chromium, port 8130):
python3 sandbox/m8-deploy/serve_bundle.py 8130 sandbox/m8-staged-deploy/bundle-mono &
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/m8-python-trim/boot_battery.mjs 8130 mono
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/m8-python-trim/boot_regchain.mjs 8130

# confirm dis.py IS in the shipped .data manifest (any windowed-opt glue):
python3 - <<'PY'
import re
s=open('build-wasm-windowed-opt/bin/blender_browser.js').read()
m=re.search(r'filename:"/bw/python/lib/python3\.13/dis\.py",start:([0-9.e+]+),end:([0-9.e+]+)',s)
st,en=(int(float(m.group(1))),int(float(m.group(2))))
print('dis.py in .data:', en-st, 'bytes')
PY
```

## Files (this lane; SPDX-tagged; `sandbox/m8-python-trim/`)

| file | role |
|---|---|
| `boot_battery.mjs` | boot the browser build; import battery (dis/inspect/getsource/pydoc/hash); screenshot |
| `boot_regchain.mjs` | characterize the `dataclasses->inspect->dis` chain + named addons + net chain |
| `artifacts/battery_boot_mono_1280x720.png` (+ `.license`) | full-UI boot evidence |
| `artifacts/console_*.log` | captured boot consoles (0 dis/import tracebacks) |

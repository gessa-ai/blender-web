<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M7.pre — files / pipeline design recon

GOAL.md M7: WasmFS/OPFS project store; open/save real files (Chromium FSA +
fallback everywhere); `.blend` drag-drop; OBJ/USD round-trips; glTF addon via the
Python runtime; staged loading + service-worker caching per LAUNCH.md. **This is
the launch killshot** — LAUNCH.md:27 makes *"drag-drop the viewer's own `.blend`
and orbit their scene"* the 30-second wow ("it opened my file"). READ-ONLY design
recon; probes in `sandbox/m7-prep/`. Toolchain: **emsdk 6.0.5**; pin fbe6228777e7.

## 1. Current state — where do reads and writes go TODAY

Two link profiles of the **same** compiled Blender object code
(`patches/platform_wasm.cmake:172`):

| | node `blender` (test) | browser `blender_browser` (M4.pre shell) |
|---|---|---|
| FS flag | `-sNODERAWFS` | `-sWASMFS -sFORCE_FILESYSTEM=1` (:289) |
| reads | host FS, absolute paths | WasmFS mounts `/bw/{python,scripts,datafiles}` from `--preload-file` (:306-308), read-only baked-in payload |
| writes | **host FS** (real files) | **WasmFS in SHARED linear memory** — RAM-only, **lost on reload** |
| exported to JS | — | `ENV, FS, callMain` (:290) — the byte-bridge hooks |

**Write path verified on the wasm binary** (`sandbox/m7-prep/probe_fs_roundtrip.sh`,
node/NODERAWFS):
- `bpy.ops.wm.save_mainfile` → real `BLO_write_file`: writes a **96 KB zstd
  `.blend`** (magic `28 b5 2f fd`), `SAVE_OK True`.
- add-cube → save → reopen → `ROUNDTRIP start=3 saved+reopened=4`: **both
  `wm.save_mainfile` and `wm.open_mainfile` work end-to-end on the wasm binary**
  through the real `BLO_write_file`/`BLO_read_file` paths.

**⇒ The Blender-side open/save operators are DONE.** M7 is not about readfile/
writefile — it is entirely about (a) giving WasmFS a **persistent** backend
(OPFS) and (b) a **JS byte-bridge** to move file bytes between the browser
(picker / download / drag-drop) and WasmFS. On the browser build today a save
succeeds but evaporates on reload; that single gap is the whole milestone.

(Aside: `save_mainfile` emits benign `unsupported hash type md5/sha1` tracebacks
— the m2-python-boot seam-#4 hashlib trim — then completes. Re-enabling those Hacl
backends is an independent hygiene item, not an M7 blocker.)

## 2. OPFS project store — design

### 2a. The API exists in our pinned toolchain (cited)
`tools/emsdk/upstream/emscripten/system/include/emscripten/wasmfs.h`:
- `wasmfs_create_opfs_backend(void)` (:91) — OPFS-backed WasmFS backend.
- `wasmfs_create_directory(path, mode, backend)` (:35) — **mount** a backend at a
  path (`wasmfs_unmount` :39). JS side: `libwasmfs_opfs.js`, `libopfs.js`.
- Bonus: `wasmfs_create_fetch_backend(base_url, chunk_size)` (:78) — a lazy
  HTTP-range backend, the natural tool for M7 **staged loading** (replace the
  wholesale `--preload-file` runtime payload with a fetch-mounted tree; the
  browser profile comment already flags this, platform_wasm.cmake:296).

### 2b. Layout & mount strategy
Mount OPFS once at Blender startup, on the `PROXY_TO_PTHREAD` worker that runs
`main()`:
```
backend_t opfs = wasmfs_create_opfs_backend();
wasmfs_create_directory("/projects", 0777, opfs);   // user project store (persistent)
// keep /bw/{python,scripts,datafiles} on the (fetch or preload) read-only backend
```
Proposed store layout under the OPFS mount:
```
/projects/
  <name>.blend            user documents (save target)
  .recovery/quit.blend    autosave / crash recovery (mirrors BLENDER_USER_AUTOSAVE)
  .cache/                 shader OPFS cache (GOAL GPU: "mirror the shader disk cache onto OPFS")
```
`BLENDER_USER_RESOURCES` / autosave paths point into `/projects` via `ENV` in
boot.js preRun (same mechanism the node recipe uses for `BLENDER_SYSTEM_*`).

### 2c. The sync-IO × worker coupling (ADR-003)
This is the load-bearing correctness point. **OPFS sync access handles
(`FileSystemSyncAccessHandle`) can only be created on a Web Worker** (GOAL's
"sync access handles are worker-only"). Blender's `BLO_read_file`/`BLO_write_file`
are **synchronous**. Because `main()` runs on the **proxied worker** (not the JS
main thread — the deliberate `-sPROXY_TO_PTHREAD` posture, m2-python-boot §"link
profile"), the WasmFS OPFS backend does its reads/writes with **synchronous access
handles on that worker — no JSPI suspend on the file IO path at all**. This is
exactly ADR-003's invariant: *"IO is worker-side sync-handle, not main-thread
JSPI"* (ADR-003:44), and its rule that JSPI suspends live **only** at top-level
async boundaries and **never** while a C++ `try` (OIIO/OCIO/EXR) or the imbuf
`setjmp` scope is active (ADR-003:33). Blender's writefile runs image/compression
under active try/setjmp scopes — keeping that IO **synchronous on the worker**
sidesteps the entire suspend hazard. **The picker/download half is the ONLY async
part, and it is confined to the JS main thread (§3), not to Blender's call stack.**

### 2d. Persistence verification approach
`sandbox/m7-prep/` node probe already proves write→read round-trips through
`BLO_*`. OPFS persistence itself is a **browser-only** property (no OPFS under
node), so it is verified in the M4/M7 tab: save to `/projects/x.blend`, reload the
page (fresh wasm instance, OPFS survives), `open_mainfile('/projects/x.blend')`,
assert the state dump equals the pre-reload dump (reuse `corpus-prep/state_dump.py`
+ `compare_dumps.py`, `--tolerance 0`). A Playwright script drives reload; this is
the M7 persistence gate.

## 3. Open / save UX bridge

Blender-side hooks (cited, `wm_files.cc`):
- `WM_OT_open_mainfile` (:3404): `invoke = wm_open_mainfile_invoke` (:3288, pops the
  `space_file` browser); `exec = wm_open_mainfile_exec` (:3295) → `WM_file_read(C,
  filepath, …)` (:1025 / :3129). Takes a `filepath` string property.
- `WM_OT_save_mainfile`: `exec = wm_save_as_mainfile_exec` (:3974) → `wm_file_write`
  (:2100 → :4059) wrapping `BLO_write_file`. Also a `filepath` property.

**MVP (bypass the native file browser):** neither picker needs `space_file`. The
JS bridge sets a WasmFS path and calls the operator `exec` directly:
- **Open** (Chromium FSA): main-thread JS `showOpenFilePicker()` → `File` →
  `ArrayBuffer` → `postMessage` to the main()-worker → worker `FS.writeFile(
  '/projects/incoming.blend', bytes)` → `ccall`/exported shim invokes
  `WM_OT_open_mainfile` exec with that path. (Fallback everywhere: a hidden
  `<input type=file>` upload feeds the same postMessage path.)
- **Save**: operator writes to `/projects/<name>.blend` (persistent on OPFS); to
  export a copy, JS reads the bytes back (`FS.readFile`) and either writes them
  through an FSA `showSaveFilePicker()` writable **(Chromium)** or triggers a
  Blob/`<a download>` **(fallback everywhere)**.

**Why postMessage, not JSPI, for FSA:** `showOpenFilePicker`/`showSaveFilePicker`
are **main-thread, async, user-gesture-gated** APIs; the worker cannot call them.
Doing the async picker on the JS main thread and shipping only the finished bytes
to the worker keeps Blender's stack synchronous and honors ADR-003 (no suspend on
the file path). **Driver decision:** MVP = direct-exec bridge (above); the
faithful path (route `space_file` browse/save onto an OPFS-backed directory
listing + FSA) is a post-launch refinement.

## 4. Drag-drop `.blend`

Blender-side drop path (cited): GHOST delivers a drag/drop; `wm_event_system.cc`
`wm_event_drag_and_drop_test` (:3958) sets `event->type = EVT_DROP` (:3980); the
handler at :3557 (`event->type == EVT_DROP`) runs `wm_drop_prepare` → the space's
dropbox (`view3d_dropboxes()`, view3d_dropboxes.cc:676, registered via
`WM_dropbox_add`). Filename drops arrive as `GHOST_kDragnDropTypeFilenames`.

**Browser flow:**
1. Shell `drop` event (`DataTransfer` → `File`), `preventDefault` the navigation.
2. Main-thread JS reads the `File` → `ArrayBuffer` → `postMessage` to the worker.
3. Worker `FS.writeFile('/projects/dropped/<name>.blend', bytes)`.
4. **Two options — driver call:**
   - **MVP:** worker directly `exec`s `WM_OT_open_mainfile` with the WasmFS path
     (same bridge as §3) — fastest to the "it opened my file" moment.
   - **Faithful:** `GHOST_SystemWeb` synthesizes a GHOST filename-drop event
     (type `Filenames`, path = the WasmFS path, at the drop x/y) so the native
     `EVT_DROP` → view3d dropbox path runs (shows Blender's real Open/Append menu).
     Needs a small `GHOST_SystemWeb::pushDragDrop` addition; depends on the M4
     GHOST-web window existing.
5. **`ADR-004` protects the read:** the wasm32 pointer-collision detector
   (`patches/0018`, `blo_wasm32_pointer_collision_refuse`) runs a header pre-scan
   and **refuses** a 64-bit `.blend` whose truncated block addresses collide,
   with a clear message, *before* any state is built — so a hostile/awkward
   dropped file fails loudly, never corrupts. Big-endian drops are refused
   upstream (5.0 removal, m1-corpus-prep §8). Both are already-proven behaviors.

## 5. glTF addon feasibility

- `io_scene_gltf2` at the pin is a **pure-Python addon**
  (`upstream/scripts/addons_core/io_scene_gltf2/`; no `.so/.pyd/.c/.cpp`), so it
  ships in the `scripts` payload the browser build already mounts — **no native
  build**.
- **Blocker: numpy.** It `import numpy`s in **30 files** (io/exp/meshopt.py,
  io/imp/gltf2_io_binary.py, blender/imp/mesh.py, blender/exp/accessors.py, …),
  and **numpy is NOT harvested for wasm** (`lib/wasm/.../site-packages` has no
  numpy; `_INSTALL_NUMPY OFF`, m2-python-boot §Deliverables; the tier-b run lists
  8 numpy failures deferred). So glTF is **feasibility-blocked on numpy-on-wasm**,
  not on the addon itself. **Driver decision (biggest M7 scope call):** (a) build
  numpy for wasm (a real dep task — CPython 3.13 + numpy under emcc, a superbuild
  addition; Pyodide proves it's possible), (b) defer glTF from the launch tier
  until numpy lands, or (c) a numpy-subset shim (fragile; not recommended).
- **Contrast for the other IO formats:** **OBJ** import/export is **C++**
  (`io/wavefront_obj`, no Python/numpy) — portable, works the moment the operators
  are reachable. **USD** needs the heavy USD dependency (`WITH_USD`; USD-Hydra
  delegates are forced OFF per GOAL, but core USD IO still needs the lib built for
  wasm) — a dep task on par with numpy. So of the launch-tier IO: OBJ is
  ~free, glTF gates on numpy, USD gates on the USD dep build.

## 6. M7 task list — dependency-ordered, sized

| # | task | dep | size | notes |
|---|---|---|---|---|
| T1 | OPFS mount shim: `wasmfs_create_opfs_backend` + `wasmfs_create_directory("/projects")` on the main() worker at startup | M4 shell boots | **S** | one small platform_web init fn (+ ENV wiring in boot.js) |
| T2 | JS byte-bridge core: main-thread ⇄ worker `postMessage`, worker `FS.writeFile/readFile`, exported `open/save` shim calling `WM_OT_*` exec | T1 | **M** | the reusable spine for §3/§4 |
| T3 | Open: FSA `showOpenFilePicker` + `<input type=file>` fallback → T2 | T2 | **S** | user-gesture gated |
| T4 | Save/export: `/projects` persist + FSA `showSaveFilePicker` writable + Blob-download fallback | T2 | **S** | |
| T5 | Drag-drop `.blend`: shell `drop` → T2 → MVP direct-exec open (ADR-004 guards) | T2 | **S** | **launch killshot; do early** |
| T6 | Persistence gate: save → reload tab → reopen → state-dump parity (Playwright + compare_dumps) | T1,T4 | **S** | the M7 correctness receipt |
| T7 | Staged loading: swap wholesale `--preload-file` for `wasmfs_create_fetch_backend` + SW caching per LAUNCH budgets; stdlib tree-shake | M4 | **L** | perf/size, parallel to T2-T5 |
| T8 | OBJ round-trip smoke (import/export) on wasm | operators reachable | **S** | C++, no numpy |
| T9 | **numpy-on-wasm** superbuild (unblocks glTF) | dep infra | **XL** | driver-gated; see §5 |
| T10 | glTF round-trip via Python runtime | T9 | **M** | pure-Python once numpy lands |
| T11 | USD dep build for wasm + USD IO round-trip | dep infra | **XL** | driver-gated |
| T12 | Faithful drag-drop: `GHOST_SystemWeb::pushDragDrop` → native `EVT_DROP` menu | M4 window, T5 | **M** | post-launch refinement of T5 |

Critical path to the launch bar (drag-drop + open/save + persistence):
**T1 → T2 → {T3, T4, T5} → T6**, all **S/M** and all pure port-layer (WasmFS +
JS + operator exec) — no dep rebuilds. T7 is the size/perf long-pole, parallel.
The XL dep builds (T9 numpy, T11 USD) gate glTF/USD only and are the real scope
forks.

## 7. Decisions needing driver sign-off vs the mechanical remainder

**Needs the driver:**
1. **glTF launch scope (§5): build numpy-on-wasm (T9, XL) vs defer glTF vs shim.**
   The single biggest M7 scope call.
2. **USD launch scope (§5/T11): build the USD dep for wasm, or defer USD IO.**
3. **Open/save MVP: direct-exec bridge vs. wiring the native `space_file`
   browser onto OPFS** (§3). Recommend direct-exec for launch.
4. **Drag-drop MVP: direct-exec open vs. faithful GHOST drag'n'drop synthesis**
   (§4). Recommend direct-exec (T5) for the killshot; T12 later.
5. **OPFS store layout / mount path** (`/projects`, `.recovery`, `.cache`) and
   whether the shader OPFS cache (GOAL GPU) shares the mount.
6. **Staged-loading approach** — `fetch_backend` mount vs. keep preload for MVP and
   optimize post-launch (T7 sizing against LAUNCH budgets).

**Mechanical (no driver needed once the above are set):**
- T1 OPFS mount shim, T2 postMessage byte-bridge, T3/T4 picker+fallback, T5
  drag-drop open, T6 persistence gate, T8 OBJ smoke. All are port-layer code on
  proven Blender operators + a documented emsdk API; no upstream edits, no dep
  rebuilds, and the FS-backend swap is byte-identical Blender object code (§1).

## 8. Sequencing
Everything here **blocks on M4** (a booted browser tab + `blender_browser` built —
today `WITH_BLENDER_WEB_BROWSER=OFF`, EXCLUDE_FROM_ALL). The Blender-side write/
read is already proven on the node binary (§1 probe), so once M4 lands the tab,
T1–T6 are additive port-layer work with no upstream surface — the same posture
that made the corpus (§7/§8 m1) and M5.pre oracle halves land cleanly.

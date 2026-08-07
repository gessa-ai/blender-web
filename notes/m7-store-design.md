<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M7 project-store design — Blender reading/writing .blend on OPFS (patch-ready)

**Outcome — the M7 project store is DESIGNED and both halves PROVEN.** The OPFS
substrate was already retired (`notes/m7-opfs-probe.md`); this round proves the
*actual store*: (a) the **mount recipe** — a pure env/boot-js routing of Blender's
own default paths onto an OPFS mount, **zero upstream edits** — cited against
`appdir.cc`; (b) the **browser half** — the designed `/projects` store mounted on
OPFS, a **real corpus `.blend` written + read back byte-identical + persisted across
a page reload**, a **directory listing** (the recent-files / account-sync seam), and
**50 MB save/load timing**; (c) the **node half** — Blender's appdir resolution
**honors the recipe's env vars under Emscripten** and userpref + a user `.blend` land
in the routed tree. The joint proof (real Blender binary writing through
`BLO_write_file` → OPFS in a tab) still lands with the M4 windowed shell — stated
honestly below; each half is separately airtight.

Probe source (all mine): `sandbox/m7-store-probe/`. Note is CC0.

---

## 1. The mount recipe (env + boot-js; no upstream edits)

The whole store is a **routing** of Blender's existing default paths onto an OPFS
WasmFS mount. Blender resolves every user path through
`BKE_appdir_folder_id{,_create}` / `BKE_tempdir_init`, all of which check
environment variables *first* — so we route by setting env in boot.js `preRun`
(same mechanism the node recipe already uses for `BLENDER_SYSTEM_*`).

### 1a. Mount (the T1 shim — one platform_web init fn on the main() worker)
```c
backend_t opfs = wasmfs_create_opfs_backend();          // emscripten/wasmfs.h:91
wasmfs_create_directory("/projects", 0777, opfs);        // wasmfs.h:35 — persistent mount
```
Everything nested under `/projects` is then OPFS-backed; Blender's own
`BLI_dir_create_recursive` (called by `BKE_appdir_folder_id_create`) makes the
sub-dirs on demand. Keep `/bw/{python,scripts,datafiles}` on the read-only
preload/fetch backend (unchanged).

### 1b. Env routing (boot.js `Module.preRun` → `ENV[...]`, or `--env` in argv)
```
BLENDER_USER_RESOURCES = /projects        # umbrella: config/, datafiles/, scripts/, extensions/
TMPDIR                 = /projects/.recovery   # BKE_tempdir_base -> autosave + quit.blend
```
`BLENDER_USER_RESOURCES` is the single-point override; per-kind overrides
(`BLENDER_USER_CONFIG`, `BLENDER_USER_DATAFILES`, …) exist if finer control is
wanted. Pre-create `/projects` and `/projects/.recovery` at mount time so the
**read path** (`check_is_dir=true`) accepts the env; **write paths** create missing
sub-dirs themselves.

### 1c. Where each Blender artifact lands (cited, read-only)
| artifact | resolver (upstream cite) | env that routes it | OPFS target |
|---|---|---|---|
| `userpref.blend` | `BKE_appdir_folder_id_create(BLENDER_USER_CONFIG)` — wm_files.cc:2521 | `BLENDER_USER_RESOURCES`→`/config` (or `BLENDER_USER_CONFIG`) | `/projects/config/userpref.blend` |
| `recent-files.txt` (`BLENDER_HISTORY_FILE`, BKE_appdir.hh:200) | same, wm_files.cc:1658-1664 (one path/line) | same | `/projects/config/recent-files.txt` |
| `startup.blend` | config dir, wm_files.cc:1324 | same | `/projects/config/startup.blend` |
| autosave `<pid>_autosave.blend` | `BKE_tempdir_base()` — wm_files.cc:2293 ← `BKE_tempdir_init(U.tempdir)` wm_files.cc:550 | `U.tempdir` pref **or** `TMPDIR` env (tempfile.cc:66) | `/projects/.recovery/<pid>_autosave.blend` |
| recovery `quit.blend` (`BLENDER_QUIT_FILE`) | `BKE_tempdir_base()` — wm_files.cc:2418, :3511 | same as autosave | `/projects/.recovery/quit.blend` |
| user-saved `.blend` | operator `filepath` property (byte-bridge sets it) | — | `/projects/<name>.blend` |
| shader cache (GOAL GPU) | backend-defined | — | `/projects/.cache/` |

**Path-resolution mechanics that make this work (appdir.cc):**
- `test_env_path` (appdir.cc:320) reads the env var; with `check_is_dir=true` it
  **rejects** the path if `BLI_is_dir()` is false — so the mount dir must *exist*
  (we create it). With `check_is_dir=false` (the write path) it accepts the env
  value **as-is**.
- `get_path_user_ex` (appdir.cc:496) checks `BLENDER_USER_RESOURCES` *before*
  portable/GHOST fallbacks (appdir.cc:506) — env wins.
- `BKE_appdir_folder_id_create` (appdir.cc:822): tries the existing dir, else falls
  to `_notest` (`check_is_dir=false`, appdir.cc:771) then `BLI_dir_create_recursive`
  (appdir.cc:840) — so **first-run creation on OPFS is automatic**.
- Tempdir (`BLI_temp_directory_path_get`, tempfile.cc:59-76): `TMPDIR` env → else
  `/tmp/`. `BKE_tempdir_init` also builds a `mkdtemp` session sub-dir
  (`blender_XXXXXX`, appdir.cc:1208-1243) — autosave/quit use the **base**, not the
  session sub-dir.

---

## 2. What each half proved

### 2a. Browser half — the actual store on OPFS (Chromium, COOP/COEP :8131)
`sandbox/m7-store-probe/` — emcc 6.0.5 TU under the **verbatim** browser link
profile (`patches/platform_wasm.cmake:287-289`: `-pthread -fexceptions
-sMALLOC=dlmalloc -sWASM_BIGINT -sPROXY_TO_PTHREAD -sWASMFS -sFORCE_FILESYSTEM=1
-sPTHREAD_POOL_SIZE=8`, no JSPI), with a **real uncompressed 2.6 MB corpus
`.blend`** (`mesh_dense.blend`, magic `BLENDER`) embedded read-only. main() runs on
the `PROXY_TO_PTHREAD` worker ⇒ every op is a synchronous WasmFS OPFS op on a
worker (ADR-003 posture). Two runs (`?fresh=1` clean, then a plain reload):

| step | result |
|---|---|
| **A. mount + designed layout** | OK — OPFS at `/projects` + `{config,.recovery,.cache}` via `mkdir` |
| **B. real `.blend` round-trip** | OK — 2 645 141 B **byte-identical** (`memcmp` + fnv `8b4da890f7147738`), **`BLENDER` magic preserved** |
| **C. config + recovery artifacts** | OK — wrote `config/userpref.blend`, `config/recent-files.txt` (one-path-per-line, exact wm_files.cc format), `.recovery/quit.blend` |
| **D. directory listing** | OK — `readdir` on `/projects` (5 entries) + `/projects/config` (2 files), names+sizes — the recent-files / library / account-sync seam |
| **E. 50 MB `.blend` timing** | OK — byte-verified (see §4) |
| **F. persistence across reload** | **OK — SURVIVED**: fresh wasm instance re-read `/projects/mesh_dense.blend` byte-identical (**same fnv `8b4da890f7147738`**), magic intact; `config/userpref.blend`, `recent-files.txt`, `.recovery/quit.blend`, `big50.blend` all persisted |

Persistence is the load-bearing receipt: run A wrote the store; the reload spun a
**brand-new wasm module (fresh linear memory)** and re-read the identical bytes — so
they genuinely came from OPFS storage, not in-RAM state. The fnv hash matching
across the reload is the proof.

### 2b. Node half — appdir env routing honored under Emscripten
`sandbox/m7-store-probe/node_route.sh` — read-only run of the pre-built node binary
`build-wasm-cycles/bin/blender.js` (NODERAWFS ⇒ writes hit the host FS; this half
proves **path routing**, which is Blender object code identical across FS backends —
**not** OPFS persistence, which is the browser half). With
`BLENDER_USER_RESOURCES=$scratch/userroot` and `TMPDIR=$scratch/recovery`:

- `bpy.utils.resource_path('USER')` → `$userroot` ✓ (env honored)
- `bpy.utils.user_resource('CONFIG')` → `$userroot/config`, `DATAFILES` →
  `$userroot/datafiles` ✓
- `bpy.app.tempdir` → `$recovery/blender_aJaicO/` ✓ (TMPDIR honored **and** `mkdtemp`
  session sub-dir created under Emscripten)
- `bpy.ops.wm.save_userpref()` → real **`$userroot/config/userpref.blend` (178 528 B)**
  written to the routed dir ✓
- `bpy.ops.wm.save_as_mainfile()` → a user `.blend` (zstd magic `28 b5 2f fd`, the
  5.2 default compression) written into the routed tree ✓ — the store is
  **compression-agnostic** (browser half moved an uncompressed one; both round-trip)

Notes: `user_resource('CONFIG')` without `create=True` returns the path but does not
materialize the dir (`CONFIG_CREATED False`) — expected; the write operators create
it via `BKE_appdir_folder_id_create`. `recent-files.txt` is **not** written in
`--background` mode (wm_files.cc:1657 "Will be nullptr in background mode") — it is a
windowed-session artifact; its *path resolution* (config dir) is what we proved, and
the browser half exercises its byte format directly.

---

## 3. Integration steps for the windowed binary (patch-ready, no upstream edits)

All port-layer; maps onto `notes/m7-files-prep.md` §6 T1/T2. **Nothing here edits
`upstream/`** — it is a `platform_web` init fn + boot.js env + the existing exported
`FS`/`callMain` hooks (`platform_wasm.cmake:290`).

1. **T1 — OPFS mount** (`platform_web`, called once from the main() worker at
   startup, before `WM_init` runs `BKE_tempdir_init`):
   ```c
   backend_t opfs = wasmfs_create_opfs_backend();
   wasmfs_create_directory("/projects", 0777, opfs);
   mkdir("/projects/.recovery", 0777);   // pre-exist so TMPDIR read-path accepts it
   ```
2. **Env routing** — in `web/boot.js` `Module.preRun` (before `callMain`):
   ```js
   Module.preRun = Module.preRun || [];
   Module.preRun.push(() => {
     Module.ENV.BLENDER_USER_RESOURCES = "/projects";
     Module.ENV.TMPDIR = "/projects/.recovery";
     // keep existing BLENDER_SYSTEM_* pointing at the read-only /bw payload
   });
   ```
   (`ENV` is already exported at `platform_wasm.cmake:290`.) These two lines +
   the T1 fn are the *entire* wiring for persistent userpref, recent-files,
   autosave, recovery, and user saves.
3. **T2 — byte-bridge** (already designed, m7-files-prep §3): main-thread picker/
   drop → `postMessage` bytes → worker `FS.writeFile("/projects/incoming.blend",
   bytes)` → exported shim `ccall`s `WM_OT_open_mainfile` exec with that path. Save/
   export reads back via `FS.readFile` → FSA writable (Chromium) or Blob download
   (fallback).
4. **T6 — persistence gate**: save → reload tab → reopen → state-dump parity
   (Playwright + `corpus-prep/compare_dumps.py --tolerance 0`). The substrate for
   this is proven here; the gate binds it to real `BLO_*` on the M4 shell.

---

## 4. Timings (Chromium 148, macOS, OPFS)

The **first** write to a freshly-wiped OPFS is a **cold path** (linear-memory growth
from the 512 MB initial, OPFS backend-thread warm-up, first `createSyncAccessHandle`
per file); the reload run is **warm/steady-state**. Report both honestly:

| op | cold (first load) | warm (reload) |
|---|---|---|
| real 2.6 MB `.blend` save | 877 ms (2.9 MB/s) | **10 ms (243 MB/s)** |
| real 2.6 MB `.blend` load | 179 ms (14.1 MB/s) | **11 ms (222 MB/s)** |
| 50 MB `.blend` save | 568 ms (88 MB/s) | **145 ms (344 MB/s)** |
| 50 MB `.blend` load | 165 ms (303 MB/s) | **65 ms (767 MB/s)** |
| persisted 2.6 MB reread (post-reload) | — | 8 ms (320 MB/s) |

Steady-state matches the substrate probe (`m7-opfs-probe.md`: 479–652 MB/s write,
954–1210 MB/s read). **Takeaway:** a 50 MB `.blend` saves in ~0.15 s and loads in
~0.07 s warm; even the worst cold save is ~0.6 s. Comfortably within any interactive
budget. Small-file ops carry a fixed OPFS sync-handle latency floor (tens–hundreds of
ms cold) that is irrelevant at `.blend` scale.

---

## 5. Platform-facing seams confirmed (for `notes/platform-integration-design.md`)

- **Recent-files seam:** `/projects/config/recent-files.txt`, one absolute path per
  line (wm_files.cc:1664, verified byte-format in the probe). Platform account-sync
  reads/mirrors this file; the `readdir` listing (step D) enumerates it.
- **⚠ Autosave dir CORRECTION (important):** `platform-integration-design.md` §1
  assumes "Blender's autosave timers write `.blend` into the OPFS **user** dir."
  That is **inaccurate** — autosave `<pid>_autosave.blend` **and** recovery
  `quit.blend` go to **`BKE_tempdir_base()` = `TMPDIR`**, a *separate* seam from the
  config dir. The dir the platform must watch/upload for autosave is
  **`/projects/.recovery`** (our `TMPDIR`), **not** `/projects/config`. This is why
  the recipe routes `TMPDIR` explicitly.
- **Tradeoff of routing `TMPDIR` to OPFS:** autosave *and* general session temp
  (render scratch, undo spill) share `BKE_tempdir_base()`; there is no upstream split.
  Routing `TMPDIR=/projects/.recovery` makes **recovery survive reload/crash** at the
  cost of session temp churn also consuming OPFS quota (session sub-dirs are purged by
  `BKE_tempdir_session_purge`). Acceptable for MVP; a dedicated persistent-recovery
  split would need a patch — deferred.
- **Directory / library seam:** `readdir` on the mount works (step D) — the basis for
  a platform file browser and OPFS↔account mirroring.

---

## 6. Remaining unknowns (joint proof + carry-forward)

1. **Joint proof pending M4.** Each half is airtight *separately*: node proves
   `BLO_write_file`/`BLO_read_file` + env routing under Emscripten; browser proves
   the OPFS store + persistence. The *combined* proof — the real windowed Blender
   binary writing through `BLO_write_file` onto the `/projects` OPFS mount in a tab —
   needs the M4 shell (`WITH_BLENDER_WEB_BROWSER=ON`). No new risk expected: the
   FS-backend swap is byte-identical Blender object code (m7-files-prep §1).
2. **`mkdtemp` on OPFS.** The node half confirmed `mkdtemp` works under Emscripten
   (host FS). Autosave/quit use `BKE_tempdir_base()` (no mkdtemp needed), but the temp
   *session* sub-dir does `mkdtemp` — verify it succeeds on the OPFS backend in the M4
   tab (if it fails, `BKE_tempdir_init` falls back to the base, appdir.cc:1273-1280,
   so autosave still works).
3. **`-sJSPI` co-existence** (carried from m7-opfs-probe): this probe ran without
   JSPI; the M4 windowed binary links it. OPFS IO never suspends (ADR-003) — re-run an
   OPFS round-trip in the JSPI binary to confirm.
4. **OPFS eviction / `navigator.storage.persist()`** — best-effort storage; call
   `persist()` for the project store, measure quota headroom vs `.blend` sizes.
   Recovery must assume eviction is possible.
5. **Cross-browser** — validated on Chromium 148 only; confirm the OPFS substrate on
   Firefox/Safari during M7 (sync access handles ship there; FSA pickers are
   Chromium-only → `<input type=file>` + Blob fallback).

---

## 7. Reproduce
```
harness/buildwrap.sh sandbox/m7-store-probe/build.sh          # emcc 6.0.5, ~18 s
python3 sandbox/m7-store-probe/web/server.py 8131             # COOP/COEP
#  open  http://localhost:8131/?fresh=1   (clean first load: PERSIST-FRESH)
#  reload http://localhost:8131/          (PERSIST-SURVIVED OK — the receipt)
bash sandbox/m7-store-probe/node_route.sh                     # node env-routing half
```
Browser markers (page log / `window.storeResults` / `document.title`): `MOUNT OK`,
`BLEND-RW OK`, `ARTIFACTS OK`, `DIRLIST OK`, `BIG50 OK`, `PERSIST-SURVIVED OK`,
`PERSIST-ARTIFACTS OK`, `PROBE-DONE`. Node markers: `RESOURCE_USER True`,
`USER_CONFIG True`, `TEMPDIR True`, `USERPREF_SAVED True`, `SAVEAS_ROUTED True`.

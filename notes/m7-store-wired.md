<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M7 project store WIRED into the windowed shell - joint proof LANDED

**Outcome: the both-halves-proven OPFS project store (notes/m7-store-design.md) is
now WIRED into the real windowed `blender_browser` binary, and the JOINT PROOF -
the combined receipt the design note said still had to land with the M4 shell
(§6.1) - is GREEN 13/13 in a real Chromium tab.** The real windowed Blender writes
through `BLO_write_file` onto the persistent OPFS `/projects` mount, a full page
reload spins a brand-new wasm instance, and the same Blender re-reads the bytes
byte-identically and restores the scene content. No upstream edits; no cmake/patch
change (the M8 `__pycache__` prune block is untouched).

Rig source (all mine): `sandbox/m7-store-wire/`. Note is CC0.

---

## 1. What was wired (3 owned files, zero cmake/link-flag change)

1. **The OPFS mount seam** - `platform_web/ghost/GHOST_SystemWeb.cc`:
   `extern "C" EMSCRIPTEN_KEEPALIVE int bw_mount_opfs(void)` runs the design
   note's exact recipe - `wasmfs_create_opfs_backend()` +
   `wasmfs_create_directory("/projects", 0777, opfs)` + `mkdir("/projects/.recovery")`
   (so the TMPDIR read-path `check_is_dir=true` accepts it). It is idempotent
   (static guard) and never aborts boot (graceful-degrade codes below). It is
   **called from `GHOST_SystemWeb::init()`** - see §2 for why that site.
2. **Env routing** - `platform_web/shell/boot-windowed.js` `ENV_VARS` gains
   `BLENDER_USER_RESOURCES=/projects` and `TMPDIR=/projects/.recovery`, set in the
   existing `Module.preRun` (same mechanism as `BLENDER_SYSTEM_*`). These two lines
   route userpref/recent-files/startup.blend/user-saves onto the mount
   (`BLENDER_USER_RESOURCES`, appdir.cc `get_path_user_ex` checks it first) and
   autosave/quit-recovery onto the separate `BKE_tempdir_base()` seam (`TMPDIR`,
   tempfile.cc).
3. **A negative marker** - `platform_web/shell/wgpu-preinit-worker.js` documents
   that the mount is deliberately NOT done in the pre-main worker seam (§2), so no
   future worker re-adds it there.

No `patches/platform_wasm.cmake` change: the binary already links `-sWASMFS
-sFORCE_FILESYSTEM=1` (so `wasmfs_create_opfs_backend` links), and
`EMSCRIPTEN_KEEPALIVE` exports the symbol without touching the (unowned) link
flags - exactly the `bw_shell_set_display` pattern already in the tree.

## 2. The load-bearing finding: mount must run INSIDE main(), not pre-main

The design note (§1a/§3 T1) and the probes describe the mount as "pre-main on the
main()-owning worker." The first wiring attempt did exactly that - called
`bw_mount_opfs` from `wgpu-preinit-worker.js` right before it dispatches the cmd:2
entry message (the same worker window that pre-acquires the WebGPU device).

**It DEADLOCKED boot** (measured, not theorized): the WebGPU
`device pre-acquired ... features=22` line printed, but the mount log line never
printed and `main()` never ran (no `--python-expr`, black canvas). Root cause: the
WebGPU acquisition works because it `await`s (yields the worker's message loop),
whereas `wasmfs_create_opfs_backend()` is a **synchronous, message-loop-blocking**
call that spins up a dedicated OPFS backend thread. Invoked before
`invokeEntryPoint` - while still inside the cmd:2 `onmessage` handler, before the
worker's pthread/OPFS-backend machinery is ready - it blocks the message loop and
never returns.

The fix matches the probes, which mounted **inside `main()`**: the mount now runs
at the top of `GHOST_SystemWeb::init()`, reached via
`wm_ghost_init` -> `GHOST_ISystem::createSystem()` (wm_init_exit.cc:205). That is
on the same WM (PROXY_TO_PTHREAD) worker, inside `main()` (runtime + pthread pool
fully warm), and crucially BEFORE the two path resolutions that matter:

- `wm_homefile_read_ex` (userpref / config dir) - wm_init_exit.cc:283
- `BKE_tempdir_init(U.tempdir)` - wm_files.cc:550 (called from the homefile read)

So it satisfies the design note's real requirement - "before WM_init runs
`BKE_tempdir_init`" - while sidestepping the pre-entry deadlock. The measured mount
cost is ~17-38 ms (see §4).

## 3. Joint proof - 13/13 GREEN (headed Chromium, COOP/COEP :8126)

`sandbox/m7-store-wire/verify-store-persistence.mjs`: RUN 1 boots windowed and a
`bpy.app.timer` inside `WM_main` adds a distinctive object
(`BW_STORE_PROOF` + `bw_marker` + a scene custom prop), then
`bpy.ops.wm.save_as_mainfile('/projects/proof.blend')`,
`bpy.ops.wm.save_userpref()`, and a recovery-class `.blend` into
`BKE_tempdir_base()` (= `/projects/.recovery`); RUN 2 RELOADS THE SAME TAB (brand
new wasm module, fresh linear memory) and re-reads everything. All sizes + FNV-1a-64
hashes are computed in Blender's own Python on the WM worker and surfaced via a
MEMFS diag file + the page console.

| check | result (representative run) |
|---|---|
| mount PERSISTENT, run 1 | `rc=0 in 19.0 ms` |
| mount PERSISTENT, run 2 | `rc=0 in 18.8 ms` |
| save `.blend` (real BLO_write_file -> OPFS) | `size=97094 fnv=178d7667451cd196 magic=28b52ffd` (zstd, 5.2 default) `objs=4` |
| **reload persists size** | save=97094 == load=97094 |
| **reload persists FNV (THE receipt)** | save=`178d7667451cd196` == load=`178d7667451cd196` |
| content survives (real BLO_read_file + bpy) | `proof_obj=FOUND marker='m7-store-wired' scene_marker=424242 objs=4` |
| userpref persists (config seam) | save fnv=`75d8e16d445a0233` == load |
| recovery/TMPDIR seam persists | save fnv == load (`/projects/.recovery/bw_recovery_proof.blend`) |
| TMPDIR routed in-tab | `bpy.app.tempdir=/projects/.recovery/blender_kaLPJB/` (env honored + mkdtemp works on OPFS) |
| **OPFS-vs-MEMFS discriminator** | `/tmp/bw_memfs_control.bin` after reload `exists=False` |
| directory-listing seam | `readdir /projects = .recovery,config,proof.blend` |
| distinct fresh sessions | tempdir suffixes differ (`blender_kaLPJB` vs `blender_MJcNKi`) |

The FNV match across the reload is the load-bearing receipt: run 2 is a fresh wasm
instance with fresh memory, so identical bytes can only have come from OPFS storage,
not in-RAM state. The MEMFS control file (written to the in-memory `/tmp`) being
**gone** after the same reload proves persistence is specifically the OPFS mount, not
an artifact of the harness - the design note's OPFS-vs-MEMFS discriminator, in the
real binary. (Aside: wasm `getpid()` is a constant 42 for every instance, so PID is
NOT a session discriminator here; the per-session `mkdtemp` tempdir suffix is, and it
differs across the reload.) FNV differs run-to-run because `save_as_mainfile` embeds
per-session bytes; the invariant that holds is save-fnv == load-fnv **within** a run.

Evidence: `sandbox/m7-store-wire/evidence/joint-proof-run.txt` (full 13/13
transcript), `m7-store-run{1,2}-*.png` (real UI renders during save/load).

## 4. Boot-time delta

The mount is the only added pre-`WM_init` work. Measured inline
(`emscripten_get_now()` around `bw_mount_opfs`, logged to console every boot):
**~17-38 ms** across runs (17.4 / 18.8 / 19.0 / 24.3 / 28.6 / 36.4 / 38.4 ms). This
is the OPFS backend-thread spin-up + two `mkdir`s; it is a one-time cost folded into
GHOST creation, dwarfed by module download + wasm instantiation. Steady-state IO
throughput is the substrate probe's (m7-opfs-probe.md: 0.5-1.2 GB/s), unchanged.

## 5. Graceful degrade + contracts

- **Graceful degrade:** `bw_mount_opfs` never aborts. `rc=0` = OPFS persistent;
  `rc=1` = OPFS unavailable, `/projects` created on the default **in-memory**
  backend so env routing still resolves (session-only, no persistence);
  `rc=-1` = could not create `/projects` (user paths fall back to Blender defaults).
  `GHOST_SystemWeb::init()` logs the mode and ignores the code, so boot proceeds in
  every case. (Real OPFS-unavailable cannot be forced in a crossOriginIsolated
  bundled Chromium - OPFS is always present there - so `rc=1`/`rc=-1` are
  proven by code path + return-contract, not a live tab; `rc=0` PERSISTENT is the
  live-proven path.)
- **`?gate=WxH` PRESERVED:** `sandbox/m7-store-wire/diag-gate.mjs` -
  `?gate=800x600` under `deviceScaleFactor=2` yields canvas backing EXACTLY
  `800x600` (DPR forced to 1), and the store still mounts `PERSISTENT` alongside it
  (`evidence/gate-contract-run.txt`).
- **Dev hooks unaffected:** `?pyexpr=` drives the entire joint proof (so it is
  exercised end-to-end); `?args=` / `bootExtraArgs` and the resize/DPR
  `bw_shell_set_display` handshake are untouched.

## 6. Carry-forward (from notes/m7-store-design.md §6, now partly closed)

- CLOSED: joint proof (§6.1) - real windowed binary BLO_* through OPFS in a tab.
- CLOSED: `mkdtemp` on OPFS (§6.2) - `bpy.app.tempdir` shows a live
  `blender_XXXXXX` session sub-dir under `/projects/.recovery` on the OPFS backend.
- CLOSED: `-sJSPI` co-existence (§6.3) - this is the JSPI-linked windowed binary
  and OPFS round-trips cleanly (IO never suspends).
- OPEN: `navigator.storage.persist()` / eviction headroom (§6.4); cross-browser
  (§6.5, Chromium 148 only). Both are UX/durability, not substrate risk.
- OPEN (not this lane): real autosave-timer landing was proven at the SEAM level
  (`/projects/.recovery` is the OPFS-backed `BKE_tempdir_base`, a recovery `.blend`
  written there survives reload); driving Blender's own autosave timer to fire is a
  timing test deferred to soak.

## 7. Reproduce
```
# relink (needs EMSDK_PYTHON or cmake reruns fall to Xcode py3.9 and abort):
EMSDK_PYTHON=/Users/paws/blender-web/tools/emsdk/python/3.13.3_64bit/bin/python3 \
  bash harness/buildwrap.sh bash scripts/ninja-locked.sh -C build-wasm-windowed blender_browser
# serve (COOP/COEP, windowed shell + bin) on :8126:
BLENDER_WEB_BIN=$PWD/build-wasm-windowed/bin BLENDER_WEB_SHELL=$PWD/platform_web/shell \
  bash scripts/serve-web.sh 8126
# joint proof + contract checks (headed bundled Chromium):
NODE_PATH=/Users/paws/plushly/game-platform/node_modules node sandbox/m7-store-wire/verify-store-persistence.mjs
NODE_PATH=/Users/paws/plushly/game-platform/node_modules node sandbox/m7-store-wire/diag-gate.mjs
```
Binary proven: `build-wasm-windowed/bin/blender_browser.wasm` @ 2026-08-07T23:41:40
(926750606 B) / `.js` @ 23:41:41, relinked from branch `agent/m2.5-python-boot`.

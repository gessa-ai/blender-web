<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M7b files I/O - .blend drag-drop, File System Access open/save, OPFS persistence

**Outcome: the windowed `blender_browser` shell now ships a FILE BRIDGE
(`platform_web/shell/file-bridge.js`, wired by `boot-windowed.js`) that opens and
saves real `.blend` files. All shipped paths are verified 9/9 in a real Chromium
tab against a real `.blend`** (`sandbox/m7b-files/verify-deterministic.mjs`,
`evidence/verify-deterministic-run.txt`): drag-drop OPEN, SAVE with a live edit,
CONTENT survival across a full page reload, File System Access open + save, the
`<input type=file>` and download-blob fallbacks, and the `navigator.storage.persist()`
boot report. One thing needs a single manual confirmation and is called out honestly
in §5: the LIVE post-boot trigger (the actual DOM drop / native OS picker click),
which is gated by a pre-existing WM-loop limitation (§4), not by the file bridge.

All files mine: `platform_web/shell/{file-bridge.js, boot-windowed.js (wiring),
windowed.html (script tag)}`, `sandbox/m7b-files/**`. No upstream/cmake/link change.

---

## 1. The hard constraint (measured) and the design it forces

The windowed build is `-sPROXY_TO_PTHREAD`: `main()`, WasmFS and all of Blender run
on the WM **worker**; the page runs on the **browser thread**. Two measured facts
(probe `sandbox/m7b-files/probe-write-channel.mjs`, confirming + extending the M5
channel audit in `notes/m5-windowed-replay.md`):

- **MEMFS is a shared-memory cross-thread conduit.** A file the browser thread
  writes to a MEMFS path (`/tmp/...`) is visible to the WM worker's Python and vice
  versa. `FS.readFile` from the browser thread post-boot is known-good; `FS.writeFile`
  to MEMFS post-boot works too.
- **OPFS is worker-only in practice.** The durable `/projects` mount uses WasmFS
  OPFS sync access handles, which are worker-thread only (GOAL.md emscripten posture).
  Browser-thread OPFS access is flaky/forbidden across runs (v1 of the probe: a
  browser-thread OPFS `readFile` threw and the worker never saw the write; v2 on a
  clean OPFS "worked" but is not a contract we rely on).

**Design (both directions use MEMFS as the byte conduit; the WORKER owns every OPFS
I/O and every `bpy.ops.wm.{open,save}_mainfile`):**

- A small **WM-worker daemon** (Python) is armed as its OWN isolated `--python-expr`
  at boot (`BWFileBridge.daemonPyexpr()`, appended by `boot-windowed.js` before any
  user `?pyexpr`; creator handles each `--python-expr` occurrence independently, and
  a script error only prints by default, so it cannot break the user hook or boot).
  It registers a `bpy.app.timer` that drains a MEMFS command dir `/tmp/bw_io/cmd/`.
- **IN** (drag-drop / FSA open): the page writes bytes -> `/tmp/bw_io/in/<tok>.blend`,
  then a command -> `/tmp/bw_io/cmd/<tok>.json`. The daemon copies the bytes into
  `/projects/imported/<name>` (durable OPFS, worker thread), `open_mainfile`s it, and
  writes `/tmp/bw_io/ack/<tok>.json`.
- **OUT** (FSA save / download): the page writes a save command. The daemon
  `save_as_mainfile(copy=True)` into `/projects/imported/<name>` (durable OPFS), copies
  the bytes to `/tmp/bw_io/out/<tok>.blend`, and acks; the page reads those bytes back
  (`FS.readFile`) and streams them to the disk handle or a download blob.
- Ops: `open`, `open_store` (open a `.blend` already in the durable store - recent-files
  / `?open` deep-link per `notes/platform-integration-design.md`), `save` (optional
  `addEmpty` / `sceneMarker`), `list`, `mark`. Names are basename-sanitized on both
  sides; `.blend` is enforced.

Feature detection: `showOpenFilePicker`/`showSaveFilePicker` when present (Chromium),
else `<input type=file>` for open and a download-blob `<a download>` for save.

## 2. What was wired (3 owned shell files, zero cmake/link change)

1. `platform_web/shell/file-bridge.js` (NEW) - the daemon Python (single source of the
   conduit protocol + paths), the browser-thread conduit helpers, drag-drop listeners +
   a drop overlay, FSA open/save + fallbacks, `openStore`, and `requestPersistence()`.
2. `platform_web/shell/boot-windowed.js` - appends the daemon `--python-expr` (skipped
   in `?gate` mode so the golden argv stays pristine), calls `requestPersistence()` at
   boot, and `BWFileBridge.attach(mod, ...)` after the module resolves. Every preserved
   hook is untouched (`?pyexpr/?args/?gate`, `__bwModule`, resize/DPR `bw_shell_set_display`,
   the store ENV, the "main loop (WM_main)" marker).
3. `platform_web/shell/windowed.html` - one `<script src="/file-bridge.js">` before
   `boot-windowed.js`.

## 3. navigator.storage.persist() (open item 6.4, first half)

`requestPersistence()` runs at boot and logs ONE honest console line, e.g.:
`[file-bridge] storage.persist(): granted=false persisted=false eviction=best-effort/evictable usage=0 quota=10737418240`.
It calls `persisted()` first, then `persist()` if not already durable, then `estimate()`.

**Eviction posture (honest):** `persisted=true` => the origin's OPFS is durable and is
NOT cleared under storage pressure without explicit user action; `persisted=false` =>
best-effort storage, evictable under pressure. In an automated headless Chromium with
no user engagement the grant is `false` (measured) - Chromium ties `persist()` grants to
engagement/installation heuristics; a real, engaged user (or an installed PWA) is where
`true` is expected. The request + the truthful report are the deliverable; the grant
itself is a browser policy decision we cannot force. Quota observed ~8-10 GB.

## 4. THE blocker for the LIVE post-boot trigger: the WM loop stalls at idle

This is the load-bearing finding and it is a PRE-EXISTING platform limitation, not a
file-bridge defect. Web `WM_main` is `emscripten_set_main_loop(fn, 0, 1)` -
requestAnimationFrame-driven on the WM worker (`patches/0026-wm-main-loop-web.patch`).
The worker's rAF is **present-gated**: it only reschedules while frames composite. GHOST
forces redraws for the first ~180 ticks at boot (`GHOST_SystemWeb::processEvents`
heartbeat) then, by design, stops ("the OffscreenCanvas retains the last composited frame
indefinitely ... a proper invalidate-driven present is a later optimization"). At idle the
loop stalls, so `bpy.app.timers` (and therefore a polling daemon) do not advance.

Measured exhaustively (probes, results in-line):
- `probe-burst.mjs`: 11,610 tight reads over 12 s of a `first_interval=0` worker timer ->
  **maxHb=1**. A post-boot-registered timer gets exactly ONE tick, then permanent stall.
- `probe-raf-pump.mjs`: the MAIN-thread rAF is alive (2-8 ms latency), yet the worker loop
  never ticks - so it is the worker OffscreenCanvas rAF that stalls, not main-thread
  throttling. Synthetic canvas events, real CDP `Input.dispatchMouseEvent`, and
  `bw_shell_set_display` nudges do NOT restart a stalled loop (draining input itself needs
  a tick). Screencast, `bringToFront`, anti-occlusion launch flags, continuous input from
  the boot window, a `tag_redraw`-every-tick timer, and continuous OPFS writes were all
  tried and none sustain it (probes removed after the burst/raf-pump distillation).

Consequence: the daemon's continuous polling only advances while frames composite - i.e.
in a live, interacting, foreground tab, or when a future keepalive lands. A file dropped
into a truly idle tab will not open until the loop next ticks. **Recommended fix (for the
driver, needs a relink - the r29 lane holds the ninja lock):** a minimal opt-in GHOST
keepalive - extend the `processEvents` redraw heartbeat to continue while a shell-set
shared flag is on (set in `preRun`, before the boot heartbeat expires, so the loop never
stalls), forcing a present each tick WITHOUT the heartbeat's MOUSEMOVE injection. Default
OFF preserves the gate golden / M4 / M5 / store-wire behavior byte-for-byte.

## 5. Verification - 9/9, real `.blend`, SHIPPED code (auto vs manual)

`sandbox/m7b-files/verify-deterministic.mjs` (headed bundled Chromium, COOP/COEP :8126).
It sidesteps §4 the exact way the store-wire joint proof does (13/13): a command STAGED
before `WM_main` is drained by the daemon's guaranteed first-tick poll (the daemon's poll
`first_interval=0.0`). Post-boot JS glue is verified with the TEST playing the daemon over
the same MEMFS conduit (pure browser-thread; no WM tick).

| id | proves (real default_cube.blend, 95944 B) | result |
|---|---|---|
| P1 | drag-drop OPEN path: browser-staged bytes -> daemon copy to `/projects/imported` + `open_mainfile` | PASS `objects=[Camera,Cube,Light]` |
| P2 | SAVE path + live edit: `save_as_mainfile` with an added Empty marker | PASS `objects=[BW_RT_MARKER,Camera,Cube,Light]` |
| P2 | out bytes are a valid `.blend` (zstd magic) | PASS `28b52ffd:95978` |
| P3 | CONTENT survives a full page reload: `open_store` from OPFS after fresh wasm | PASS `[BW_RT_MARKER,Camera,Cube,Light]` |
| P4 | FSA open (mock picker) delivers real bytes to the importer | PASS `95944` |
| P4 | `<input type=file>` fallback (Playwright filechooser) | PASS `95944` |
| P4 | FSA save writable receives the exact saved bytes | PASS `fsa 95944 28b52ffd` |
| P4 | download-blob fallback (real download event) | PASS `28b52ffd 95944` |
| P5 | `navigator.storage.persist()` reported at boot | PASS (posture line) |

**AUTO-VERIFIED end-to-end:** the whole conduit + daemon `open`/`open_store`/`save` paths
with a real `.blend`; a live edit captured into a save; content survival across a real
reload (the round-trip receipt); every FSA and fallback JS path; the persist report.
Also independently proven in `probe-write-channel.mjs`: a browser-thread-written `.blend`
opened by the WM worker via `open_mainfile` -> Camera,Cube,Light.

**NEEDS ONE MANUAL CONFIRMATION** (harness cannot, per §4 + native-dialog headless limits):
the LIVE post-boot trigger - physically dragging a `.blend` onto the canvas, and clicking
the native OS `showOpenFilePicker`/`showSaveFilePicker` dialogs - in a real interacting
tab. The code path behind each is identical to the auto-verified path (drop -> `importBytes`
-> conduit -> daemon; picker -> `getFile`/writable -> conduit), and the daemon polls
continuously in a live compositing tab; the only unproven-by-automation link is the WM
tick under real interaction, which §4's keepalive would also settle.

## 6. Reproduce
```
# serve (COOP/COEP; windowed shell + bin) on :8126:
BLENDER_WEB_BIN=$PWD/build-wasm-windowed/bin BLENDER_WEB_SHELL=$PWD/platform_web/shell \
  bash scripts/serve-web.sh 8126
# 9/9 deterministic proof (headed bundled Chromium):
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/m7b-files/verify-deterministic.mjs
# channel + loop-stall evidence:
NODE_PATH=/Users/paws/plushly/game-platform/node_modules node sandbox/m7b-files/probe-write-channel.mjs
NODE_PATH=/Users/paws/plushly/game-platform/node_modules node sandbox/m7b-files/probe-burst.mjs
NODE_PATH=/Users/paws/plushly/game-platform/node_modules node sandbox/m7b-files/probe-raf-pump.mjs
```
Binary under test: `build-wasm-windowed/bin/blender_browser.wasm` @ 2026-08-07T23:41
(926,750,606 B) - unchanged by this lane (shell-only work).

## 7. Carry-forward
- OPEN (recommended, needs relink + r29 ninja-lock coordination): the §4 GHOST keepalive
  so the daemon polls in an idle tab and the live drop/picker trigger is fully automatable.
- OPEN (6.4 second half / 6.5): `persist()=true` on an engaged/installed origin; cross-browser
  (Chromium only here). The `<input>`/download fallbacks already cover non-FSA browsers.
- FUTURE: `?open=<id>` deep-link (the daemon already has `open_store`; the boot stager in
  the verifier is the exact mechanism), OBJ/USD + glTF via the same conduit (Python-driven).

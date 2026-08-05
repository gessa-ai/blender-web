<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->
# M7-prep — OPFS / WasmFS probe (empirical, in a real tab)

**Outcome: the coupled M7 filesystem risk is RETIRED for the substrate.** Under the
*exact* browser flag family the real Blender binary links, WasmFS + the OPFS backend
mount, do a 100 MB (.blend-scale) byte-identical round-trip, **persist across a full
page reload**, run synchronous IO from pthreads, and take two concurrent pthread
writers without corruption. The "sync access handles are worker-only — threads and
sync IO are one coupled decision" architecture decision (GOAL.md *Emscripten posture*;
ADR-003) is now **verified, not assumed**. What remains for M7 is *wiring* (operator
`exec` ↔ OPFS mount ↔ JS byte-bridge) and *cross-browser + user-gesture* UX — none of
it substrate risk. This is the browser-only validation that `notes/m7-files-prep.md`
§2c/§2d said still had to be done in a tab; that design recon is not duplicated here.

Probe source: `sandbox/opfs-probe/` (all mine). Note is CC0.

## Exact flag profile tested (the real browser link line)

Verbatim from `patches/platform_wasm.cmake:287-289` (`_bw_browser_flags`, the WASMFS
browser profile), minus the `--preload-file` payload and re-homed `EXPORT_NAME`:

```
-pthread -fexceptions -sMALLOC=dlmalloc -sWASM_BIGINT -sALLOW_MEMORY_GROWTH
-sINITIAL_MEMORY=536870912 -sPROXY_TO_PTHREAD -sEXIT_RUNTIME=1 -sSTACK_SIZE=8388608
-sPTHREAD_POOL_SIZE=8 -sWASMFS -sFORCE_FILESYSTEM=1
```

- **emcc 6.0.5** (pinned emsdk, `1db513782be2`), `em++ -std=c++20 -funsigned-char`.
- **JS-EH** (`-fexceptions`, matches the real link line 287, not `-fwasm-exceptions`).
- **Allocator = dlmalloc**, matching the real browser binary. GOAL's posture bullet
  names mimalloc, but the actual browser link overrides to dlmalloc because of the
  CPython mimalloc duplicate-symbol clash (`platform_wasm.cmake:134-139`; mimalloc is
  kept only for gtest/host-tool binaries that don't link libpython). Allocator choice
  is orthogonal to OPFS/WasmFS semantics.
- **NOT tested here: `-sJSPI`.** The M4 *windowed* build adds `-sJSPI` for the one-time
  device await (`platform_wasm.cmake:313`). The OPFS IO path never suspends (ADR-003),
  so co-existence is expected-fine, but it is an open integration check (below).
- Browser: **Chromium 148.0.7778.280** (Electron 42 shell), macOS.
  `crossOriginIsolated=true` (COOP/COEP server), `navigator.storage.getDirectory`
  present, OPFS origin quota ≈ 9.2 GB.
- API used: `wasmfs_create_opfs_backend()` + `wasmfs_create_directory("/opfs",0777,b)`
  (`emscripten/wasmfs.h:35,91`), then plain POSIX `open/write/read/close`.

## What works (measured, Chromium 148 / macOS, 100 MB payload)

| test | result | numbers |
|---|---|---|
| **1. mount + 100 MB round-trip** | OK, byte-identical (`memcmp`, 104857600 B) | write **479–652 MB/s** (209 / 153 ms); read **954–1199 MB/s** (83 / 105 ms) |
| **2. persistence across page reload** | **OK — survived**, byte-identical on a fresh wasm instance | reread 83 ms, **1210 MB/s** |
| **3. sync IO from pthread** (main() worker + spawned thread) | OK — all sync `open/write/read` on the `PROXY_TO_PTHREAD` worker | — |
| **3. sync handle on browser MAIN thread** | correctly **unavailable** | `FileSystemFileHandle.createSyncAccessHandle` is **not a function** on the window; present + working in a dedicated Worker |
| **4. two pthreads writing distinct files** | OK — both verified, no cross-file corruption | 2×24 MB, per-thread 45–90 ms; wall 0.8–1.2 s (spawn/join + post-verify, not IO) |

Persistence is the load-bearing receipt: **run A** (`?fresh=1`) wiped OPFS then wrote
`/opfs/throughput.bin`; **run B** (plain reload → brand-new wasm module, fresh linear
memory) re-read that file from OPFS and it was byte-identical. WasmFS's in-RAM state is
gone across the reload, so the bytes genuinely came from OPFS storage.

Test 3 is the crux of the "coupled decision": because `main()` runs on the
`-sPROXY_TO_PTHREAD` worker, every file op is a **synchronous WasmFS OPFS op on a
worker/pthread** — exactly what OPFS sync access handles require and what ADR-003's
"IO is worker-side sync-handle, not main-thread JSPI" invariant assumes. The negative
half proves the coupling from the other side: on the browser **main** thread the sync
handle API is not even exposed, so the design's insistence that main() live on a worker
is a hard requirement, now demonstrated rather than asserted.

## Emscripten gotchas / bugs hit (emcc 6.0.5)

1. **Two benign `"Blocking on the main thread is very dangerous"` console errors** per
   run (Emscripten pthreads note). **Non-fatal** — every byte verified identical. They
   track pthread/worker spawn coordination, not IO: note the concurrency **wall time
   (0.8–1.2 s) dwarfs the per-thread IO (45–90 ms)** — that gap is on-demand Worker
   creation for the two `pthread_create`s (pool warm-up), not OPFS. **M7 implication:**
   do OPFS IO on **long-lived** threads spawned once at startup (Blender already runs
   `main()`/save on the persistent proxied worker), never spin a thread per file op.
2. **`createSyncAccessHandle` is entirely absent on the window** (a `TypeError: not a
   function`), not an `InvalidStateError` throw. Feature-detect by presence, and never
   attempt sync-handle IO from main-thread JS.
3. No mount/threading surprises: `wasmfs_create_opfs_backend()` returned non-null and
   `wasmfs_create_directory("/opfs")` returned 0 on the proxied worker; `-sPTHREAD_POOL_SIZE=8`
   comfortably covered the OPFS backend thread + 2 concurrent workers.

## Remaining M7 unknowns (document, do not automate)

1. **File System Access pickers need a user gesture.** `showOpenFilePicker` /
   `showSaveFilePicker` are main-thread, async, and gesture-gated — **cannot** be
   auto-driven, so they are out of scope for an automated probe. The design
   (`m7-files-prep.md` §3): run the picker on the JS main thread, `postMessage` the
   finished bytes to the worker, keep Blender's stack synchronous. Still needs a
   gesture-driven manual/e2e check in M7.
2. **Cross-browser matrix untested.** Only Chromium 148 here. OPFS **sync access
   handles in workers** ship in current Chrome/Edge/Firefox/Safari, but
   `showSaveFilePicker`/`showOpenFilePicker` are **Chromium-only** → Firefox/Safari must
   use the `<input type=file>` + Blob-download fallback (`m7-files-prep.md` §3). Confirm
   the OPFS substrate itself on Firefox/Safari during M7.
3. **`-sJSPI` co-existence.** This probe ran without JSPI; the M4 windowed binary links
   it. Expected safe (OPFS IO never suspends, ADR-003), but re-run an OPFS round-trip in
   the full JSPI-enabled binary to confirm no interaction.
4. **Persistence durability / eviction.** OPFS is best-effort; under storage pressure an
   origin can be evicted. Call `navigator.storage.persist()` (may prompt) for the
   project store; measure real quota headroom vs .blend sizes. Autosave/recovery
   (`.recovery/quit.blend`, `m7-files-prep.md` §2b) should assume eviction is possible.
5. **End-to-end `BLO_write_file` → OPFS in a tab.** `m7-files-prep.md` §1 already proved
   `BLO_*` save/open on the wasm binary via NODERAWFS (node). This probe proves the OPFS
   substrate. The remaining step — pointing Blender's synchronous writefile/readfile at
   the `/opfs` mount in the *browser* build — is M7 T1/T2 and blocks on the M4 shell; it
   was not exercised here (no full Blender binary in this probe).

## Reproduce

```
harness/buildwrap.sh sandbox/opfs-probe/build.sh          # emcc 6.0.5, ~2 s
python3 sandbox/opfs-probe/web/server.py 8131             # COOP/COEP
#  open http://localhost:8131/?fresh=1   (clean first load: PERSIST-FRESH)
#  reload http://localhost:8131/         (PERSIST-SURVIVED OK)
```
Results land in the page log (and `window.opfsResults` / `document.title`); look for
`MOUNT OK`, `THROUGHPUT OK`, `PERSIST-SURVIVED OK`, `CONCURRENT OK`, `WORKER-SYNC OK`,
`MAINTHREAD-SYNC BLOCKED (expected)`, `PROBE-DONE`.

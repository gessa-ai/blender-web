// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// stage1-loader.js - deferred STAGE-1 streamer for the staged deploy bundle.
//
// The build preloads ONLY stage-0 (the baked manifest was rewritten by
// stage_pack.py: stage-0 files carry real bytes, every deferred file is a
// zero-length placeholder so its DIRECTORY exists after preload - post-boot mkdir
// is impossible under the 0555 /bw mount, recon in notes/m8-staged-deploy.md). This
// script runs AFTER first pixels and streams the rest into the SAME live WasmFS via
// FS.writeFile (writing into existing dirs / overwriting placeholders both work
// post-boot; verified). It never blocks boot: it self-schedules off first pixels.
//
// Contract preserved: this is an ADDITIVE bundle-only script injected after
// boot-windowed.js; it touches no shell contract, no argv, no canvas, no gate path.
// It exposes window.__bwStage1 (honest progress state) and window.__bwStage1Load()
// (idempotent manual trigger, used by the deferred-asset proof).

"use strict";
(function () {
  const BIN_PREFIX = "/bin/";
  const YIELD_EVERY = 24;              // files per tick, so the WM loop keeps breathing
  const state = {
    phase: "idle",                    // idle -> fetching -> writing -> done | error
    filesTotal: 0, filesDone: 0,
    bytesTotal: 0, bytesDone: 0,
    startedAt: 0, fetchedAt: 0, doneAt: 0,
    error: null,
  };
  window.__bwStage1 = state;

  function log(s) { try { console.log("[stage1] " + s); } catch (_) {} }
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  let started = false;
  async function run() {
    if (started) return state;
    started = true;
    const mod = window.__bwModule;
    if (!mod || !mod.FS) { state.phase = "error"; state.error = "no __bwModule.FS"; log(state.error); return state; }
    const FS = mod.FS;
    state.phase = "fetching";
    state.startedAt = performance.now();
    let man, buf;
    try {
      man = await (await fetch(BIN_PREFIX + "stage1-manifest.json")).json();
      const resp = await fetch(BIN_PREFIX + "stage1.data");
      buf = new Uint8Array(await resp.arrayBuffer());
    } catch (e) {
      state.phase = "error"; state.error = "fetch: " + (e && e.message || e); log(state.error); return state;
    }
    state.fetchedAt = performance.now();
    state.filesTotal = man.files.length;
    state.bytesTotal = man.total_bytes || buf.length;
    log("fetched stage1.data " + buf.length + " B / " + state.filesTotal + " files in " +
        (state.fetchedAt - state.startedAt).toFixed(0) + " ms; unpacking...");
    state.phase = "writing";
    let i = 0;
    for (const f of man.files) {
      try {
        // subarray = view (no copy); writeFile copies the slice into the live FS.
        FS.writeFile(f.filename, buf.subarray(f.start, f.end));
        state.bytesDone += (f.end - f.start);
      } catch (e) {
        // Do not abort the whole stream on one file; record and continue.
        if (!state.error) state.error = "write " + f.filename + ": " + (e && e.message || e);
      }
      state.filesDone = ++i;
      if (i % YIELD_EVERY === 0) await sleep(0); // let the WM worker + paint proceed
    }
    buf = null; // release the 37 MiB ArrayBuffer for GC
    state.doneAt = performance.now();
    state.phase = state.error ? "done-with-errors" : "done";
    log("unpacked " + state.filesDone + "/" + state.filesTotal + " files (" +
        (state.bytesDone / 1048576).toFixed(1) + " MiB) in " +
        (state.doneAt - state.fetchedAt).toFixed(0) + " ms" +
        (state.error ? " [first error: " + state.error + "]" : ""));
    return state;
  }
  // manual, idempotent trigger (deferred-asset proof / on-demand callers)
  window.__bwStage1Load = run;

  // ?stage1=manual (or window.__BW_STAGE1_MANUAL) disables the auto-schedule so a
  // rig can observe the pre-stream placeholder state and time the stream itself.
  let manual = (typeof window.__BW_STAGE1_MANUAL !== "undefined") && window.__BW_STAGE1_MANUAL;
  try { if (new URLSearchParams(location.search).get("stage1") === "manual") manual = true; } catch (_) {}
  if (manual) { state.phase = "manual"; log("auto-schedule disabled (?stage1=manual)"); return; }

  // Auto-schedule: start streaming once the module is up AND first pixels have
  // composited (boot-windowed.js adds .bw-hidden to #loader on presentBackbuffer),
  // so time-to-first-pixels is never charged for stage-1. Fallbacks bound the wait.
  function ready() {
    const loader = document.getElementById("loader");
    const firstPixels = loader && (loader.classList.contains("bw-hidden") || loader.classList.contains("bw-gone"));
    return window.__bwModule && window.__bwModule.FS && firstPixels;
  }
  (async function schedule() {
    // Bounded wait for module (never block the page).
    for (let i = 0; i < 600 && !(window.__bwModule && window.__bwModule.FS); i++) await sleep(200);
    // Wait for first pixels, but do not wait forever (gate mode hides the loader
    // immediately; the normal path hides it on presentBackbuffer or a 2.5s settle).
    for (let i = 0; i < 100 && !ready(); i++) await sleep(100);
    // A small extra breath so the first interactive frames are not contended.
    await sleep(500);
    run();
  })();
})();

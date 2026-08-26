// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// stage1-loader.js - deferred STAGE-1 streamer for the staged deploy bundle.
//
// The build preloads ONLY stage-0 (the baked manifest was rewritten by
// stage_pack.py: stage-0 files carry real bytes; deferred files are absent except
// for zero-byte filenames whose one-time startup directory discovery must match
// the monolith. The original file-packager glue still pre-creates the complete
// DIRECTORY tree - post-boot mkdir is impossible under the 0555 /bw mount, recon
// in notes/m8-staged-deploy.md. This script runs AFTER first pixels and streams
// the rest into the SAME live WasmFS via FS.writeFile (creating or overwriting
// files inside those existing dirs is verified). It never blocks boot: it
// self-schedules off first pixels.
//
// Contract preserved: this is an ADDITIVE bundle-only script injected after
// boot-windowed.js; it touches no shell contract, no argv, no canvas, no gate path.
// It exposes window.__bwStage1 (honest progress state) and window.__bwStage1Load()
// (idempotent manual trigger, used by the deferred-asset proof).

"use strict";
(function () {
  const BIN_PREFIX = "/bin/";
  const YIELD_EVERY = 24;              // files per tick, so the WM loop keeps breathing
  const MAX_ATTEMPTS = 3;              // initial transfer plus two bounded automatic retries
  const state = {
    phase: "idle",                    // idle -> fetching -> writing -> done | error
    filesTotal: 0, filesDone: 0,
    bytesTotal: 0, bytesDone: 0,
    startedAt: 0, fetchedAt: 0, doneAt: 0,
    attempt: 0, maxAttempts: MAX_ATTEMPTS, retryable: false,
    error: null, visible: false, visibleLabel: "", visiblePhases: [],
  };
  window.__bwStage1 = state;

  function log(s) { try { console.log("[stage1] " + s); } catch (_) {} }
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const queryDevHooks = window.__bwDevHooksAllowed === true;
  const gateMode = document.body.classList.contains("bw-gate") ||
    (queryDevHooks && new URLSearchParams(location.search).has("gate"));
  let progressEl = null;
  let hideTimer = 0;
  let lastProgressAt = 0;
  let lastProgressLabel = "";
  function mb(n) { return (n / 1048576).toFixed(1); }
  function updateVisibleProgress(label, done, total, finished) {
    if (gateMode) return;
    const now = performance.now();
    if (progressEl && !finished && done < total && label === lastProgressLabel &&
        now - lastProgressAt < 50) return;
    lastProgressAt = now;
    lastProgressLabel = label;
    if (!progressEl) {
      progressEl = document.createElement("div");
      progressEl.id = "bw-stage-progress";
      progressEl.setAttribute("role", "status");
      progressEl.setAttribute("aria-live", "polite");
      Object.assign(progressEl.style, {
        position: "fixed", left: "50%", bottom: "22px", zIndex: "30",
        transform: "translateX(-50%)", pointerEvents: "none",
        padding: "8px 12px", borderRadius: "6px",
        color: "#d6dce4", background: "rgba(18, 22, 30, 0.92)",
        boxShadow: "0 2px 12px rgba(0, 0, 0, 0.45)",
        font: "11px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace",
        letterSpacing: ".02em", opacity: "1", transition: "opacity .35s ease",
      });
      document.body.appendChild(progressEl);
    }
    const counts = total > 0 ? " · " + mb(done) + " / " + mb(total) + " MB" : "";
    progressEl.textContent = label + counts;
    progressEl.dataset.phase = state.phase;
    progressEl.dataset.bytesDone = String(done);
    progressEl.dataset.bytesTotal = String(total);
    progressEl.style.opacity = "1";
    state.visibleLabel = progressEl.textContent;
    state.visible = true;
    if (!state.visiblePhases.includes(label)) state.visiblePhases.push(label);
    if (finished) {
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => {
        if (!progressEl) return;
        progressEl.style.opacity = "0";
        state.visible = false;
        setTimeout(() => { if (progressEl) { progressEl.remove(); progressEl = null; } }, 400);
      }, 2200);
    }
  }

  function validateStageManifest(man) {
    if (!man || !Number.isSafeInteger(man.total_bytes) || man.total_bytes < 0 ||
        !Array.isArray(man.files)) {
      throw new Error("stage1 manifest shape is invalid");
    }
    const expected = man.total_bytes;
    let cursor = 0;
    for (let i = 0; i < man.files.length; i++) {
      const f = man.files[i];
      if (!f || !Number.isSafeInteger(f.start) || !Number.isSafeInteger(f.end) ||
          f.start < 0 || f.end < f.start || f.end > expected) {
        throw new Error("stage1 manifest span " + i + " is out of bounds");
      }
      if (f.start !== cursor) {
        throw new Error("stage1 manifest span " + i + " starts at " + f.start +
                        " instead of " + cursor);
      }
      cursor = f.end;
    }
    if (cursor !== expected) {
      throw new Error("stage1 manifest spans end at " + cursor + " instead of " + expected);
    }
    return expected;
  }

  async function fetchStageData(expected) {
    const resp = await fetch(BIN_PREFIX + "stage1.data");
    if (!resp.ok) throw new Error("stage1.data HTTP " + resp.status);
    state.bytesTotal = expected;
    state.bytesDone = 0;
    updateVisibleProgress("Downloading assets", 0, expected, false);
    if (!resp.body || !resp.body.getReader || !expected) {
      const fallback = new Uint8Array(await resp.arrayBuffer());
      if (fallback.length !== expected) {
        throw new Error("stage1.data size " + fallback.length + " != " + expected);
      }
      state.bytesDone = fallback.length;
      updateVisibleProgress("Downloading assets", fallback.length, expected, false);
      return fallback;
    }
    const out = new Uint8Array(expected);
    const reader = resp.body.getReader();
    let offset = 0;
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      if (offset + value.length > out.length) throw new Error("stage1.data exceeds manifest size");
      out.set(value, offset);
      offset += value.length;
      state.bytesDone = offset;
      updateVisibleProgress("Downloading assets", offset, expected, false);
    }
    if (offset !== expected) throw new Error("stage1.data size " + offset + " != " + expected);
    return out;
  }

  function beginAttempt(attempt) {
    clearTimeout(hideTimer);
    hideTimer = 0;
    state.phase = "fetching";
    state.filesTotal = 0;
    state.filesDone = 0;
    state.bytesTotal = 0;
    state.bytesDone = 0;
    state.startedAt = performance.now();
    state.fetchedAt = 0;
    state.doneAt = 0;
    state.attempt = attempt;
    state.retryable = false;
    state.error = null;
  }

  async function runAttempt(attempt) {
    beginAttempt(attempt);
    const mod = window.__bwModule;
    if (!mod || !mod.FS) throw new Error("no __bwModule.FS");
    const FS = mod.FS;
    const man = await (await fetch(BIN_PREFIX + "stage1-manifest.json")).json();
    const expected = validateStageManifest(man);
    let buf = await fetchStageData(expected);
    state.fetchedAt = performance.now();
    state.filesTotal = man.files.length;
    state.bytesTotal = expected;
    log("fetched stage1.data " + buf.length + " B / " + state.filesTotal + " files in " +
        (state.fetchedAt - state.startedAt).toFixed(0) + " ms; unpacking...");
    state.phase = "writing";
    state.bytesDone = 0;
    updateVisibleProgress("Installing assets", 0, state.bytesTotal, false);
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
      updateVisibleProgress("Installing assets", state.bytesDone, state.bytesTotal, false);
      if (i % YIELD_EVERY === 0) await sleep(0); // let the WM worker + paint proceed
    }
    buf = null; // release the 37 MiB ArrayBuffer for GC
    state.doneAt = performance.now();
    state.phase = state.error ? "done-with-errors" : "done";
    updateVisibleProgress(state.error ? "Assets installed with errors" : "Assets ready",
                          state.bytesDone, state.bytesTotal, true);
    log("unpacked " + state.filesDone + "/" + state.filesTotal + " files (" +
        (state.bytesDone / 1048576).toFixed(1) + " MiB) in " +
        (state.doneAt - state.fetchedAt).toFixed(0) + " ms" +
        (state.error ? " [first error: " + state.error + "]" : ""));
    return state;
  }

  async function runWithRetries() {
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
      try {
        return await runAttempt(attempt);
      } catch (e) {
        const detail = e && e.message ? e.message : String(e);
        state.error = detail === "no __bwModule.FS" ? detail : "fetch: " + detail;
        state.retryable = true;
        if (attempt < MAX_ATTEMPTS) {
          state.phase = "retrying";
          updateVisibleProgress("Retrying assets", state.bytesDone, state.bytesTotal, false);
          log(state.error + "; retrying attempt " + (attempt + 1) + "/" + MAX_ATTEMPTS);
          // Yield one microtask so concurrent callers can observe the honest retry state.
          await Promise.resolve();
          continue;
        }
        state.phase = "error";
        updateVisibleProgress("Assets unavailable - retry available",
                              state.bytesDone, state.bytesTotal, false);
        log(state.error + "; automatic retry limit reached");
        return state;
      }
    }
    return state;
  }

  let inFlight = null;
  function clearInFlight(operation) {
    if (inFlight === operation) inFlight = null;
  }
  function run() {
    if (state.phase === "done" || state.phase === "done-with-errors") {
      return Promise.resolve(state);
    }
    if (inFlight) return inFlight;
    const operation = runWithRetries();
    inFlight = operation;
    operation.then(() => clearInFlight(operation), () => clearInFlight(operation));
    return operation;
  }
  // manual, idempotent trigger (deferred-asset proof / on-demand callers)
  window.__bwStage1Load = run;

  // A trusted local rig may set window.__BW_STAGE1_MANUAL with addInitScript. The
  // query form is a development-shell hook and is ignored by the public copy,
  // just like gate/keepalive/Python/argv diagnostics.
  let manual = window.__BW_STAGE1_MANUAL === true;
  try {
    if (queryDevHooks && new URLSearchParams(location.search).get("stage1") === "manual") manual = true;
  } catch (_) {}
  if (manual) { state.phase = "manual"; log("auto-schedule disabled by trusted verifier"); return; }

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

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
// the rest into the SAME live WasmFS. Each completed file is buffered separately,
// written beside its final path while that 0555 parent is temporarily owner-writable,
// and atomically renamed into place only after the response is complete. WasmFS
// rejects cross-directory /tmp -> /bw renames, so same-directory publication is
// part of the contract, not an optimization. This bounds transient JS retention
// without publishing corrupt partial transfers.
// It never blocks boot: it
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
  const MAX_BUFFERED_FILE_BYTES = 16 * 1024 * 1024;
  const MAX_STREAM_CHUNK_BYTES = 16 * 1024 * 1024;
  const MAX_TRANSIENT_BYTES = MAX_BUFFERED_FILE_BYTES + MAX_STREAM_CHUNK_BYTES;
  const state = {
    phase: "idle",                    // idle -> fetching -> writing -> done | error
    filesTotal: 0, filesDone: 0,
    bytesTotal: 0, bytesFetched: 0, bytesDone: 0,
    bufferLimitBytes: MAX_BUFFERED_FILE_BYTES,
    largestFileBytes: 0, bufferedBytes: 0, peakBufferedBytes: 0,
    streamChunkLimitBytes: MAX_STREAM_CHUNK_BYTES,
    chunkBytes: 0, peakChunkBytes: 0,
    transientLimitBytes: MAX_TRANSIENT_BYTES, peakTransientBytes: 0,
    writableDirectoryCount: 0,
    bootstrapTotal: 0, bootstrapDone: 0, fontRefresh: "not-needed",
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

  function manifestPath(filename, index) {
    if (typeof filename !== "string" || filename.length < 2 || filename.length > 4096 ||
        filename[0] !== "/" || filename.includes("\\") || filename.includes("\0")) {
      throw new Error("stage1 manifest path " + index + " is invalid");
    }
    const parts = filename.slice(1).split("/");
    if (parts.some((part) => !part || part === "." || part === "..")) {
      throw new Error("stage1 manifest path " + index + " is unsafe");
    }
    const slash = filename.lastIndexOf("/");
    return {parent: filename.slice(0, slash) || "/", basename: filename.slice(slash + 1)};
  }

  function validateStageManifest(man) {
    if (!man || !Number.isSafeInteger(man.total_bytes) || man.total_bytes < 0 ||
        !Array.isArray(man.files)) {
      throw new Error("stage1 manifest shape is invalid");
    }
    const expected = man.total_bytes;
    const seen = new Set();
    const spans = new Map();
    let cursor = 0;
    let largestFileBytes = 0;
    for (let i = 0; i < man.files.length; i++) {
      const f = man.files[i];
      if (!f || !Number.isSafeInteger(f.start) || !Number.isSafeInteger(f.end) ||
          f.start < 0 || f.end < f.start || f.end > expected) {
        throw new Error("stage1 manifest span " + i + " is out of bounds");
      }
      manifestPath(f.filename, i);
      if (seen.has(f.filename)) {
        throw new Error("stage1 manifest path " + i + " is duplicate");
      }
      seen.add(f.filename);
      if (f.start !== cursor) {
        throw new Error("stage1 manifest span " + i + " starts at " + f.start +
                        " instead of " + cursor);
      }
      const fileBytes = f.end - f.start;
      if (fileBytes > MAX_BUFFERED_FILE_BYTES) {
        throw new Error("stage1 manifest span " + i + " is " + fileBytes +
                        " bytes; buffer limit is " + MAX_BUFFERED_FILE_BYTES);
      }
      largestFileBytes = Math.max(largestFileBytes, fileBytes);
      spans.set(f.filename, fileBytes);
      cursor = f.end;
    }
    if (cursor !== expected) {
      throw new Error("stage1 manifest spans end at " + cursor + " instead of " + expected);
    }
    const bootstrap = man.bootstrap === undefined ? [] : man.bootstrap;
    if (!Array.isArray(bootstrap) || bootstrap.length > 2) {
      throw new Error("stage1 bootstrap manifest is invalid");
    }
    const bootstrapSeen = new Set();
    for (let i = 0; i < bootstrap.length; i++) {
      const row = bootstrap[i];
      if (!row || row.action !== "reload-interface-fonts" ||
          !Number.isSafeInteger(row.stage0_bytes) || row.stage0_bytes <= 0 ||
          !Number.isSafeInteger(row.restored_bytes) || row.restored_bytes <= 0 ||
          !/^[0-9a-f]{64}$/.test(row.stage0_sha256) ||
          !/^[0-9a-f]{64}$/.test(row.restored_sha256) ||
          spans.get(row.filename) !== row.restored_bytes ||
          bootstrapSeen.has(row.filename)) {
        throw new Error("stage1 bootstrap entry " + i + " is invalid");
      }
      bootstrapSeen.add(row.filename);
    }
    return {expected, largestFileBytes, bootstrap};
  }

  function updateTransientPeak() {
    const transient = state.bufferedBytes + state.chunkBytes;
    state.peakTransientBytes = Math.max(state.peakTransientBytes, transient);
    if (transient > MAX_TRANSIENT_BYTES) {
      throw new Error("stage1 transient bytes " + transient +
                      " exceed limit " + MAX_TRANSIENT_BYTES);
    }
  }

  function setBufferedBytes(bytes) {
    if (bytes > MAX_BUFFERED_FILE_BYTES) {
      throw new Error("stage1 buffered bytes " + bytes +
                      " exceed limit " + MAX_BUFFERED_FILE_BYTES);
    }
    state.bufferedBytes = bytes;
    state.peakBufferedBytes = Math.max(state.peakBufferedBytes, bytes);
    updateTransientPeak();
  }

  function setChunkBytes(bytes) {
    state.chunkBytes = bytes;
    state.peakChunkBytes = Math.max(state.peakChunkBytes, bytes);
    if (bytes > MAX_STREAM_CHUNK_BYTES) {
      throw new Error("stage1 response chunk " + bytes +
                      " exceeds limit " + MAX_STREAM_CHUNK_BYTES);
    }
    updateTransientPeak();
  }

  function temporaryName(generation, index, filename) {
    const path = manifestPath(filename, index);
    return path.parent + "/." + path.basename + ".bw-stage1-" + generation + "-" + index;
  }

  function makeDirectoriesWritable(FS, files) {
    const originalModes = new Map();
    try {
      for (let index = 0; index < files.length; index++) {
        const parent = manifestPath(files[index].filename, index).parent;
        if (originalModes.has(parent)) continue;
        const mode = FS.stat(parent).mode;
        originalModes.set(parent, mode);
        FS.chmod(parent, mode | 0o300);
      }
    }
    catch (error) {
      restoreDirectoryModes(FS, originalModes);
      throw error;
    }
    return originalModes;
  }

  function restoreDirectoryModes(FS, originalModes) {
    let failure = null;
    for (const [directory, mode] of originalModes) {
      try { FS.chmod(directory, mode); }
      catch (error) { if (!failure) failure = error; }
    }
    if (failure) throw failure;
  }

  function cleanupTemporaryFiles(FS, temporaryFiles) {
    let failure = null;
    for (const filename of temporaryFiles) {
      if (!filename) continue;
      try { FS.unlink(filename); }
      catch (e) { if (!failure) failure = e; }
    }
    temporaryFiles.length = 0;
    if (failure) throw failure;
  }

  async function stageFile(FS, f, index, generation, bytes, temporaryFiles) {
    const filename = temporaryName(generation, index, f.filename);
    FS.writeFile(filename, bytes);
    temporaryFiles.push(filename);
    if ((index + 1) % YIELD_EVERY === 0) await sleep(0);
  }

  async function sha256Hex(bytes) {
    if (!globalThis.crypto?.subtle) throw new Error("Web Crypto unavailable for bootstrap");
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    return Array.from(digest, (value) => value.toString(16).padStart(2, "0")).join("");
  }

  async function validateBootstrapAssets(FS, bootstrap) {
    state.bootstrapTotal = bootstrap.length;
    state.bootstrapDone = 0;
    state.fontRefresh = bootstrap.length ? "pending" : "not-needed";
    for (const row of bootstrap) {
      const stage0 = FS.readFile(row.filename);
      setBufferedBytes(stage0.length);
      let digest;
      try { digest = await sha256Hex(stage0); }
      finally { setBufferedBytes(0); }
      if (stage0.length !== row.stage0_bytes || digest !== row.stage0_sha256) {
        throw new Error("Stage-0 bootstrap identity mismatch: " + row.filename);
      }
    }
  }

  async function refreshBootstrapAssets(FS, bootstrap) {
    for (const row of bootstrap) {
      const restored = FS.readFile(row.filename);
      setBufferedBytes(restored.length);
      let digest;
      try { digest = await sha256Hex(restored); }
      finally { setBufferedBytes(0); }
      if (restored.length !== row.restored_bytes || digest !== row.restored_sha256) {
        throw new Error("restored bootstrap identity mismatch: " + row.filename);
      }
    }
    if (!bootstrap.length) return;
    const bridge = window.BWFileBridge;
    if (!bridge || typeof bridge.refreshInterfaceFonts !== "function") {
      throw new Error("interface-font refresh bridge unavailable");
    }
    const ready = await bridge.ready();
    if (!ready) throw new Error("interface-font refresh daemon unavailable");
    const ack = await bridge.refreshInterfaceFonts();
    if (!ack?.ok || !ack.fontBytes || typeof ack.fontBytes !== "object") {
      throw new Error("interface-font refresh rejected");
    }
    for (const row of bootstrap) {
      if (ack.fontBytes[row.filename] !== row.restored_bytes) {
        throw new Error("interface-font refresh rejected: " + row.filename);
      }
    }
    state.bootstrapDone = bootstrap.length;
    state.fontRefresh = "done";
  }

  async function fetchAndStage(FS, man, expected, generation, temporaryFiles) {
    const resp = await fetch(BIN_PREFIX + "stage1.data");
    if (!resp.ok) throw new Error("stage1.data HTTP " + resp.status);
    state.bytesTotal = expected;
    state.bytesFetched = 0;
    state.bytesDone = 0;
    updateVisibleProgress("Downloading assets", 0, expected, false);
    if (!resp.body || !resp.body.getReader || !expected) {
      if (expected > MAX_BUFFERED_FILE_BYTES) {
        throw new Error("stage1.data streaming response required for " + expected +
                        " bytes; fallback limit is " + MAX_BUFFERED_FILE_BYTES);
      }
      const fallback = new Uint8Array(await resp.arrayBuffer());
      if (fallback.length !== expected) {
        throw new Error("stage1.data size " + fallback.length + " != " + expected);
      }
      setBufferedBytes(fallback.length);
      for (let index = 0; index < man.files.length; index++) {
        const f = man.files[index];
        await stageFile(FS, f, index, generation,
                        fallback.subarray(f.start, f.end), temporaryFiles);
      }
      setBufferedBytes(0);
      state.bytesFetched = fallback.length;
      updateVisibleProgress("Downloading assets", fallback.length, expected, false);
      return;
    }
    const reader = resp.body.getReader();
    let offset = 0;
    let fileIndex = 0;
    let fileBuffer = null;
    let fileOffset = 0;
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      setChunkBytes(value.length);
      if (offset + value.length > expected) throw new Error("stage1.data exceeds manifest size");
      let chunkOffset = 0;
      while (chunkOffset < value.length) {
        if (fileIndex >= man.files.length) throw new Error("stage1.data exceeds manifest spans");
        const f = man.files[fileIndex];
        const fileBytes = f.end - f.start;
        if (fileBuffer === null) {
          fileBuffer = new Uint8Array(fileBytes);
          fileOffset = 0;
          setBufferedBytes(fileBytes);
        }
        const take = Math.min(fileBytes - fileOffset, value.length - chunkOffset);
        fileBuffer.set(value.subarray(chunkOffset, chunkOffset + take), fileOffset);
        fileOffset += take;
        chunkOffset += take;
        if (fileOffset === fileBytes) {
          await stageFile(FS, f, fileIndex, generation, fileBuffer, temporaryFiles);
          fileBuffer = null;
          fileOffset = 0;
          setBufferedBytes(0);
          fileIndex += 1;
        }
      }
      offset += value.length;
      state.bytesFetched = offset;
      updateVisibleProgress("Downloading assets", offset, expected, false);
      setChunkBytes(0);
    }
    if (offset !== expected) throw new Error("stage1.data size " + offset + " != " + expected);
    while (fileIndex < man.files.length &&
           man.files[fileIndex].end === man.files[fileIndex].start) {
      await stageFile(FS, man.files[fileIndex], fileIndex, generation,
                      new Uint8Array(0), temporaryFiles);
      fileIndex += 1;
    }
    if (fileIndex !== man.files.length || fileBuffer !== null) {
      throw new Error("stage1.data did not complete every manifest span");
    }
  }

  function beginAttempt(attempt) {
    clearTimeout(hideTimer);
    hideTimer = 0;
    state.phase = "fetching";
    state.filesTotal = 0;
    state.filesDone = 0;
    state.bytesTotal = 0;
    state.bytesFetched = 0;
    state.bytesDone = 0;
    state.largestFileBytes = 0;
    state.bufferedBytes = 0;
    state.chunkBytes = 0;
    state.writableDirectoryCount = 0;
    state.bootstrapTotal = 0;
    state.bootstrapDone = 0;
    state.fontRefresh = "not-needed";
    if (attempt === 1) {
      state.peakBufferedBytes = 0;
      state.peakChunkBytes = 0;
      state.peakTransientBytes = 0;
    }
    state.startedAt = performance.now();
    state.fetchedAt = 0;
    state.doneAt = 0;
    state.attempt = attempt;
    state.retryable = false;
    state.error = null;
  }

  let stagingGeneration = 0;
  async function runAttempt(attempt) {
    beginAttempt(attempt);
    const mod = window.__bwModule;
    if (!mod || !mod.FS) throw new Error("no __bwModule.FS");
    const FS = mod.FS;
    const man = await (await fetch(BIN_PREFIX + "stage1-manifest.json")).json();
    const contract = validateStageManifest(man);
    const expected = contract.expected;
    const temporaryFiles = [];
    const generation = ++stagingGeneration;
    state.filesTotal = man.files.length;
    state.bytesTotal = expected;
    state.largestFileBytes = contract.largestFileBytes;
    let originalModes = new Map();
    try {
      await validateBootstrapAssets(FS, contract.bootstrap);
      originalModes = makeDirectoriesWritable(FS, man.files);
      state.writableDirectoryCount = originalModes.size;
      await fetchAndStage(FS, man, expected, generation, temporaryFiles);
    } catch (e) {
      setChunkBytes(0);
      setBufferedBytes(0);
      let cleanupError = null;
      let modeError = null;
      try { cleanupTemporaryFiles(FS, temporaryFiles); }
      catch (error) { cleanupError = error; }
      // Permission restoration is mandatory even when temporary cleanup fails.
      try { restoreDirectoryModes(FS, originalModes); }
      catch (error) { modeError = error; }
      if (cleanupError || modeError) {
        throw new Error((e && e.message || e) +
                        (cleanupError ? "; temporary cleanup: " +
                          (cleanupError && cleanupError.message || cleanupError) : "") +
                        (modeError ? "; permission restore: " +
                          (modeError && modeError.message || modeError) : ""));
      }
      throw e;
    }
    state.fetchedAt = performance.now();
    log("fetched stage1.data " + expected + " B / " + state.filesTotal + " files in " +
        (state.fetchedAt - state.startedAt).toFixed(0) + " ms; unpacking...");
    state.phase = "writing";
    state.bytesDone = 0;
    updateVisibleProgress("Installing assets", 0, state.bytesTotal, false);
    for (let index = 0; index < man.files.length; index++) {
      const f = man.files[index];
      try {
        FS.rename(temporaryFiles[index], f.filename);
        temporaryFiles[index] = null;
        state.bytesDone += (f.end - f.start);
      } catch (e) {
        // Do not abort the whole stream on one file; record and continue.
        if (!state.error) state.error = "write " + f.filename + ": " + (e && e.message || e);
      }
      state.filesDone = index + 1;
      updateVisibleProgress("Installing assets", state.bytesDone, state.bytesTotal, false);
      if ((index + 1) % YIELD_EVERY === 0) await sleep(0); // let the WM worker + paint proceed
    }
    try { cleanupTemporaryFiles(FS, temporaryFiles); }
    catch (cleanupError) {
      if (!state.error) state.error = "temporary cleanup: " +
        (cleanupError && cleanupError.message || cleanupError);
    }
    try { restoreDirectoryModes(FS, originalModes); }
    catch (modeError) {
      if (!state.error) state.error = "permission restore: " +
        (modeError && modeError.message || modeError);
    }
    if (!state.error) {
      try { await refreshBootstrapAssets(FS, contract.bootstrap); }
      catch (bootstrapError) {
        state.fontRefresh = "error";
        state.error = "bootstrap: " + (bootstrapError && bootstrapError.message || bootstrapError);
      }
    }
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

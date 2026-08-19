// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Profile-only Emscripten post-js for the production wasm-split capture build.
// Binaryen's instrumented module adds __write_profile but Emscripten does not
// expose it on Module. Copy the exact byte stream while the instrumented module
// is alive; the strict finalizer binds these bytes to the same .wasm.orig.

(() => {
  // Binaryen 125's shared in-memory instrumentation uses atomic 32-bit slots
  // (the current Blender profile is 539,532 bytes for 135,449 functions), even
  // though wasm-split --help describes one byte per function. Keep a full MiB
  // below GLOBAL_BASE; the finalizer proves the matching link flag.
  const BW_SPLIT_PROFILE_RESERVE = 1048576;

  Module["bwWriteSplitProfile"] = () => {
    const writeProfile = wasmExports["__write_profile"];
    if (typeof writeProfile !== "function") {
      throw new Error("BW_SPLIT_PROFILE_EXPORT_V1: __write_profile is unavailable");
    }

    const length = Number(writeProfile(0, 0));
    if (!Number.isSafeInteger(length) || length <= 0 || length > BW_SPLIT_PROFILE_RESERVE) {
      throw new Error(
        `BW_SPLIT_PROFILE_EXPORT_V1: invalid length ${length}; reserve=${BW_SPLIT_PROFILE_RESERVE}`,
      );
    }

    const offset = _malloc(length);
    if (!offset) {
      throw new Error(`BW_SPLIT_PROFILE_EXPORT_V1: malloc(${length}) failed`);
    }
    try {
      const actualLength = Number(writeProfile(offset, length));
      if (actualLength !== length) {
        throw new Error(
          `BW_SPLIT_PROFILE_EXPORT_V1: wrote ${actualLength}, expected ${length}`,
        );
      }
      return HEAPU8.slice(offset, offset + length);
    } finally {
      _free(offset);
    }
  };

  Module["bwSplitProfileContract"] = Object.freeze({
    marker: "BW_SPLIT_PROFILE_EXPORT_V1",
    preEntryAttestation: "BW_SPLIT_CAPTURE_PREENTRY_ATTESTATION_V1",
    reserve: BW_SPLIT_PROFILE_RESERVE,
    sharedMainMemory: true,
  });

  const nativeExport = (name) => {
    const value = Module[`_${name}`] || wasmExports?.[name] || wasmRawExports?.[name];
    if (typeof value !== "function") {
      throw new Error(`BW_SPLIT_PROFILE_EXPORT_V1: missing controller export ${name}`);
    }
    return value;
  };
  const read = (name) => Number(nativeExport(name)());
  Module["bwCaptureSplitStatus"] = () => ({
    phase: read("BW_web_split_phase"),
    requestGeneration: read("BW_web_split_request_generation"),
    parkedGeneration: read("BW_web_split_parked_generation"),
    preparedGeneration: read("BW_web_split_prepared_generation"),
    appliedGeneration: read("BW_web_split_applied_generation"),
    pageReadyGeneration: read("BW_web_split_page_ready_generation"),
    resumedGeneration: read("BW_web_split_resumed_generation"),
    errorGeneration: read("BW_web_split_error_generation"),
    offendingGeneration: read("BW_web_split_offending_generation"),
    errorCode: read("BW_web_split_error_code"),
    targetThreads: read("BW_web_split_target_threads"),
    activeThreads: read("BW_web_split_active_threads"),
    nativeReady: read("BW_web_split_native_ready"),
    openexrThreads: read("BW_web_split_openexr_threads"),
    oiioThreads: read("BW_web_split_oiio_threads"),
    applyOpenexrSet: read("BW_web_split_apply_openexr_set"),
    applyOpenexrThreads: read("BW_web_split_apply_openexr_threads"),
    applyOiioSet: read("BW_web_split_apply_oiio_set"),
    applyOiioThreads: read("BW_web_split_apply_oiio_threads"),
    rollbackOpenexrSet: read("BW_web_split_rollback_openexr_set"),
    rollbackOpenexrThreads: read("BW_web_split_rollback_openexr_threads"),
    rollbackOiioSet: read("BW_web_split_rollback_oiio_set"),
    rollbackOiioThreads: read("BW_web_split_rollback_oiio_threads"),
    reloadRequired: read("BW_web_split_reload_required"),
    preparedWorkers: read("BW_web_split_prepared_workers"),
    preparedAcknowledgements: read("BW_web_split_prepared_acknowledgements"),
    preparedInstances: read("BW_web_split_prepared_instances"),
    preparedLocalInstances: read("BW_web_split_prepared_local_instances"),
    preparedPending: read("BW_web_split_prepared_pending"),
    preparedProtocolErrors: read("BW_web_split_prepared_protocol_errors"),
    preparedStabilizationEpoch: read("BW_web_split_prepared_stabilization_epoch"),
    pageReadyWorkers: read("BW_web_split_page_ready_workers"),
    pageReadyAcknowledgements: read("BW_web_split_page_ready_acknowledgements"),
    pageReadyInstances: read("BW_web_split_page_ready_instances"),
    pageReadyLocalInstances: read("BW_web_split_page_ready_local_instances"),
    pageReadyPending: read("BW_web_split_page_ready_pending"),
    pageReadyProtocolErrors: read("BW_web_split_page_ready_protocol_errors"),
    pageReadyLateWorkers: read("BW_web_split_page_ready_late_workers"),
    pageReadyStabilizationEpoch: read("BW_web_split_page_ready_stabilization_epoch"),
  });
  let captureApplyRequested = false;
  let postApplyProbeCount = 0;
  Module["bwCaptureSplitCall"] = (name, args) => {
    if (name === "BW_web_split_request_apply") captureApplyRequested = true;
    return Number(nativeExport(name)(...args));
  };
  if (ENVIRONMENT_IS_PTHREAD) {
    const baseHandleMessage = handleMessage;
    handleMessage = (event) => {
      const message = event?.data;
      if (message?.cmd === "bwCaptureProbe") {
        postMessage({ cmd: "bwCaptureProbeAck", token: message.token, workerId: message.workerId });
        return;
      }
      return baseHandleMessage(event);
    };
  } else {
    let workerSequence = 0;
    let stabilizationEpoch = 0;
    let captureGeneration = 0;
    let preparedWorkerIds = [];
    let pageReadyAttestation = null;
    const atomicDiagnostics = globalThis.__bwCaptureAtomicDiagnostics ??= [];
    const threadEntryDiagnostics = globalThis.__bwCaptureThreadEntryDiagnostics ??= [];
    Module["bwCaptureAtomicDiagnostics"] = () => atomicDiagnostics.slice();
    Module["bwCaptureThreadEntryDiagnostics"] = () => threadEntryDiagnostics.slice();
    const attach = (worker) => {
      if (!worker.__bwCaptureId) worker.__bwCaptureId = ++workerSequence;
      if (worker.__bwCaptureAttachedHandler === worker.onmessage) return;
      worker.__bwCaptureAttached = true;
      const original = worker.onmessage;
      const attachedHandler = (event) => {
        const message = event?.data;
        if (message?.cmd === "bwCaptureAtomicError") {
          const detail = { ...message.detail, captureWorkerId: worker.__bwCaptureId };
          atomicDiagnostics.push(detail);
          console.error(`BW_SPLIT_CAPTURE_ATOMIC ${JSON.stringify(detail)}`);
          return;
        }
        if (message?.cmd === "bwCaptureThreadEntryError") {
          const detail = { ...message.detail, captureWorkerId: worker.__bwCaptureId };
          threadEntryDiagnostics.push(detail);
          console.error(`BW_SPLIT_CAPTURE_THREAD_ENTRY ${JSON.stringify(detail)}`);
          return;
        }
        if (message?.cmd === "bwCaptureProbeAck") {
          const pending = worker.__bwCapturePending;
          if (!pending || message.workerId !== worker.__bwCaptureId || message.token !== pending.token) {
            if (pending) pending.reject(new Error("BW_SPLIT_PROFILE_EXPORT_V1: rejected worker probe ACK"));
            return;
          }
          worker.__bwCapturePending = null;
          pending.resolve(worker);
          return;
        }
        return original.call(worker, event);
      };
      worker.onmessage = attachedHandler;
      worker.__bwCaptureAttachedHandler = attachedHandler;
    };
    const originalLoadWasmModuleToWorker = PThread.loadWasmModuleToWorker;
    PThread.loadWasmModuleToWorker = (worker) => {
      // Assign the stable ID first. The Emscripten loader replaces onmessage,
      // so call it before synchronously attaching our observer to that exact
      // handler. Its promise resolves from cmd3, which startWorker posts before
      // draining queued cmd2/application-entry work.
      if (!worker.__bwCaptureId) worker.__bwCaptureId = ++workerSequence;
      worker.__bwCaptureLoadState = "pending";
      worker.__bwCaptureLoadError = null;
      const loading = originalLoadWasmModuleToWorker(worker);
      attach(worker);
      const tracked = Promise.resolve(loading).then((loadedWorker) => {
        worker.__bwCaptureLoadState = "ready-before-entry";
        worker.__bwCaptureLoadGeneration = captureGeneration;
        return loadedWorker;
      }, (error) => {
        worker.__bwCaptureLoadState = "error";
        worker.__bwCaptureLoadError = String(error?.stack || error);
        throw error;
      });
      worker.__bwCaptureLoadPromise = tracked;
      return tracked;
    };
    const currentWorkers = () => {
      const workers = Array.from(new Set(PThread.unusedWorkers.concat(Object.values(PThread.pthreads))));
      workers.forEach(attach);
      return workers;
    };
    Module["bwCaptureSplitWorkers"] = () => {
      const workers = currentWorkers();
      return { workers: workers.length, workerIds: workers.map((worker) => worker.__bwCaptureId),
        unused: PThread.unusedWorkers.length, running: Object.keys(PThread.pthreads).length,
        stabilizationEpoch };
    };
    Module["bwCaptureStabilizeWorkers"] = async (generation) => {
      if (!Number.isSafeInteger(generation) || generation <= 0 ||
          (captureGeneration !== 0 && captureGeneration !== generation)) {
        throw new Error(`BW_SPLIT_PROFILE_EXPORT_V1: invalid PREPARED generation ${generation}`);
      }
      captureGeneration = generation;
      let previous = "";
      let stableRounds = 0;
      let finalWorkers = [];
      for (let round = 0; round < 16 && stableRounds < 2; round++) {
        const workers = currentWorkers();
        await Promise.all(workers.map((worker) => new Promise((resolve, reject) => {
          if (worker.__bwCapturePending) {
            reject(new Error("BW_SPLIT_PROFILE_EXPORT_V1: duplicate worker probe"));
            return;
          }
          const token = `${Date.now()}-${round}-${worker.__bwCaptureId}`;
          const timeout = setTimeout(() => {
            worker.__bwCapturePending = null;
            reject(new Error(`BW_SPLIT_PROFILE_EXPORT_V1: worker probe timeout ${worker.__bwCaptureId}`));
          }, 30000);
          worker.__bwCapturePending = { token, resolve: (value) => { clearTimeout(timeout); resolve(value); },
            reject: (error) => { clearTimeout(timeout); reject(error); } };
          if (captureApplyRequested) postApplyProbeCount++;
          worker.postMessage({ cmd: "bwCaptureProbe", token, workerId: worker.__bwCaptureId });
        })));
        const ids = workers.map((worker) => worker.__bwCaptureId).sort((a, b) => a - b);
        const key = ids.join(",");
        stableRounds = key === previous ? stableRounds + 1 : 0;
        previous = key;
        finalWorkers = workers;
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
      if (stableRounds < 2 || finalWorkers.length < 8) {
        throw new Error("BW_SPLIT_PROFILE_EXPORT_V1: worker set did not stabilize at eight or more");
      }
      stabilizationEpoch++;
      const workerIds = finalWorkers.map((worker) => worker.__bwCaptureId).sort((a, b) => a - b);
      preparedWorkerIds = workerIds.slice();
      return { workers: finalWorkers.length, acknowledgements: finalWorkers.length,
        instances: finalWorkers.length, localInstances: 1, pending: 0, protocolErrors: 0,
        workerIds, preparedWorkerIds: workerIds.slice(), lateWorkerIds: [],
        latePreEntryLoadIds: [], pendingWorkerIds: [], errorWorkerIds: [],
        postApplyProbeCount, stabilizationEpoch };
    };
    const validateIds = (ids, label) => {
      if (!Array.isArray(ids) || ids.length < 8 ||
          ids.some((id) => !Number.isSafeInteger(id) || id <= 0) ||
          new Set(ids).size !== ids.length) {
        throw new Error(`BW_SPLIT_PROFILE_EXPORT_V1: invalid ${label} worker IDs`);
      }
      return ids.slice().sort((a, b) => a - b);
    };
    const awaitLatePreEntryLoad = async (worker) => {
      if (worker.__bwCaptureLoadState === "ready-before-entry") return;
      if (worker.__bwCaptureLoadState === "error") {
        throw new Error(`BW_SPLIT_PROFILE_EXPORT_V1: late worker load failed ${worker.__bwCaptureId}: ${worker.__bwCaptureLoadError}`);
      }
      if (worker.__bwCaptureLoadState !== "pending" || !worker.__bwCaptureLoadPromise) {
        throw new Error(`BW_SPLIT_PROFILE_EXPORT_V1: late worker lacks pre-entry load ${worker.__bwCaptureId}`);
      }
      await worker.__bwCaptureLoadPromise;
      if (worker.__bwCaptureLoadState !== "ready-before-entry") {
        throw new Error(`BW_SPLIT_PROFILE_EXPORT_V1: late worker load incomplete ${worker.__bwCaptureId}`);
      }
    };
    const attestWithoutPostEntryMessages = async (generation, expectedPreparedWorkerIds) => {
      if (!Number.isSafeInteger(generation) || generation <= 0) {
        throw new Error(`BW_SPLIT_PROFILE_EXPORT_V1: invalid attestation generation ${generation}`);
      }
      if (generation !== captureGeneration) {
        throw new Error(`BW_SPLIT_PROFILE_EXPORT_V1: wrong attestation generation ${generation}`);
      }
      const expectedPrepared = validateIds(expectedPreparedWorkerIds, "expected PREPARED");
      if (preparedWorkerIds.join(",") !== expectedPrepared.join(",")) {
        throw new Error("BW_SPLIT_PROFILE_EXPORT_V1: PREPARED worker identity mismatch");
      }
      const prepared = new Set(expectedPrepared);
      let previous = "";
      let stableRounds = 0;
      let finalWorkers = [];
      for (let round = 0; round < 16 && stableRounds < 2; round++) {
        const workers = currentWorkers();
        const ids = workers.map((worker) => worker.__bwCaptureId);
        if (new Set(ids).size !== ids.length || !expectedPrepared.every((id) => ids.includes(id))) {
          throw new Error("BW_SPLIT_PROFILE_EXPORT_V1: PAGE_READY worker shrink/replacement/duplicate");
        }
        const late = workers.filter((worker) => !prepared.has(worker.__bwCaptureId));
        // This is deliberately the only await in a round. It observes the
        // page-main load promise; it never posts a message to a worker that may
        // already be running long-lived C++ code.
        await Promise.all(late.map(awaitLatePreEntryLoad));
        const sortedIds = ids.slice().sort((a, b) => a - b);
        const key = sortedIds.join(",");
        stableRounds = key === previous ? stableRounds + 1 : 0;
        previous = key;
        finalWorkers = workers;
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
      if (stableRounds < 2) {
        throw new Error("BW_SPLIT_PROFILE_EXPORT_V1: non-messaging worker set did not stabilize");
      }
      const workerIds = finalWorkers.map((worker) => worker.__bwCaptureId).sort((a, b) => a - b);
      const lateWorkers = finalWorkers.filter((worker) => !prepared.has(worker.__bwCaptureId));
      const lateWorkerIds = lateWorkers.map((worker) => worker.__bwCaptureId).sort((a, b) => a - b);
      const latePreEntryLoadIds = lateWorkers.filter((worker) =>
        worker.__bwCaptureLoadState === "ready-before-entry" && worker.__bwCaptureLoadGeneration === generation)
        .map((worker) => worker.__bwCaptureId).sort((a, b) => a - b);
      const pendingWorkerIds = lateWorkers.filter((worker) => worker.__bwCaptureLoadState === "pending")
        .map((worker) => worker.__bwCaptureId).sort((a, b) => a - b);
      const errorWorkerIds = lateWorkers.filter((worker) => worker.__bwCaptureLoadState === "error")
        .map((worker) => worker.__bwCaptureId).sort((a, b) => a - b);
      if (lateWorkerIds.join(",") !== latePreEntryLoadIds.join(",") ||
          pendingWorkerIds.length !== 0 || errorWorkerIds.length !== 0) {
        throw new Error("BW_SPLIT_PROFILE_EXPORT_V1: late pre-entry load attestation failed");
      }
      stabilizationEpoch++;
      return { generation, workers: workerIds.length, acknowledgements: workerIds.length,
        instances: workerIds.length, localInstances: 1, pending: 0, protocolErrors: 0,
        workerIds, preparedWorkerIds: expectedPrepared, lateWorkerIds, latePreEntryLoadIds,
        pendingWorkerIds, errorWorkerIds, postApplyProbeCount, stabilizationEpoch };
    };
    Module["bwCaptureAttestPageReady"] = async (generation, expectedPreparedWorkerIds) => {
      const stable = await attestWithoutPostEntryMessages(generation, expectedPreparedWorkerIds);
      pageReadyAttestation = { ...stable, workerIds: stable.workerIds.slice() };
      return stable;
    };
    Module["bwCaptureResumeAfterStable"] = async (generation, expectedWorkerIds) => {
      if (pageReadyAttestation === null || pageReadyAttestation.generation !== generation) {
        throw new Error("BW_SPLIT_PROFILE_EXPORT_V1: missing PAGE_READY attestation");
      }
      const expected = validateIds(expectedWorkerIds, "PAGE_READY");
      if (expected.join(",") !== pageReadyAttestation.workerIds.join(",")) {
        throw new Error("BW_SPLIT_PROFILE_EXPORT_V1: PAGE_READY attestation identity mismatch");
      }
      const stable = await attestWithoutPostEntryMessages(generation, preparedWorkerIds);
      if (stable.workerIds.join(",") !== expectedWorkerIds.join(",")) {
        throw new Error("BW_SPLIT_PROFILE_EXPORT_V1: PAGE_READY worker set drift");
      }
      // No await/yield exists between this final exact attestation and native
      // RESUME publication; both execute in the same page task.
      const current = Module["bwCaptureSplitWorkers"]();
      if (current.workerIds.slice().sort((a, b) => a - b).join(",") !== stable.workerIds.join(",") ||
          stable.lateWorkerIds.join(",") !== pageReadyAttestation.lateWorkerIds.join(",") ||
          stable.latePreEntryLoadIds.join(",") !== pageReadyAttestation.latePreEntryLoadIds.join(",") ||
          stable.pending !== 0 || stable.protocolErrors !== 0 ||
          stable.postApplyProbeCount !== 0) {
        throw new Error("BW_SPLIT_PROFILE_EXPORT_V1: RESUME attestation drift");
      }
      const result = Module["bwCaptureSplitCall"]("BW_web_split_request_resume", [generation]);
      if (result !== 1) throw new Error(`BW_SPLIT_PROFILE_EXPORT_V1: RESUME rejected ${result}`);
      return stable;
    };
  }
})();

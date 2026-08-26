// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// APPLY-only Emscripten split-module runtime. The page fetches and verifies the
// deferred shard once, compiles it once, then structured-clones the compiled
// WebAssembly.Module into every already-loaded pthread. Each JavaScript realm
// instantiates at most once against its own primary exports/table. The post-link
// finalizer replaces the three identity sentinels and disables Emscripten's
// stock synchronous lazy loader before this source can be shipped.

var bwSplitRuntimeMarker = "BW_SPLIT_SINGLE_FLIGHT_RUNTIME_V1";
var bwSplitCacheMarker = "BW_SPLIT_SW_CACHEABLE_REQUEST_V1";
var bwSplitContentAddressMarker = "BW_SPLIT_CONTENT_ADDRESSED_URL_V1";
var bwSplitSecondaryFilename = "__BW_SPLIT_SECONDARY_FILENAME_SENTINEL__";
var bwSplitSecondaryBytes = Number("__BW_SPLIT_SECONDARY_BYTES_SENTINEL__");
var bwSplitSecondarySha256 = "__BW_SPLIT_SECONDARY_SHA256_SENTINEL__";
var bwSplitGeneration = 1;
var bwSplitSecondaryModule = null;
var bwSplitSecondaryInstance = null;
var bwSplitLocalInstanceCount = 0;
var bwSplitWorkerInstallGeneration = 0;
var bwSplitWorkerId = null;
var bwSplitPreparePromise = null;
var bwSplitPrepareGeneration = 0;
var bwSplitWorkerSequence = 0;
var bwSplitBroadcastSnapshotIds = [];
var bwSplitPreparedWorkerIds = [];
var bwSplitStabilizationEpoch = 0;
var bwSplitPreparedStabilizationEpoch = 0;
var bwSplitPageReadyAttestation = null;
var bwSplitProtocolError = null;
var bwSplitStats = {
  fetchCount: 0,
  compileCount: 0,
  pageInstanceCount: 0,
  workerAckCount: 0,
  workerInstanceCount: 0,
  lateWorkerAckCount: 0,
  duplicateAckCount: 0,
  rejectedAckCount: 0,
  ackTimeoutCount: 0,
};

function bwSplitHex(bytes) {
  return Array.from(new Uint8Array(bytes), function (value) {
    return value.toString(16).padStart(2, "0");
  }).join("");
}

function bwSplitInstallLocal(module) {
  if (bwSplitSecondaryInstance !== null) {
    return bwSplitSecondaryInstance;
  }
  if (!(module instanceof WebAssembly.Module)) {
    throw new Error(bwSplitRuntimeMarker + ": install payload is not a WebAssembly.Module");
  }
  if (typeof wasmRawExports !== "object" || wasmRawExports === null) {
    throw new Error(bwSplitRuntimeMarker + ": primary exports are not initialized");
  }
  bwSplitSecondaryModule = module;
  bwSplitSecondaryInstance = new WebAssembly.Instance(module, { primary: wasmRawExports });
  bwSplitLocalInstanceCount++;
  return bwSplitSecondaryInstance;
}

async function bwSplitInstallPage(module) {
  if (bwSplitSecondaryInstance !== null) {
    return bwSplitSecondaryInstance;
  }
  if (!(module instanceof WebAssembly.Module)) {
    throw new Error(bwSplitRuntimeMarker + ": page install payload is not a WebAssembly.Module");
  }
  if (typeof wasmRawExports !== "object" || wasmRawExports === null) {
    throw new Error(bwSplitRuntimeMarker + ": page primary exports are not initialized");
  }
  bwSplitSecondaryModule = module;
  // Chromium deliberately rejects synchronous WebAssembly.Instance for modules
  // larger than 8 MiB on the page main thread. A precompiled Module passed to
  // WebAssembly.instantiate does not compile again; it only instantiates async.
  bwSplitSecondaryInstance = await WebAssembly.instantiate(module, { primary: wasmRawExports });
  bwSplitLocalInstanceCount++;
  return bwSplitSecondaryInstance;
}

function bwSplitPostWorkerAck(ok, error, workerId, delivery) {
  postMessage({
    cmd: "bwSplitReady",
    generation: bwSplitGeneration,
    workerId: workerId,
    ok: ok,
    error: error || null,
    instanceCount: bwSplitLocalInstanceCount,
    delivery: delivery,
  });
}

function bwSplitProcessWorkerInstall(module, generation, workerId, delivery) {
  try {
    if (!Number.isSafeInteger(generation) || generation <= 0 ||
        !Number.isSafeInteger(workerId) || workerId <= 0 ||
        !(module instanceof WebAssembly.Module) ||
        (delivery !== "initial-before-start" && delivery !== "command")) {
      throw new Error(bwSplitRuntimeMarker + ": invalid worker install payload");
    }
    if (bwSplitWorkerInstallGeneration !== 0 || bwSplitSecondaryInstance !== null) {
      throw new Error(bwSplitRuntimeMarker + ": duplicate worker install command");
    }
    bwSplitGeneration = generation;
    bwSplitWorkerInstallGeneration = generation;
    bwSplitWorkerId = workerId;
    bwSplitInstallLocal(module);
    bwSplitPostWorkerAck(true, null, workerId, delivery);
    return true;
  }
  catch (error) {
    bwSplitPostWorkerAck(false, String(error && error.stack || error), workerId, delivery);
    return false;
  }
}

// Placeholder imports call this synchronously. Shipping code can only reach a
// pre-instantiated module; the finalizer replaces the stock instantiateSync
// initializer, so there is no browser sync-XHR/readBinary fallback.
loadSplitModule = function (file, imports, base) {
  if (bwSplitSecondaryInstance === null) {
    var detail = {
      file: String(file),
      base: typeof base === "undefined" ? null : String(base),
      realm: ENVIRONMENT_IS_PTHREAD ? "pthread" : "page",
      workerId: bwSplitWorkerId,
      generation: bwSplitGeneration,
      workerInstallGeneration: bwSplitWorkerInstallGeneration,
      localInstanceCount: bwSplitLocalInstanceCount,
      hasCompiledModule: bwSplitSecondaryModule !== null,
    };
    throw new Error(
      bwSplitRuntimeMarker + ": deferred call before Module.bwPrepareSplitSecondary(): " +
        JSON.stringify(detail),
    );
  }
  return [bwSplitSecondaryInstance, bwSplitSecondaryModule];
};

if (ENVIRONMENT_IS_PTHREAD) {
  var bwSplitBaseHandleMessage = handleMessage;
  handleMessage = function (event) {
    var message = event && event.data;
    if (message && message.cmd === "bwSplitInstall") {
      bwSplitProcessWorkerInstall(message.module, message.generation, message.workerId, "command");
      return;
    }
    return bwSplitBaseHandleMessage(event);
  };
}
else {
  var bwSplitOriginalLoadWorker = PThread.loadWasmModuleToWorker;

  function bwSplitAttachWorker(worker) {
    bwSplitEnsureWorkerId(worker);
    if (worker.__bwSplitAttachedHandler === worker.onmessage) {
      return;
    }
    worker.__bwSplitAttached = true;
    var originalOnMessage = worker.onmessage;
    var attachedHandler = function (event) {
      var message = event && event.data;
      if (message && message.cmd === "bwSplitReady") {
        var pending = worker.__bwSplitPending;
        worker.__bwSplitPending = null;
        var expectedDelivery = worker.__bwSplitInitialDelivery ? "initial-before-start" : "command";
        if (message.workerId !== worker.__bwSplitId) {
          bwSplitStats.rejectedAckCount++;
          bwSplitProtocolError = new Error(
            bwSplitRuntimeMarker + ": ACK worker id " + message.workerId +
              " != expected " + worker.__bwSplitId,
          );
          if (pending) pending.reject(bwSplitProtocolError);
          return;
        }
        if (message.generation !== bwSplitGeneration) {
          bwSplitStats.rejectedAckCount++;
          bwSplitProtocolError = new Error(
            bwSplitRuntimeMarker + ": ACK generation " + message.generation +
              " != expected " + bwSplitGeneration + " from worker " + worker.__bwSplitId,
          );
          if (pending) pending.reject(bwSplitProtocolError);
          return;
        }
        if (worker.__bwSplitAckGeneration === message.generation) {
          bwSplitStats.duplicateAckCount++;
          bwSplitProtocolError = new Error(
            bwSplitRuntimeMarker + ": duplicate ACK from worker " + worker.__bwSplitId,
          );
          if (pending) pending.reject(bwSplitProtocolError);
          return;
        }
        worker.__bwSplitAckGeneration = message.generation;
        if (!message.ok || message.instanceCount !== 1 || message.delivery !== expectedDelivery) {
          bwSplitStats.rejectedAckCount++;
          worker.__bwSplitInstallError = message.error ||
            "worker " + worker.__bwSplitId + " delivery " + message.delivery +
              " != expected " + expectedDelivery;
          bwSplitProtocolError = new Error(
            worker.__bwSplitInstallError || "worker " + worker.__bwSplitId + " did not install exactly once",
          );
          if (pending) pending.reject(bwSplitProtocolError);
          return;
        }
        worker.__bwSplitReadyGeneration = message.generation;
        worker.__bwSplitInstanceCount = message.instanceCount;
        worker.__bwSplitInstallDelivery = message.delivery;
        if (message.delivery === "initial-before-start") {
          worker.__bwSplitInitialAckGeneration = message.generation;
        }
        worker.__bwSplitInitialDelivery = false;
        if (!bwSplitBroadcastSnapshotIds.includes(worker.__bwSplitId) && !worker.__bwSplitLateCounted) {
          worker.__bwSplitLateCounted = true;
          bwSplitStats.lateWorkerAckCount++;
        }
        if (pending) pending.resolve(worker);
        return;
      }
      return originalOnMessage.call(worker, event);
    };
    worker.onmessage = attachedHandler;
    worker.__bwSplitAttachedHandler = attachedHandler;
  }

  function bwSplitEnsureWorkerId(worker) {
    if (!worker.__bwSplitId) worker.__bwSplitId = ++bwSplitWorkerSequence;
    return worker.__bwSplitId;
  }

  function bwSplitInstallWorker(worker, late) {
    bwSplitAttachWorker(worker);
    if (worker.__bwSplitReadyGeneration === bwSplitGeneration) {
      return Promise.resolve(worker);
    }
    if (worker.__bwSplitPending) {
      return worker.__bwSplitPending.promise;
    }
    var resolvePending;
    var rejectPending;
    var promise = new Promise(function (resolve, reject) {
      resolvePending = resolve;
      rejectPending = reject;
    });
    var timeout = setTimeout(function () {
      if (worker.__bwSplitPending) {
        worker.__bwSplitPending = null;
        bwSplitStats.ackTimeoutCount++;
        bwSplitProtocolError = new Error(
          bwSplitRuntimeMarker + ": pthread ACK timeout workerId=" + worker.__bwSplitId +
            " initialDelivery=" + !!worker.__bwSplitInitialDelivery +
            " attached=" + !!worker.__bwSplitAttached,
        );
        worker.__bwSplitInstallError = String(bwSplitProtocolError);
        rejectPending(bwSplitProtocolError);
      }
    }, 30000);
    worker.__bwSplitPending = {
      promise: promise,
      resolve: function (value) { clearTimeout(timeout); resolvePending(value); },
      reject: function (error) { clearTimeout(timeout); rejectPending(error); },
    };
    if (!worker.__bwSplitInitialDelivery) {
      worker.postMessage({
        cmd: "bwSplitInstall",
        generation: bwSplitGeneration,
        workerId: worker.__bwSplitId,
        module: bwSplitSecondaryModule,
      });
    }
    return promise;
  }

  PThread.loadWasmModuleToWorker = function (worker) {
    // Preassign the stable ID, let Emscripten synchronously post cmd1 and install
    // worker.onmessage, then synchronously queue the secondary install. The
    // browser's per-Worker FIFO guarantees cmd1 -> bwSplitInitialInstall -> cmd2,
    // even though Emscripten getNewWorker() does not await this load promise.
    bwSplitEnsureWorkerId(worker);
    var loading = bwSplitOriginalLoadWorker(worker);
    bwSplitAttachWorker(worker);
    if (bwSplitSecondaryModule !== null) {
      worker.__bwSplitInitialDelivery = true;
      worker.postMessage({
        cmd: "bwSplitInitialInstall",
        generation: bwSplitGeneration,
        workerId: worker.__bwSplitId,
        module: bwSplitSecondaryModule,
      });
    }
    return loading.then(function (loadedWorker) {
      if (bwSplitSecondaryModule === null) return loadedWorker;
      return bwSplitInstallWorker(loadedWorker, true);
    });
  };

  for (var bwSplitInitialWorker of PThread.unusedWorkers) {
    bwSplitAttachWorker(bwSplitInitialWorker);
  }
  for (var bwSplitRunningWorker of Object.values(PThread.pthreads)) {
    bwSplitAttachWorker(bwSplitRunningWorker);
  }

  function bwSplitCurrentWorkers() {
    var workers = Array.from(new Set(PThread.unusedWorkers.concat(Object.values(PThread.pthreads))));
    workers.forEach(bwSplitAttachWorker);
    return workers;
  }

  function bwSplitStatus() {
    var workers = bwSplitCurrentWorkers();
    var unusedWorkers = new Set(PThread.unusedWorkers);
    var runningWorkers = new Set(Object.values(PThread.pthreads));
    return {
      marker: bwSplitRuntimeMarker,
      cacheMarker: bwSplitCacheMarker,
      contentAddressMarker: bwSplitContentAddressMarker,
      ready: bwSplitSecondaryInstance !== null && workers.length > 0 &&
        workers.every(function (worker) {
          return worker.__bwSplitReadyGeneration === bwSplitGeneration &&
            worker.__bwSplitInstanceCount === 1;
        }),
      expected: {
        filename: bwSplitSecondaryFilename,
        bytes: bwSplitSecondaryBytes,
        sha256: bwSplitSecondarySha256,
        requestKey: bwSplitSecondaryFilename + "?sha256=" + bwSplitSecondarySha256,
      },
      workerCount: workers.length,
      workerIds: workers.map(function (worker) { return worker.__bwSplitId; }),
      ackWorkerIds: workers.filter(function (worker) {
        return worker.__bwSplitReadyGeneration === bwSplitGeneration;
      }).map(function (worker) { return worker.__bwSplitId; }),
      pendingWorkerIds: workers.filter(function (worker) {
        return worker.__bwSplitReadyGeneration !== bwSplitGeneration;
      }).map(function (worker) { return worker.__bwSplitId; }),
      broadcastSnapshotIds: bwSplitBroadcastSnapshotIds.slice(),
      workerLifecycle: workers.map(function (worker) {
        return {
          workerId: worker.__bwSplitId,
          unused: unusedWorkers.has(worker),
          running: runningWorkers.has(worker),
          attached: !!worker.__bwSplitAttached,
          pending: !!worker.__bwSplitPending,
          initialDelivery: !!worker.__bwSplitInitialDelivery,
          installDelivery: worker.__bwSplitInstallDelivery || null,
          initialAckGeneration: worker.__bwSplitInitialAckGeneration || 0,
          readyGeneration: worker.__bwSplitReadyGeneration || 0,
          ackGeneration: worker.__bwSplitAckGeneration || 0,
          instanceCount: worker.__bwSplitInstanceCount || 0,
        };
      }),
      workerAckCount: workers.filter(function (worker) {
        return worker.__bwSplitReadyGeneration === bwSplitGeneration;
      }).length,
      workerInstanceCount: workers.reduce(function (total, worker) {
        return total + (worker.__bwSplitInstanceCount || 0);
      }, 0),
      localInstanceCount: bwSplitLocalInstanceCount,
      preparedWorkerIds: bwSplitPreparedWorkerIds.slice(),
      lateWorkerIds: workers.filter(function (worker) {
        return bwSplitPreparedWorkerIds.length > 0 &&
          !bwSplitPreparedWorkerIds.includes(worker.__bwSplitId);
      }).map(function (worker) { return worker.__bwSplitId; }),
      initialAckWorkerIds: workers.filter(function (worker) {
        return worker.__bwSplitInitialAckGeneration === bwSplitGeneration;
      }).map(function (worker) { return worker.__bwSplitId; }),
      lateInitialAckWorkerIds: workers.filter(function (worker) {
        return bwSplitPreparedWorkerIds.length > 0 &&
          !bwSplitPreparedWorkerIds.includes(worker.__bwSplitId) &&
          worker.__bwSplitInitialAckGeneration === bwSplitGeneration &&
          worker.__bwSplitInstallDelivery === "initial-before-start";
      }).map(function (worker) { return worker.__bwSplitId; }),
      errorWorkerIds: workers.filter(function (worker) {
        return !!worker.__bwSplitInstallError;
      }).map(function (worker) { return worker.__bwSplitId; }),
      stats: Object.assign({}, bwSplitStats),
      protocolError: bwSplitProtocolError ? String(bwSplitProtocolError) : null,
    };
  }

  function bwSplitNativeExport(name) {
    var exported = Module["_" + name];
    if (typeof exported !== "function" && typeof wasmExports === "object" && wasmExports !== null) {
      exported = wasmExports[name];
    }
    if (typeof exported !== "function" && typeof wasmRawExports === "object" && wasmRawExports !== null) {
      exported = wasmRawExports[name];
    }
    if (typeof exported !== "function") {
      throw new Error(bwSplitRuntimeMarker + ": missing native transition export " + name);
    }
    return exported;
  }

  function bwSplitNativeRead(name) {
    return Number(bwSplitNativeExport(name)());
  }

  function bwSplitNativeStatus() {
    return {
      phase: bwSplitNativeRead("BW_web_split_phase"),
      requestGeneration: bwSplitNativeRead("BW_web_split_request_generation"),
      parkRequestGeneration: bwSplitNativeRead("BW_web_split_park_request_generation"),
      parkedGeneration: bwSplitNativeRead("BW_web_split_parked_generation"),
      preparedRequestGeneration: bwSplitNativeRead("BW_web_split_prepared_request_generation"),
      preparedGeneration: bwSplitNativeRead("BW_web_split_prepared_generation"),
      applyRequestGeneration: bwSplitNativeRead("BW_web_split_apply_request_generation"),
      appliedGeneration: bwSplitNativeRead("BW_web_split_applied_generation"),
      pageReadyRequestGeneration: bwSplitNativeRead("BW_web_split_page_ready_request_generation"),
      pageReadyGeneration: bwSplitNativeRead("BW_web_split_page_ready_generation"),
      resumeRequestGeneration: bwSplitNativeRead("BW_web_split_resume_request_generation"),
      resumedGeneration: bwSplitNativeRead("BW_web_split_resumed_generation"),
      errorGeneration: bwSplitNativeRead("BW_web_split_error_generation"),
      offendingGeneration: bwSplitNativeRead("BW_web_split_offending_generation"),
      errorCode: bwSplitNativeRead("BW_web_split_error_code"),
      targetThreads: bwSplitNativeRead("BW_web_split_target_threads"),
      activeThreads: bwSplitNativeRead("BW_web_split_active_threads"),
      nativeReady: bwSplitNativeRead("BW_web_split_native_ready"),
      openexrThreads: bwSplitNativeRead("BW_web_split_openexr_threads"),
      oiioThreads: bwSplitNativeRead("BW_web_split_oiio_threads"),
      applyOpenexrSet: bwSplitNativeRead("BW_web_split_apply_openexr_set"),
      applyOpenexrThreads: bwSplitNativeRead("BW_web_split_apply_openexr_threads"),
      applyOiioSet: bwSplitNativeRead("BW_web_split_apply_oiio_set"),
      applyOiioThreads: bwSplitNativeRead("BW_web_split_apply_oiio_threads"),
      rollbackOpenexrSet: bwSplitNativeRead("BW_web_split_rollback_openexr_set"),
      rollbackOpenexrThreads: bwSplitNativeRead("BW_web_split_rollback_openexr_threads"),
      rollbackOiioSet: bwSplitNativeRead("BW_web_split_rollback_oiio_set"),
      rollbackOiioThreads: bwSplitNativeRead("BW_web_split_rollback_oiio_threads"),
      reloadRequired: bwSplitNativeRead("BW_web_split_reload_required"),
      preparedWorkers: bwSplitNativeRead("BW_web_split_prepared_workers"),
      preparedAcknowledgements: bwSplitNativeRead("BW_web_split_prepared_acknowledgements"),
      preparedInstances: bwSplitNativeRead("BW_web_split_prepared_instances"),
      preparedLocalInstances: bwSplitNativeRead("BW_web_split_prepared_local_instances"),
      preparedPending: bwSplitNativeRead("BW_web_split_prepared_pending"),
      preparedProtocolErrors: bwSplitNativeRead("BW_web_split_prepared_protocol_errors"),
      preparedStabilizationEpoch: bwSplitNativeRead("BW_web_split_prepared_stabilization_epoch"),
      pageReadyWorkers: bwSplitNativeRead("BW_web_split_page_ready_workers"),
      pageReadyAcknowledgements: bwSplitNativeRead("BW_web_split_page_ready_acknowledgements"),
      pageReadyInstances: bwSplitNativeRead("BW_web_split_page_ready_instances"),
      pageReadyLocalInstances: bwSplitNativeRead("BW_web_split_page_ready_local_instances"),
      pageReadyPending: bwSplitNativeRead("BW_web_split_page_ready_pending"),
      pageReadyProtocolErrors: bwSplitNativeRead("BW_web_split_page_ready_protocol_errors"),
      pageReadyLateWorkers: bwSplitNativeRead("BW_web_split_page_ready_late_workers"),
      pageReadyStabilizationEpoch: bwSplitNativeRead("BW_web_split_page_ready_stabilization_epoch"),
    };
  }

  function bwSplitNativeCall(name, args) {
    var result = Number(bwSplitNativeExport(name).apply(null, args));
    if (result !== 1) {
      throw new Error(
        bwSplitRuntimeMarker + ": native transition " + name + " rejected: " + result + " " +
          JSON.stringify(bwSplitNativeStatus()),
      );
    }
  }

  async function bwSplitWaitNativeGeneration(field, generation) {
    var deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      var nativeStatus = bwSplitNativeStatus();
      if (nativeStatus.errorGeneration === generation) {
        throw new Error(
          bwSplitRuntimeMarker + ": native transition failed while waiting for " + field + ": " +
            JSON.stringify(nativeStatus),
        );
      }
      if (nativeStatus[field] === generation) return nativeStatus;
      await new Promise(function (resolve) { setTimeout(resolve, 10); });
    }
    throw new Error(
      bwSplitRuntimeMarker + ": native transition timeout waiting for " + field + ": " +
        JSON.stringify(bwSplitNativeStatus()),
    );
  }

  function bwSplitProtocolErrorCount(status) {
    return status.protocolError === null && status.stats.duplicateAckCount === 0 &&
      status.stats.rejectedAckCount === 0 && status.stats.ackTimeoutCount === 0 ? 0 : 1;
  }

  async function bwSplitStabilizeWorkers(initialOnlyLate) {
    var stableRounds = 0;
    var previousIds = "";
    for (var round = 0; round < 16 && stableRounds < 2; round++) {
      var current = bwSplitCurrentWorkers();
      await Promise.all(current.map(function (worker) {
        if (initialOnlyLate) {
          var prepared = bwSplitPreparedWorkerIds.includes(worker.__bwSplitId);
          if (worker.__bwSplitReadyGeneration === bwSplitGeneration) {
            if (!prepared && (worker.__bwSplitInitialAckGeneration !== bwSplitGeneration ||
                worker.__bwSplitInstallDelivery !== "initial-before-start")) {
              throw new Error(
                bwSplitRuntimeMarker + ": late worker lacks initial-before-start ACK " +
                  worker.__bwSplitId,
              );
            }
            return Promise.resolve(worker);
          }
          if (prepared || !worker.__bwSplitInitialDelivery) {
            throw new Error(
              bwSplitRuntimeMarker + ": PAGE_READY refuses post-entry worker install " +
                worker.__bwSplitId,
            );
          }
        }
        return bwSplitInstallWorker(worker, !bwSplitBroadcastSnapshotIds.includes(worker.__bwSplitId));
      }));
      var currentIds = current.map(function (worker) { return worker.__bwSplitId; }).sort(function (a, b) {
        return a - b;
      }).join(",");
      stableRounds = currentIds === previousIds ? stableRounds + 1 : 0;
      previousIds = currentIds;
      await new Promise(function (resolve) { setTimeout(resolve, 0); });
    }
    if (stableRounds < 2) {
      throw new Error(bwSplitRuntimeMarker + ": worker set did not stabilize during preload");
    }
    bwSplitStabilizationEpoch++;
    return bwSplitStatus();
  }

  Module["bwSplitSecondaryStatus"] = bwSplitStatus;
  Module["bwSplitNativeStatus"] = bwSplitNativeStatus;
  Module["bwRequestSplitPark"] = async function (generation) {
    if (!Number.isSafeInteger(generation) || generation <= 0) {
      throw new Error(bwSplitRuntimeMarker + ": invalid PARK generation " + generation);
    }
    bwSplitGeneration = generation;
    bwSplitNativeCall("BW_web_split_request_park", [generation]);
    return bwSplitWaitNativeGeneration("parkedGeneration", generation);
  };
  Module["bwPrepareSplitSecondary"] = function (generation) {
    if (bwSplitPreparePromise !== null) {
      throw new Error(
        bwSplitRuntimeMarker + ": duplicate prepare request; active generation=" +
          bwSplitPrepareGeneration + " requested=" + generation,
      );
    }
    bwSplitPrepareGeneration = generation;
    bwSplitPreparePromise = (async function () {
      if (!Number.isSafeInteger(generation) || generation <= 0 || generation !== bwSplitGeneration) {
        throw new Error(bwSplitRuntimeMarker + ": prepare requires the active positive generation");
      }
      var parkedStatus = bwSplitNativeStatus();
      if (parkedStatus.parkedGeneration !== generation || parkedStatus.phase !== 2) {
        throw new Error(bwSplitRuntimeMarker + ": prepare requires exact PARK ACK " +
          JSON.stringify(parkedStatus));
      }
      if (!Number.isSafeInteger(bwSplitSecondaryBytes) || bwSplitSecondaryBytes <= 0 ||
          !/^[0-9a-f]{64}$/.test(bwSplitSecondarySha256) ||
          !/^blender_browser\.[a-z0-9._-]+\.wasm$/.test(bwSplitSecondaryFilename)) {
        throw new Error(bwSplitRuntimeMarker + ": finalizer did not bind a valid shard identity");
      }
      var workers = bwSplitCurrentWorkers();
      if (workers.length < 8) {
        throw new Error(bwSplitRuntimeMarker + ": expected at least 8 loaded pthreads, found " + workers.length);
      }
      bwSplitBroadcastSnapshotIds = workers.map(function (worker) { return worker.__bwSplitId; });
      if (new Set(bwSplitBroadcastSnapshotIds).size !== bwSplitBroadcastSnapshotIds.length) {
        throw new Error(bwSplitRuntimeMarker + ": duplicate worker identity in broadcast snapshot");
      }
      var secondaryUrl = locateFile(bwSplitSecondaryFilename);
      secondaryUrl += (secondaryUrl.includes("?") ? "&" : "?") +
        "sha256=" + encodeURIComponent(bwSplitSecondarySha256);
      bwSplitStats.fetchCount++;
      // Use an ordinary same-origin request so the versioned service worker can
      // satisfy this exact stable shard URL from its offline precache.
      var response = await fetch(secondaryUrl, { credentials: "same-origin" });
      if (!response.ok) throw new Error(bwSplitRuntimeMarker + ": fetch status " + response.status);
      var body = await response.arrayBuffer();
      if (body.byteLength !== bwSplitSecondaryBytes) {
        throw new Error(bwSplitRuntimeMarker + ": bytes " + body.byteLength + " != " + bwSplitSecondaryBytes);
      }
      var actualSha256 = bwSplitHex(await globalThis.crypto.subtle.digest("SHA-256", body));
      if (actualSha256 !== bwSplitSecondarySha256) {
        throw new Error(bwSplitRuntimeMarker + ": sha256 " + actualSha256 + " != " + bwSplitSecondarySha256);
      }
      var headerBytes = response.headers.get("X-BW-Content-Bytes");
      var headerSha256 = response.headers.get("X-BW-Content-SHA256");
      if (headerBytes !== null && Number(headerBytes) !== bwSplitSecondaryBytes) {
        throw new Error(bwSplitRuntimeMarker + ": server byte identity mismatch");
      }
      if (headerSha256 !== null && headerSha256 !== bwSplitSecondarySha256) {
        throw new Error(bwSplitRuntimeMarker + ": server hash identity mismatch");
      }
      bwSplitStats.compileCount++;
      bwSplitSecondaryModule = await WebAssembly.compile(body);
      await bwSplitInstallPage(bwSplitSecondaryModule);
      bwSplitStats.pageInstanceCount = bwSplitLocalInstanceCount;
      await Promise.all(workers.map(function (worker) { return bwSplitInstallWorker(worker, false); }));
      var snapshotStatus = bwSplitStatus();
      var snapshotAcks = workers.filter(function (worker) {
        return worker.__bwSplitReadyGeneration === bwSplitGeneration &&
          worker.__bwSplitInstanceCount === 1;
      });
      if (snapshotAcks.length !== workers.length || bwSplitProtocolError !== null) {
        throw new Error(bwSplitRuntimeMarker + ": broadcast snapshot ACK contract failed");
      }
      // Workers may be created while the initial broadcast is in flight. Keep
      // taking unique current-worker snapshots until two consecutive rounds are
      // stable; every new worker is installed through the same late-worker path.
      var status = await bwSplitStabilizeWorkers();
      bwSplitStats.workerAckCount = status.workerAckCount;
      bwSplitStats.workerInstanceCount = status.workerInstanceCount;
      status = bwSplitStatus();
      if (!status.ready || status.workerAckCount !== status.workerCount ||
          status.workerInstanceCount !== status.workerCount ||
          status.localInstanceCount !== 1 || status.stats.fetchCount !== 1 ||
          status.stats.compileCount !== 1 || status.protocolError !== null ||
          status.broadcastSnapshotIds.length !== workers.length) {
        throw new Error(bwSplitRuntimeMarker + ": readiness contract failed " + JSON.stringify(status));
      }
      bwSplitPreparedWorkerIds = status.workerIds.slice().sort(function (a, b) { return a - b; });
      bwSplitPreparedStabilizationEpoch = bwSplitStabilizationEpoch;
      // bwSplitStatus() returns copied arrays. Refresh after publishing the
      // prepared ID set so both the native request and returned page receipt
      // describe the same exact prepared snapshot.
      status = bwSplitStatus();
      bwSplitNativeCall("BW_web_split_request_prepared", [
        generation,
        status.workerCount,
        status.workerAckCount,
        status.workerInstanceCount,
        status.localInstanceCount,
        status.pendingWorkerIds.length,
        bwSplitProtocolErrorCount(status),
        bwSplitPreparedStabilizationEpoch,
      ]);
      var nativeStatus = await bwSplitWaitNativeGeneration("preparedGeneration", generation);
      return { split: status, native: nativeStatus };
    })();
    return bwSplitPreparePromise;
  };
  Module["bwApplySplitScheduler"] = async function (generation) {
    var nativeStatus = bwSplitNativeStatus();
    if (nativeStatus.preparedGeneration !== generation || nativeStatus.phase !== 4) {
      throw new Error(bwSplitRuntimeMarker + ": APPLY requires exact PREPARED ACK " +
        JSON.stringify(nativeStatus));
    }
    bwSplitNativeCall("BW_web_split_request_apply", [generation, 8]);
    return bwSplitWaitNativeGeneration("appliedGeneration", generation);
  };
  Module["bwMarkSplitPageReady"] = async function (generation) {
    var nativeStatus = bwSplitNativeStatus();
    if (nativeStatus.appliedGeneration !== generation || nativeStatus.phase !== 6) {
      throw new Error(bwSplitRuntimeMarker + ": PAGE_READY requires exact APPLY ACK " +
        JSON.stringify(nativeStatus));
    }
    var status = await bwSplitStabilizeWorkers(true);
    var pageReadyStabilizationEpoch = bwSplitStabilizationEpoch;
    if (pageReadyStabilizationEpoch <= bwSplitPreparedStabilizationEpoch) {
      throw new Error(bwSplitRuntimeMarker + ": PAGE_READY requires a distinct post-APPLY stabilization epoch");
    }
    var finalIds = status.workerIds.slice().sort(function (a, b) { return a - b; });
    if (bwSplitPreparedWorkerIds.length < 8 ||
        !bwSplitPreparedWorkerIds.every(function (workerId) { return finalIds.includes(workerId); })) {
      throw new Error(bwSplitRuntimeMarker + ": final worker set does not contain PREPARED set");
    }
    var lateWorkers = finalIds.length - bwSplitPreparedWorkerIds.length;
    var exactLateIds = finalIds.filter(function (workerId) {
      return !bwSplitPreparedWorkerIds.includes(workerId);
    });
    var exactLateInitialAckIds = status.lateInitialAckWorkerIds.slice().sort(function (a, b) {
      return a - b;
    });
    if (!status.ready || status.workerAckCount !== status.workerCount ||
        status.workerInstanceCount !== status.workerCount || status.localInstanceCount !== 1 ||
        status.pendingWorkerIds.length !== 0 || status.errorWorkerIds.length !== 0 ||
        bwSplitProtocolErrorCount(status) !== 0 ||
        exactLateIds.join(",") !== exactLateInitialAckIds.join(",")) {
      throw new Error(bwSplitRuntimeMarker + ": PAGE_READY worker contract failed " +
        JSON.stringify(status));
    }
    bwSplitNativeCall("BW_web_split_request_page_ready", [
      generation,
      status.workerCount,
      status.workerAckCount,
      status.workerInstanceCount,
      status.localInstanceCount,
      status.pendingWorkerIds.length,
      bwSplitProtocolErrorCount(status),
      lateWorkers,
      pageReadyStabilizationEpoch,
    ]);
    nativeStatus = await bwSplitWaitNativeGeneration("pageReadyGeneration", generation);
    var rechecked = await bwSplitStabilizeWorkers(true);
    var recheckedIds = rechecked.workerIds.slice().sort(function (a, b) { return a - b; });
    if (!rechecked.ready || rechecked.pendingWorkerIds.length !== 0 ||
        rechecked.errorWorkerIds.length !== 0 || bwSplitProtocolErrorCount(rechecked) !== 0 ||
        recheckedIds.join(",") !== finalIds.join(",") ||
        rechecked.lateWorkerIds.slice().sort(function (a, b) { return a - b; }).join(",") !==
          exactLateIds.join(",") ||
        rechecked.lateInitialAckWorkerIds.slice().sort(function (a, b) { return a - b; }).join(",") !==
          exactLateIds.join(",")) {
      throw new Error(bwSplitRuntimeMarker + ": worker set drifted after PAGE_READY ACK " +
        JSON.stringify(rechecked));
    }
    bwSplitPageReadyAttestation = {
      generation: generation,
      workerIds: recheckedIds,
      workerCount: rechecked.workerCount,
      workerAckCount: rechecked.workerAckCount,
      workerInstanceCount: rechecked.workerInstanceCount,
      localInstanceCount: rechecked.localInstanceCount,
      stabilizationEpoch: pageReadyStabilizationEpoch,
      lateWorkerIds: exactLateIds,
      lateInitialAckWorkerIds: exactLateInitialAckIds,
    };
    return { split: bwSplitStatus(), native: nativeStatus, lateWorkers: lateWorkers };
  };
  Module["bwResumeSplitScheduler"] = async function (generation) {
    var nativeStatus = bwSplitNativeStatus();
    if (nativeStatus.pageReadyGeneration !== generation || nativeStatus.phase !== 8) {
      throw new Error(bwSplitRuntimeMarker + ": RESUME requires exact PAGE_READY ACK " +
        JSON.stringify(nativeStatus));
    }
    // This status read, exact ID/payload comparison, and native RESUME request
    // are deliberately synchronous in one page task. No worker can dispatch an
    // ACK/new-worker event between the attestation check and request publication.
    var status = bwSplitStatus();
    var ids = status.workerIds.slice().sort(function (a, b) { return a - b; });
    var attestation = bwSplitPageReadyAttestation;
    if (attestation === null || attestation.generation !== generation ||
        ids.join(",") !== attestation.workerIds.join(",") ||
        status.workerCount !== attestation.workerCount ||
        status.workerAckCount !== attestation.workerAckCount ||
        status.workerInstanceCount !== attestation.workerInstanceCount ||
        status.localInstanceCount !== attestation.localInstanceCount ||
        status.lateWorkerIds.slice().sort(function (a, b) { return a - b; }).join(",") !==
          attestation.lateWorkerIds.join(",") ||
        status.lateInitialAckWorkerIds.slice().sort(function (a, b) { return a - b; }).join(",") !==
          attestation.lateInitialAckWorkerIds.join(",") ||
        status.errorWorkerIds.length !== 0 ||
        !status.ready || status.pendingWorkerIds.length !== 0 || bwSplitProtocolErrorCount(status) !== 0) {
      throw new Error(bwSplitRuntimeMarker + ": RESUME attestation drift " +
        JSON.stringify({ attestation: attestation, status: status }));
    }
    bwSplitNativeCall("BW_web_split_request_resume", [generation]);
    nativeStatus = await bwSplitWaitNativeGeneration("resumedGeneration", generation);
    return { split: bwSplitStatus(), native: nativeStatus };
  };
  Module["bwFinalizeSplitTransition"] = async function (generation) {
    var pageReady = await Module["bwMarkSplitPageReady"](generation);
    var resumed = await Module["bwResumeSplitScheduler"](generation);
    return { split: resumed.split, native: resumed.native, lateWorkers: pageReady.lateWorkers };
  };
}

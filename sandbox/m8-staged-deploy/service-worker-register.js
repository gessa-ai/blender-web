// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Registration and honest progress surface for the staged-bundle cache. Exposes
// window.__bwServiceWorker and an idempotent window.__bwPrecache() for the launch
// verifier. Automatic precaching waits for stage-1 to finish so it never competes
// with time-to-first-pixels or the deferred payload stream. This exact generated
// file is a precached but network-first control resource: an old worker fetches
// its new bytes online, while the old exact cache remains its offline fallback.

"use strict";
(function () {
  const EXPECTED_CACHE_VERSION = "__BW_EXPECTED_CACHE_VERSION__";
  const state = {
    supported: "serviceWorker" in navigator,
    phase: "idle", // idle -> registering -> ready -> caching -> done | error
    version: null,
    filesDone: 0,
    filesTotal: 0,
    bytesDone: 0,
    error: null,
  };
  window.__bwServiceWorker = state;
  let registrationPromise = null;
  let precachePromise = null;
  let exactWorker = null;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  function fail(error) {
    state.phase = "error";
    state.error = String(error && error.message || error);
    try { console.warn("[service-worker] " + state.error); } catch (_) {}
    return state;
  }

  async function registration() {
    if (!state.supported) return null;
    if (!registrationPromise) {
      state.phase = "registering";
      registrationPromise = navigator.serviceWorker.register("/service-worker.js", {
        scope: "/", updateViaCache: "none",
      }).then(async (registered) => {
        await registered.update();
        const deadline = Date.now() + 30000;
        async function identity(worker) {
          if (!worker || worker.state !== "activated") return null;
          return await new Promise((resolve, reject) => {
          const channel = new MessageChannel();
          const timer = setTimeout(() => reject(new Error("service-worker identity timeout")), 1000);
          channel.port1.onmessage = (event) => { clearTimeout(timer); resolve(event.data); };
            worker.postMessage({type: "BW_CACHE_IDENTITY"}, [channel.port2]);
          });
        }
        let active = null;
        let currentIdentity = null;
        while (Date.now() < deadline) {
          active = registered.active;
          try { currentIdentity = await identity(active); } catch (_) { currentIdentity = null; }
          if (currentIdentity && currentIdentity.version === EXPECTED_CACHE_VERSION) break;
          await sleep(25);
        }
        if (!active || !currentIdentity || currentIdentity.version !== EXPECTED_CACHE_VERSION) {
          throw new Error("registration has no active exact generated service worker");
        }
        const identityValue = currentIdentity;
        if (!identityValue || identityValue.type !== "BW_CACHE_IDENTITY" ||
            identityValue.version !== EXPECTED_CACHE_VERSION ||
            !Array.isArray(identityValue.precacheUrls) ||
            !Array.isArray(identityValue.cacheFirstUrls)) {
          throw new Error("service-worker returned an invalid cache identity");
        }
        state.version = identityValue.version;
        state.precacheUrls = identityValue.precacheUrls;
        state.cacheFirstUrls = identityValue.cacheFirstUrls;
        exactWorker = active;
        state.phase = "ready";
        return registered;
      }).catch((error) => {
        registrationPromise = null;
        fail(error);
        return null;
      });
    }
    return registrationPromise;
  }

  navigator.serviceWorker && navigator.serviceWorker.addEventListener("message", (event) => {
    const msg = event.data || {};
    if (!msg.type || !msg.type.startsWith("BW_PRECACHE_")) return;
    if (event.source !== exactWorker ||
        msg.version !== EXPECTED_CACHE_VERSION) return;
    if (Number.isFinite(msg.done)) state.filesDone = msg.done;
    if (Number.isFinite(msg.total)) state.filesTotal = msg.total;
    if (Number.isFinite(msg.bytes)) state.bytesDone = msg.bytes;
    if (msg.type === "BW_PRECACHE_PROGRESS") state.phase = "caching";
    if (msg.type === "BW_PRECACHE_DONE") state.phase = "done";
    if (msg.type === "BW_PRECACHE_ERROR") fail(msg.error || "precache failed");
  });

  async function precache() {
    if (precachePromise && state.phase !== "error") return precachePromise;
    // A manual retry after a transient network error resumes from any same-version
    // entries the worker already cached.
    if (state.phase === "error") {
      state.error = null;
      precachePromise = null;
    }
    precachePromise = (async () => {
      const reg = await registration();
      if (!reg) return state;
      const worker = exactWorker;
      if (!worker) return fail("registered service worker has no exact active worker");
      state.phase = "caching";
      worker.postMessage({type: "BW_PRECACHE"});
      for (let i = 0; i < 1800 && state.phase === "caching"; i++) await sleep(200);
      if (state.phase === "caching") fail("precache completion timed out");
      if (state.phase === "done") {
        for (let i = 0; i < 1200 && navigator.serviceWorker.controller !== worker; i++) {
          await sleep(25);
        }
        if (navigator.serviceWorker.controller !== worker) {
          fail("exact precached service worker did not claim the current page");
        }
      }
      return state;
    })();
    return precachePromise;
  }
  window.__bwPrecache = precache;

  if (!state.supported) {
    fail("Service Worker API unavailable; HTTP cache remains active");
    return;
  }
  registration();

  (async function schedule() {
    // stage1-loader owns the background stream. Cache only after its real bytes
    // are installed, or after an explicit manual trigger completes in a rig.
    for (let i = 0; i < 3600; i++) {
      const stage = window.__bwStage1;
      if (stage && stage.phase === "done") {
        await precache();
        return;
      }
      if (stage && (stage.phase === "error" || stage.phase === "done-with-errors")) return;
      await sleep(250);
    }
  })();
})();

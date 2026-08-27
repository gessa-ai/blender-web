// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Public-bundle-only pthread bootstrap.  Emscripten normally starts every
// pthread from the full blender_browser.js URL.  Browser caches may avoid bytes
// on the wire, but the request still repeats and cannot satisfy the launch
// receipt's exact one-response-per-critical-path contract.  Fetch one separately
// inventoried copy, bind its exact runtime identity, then give Emscripten the
// resulting Blob through its supported mainScriptUrlOrBlob Module property.

"use strict";

(() => {
  const SOURCE_PATH = "/bin/blender_browser.worker.js";
  const CONTRACT = "pthread-main-script-blob-v1";
  const originalFactory = globalThis.createBlenderModule;
  if (typeof originalFactory !== "function") {
    throw new Error("pthread bootstrap loaded before createBlenderModule");
  }
  if (globalThis.__bwPthreadMainScript) {
    throw new Error("pthread bootstrap installed more than once");
  }

  const state = {
    contract: CONTRACT,
    sourcePath: SOURCE_PATH,
    phase: "fetching",
    bytes: null,
    sha256: null,
    factoryCalls: 0,
    error: null,
  };
  globalThis.__bwPthreadMainScript = state;

  const blobReady = (async () => {
    try {
      const response = await fetch(SOURCE_PATH, {
        cache: "default",
        credentials: "same-origin",
        redirect: "error",
      });
      if (!response.ok || response.status !== 200) {
        throw new Error("worker source fetch failed with status " + response.status);
      }
      const responseUrl = new URL(response.url, location.href);
      if (responseUrl.origin !== location.origin ||
          responseUrl.pathname !== SOURCE_PATH || responseUrl.search || responseUrl.hash) {
        throw new Error("worker source resolved to a noncanonical URL");
      }
      const blob = await response.blob();
      if (!(blob instanceof Blob) || blob.size <= 0) {
        throw new Error("worker source response is empty");
      }
      const digest = new Uint8Array(await crypto.subtle.digest(
        "SHA-256", await blob.arrayBuffer()));
      state.bytes = blob.size;
      state.sha256 = Array.from(
        digest, (value) => value.toString(16).padStart(2, "0")).join("");
      state.phase = "ready";
      return blob;
    }
    catch (error) {
      state.phase = "error";
      state.error = String(error && error.message || error);
      throw error;
    }
  })();
  // The fetch begins before the later boot script calls the Module factory.
  // Mark the promise handled immediately so a fast network failure cannot emit
  // an unhandledrejection in that ordering window; the factory still awaits and
  // propagates the original rejection through the normal boot-failure path.
  void blobReady.catch(() => {});

  globalThis.createBlenderModule = async function createBlenderModuleWithWorkerBlob(config) {
    if (!config || typeof config !== "object" || Array.isArray(config)) {
      throw new TypeError("pthread bootstrap requires a Module configuration object");
    }
    if (Object.prototype.hasOwnProperty.call(config, "mainScriptUrlOrBlob")) {
      throw new Error("mainScriptUrlOrBlob was already supplied");
    }
    state.factoryCalls++;
    if (state.factoryCalls !== 1) {
      throw new Error("createBlenderModule called more than once");
    }
    config.mainScriptUrlOrBlob = await blobReady;
    return originalFactory(config);
  };
})();

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Public-bundle-only pthread bootstrap.  Emscripten normally starts every
// pthread from the full blender_browser.js URL.  The public assembler gives the
// page glue a content-addressed immutable URL.  Fetch that exact URL after the
// page factory has loaded: Chromium reuses the already-decoded response with no
// second origin body, and the same bytes become every pthread's in-memory Blob.
// This keeps page execution under CSP script-src 'self' while avoiding a second
// worker-source artifact on the critical wire.

"use strict";

(() => {
  const SOURCE_URL = "/bin/blender_browser.js?sha256=__BW_PAGE_GLUE_SHA256__";
  const SOURCE_PATH = "/bin/blender_browser.js";
  const CONTRACT = "pthread-main-script-cache-v2";
  const expectedDigest = SOURCE_URL.slice(SOURCE_URL.indexOf("sha256=") + 7);
  if (!/^\/[A-Za-z0-9._/-]+\?sha256=[0-9a-f]{64}$/.test(SOURCE_URL) ||
      !/^[0-9a-f]{64}$/.test(expectedDigest)) {
    throw new Error("pthread bootstrap source URL is not content-addressed");
  }
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
    sourceUrl: SOURCE_URL,
    phase: "fetching",
    bytes: null,
    sha256: null,
    factoryCalls: 0,
    error: null,
  };
  globalThis.__bwPthreadMainScript = state;

  const blobReady = (async () => {
    try {
      const response = await fetch(SOURCE_URL, {
        cache: "default",
        credentials: "same-origin",
        redirect: "error",
      });
      if (!response.ok || response.status !== 200) {
        throw new Error("worker source fetch failed with status " + response.status);
      }
      const responseUrl = new URL(response.url, location.href);
      if (responseUrl.origin !== location.origin ||
          responseUrl.pathname + responseUrl.search !== SOURCE_URL || responseUrl.hash) {
        throw new Error("worker source resolved to a noncanonical URL");
      }
      const blob = await response.blob();
      if (!(blob instanceof Blob) || blob.size <= 0) {
        throw new Error("worker source response is empty");
      }
      const digest = new Uint8Array(await crypto.subtle.digest(
        "SHA-256", await blob.arrayBuffer()));
      const actualDigest = Array.from(
        digest, (value) => value.toString(16).padStart(2, "0")).join("");
      if (actualDigest !== expectedDigest) {
        throw new Error("worker source identity differs from its content-addressed URL");
      }
      state.bytes = blob.size;
      state.sha256 = actualDigest;
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

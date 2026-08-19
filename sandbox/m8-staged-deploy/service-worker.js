// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Staged-bundle service worker. make_staged_bundle.sh replaces all three tokens
// below from the exact validated split inventory. Content-addressed deferred Wasm
// requests and every other exact launch asset except the registration control
// resource are cache-first after the explicit post-stage-1 precache. The control
// resource revalidates online and falls back to this exact cache offline, allowing
// an old controlled shell to discover a newly active worker. Every returned cached
// body is re-hashed before use.

"use strict";

const CACHE_VERSION = "__BW_CACHE_VERSION__";
const CACHE_PREFIX = "blender-web-staged-";
const CACHE_NAME = CACHE_PREFIX + CACHE_VERSION;
const PRECACHE_URLS = __BW_PRECACHE_URLS__;
const CACHE_FIRST_URLS = new Set(__BW_CACHE_FIRST_URLS__);
const CACHE_SHA256 = new Map(__BW_CACHE_SHA256__);

self.addEventListener("install", (event) => {
  // Do not fetch the 100+ MiB application during install: that would race the
  // first interactive boot. The page explicitly starts precaching post-stage-1.
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  // Do not claim clients until this version's exact cache has fully committed.
  // An interrupted update therefore leaves existing clients on the prior,
  // complete worker/cache instead of switching them to an empty new cache.
  event.waitUntil(Promise.resolve());
});

async function fetchCurrent(request) {
  const response = await fetch(request, {cache: "no-cache"});
  if (!response.ok) throw new Error(response.status + " " + request.url);
  return response;
}

function cacheKey(request) {
  const url = new URL(typeof request === "string" ? request : request.url, self.location.origin);
  return url.pathname + url.search;
}

async function verifiedResponse(request, response) {
  const key = cacheKey(request);
  const expected = CACHE_SHA256.get(key);
  if (!expected) throw new Error("no generated digest for cache key " + key);
  const bytes = await response.clone().arrayBuffer();
  const actual = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)))
    .map((value) => value.toString(16).padStart(2, "0")).join("");
  if (actual !== expected) throw new Error("cache body integrity mismatch for " + key);
  return response;
}

async function precache(source) {
  const cache = await caches.open(CACHE_NAME);
  let done = 0;
  let bytes = 0;
  for (const url of PRECACHE_URLS) {
    const request = new Request(url, {credentials: "same-origin"});
    // A completed cache must remain self-verifying while offline. A new deploy
    // has a new CACHE_NAME, so only same-version bytes can satisfy this lookup.
    const cached = await cache.match(request);
    const response = await verifiedResponse(request, cached || await fetchCurrent(request));
    const length = Number(response.headers.get("content-length")) || 0;
    if (!cached) await cache.put(request, response.clone());
    done++;
    bytes += length;
    if (source) source.postMessage({type: "BW_PRECACHE_PROGRESS", version: CACHE_VERSION,
                                   done, total: PRECACHE_URLS.length, bytes});
  }
  // Claim first: until this succeeds, old controlled clients still depend on
  // their prior complete cache for offline continuity.
  await self.clients.claim();
  const keys = await caches.keys();
  await Promise.all(keys.filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
    .map((key) => caches.delete(key)));
  if (source) source.postMessage({type: "BW_PRECACHE_DONE", version: CACHE_VERSION,
                                 done, total: PRECACHE_URLS.length, bytes});
}

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "BW_CACHE_IDENTITY") {
    const reply = event.ports && event.ports[0];
    if (reply) reply.postMessage({type: "BW_CACHE_IDENTITY", version: CACHE_VERSION,
      precacheUrls: PRECACHE_URLS, cacheFirstUrls: Array.from(CACHE_FIRST_URLS)});
    return;
  }
  if (!event.data || event.data.type !== "BW_PRECACHE") return;
  event.waitUntil(precache(event.source).catch((error) => {
    if (event.source) event.source.postMessage({type: "BW_PRECACHE_ERROR",
      version: CACHE_VERSION, error: String(error && error.message || error)});
    throw error;
  }));
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin ||
      request.headers.has("range")) return;
  event.respondWith((async () => {
    const logicalKey = url.pathname + url.search;
    if (CACHE_FIRST_URLS.has(logicalKey)) {
      const cache = await caches.open(CACHE_NAME);
      const cached = await cache.match(request);
      if (cached) {
        // CacheStorage is mutable same-origin state. Re-hash every returned body;
        // a URL-only memo would let a post-precache mutation false-green offline.
        return await verifiedResponse(request, cached);
      }
      const response = await verifiedResponse(request, await fetchCurrent(request));
      await cache.put(request, response.clone());
      return response;
    }
    try {
      // The generated control resource is intentionally absent from CACHE_FIRST:
      // an old worker must fetch the new registration bytes online. Other misses
      // also remain network-first. The exact current CACHE_NAME is the only
      // offline fallback, and every such cached body is re-hashed below.
      // `network-first` must bypass a fresh browser HTTP-cache entry too. In
      // particular, an old controlled shell cannot discover the newly active
      // worker if this stable registration URL reuses its old response bytes.
      return await fetchCurrent(request);
    }
    catch (networkError) {
      const cache = await caches.open(CACHE_NAME);
      const cached = await cache.match(request);
      if (cached) return await verifiedResponse(request, cached);
      if (request.mode === "navigate") {
        const fallback = await cache.match("/index.html");
        if (fallback) return await verifiedResponse("/index.html", fallback);
      }
      throw networkError;
    }
  })());
});

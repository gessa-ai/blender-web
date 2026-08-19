// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Browser-free two-version service-worker transition fixture. It binds the
// shipping source seams, then models the one cross-version case a single-version
// bundle verifier cannot exercise: an old controlled shell discovering the new
// register online while retaining its exact cached register offline.

"use strict";

import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {readFileSync} from "node:fs";

const ROOT = "/Users/paws/blender-web";
const SELF = `${ROOT}/sandbox/m8-staged-deploy`;
const assembler = readFileSync(`${SELF}/make_staged_bundle.sh`, "utf8");
const workerSource = readFileSync(`${SELF}/service-worker.js`, "utf8");
const registerSource = readFileSync(`${SELF}/service-worker-register.js`, "utf8");
const verifierSource = readFileSync(`${ROOT}/sandbox/m8-launch-gate/verify_m8.py`, "utf8");

const CONTROL = "/service-worker-register.js";
const OLD = "11111111111111111111";
const NEW = "22222222222222222222";
const PRECACHE = ["/", "/index.html", CONTROL, "/bin/deferred.wasm?sha256=abc"];

function sourceContract() {
  assert.match(assembler,
    /cache_first = \[url for url in precache if url != "\/service-worker-register\.js"\]/);
  assert.match(workerSource, /if \(CACHE_FIRST_URLS\.has\(logicalKey\)\)/);
  assert.match(workerSource, /return await fetchCurrent\(request\)/);
  assert.match(workerSource, /fetch\(request, \{cache: "no-cache"\}\)/);
  assert.doesNotMatch(workerSource, /return await fetch\(request\)/);
  assert.match(assembler,
    /\/service-worker-register\.js\n  Content-Type: text\/javascript; charset=utf-8\n  Cache-Control: no-cache, must-revalidate/);
  assert.match(workerSource,
    /const cache = await caches\.open\(CACHE_NAME\);[\s\S]*cache\.match\(request\)/);
  assert.match(registerSource, /active = registered\.active/);
  assert.match(registerSource, /currentIdentity\.version === EXPECTED_CACHE_VERSION/);
  assert.match(registerSource, /worker\.postMessage\(\{type: "BW_PRECACHE"\}\)/);
  assert.match(registerSource, /navigator\.serviceWorker\.controller !== worker/);
  const claim = workerSource.indexOf("await self.clients.claim();");
  const enumerateCaches = workerSource.indexOf("const keys = await caches.keys();");
  assert.ok(claim >= 0 && enumerateCaches > claim,
    "old caches must be enumerated/deleted only after the exact worker claims");
  assert.match(verifierSource,
    /url for url in expected_precache if url != "\/service-worker-register\.js"/);
  assert.match(verifierSource,
    /source\.count\('return await fetchCurrent\(request\);'\) == 1/);
  assert.match(verifierSource,
    /registration control resource can reuse the browser HTTP cache/);
}

function sha256(body) {
  return createHash("sha256").update(body).digest("hex");
}

function release(version) {
  const bodies = new Map([
    ["/", `index-${version}`],
    ["/index.html", `index-${version}`],
    [CONTROL, `const EXPECTED_CACHE_VERSION = "${version}";`],
    ["/bin/deferred.wasm?sha256=abc", `wasm-${version}`],
  ]);
  return {version, bodies,
    digests: new Map([...bodies].map(([url, body]) => [url, sha256(body)]))};
}

function makeWorker(releaseValue, populated) {
  return {
    version: releaseValue.version,
    release: releaseValue,
    cacheFirst: new Set(PRECACHE.filter((url) => url !== CONTROL)),
    cache: populated ? new Map(releaseValue.bodies) : new Map(),
    claimed: false,
  };
}

function verified(worker, url, body) {
  assert.equal(sha256(body), worker.release.digests.get(url),
    `cached/network body identity mismatch for ${url}`);
  return body;
}

function route(worker, url, {online, origin, httpCache, revalidateControl = true}) {
  if (worker.cacheFirst.has(url)) {
    if (worker.cache.has(url)) {
      return {body: verified(worker, url, worker.cache.get(url)), source: "cache"};
    }
    if (!online) throw new Error(`offline cache miss: ${url}`);
    const body = verified(worker, url, origin.bodies.get(url));
    worker.cache.set(url, body);
    return {body, source: "network"};
  }
  if (online) {
    if (url === CONTROL && !revalidateControl && httpCache?.has(url)) {
      return {body: httpCache.get(url), source: "http-cache"};
    }
    if (url === CONTROL && httpCache) httpCache.set(url, origin.bodies.get(url));
    return {body: origin.bodies.get(url), source: "network"};
  }
  if (!worker.cache.has(url)) throw new Error(`offline fallback miss: ${url}`);
  return {body: verified(worker, url, worker.cache.get(url)), source: "cache-fallback"};
}

function expectedVersion(registerBody) {
  const match = /EXPECTED_CACHE_VERSION = "([0-9a-f]{20})"/.exec(registerBody);
  assert.ok(match, "registration bytes carry no exact version");
  return match[1];
}

function precacheAndClaim(active, origin, cacheRegistry, claimSucceeds = true) {
  const sequence = [];
  for (const url of PRECACHE) {
    const body = verified(active, url, origin.bodies.get(url));
    active.cache.set(url, body);
  }
  sequence.push("cache-committed");
  if (!claimSucceeds) {
    sequence.push("claim-failed");
    return sequence;
  }
  active.claimed = true;
  sequence.push("claimed");
  for (const version of [...cacheRegistry.keys()]) {
    if (version !== active.version) cacheRegistry.delete(version);
  }
  sequence.push("old-cache-deleted");
  return sequence;
}

function transitionSelfcheck() {
  const oldRelease = release(OLD);
  const newRelease = release(NEW);
  const oldWorker = makeWorker(oldRelease, true);
  const newWorker = makeWorker(newRelease, false);
  const caches = new Map([[OLD, oldWorker.cache], [NEW, newWorker.cache]]);
  const staleHttpCache = new Map([[CONTROL, oldRelease.bodies.get(CONTROL)]]);

  // The index may be old/cache-first, but its stable control-script request must
  // revalidate and therefore receives the new expected-version bytes online.
  const oldIndex = route(oldWorker, "/", {online: true, origin: newRelease});
  assert.deepEqual(oldIndex, {body: `index-${OLD}`, source: "cache"});
  // Negative sensitivity control: excluding the URL from CacheStorage is not
  // sufficient if the nested network fetch can reuse the browser HTTP cache.
  const unrevalidatedControl = route(oldWorker, CONTROL, {
    online: true, origin: newRelease, httpCache: staleHttpCache, revalidateControl: false,
  });
  assert.equal(unrevalidatedControl.source, "http-cache");
  assert.equal(expectedVersion(unrevalidatedControl.body), OLD);

  // The shipping `cache: no-cache` fetch revalidates and replaces those stale
  // HTTP-cache bytes with the new registration/version-discovery resource.
  const onlineControl = route(oldWorker, CONTROL, {
    online: true, origin: newRelease, httpCache: staleHttpCache,
  });
  assert.equal(onlineControl.source, "network");
  assert.equal(expectedVersion(onlineControl.body), newWorker.version);
  assert.equal(expectedVersion(staleHttpCache.get(CONTROL)), NEW);

  // The new registration bytes authenticate the newly active exact worker,
  // populate its complete current-version cache, claim, then retire the old cache.
  const sequence = precacheAndClaim(newWorker, newRelease, caches);
  assert.deepEqual(sequence, ["cache-committed", "claimed", "old-cache-deleted"]);
  assert.equal(newWorker.claimed, true);
  assert.deepEqual([...newWorker.cache.keys()].sort(), [...PRECACHE].sort());
  assert.deepEqual([...caches.keys()], [NEW]);

  // In a separate interrupted/offline path the old worker can still return its
  // exact cached register, and a failed claim must not delete that old cache.
  const retainedOld = makeWorker(oldRelease, true);
  const pendingNew = makeWorker(newRelease, false);
  const retainedCaches = new Map([[OLD, retainedOld.cache], [NEW, pendingNew.cache]]);
  const offlineControl = route(retainedOld, CONTROL, {online: false, origin: newRelease});
  assert.equal(offlineControl.source, "cache-fallback");
  assert.equal(expectedVersion(offlineControl.body), OLD);
  const failed = precacheAndClaim(pendingNew, newRelease, retainedCaches, false);
  assert.deepEqual(failed, ["cache-committed", "claim-failed"]);
  assert.equal(retainedCaches.has(OLD), true);

  // Adversarial policy regression: making CONTROL cache-first reproduces the
  // stale old-register/new-active mismatch this fixture exists to prevent.
  const regressed = makeWorker(oldRelease, true);
  regressed.cacheFirst.add(CONTROL);
  const staleControl = route(regressed, CONTROL, {online: true, origin: newRelease});
  assert.equal(staleControl.source, "cache");
  assert.notEqual(expectedVersion(staleControl.body), newWorker.version);

  // Offline fallback remains fail-closed on mutated cached control bytes.
  const corrupted = makeWorker(oldRelease, true);
  corrupted.cache.set(CONTROL, "corrupted-register");
  assert.throws(() => route(corrupted, CONTROL, {online: false, origin: newRelease}),
    /identity mismatch/);
}

sourceContract();
transitionSelfcheck();
console.log("M8_SW_UPDATE_TRANSITION_SELFCHECK_PASS positive=3 negative=4 versions=2");

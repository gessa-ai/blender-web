// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

import assert from "node:assert/strict";
import {createHash, webcrypto} from "node:crypto";
import {readFileSync} from "node:fs";
import {basename, resolve} from "node:path";
import vm from "node:vm";

const HERE = resolve(import.meta.dirname);
const loaderPath = resolve(process.argv[2] || `${HERE}/pthread-main-loader.js`);
const loaderSource = readFileSync(loaderPath, "utf8");
const settingsSource = readFileSync(
  resolve(HERE, "../../tools/emsdk/upstream/emscripten/src/settings.js"), "utf8");
const pthreadSource = readFileSync(
  resolve(HERE, "../../tools/emsdk/upstream/emscripten/src/lib/libpthread.js"), "utf8");
const cmakeSource = readFileSync(resolve(HERE, "../../patches/platform_wasm.cmake"), "utf8");
const ORIGIN = "https://fixture.invalid";
const SOURCE_PATH = "/bin/blender_browser.worker.js";
const WORKER_SOURCE = new TextEncoder().encode("self.fixtureWorker = true;\n");
const WORKER_SHA256 = createHash("sha256").update(WORKER_SOURCE).digest("hex");

const defaultIncomingMatch = settingsSource.match(
  /var INCOMING_MODULE_JS_API = \[([\s\S]*?)\n\];/,
);
assert(defaultIncomingMatch, "pinned Emscripten incoming Module defaults are absent");
const defaultIncoming = [...defaultIncomingMatch[1].matchAll(/'([^']+)'/g)]
  .map((match) => match[1]);
const cmakeIncomingMatches = [...cmakeSource.matchAll(
  /-sINCOMING_MODULE_JS_API=([A-Za-z0-9_,]+)/g,
)];
assert.equal(cmakeIncomingMatches.length, 1);
const cmakeIncoming = cmakeIncomingMatches[0][1].split(",");
assert.equal(new Set(cmakeIncoming).size, cmakeIncoming.length);
assert.equal(cmakeIncoming.filter((name) => name === "mainScriptUrlOrBlob").length, 1);
assert.deepEqual(
  cmakeIncoming.filter((name) => name !== "mainScriptUrlOrBlob"),
  defaultIncoming,
  "browser link must preserve every pinned Emscripten incoming Module default",
);
assert.equal((pthreadSource.match(/Module\['mainScriptUrlOrBlob'\]/g) || []).length, 4);
assert.equal((pthreadSource.match(/expectToReceiveOnModule\('mainScriptUrlOrBlob'\)/g) || []).length, 2);

function makeFixture(options = {}) {
  let fetchCalls = 0;
  let originalCalls = 0;
  const originalConfigs = [];
  const context = vm.createContext({
    Blob,
    URL,
    crypto: webcrypto,
    location: {href: `${ORIGIN}/index.html`, origin: ORIGIN},
    fetch: async (path, init) => {
      fetchCalls++;
      if (options.fetchError) throw new Error(options.fetchError);
      assert.equal(path, SOURCE_PATH);
      assert.equal(init.cache, "default");
      assert.equal(init.credentials, "same-origin");
      assert.equal(init.redirect, "error");
      assert.deepEqual(Object.keys(init).sort(), ["cache", "credentials", "redirect"]);
      return {
        ok: options.ok ?? true,
        status: options.status ?? 200,
        url: options.url ?? `${ORIGIN}${SOURCE_PATH}`,
        blob: async () => options.emptyBlob ? new Blob([]) :
          new Blob([WORKER_SOURCE], {type: "text/javascript"}),
      };
    },
  });
  if (!options.noFactory) {
    context.createBlenderModule = async (config) => {
      originalCalls++;
      originalConfigs.push(config);
      return {config};
    };
  }
  if (options.existingState) context.__bwPthreadMainScript = {phase: "forged"};
  return {
    context,
    install() {
      return vm.runInContext(loaderSource, context, {filename: basename(loaderPath)});
    },
    get fetchCalls() { return fetchCalls; },
    get originalCalls() { return originalCalls; },
    get originalConfigs() { return originalConfigs; },
  };
}

async function expectFactoryReject(options, pattern) {
  const fixture = makeFixture(options);
  fixture.install();
  await assert.rejects(fixture.context.createBlenderModule({}), pattern);
  assert.equal(fixture.originalCalls, 0);
  assert.equal(fixture.context.__bwPthreadMainScript.phase, "error");
  assert.match(fixture.context.__bwPthreadMainScript.error, pattern);
}

const positive = makeFixture();
positive.install();
const config = {canvas: "fixture"};
const result = await positive.context.createBlenderModule(config);
assert.equal(result.config, config);
assert.equal(positive.fetchCalls, 1);
assert.equal(positive.originalCalls, 1);
assert.equal(positive.originalConfigs[0], config);
assert(config.mainScriptUrlOrBlob instanceof Blob);
assert.equal(config.mainScriptUrlOrBlob.size, WORKER_SOURCE.byteLength);
assert.deepEqual(JSON.parse(JSON.stringify(positive.context.__bwPthreadMainScript)), {
  contract: "pthread-main-script-blob-v1",
  sourcePath: SOURCE_PATH,
  phase: "ready",
  bytes: WORKER_SOURCE.byteLength,
  sha256: WORKER_SHA256,
  factoryCalls: 1,
  error: null,
});
await assert.rejects(positive.context.createBlenderModule({}), /more than once/);
assert.equal(positive.fetchCalls, 1);
assert.equal(positive.originalCalls, 1);

for (const value of [null, [], "config"]) {
  const fixture = makeFixture();
  fixture.install();
  await assert.rejects(fixture.context.createBlenderModule(value), /configuration object/);
  assert.equal(fixture.originalCalls, 0);
}

const preconfigured = makeFixture();
preconfigured.install();
await assert.rejects(
  preconfigured.context.createBlenderModule({mainScriptUrlOrBlob: "forged"}),
  /already supplied/,
);
assert.equal(preconfigured.originalCalls, 0);

for (const [options, pattern] of [
  [{ok: false, status: 503}, /status 503/],
  [{url: "https://other.invalid/bin/blender_browser.worker.js"}, /noncanonical URL/],
  [{emptyBlob: true}, /response is empty/],
  [{fetchError: "network fixture"}, /network fixture/],
]) {
  await expectFactoryReject(options, pattern);
}

for (const options of [{noFactory: true}, {existingState: true}]) {
  const fixture = makeFixture(options);
  assert.throws(() => fixture.install(),
    options.noFactory ? /before createBlenderModule/ : /installed more than once/);
  assert.equal(fixture.fetchCalls, 0);
}

console.log(
  `M8_PTHREAD_MAIN_LOADER_CONTRACT_PASS source=${basename(loaderPath)} ` +
  "positive=10 negative=10 fetches=one identity=sha256 factory=singleton " +
  "link=emscripten-defaults+mainScriptUrlOrBlob",
);

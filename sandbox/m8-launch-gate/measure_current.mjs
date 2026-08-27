// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Cold current-bundle launch measurement at the pinned mid-laptop network profile.
// Uses a decoded canvas pixel-content gate; release builds need not retain a
// diagnostic presentBackbuffer log.

import {createRequire} from "module";
import {mkdirSync, readFileSync, writeFileSync} from "fs";
import {delimiter, dirname, isAbsolute, join, relative, resolve} from "path";
import {fileURLToPath} from "url";
import {
  BOOT_CRITICAL_URLS, canonicalBundleDigest, collectArtifacts, loadArtifactContract,
  requireServedBundle,
} from "./bundle_identity.mjs";
import {
  bindRuntimeVersion, browserIdentityContract, collectBrowserRuntimeIdentity, legacySigning,
  requireEmptyEarlyDiagnostics, requireHardwareRuntimeAdapter, revalidateBrowserRuntimeIdentity,
} from "./runtime_evidence.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..");
const NODE_VERSION = "v22.16.0";
const PLAYWRIGHT_VERSION = "1.61.1";
const PNGJS_VERSION = "7.0.0";
const LOCAL_MODULE_ROOTS = Object.freeze([
  join(ROOT, ".m4-node/node_modules"),
  join(ROOT, "node_modules"),
]);
const MODULE_ROOTS = Object.freeze([...new Set([
  process.env.BW_NODE_MODULES,
  process.env.NODE_PATH,
  ...LOCAL_MODULE_ROOTS,
].filter(Boolean).flatMap((entry) => entry.split(delimiter)).filter(Boolean)
  .map((entry) => resolve(entry)))]);

function requireNodeVersion(version = process.version) {
  if (version !== NODE_VERSION) throw new Error(`Node ${NODE_VERSION} required, got ${version}`);
}

function resolveBrowserDependencies(
  roots = MODULE_ROOTS,
  load = (root) => {
    const require = createRequire(join(root, "package.json"));
    return {
      chromium: require("playwright").chromium,
      playwrightVersion: require("playwright/package.json").version,
      PNG: require("pngjs").PNG,
      pngjsVersion: require("pngjs/package.json").version,
    };
  },
) {
  const failures = [];
  for (const root of roots) {
    try {
      const loaded = load(root);
      if (!loaded?.chromium || !loaded?.PNG) throw new Error("browser dependency exports are absent");
      if (loaded.playwrightVersion !== PLAYWRIGHT_VERSION || loaded.pngjsVersion !== PNGJS_VERSION) {
        throw new Error(`versions playwright=${loaded.playwrightVersion} pngjs=${loaded.pngjsVersion}`);
      }
      return {...loaded, root};
    }
    catch (error) {
      failures.push(`${root}: ${error.message}`);
    }
  }
  throw new Error(`cannot resolve exact browser dependencies; set BW_NODE_MODULES\n${failures.join("\n")}`);
}

function isRepositoryDescendant(path) {
  const rel = relative(ROOT, resolve(path));
  return rel !== "" && !isAbsolute(rel) && rel.split(/[\\/]/)[0] !== "..";
}

function parseInvocation(argv = process.argv.slice(2)) {
  if (argv.length === 1 && argv[0] === "--selfcheck") return {selfcheck: true};
  if (argv.length > 3) throw new Error("too many arguments");
  const portText = argv[0] || "8168";
  const executable = argv[1] || "";
  const runsText = argv[2] || "3";
  const port = Number.parseInt(portText, 10);
  const runs = Number.parseInt(runsText, 10);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535 || String(port) !== portText) {
    throw new Error(`invalid port: ${portText}`);
  }
  if (!executable || !isAbsolute(executable)) {
    throw new Error("usage: measure_current.mjs PORT /absolute/path/to/canonical-branded-chrome [RUNS]");
  }
  if (!Number.isSafeInteger(runs) || runs < 3 || String(runs) !== runsText) {
    throw new Error("at least 3 integer cold runs are required");
  }
  return {selfcheck: false, port, executable, runs};
}

function bundleArtifactForPath(path, bundleNames) {
  if (typeof path !== "string" || !path.startsWith("/")) return null;
  const artifact = path.slice(1);
  return bundleNames.includes(artifact) ? artifact : null;
}

function analyzeCriticalTransport(
  requests, semanticInteractionMs, mandatoryPaths, bundleNames, mainGlueUrl,
) {
  const failures = [];
  if (!Number.isFinite(semanticInteractionMs)) {
    return {criticalPaths: [], failures: ["semantic interaction timestamp is absent or invalid"]};
  }
  if (!Array.isArray(requests)) {
    return {criticalPaths: [], failures: ["same-origin request evidence is absent"]};
  }
  const critical = [];
  for (let index = 0; index < requests.length; index++) {
    const row = requests[index];
    if (!row || typeof row !== "object" || Array.isArray(row)) {
      failures.push(`same-origin request ${index} is not an object`);
      continue;
    }
    if (!Number.isFinite(row.at_ms) || row.at_ms < 0) {
      failures.push(`same-origin request ${index} has an invalid timestamp`);
      continue;
    }
    if (row.at_ms <= semanticInteractionMs) critical.push(row);
  }

  const criticalPaths = [];
  const seen = new Map();
  const bundle = new Set(bundleNames);
  for (let index = 0; index < critical.length; index++) {
    const row = critical[index];
    const path = row.path;
    if (typeof path !== "string") {
      failures.push(`critical request ${index} has no URL path`);
      continue;
    }
    const count = (seen.get(path) || 0) + 1;
    seen.set(path, count);
    if (count === 1) criticalPaths.push(path);
    if (path === "/bin/blender_browser.js") {
      if (count > 2) failures.push(`page glue has more than its script+fetch consumers: ${count}`);
      if (row.url !== mainGlueUrl) {
        failures.push(`page glue request is not the exact content-addressed URL: ${row.url}`);
      }
    }
    else {
      if (count > 1) failures.push(`critical request path was fetched more than once: ${path}`);
      if (row.url !== path) failures.push(`critical request has a query or noncanonical URL: ${row.url}`);
    }
    if (row.method !== "GET") failures.push(`critical request is not GET: ${path}`);
    const parts = path.replace(/^\//, "").split("/");
    const canonical = path.startsWith("/") && !path.endsWith("/") &&
      parts.every((part) => part !== "" && part !== "." && part !== "..") &&
      /^\/[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(path);
    if (!canonical) failures.push(`critical URL path is not canonical: ${path}`);
    const artifact = canonical ? path.slice(1) : null;
    if (row.bundle_artifact !== artifact) {
      failures.push(`critical response does not map to its exact bundle artifact: ${path}`);
    }
    if (artifact?.endsWith(".br")) {
      failures.push(`critical request targets a transport sibling directly: ${path}`);
    }
    else if (!artifact || !bundle.has(artifact)) {
      failures.push(`critical request does not map to a bundle artifact: ${path}`);
    }
    else if (!bundle.has(`${artifact}.br`)) {
      failures.push(`critical bundle artifact has no Brotli wire sibling: ${path}`);
    }
    if (row.response_count !== 1) failures.push(`critical request response count is not one: ${path}`);
    if (row.response_url !== row.url) failures.push(`critical response URL differs from its request: ${path}`);
    if (row.response_status !== 200) failures.push(`critical response status is not 200: ${path}`);
    if (row.content_encoding !== "br") failures.push(`critical response is not Brotli encoded: ${path}`);
  }
  criticalPaths.sort();
  if (seen.get("/bin/blender_browser.js") !== 2) {
    failures.push("page glue did not have exactly one script and one cached fetch consumer");
  }
  const missing = [...new Set(mandatoryPaths)].filter((path) => !seen.has(path)).sort();
  if (missing.length) failures.push(`mandatory critical paths are absent: ${JSON.stringify(missing)}`);
  return {criticalPaths, failures};
}

function analyzePthreadBlobTransport(
  workers, proof, semanticInteractionMs, expected, sourceUrl, baseOrigin,
) {
  const failures = [];
  if (!proof || typeof proof !== "object" || Array.isArray(proof)) {
    return ["pthread Blob bootstrap proof is absent"];
  }
  if (proof.contract !== "pthread-main-script-cache-v2" ||
      proof.sourcePath !== "/bin/blender_browser.js" || proof.sourceUrl !== sourceUrl ||
      proof.phase !== "ready") {
    failures.push("pthread Blob bootstrap contract is invalid");
  }
  if (!expected || proof.bytes !== expected.bytes || proof.sha256 !== expected.sha256) {
    failures.push("pthread Blob source identity differs from the public bundle artifact");
  }
  if (proof.factoryCalls !== 1 || proof.error !== null) {
    failures.push("pthread Blob factory accounting is invalid");
  }
  if (!Array.isArray(workers) || workers.length < 9) {
    return [...failures, "fewer than the proxied-main plus eight pool Blob workers were observed"];
  }
  const urls = new Set();
  let initialWorkers = 0;
  for (let index = 0; index < workers.length; index++) {
    const row = workers[index];
    if (!row || typeof row !== "object" || Array.isArray(row)) {
      failures.push(`pthread Blob worker ${index} is invalid`);
      continue;
    }
    if (row.protocol !== "blob:" || row.origin !== baseOrigin ||
        typeof row.url !== "string" || !row.url.startsWith(`blob:${baseOrigin}/`)) {
      failures.push(`pthread Blob worker ${index} escaped the exact page origin`);
    }
    if (row.kind !== "dedicated-worker") {
      failures.push(`pthread Blob worker ${index} is not a dedicated worker`);
    }
    if (!Number.isFinite(row.at_ms) || row.at_ms < 0) {
      failures.push(`pthread Blob worker ${index} has an invalid timestamp`);
    }
    else if (Number.isFinite(semanticInteractionMs) && row.at_ms <= semanticInteractionMs) {
      initialWorkers++;
    }
    if (urls.has(row.url)) failures.push(`pthread Blob URL was reused: ${row.url}`);
    urls.add(row.url);
  }
  if (initialWorkers < 9) {
    failures.push("proxied-main plus eight pool Blob workers were not ready before interaction");
  }
  return failures;
}

function analyzePthreadSourceCache(proof, expectedUrl, expectedIdentity) {
  const failures = [];
  if (!proof || typeof proof !== "object" || Array.isArray(proof)) {
    return ["pthread page-glue cache proof is absent"];
  }
  if (proof.contract !== "pthread-page-glue-http-cache-v1" ||
      proof.source_url !== expectedUrl || proof.source_path !== "/bin/blender_browser.js") {
    failures.push("pthread page-glue cache contract is invalid");
  }
  if (proof.origin_request_count !== 1) {
    failures.push(`page glue transferred ${proof.origin_request_count} origin bodies instead of one`);
  }
  const entries = proof.resource_entries;
  if (!Array.isArray(entries) || entries.length !== 2) {
    return [...failures, "page glue does not have exactly two resource timing entries"];
  }
  const initiators = entries.map((entry) => entry?.initiator_type).sort();
  if (JSON.stringify(initiators) !== JSON.stringify(["fetch", "script"])) {
    failures.push("page glue consumers are not exactly one script plus one fetch");
  }
  let transferred = 0;
  let cached = 0;
  for (let index = 0; index < entries.length; index++) {
    const entry = entries[index];
    if (!entry || entry.name !== expectedUrl ||
        !Number.isFinite(entry.transfer_size) || entry.transfer_size < 0 ||
        !Number.isFinite(entry.decoded_body_size) ||
        entry.decoded_body_size !== expectedIdentity?.bytes) {
      failures.push(`page glue resource timing entry ${index} is invalid`);
      continue;
    }
    if (entry.transfer_size === 0) cached++;
    else transferred++;
  }
  if (transferred !== 1 || cached !== 1) {
    failures.push(`page glue cache reuse is not one transfer plus one hit: ${transferred}/${cached}`);
  }
  return failures;
}

function originRequestDelta(cumulative, baseline) {
  if (!Number.isSafeInteger(cumulative) || cumulative < 0 ||
      !Number.isSafeInteger(baseline) || baseline < 0 || cumulative < baseline) {
    return {count: null, next: baseline};
  }
  return {count: cumulative - baseline, next: cumulative};
}

async function readMainOriginCount(base, expectedBundleDigest, fetcher = fetch) {
  const response = await fetcher(`${base}/.well-known/bw-transport-proof`, {cache: "no-store"});
  if (!response.ok) throw new Error(`transport proof fetch failed with ${response.status}`);
  const proof = await response.json();
  if (proof?.schema !== 1 || proof?.served_bundle_sha256 !== expectedBundleDigest) {
    throw new Error("transport proof is not bound to the measured public bundle");
  }
  const count = proof?.asset_get_counts?.["/bin/blender_browser.js"] ?? 0;
  if (!Number.isSafeInteger(count) || count < 0) {
    throw new Error("transport proof has an invalid page-glue origin count");
  }
  return count;
}

async function officialChromeVersion(platform, fetcher = fetch) {
  const apiPlatform = platform === "darwin" ? "mac" : platform === "linux" ? "linux" : null;
  if (!apiPlatform) throw new Error(`unsupported Chrome release platform: ${platform}`);
  const source = `https://versionhistory.googleapis.com/v1/chrome/platforms/${apiPlatform}/channels/stable/versions?page_size=1`;
  const response = await fetcher(source);
  if (!response.ok) throw new Error(`Chrome version lookup ${response.status}`);
  const body = await response.json();
  const version = body?.versions?.[0]?.version;
  if (!/^[0-9]+(?:\.[0-9]+){3}$/.test(version || "")) {
    throw new Error("Chrome stable API returned no canonical version");
  }
  return {version, source};
}

async function runSelfcheck() {
  let positive = 0;
  let negative = 0;
  const check = (condition, message) => {
    if (!condition) throw new Error(`M8 performance self-check: ${message}`);
    positive++;
  };
  const reject = async (name, action) => {
    try { await action(); }
    catch (_) { negative++; return; }
    throw new Error(`M8 performance self-check false green: ${name}`);
  };

  check(readFileSync(join(ROOT, "GOAL.md"), "utf8").length > 0,
    "repository root is not producer-derived");
  check(MODULE_ROOTS.every(isAbsolute) && new Set(MODULE_ROOTS).size === MODULE_ROOTS.length,
    "module roots are not absolute and unique");
  check(LOCAL_MODULE_ROOTS.every((root) => MODULE_ROOTS.includes(root) && isRepositoryDescendant(root)),
    "repository-local module fallbacks are incomplete or escaped");
  check(BOOT_CRITICAL_URLS.length === 11 && new Set(BOOT_CRITICAL_URLS).size === 11 &&
    BOOT_CRITICAL_URLS.every((path) => path.startsWith("/")),
  "boot-critical transport inventory is incomplete or ambiguous");
  requireNodeVersion();
  check(true, "exact Node acceptance");
  await reject("wrong_node", () => requireNodeVersion("v25.1.0"));

  const chromiumToken = {};
  const pngToken = {};
  const synthetic = resolveBrowserDependencies(["/missing", "/fixture/modules"], (root) => {
    if (root === "/missing") throw new Error("fixture miss");
    return {chromium: chromiumToken, PNG: pngToken,
      playwrightVersion: PLAYWRIGHT_VERSION, pngjsVersion: PNGJS_VERSION};
  });
  check(synthetic.chromium === chromiumToken && synthetic.PNG === pngToken &&
    synthetic.root === "/fixture/modules", "dependency fallback drifted");
  await reject("wrong_playwright", () => resolveBrowserDependencies(["/fixture"], () => ({
    chromium: chromiumToken, PNG: pngToken,
    playwrightVersion: "1.61.0", pngjsVersion: PNGJS_VERSION,
  })));
  await reject("wrong_pngjs", () => resolveBrowserDependencies(["/fixture"], () => ({
    chromium: chromiumToken, PNG: pngToken,
    playwrightVersion: PLAYWRIGHT_VERSION, pngjsVersion: "6.0.0",
  })));
  await reject("missing_exports", () => resolveBrowserDependencies(["/fixture"], () => ({
    playwrightVersion: PLAYWRIGHT_VERSION, pngjsVersion: PNGJS_VERSION,
  })));

  const linuxContract = browserIdentityContract("chrome", "linux");
  const darwinContract = browserIdentityContract("chrome", "darwin");
  check(linuxContract.executablePath === "/opt/google/chrome/chrome" &&
    linuxContract.packageName === "google-chrome-stable", "Linux Chrome identity contract drifted");
  check(darwinContract.identifier === "com.google.Chrome" && darwinContract.team === "EQHXZ8M8AV",
    "Darwin Chrome identity contract drifted");

  const urls = [];
  const fakeFetch = async (url) => {
    urls.push(url);
    return {ok: true, json: async () => ({versions: [{version: "151.0.7922.173"}]})};
  };
  const linux = await officialChromeVersion("linux", fakeFetch);
  const darwin = await officialChromeVersion("darwin", fakeFetch);
  check(linux.version === darwin.version && linux.source.includes("/platforms/linux/") &&
    darwin.source.includes("/platforms/mac/"), "platform Chrome release selection drifted");
  check(urls.length === 2, "release selector request count drifted");
  await reject("unsupported_platform", () => officialChromeVersion("win32", fakeFetch));
  await reject("missing_release", () => officialChromeVersion("linux", async () => ({
    ok: true, json: async () => ({versions: []}),
  })));
  await reject("http_failure", () => officialChromeVersion("linux", async () => ({
    ok: false, status: 503,
  })));

  const parsed = parseInvocation(["8168", "/fixture/chrome", "4"]);
  check(parsed.port === 8168 && parsed.executable === "/fixture/chrome" && parsed.runs === 4,
    "invocation parser drifted");
  check(parseInvocation(["8168", "/fixture/chrome"]).runs === 3, "default run count drifted");
  for (const [name, args] of [
    ["missing_executable", ["8168"]],
    ["relative_executable", ["8168", "fixture/chrome"]],
    ["invalid_port", ["8168junk", "/fixture/chrome"]],
    ["out_of_range_port", ["65536", "/fixture/chrome"]],
    ["too_few_runs", ["8168", "/fixture/chrome", "2"]],
    ["invalid_runs", ["8168", "/fixture/chrome", "3junk"]],
    ["extra_argument", ["8168", "/fixture/chrome", "3", "extra"]],
  ]) await reject(name, () => parseInvocation(args));

  const mandatoryTransport = [...BOOT_CRITICAL_URLS, "/bin/blender_browser.wasm"].sort();
  const transportBundle = mandatoryTransport.flatMap((path) => [path.slice(1), `${path.slice(1)}.br`]);
  const mainGlueUrl = `/bin/blender_browser.js?sha256=${"c".repeat(64)}`;
  const transportRow = (url, at_ms, overrides = {}) => {
    const path = overrides.path || url.split("?", 1)[0];
    return {url, path, method: "GET", at_ms,
      bundle_artifact: bundleArtifactForPath(path, [...transportBundle, ...(overrides.bundleNames || [])]),
      response_count: 1, response_url: url, response_status: 200, content_encoding: "br",
      ...overrides};
  };
  const observedTransport = mandatoryTransport.map((path, index) =>
    transportRow(path === "/bin/blender_browser.js" ? mainGlueUrl : path, 10 + index,
      {path}));
  observedTransport.push(transportRow(mainGlueUrl, 30, {path: "/bin/blender_browser.js"}));
  observedTransport.push(transportRow(
    `/bin/blender_browser.deferred.wasm?sha256=${"b".repeat(64)}`, 101,
    {path: "/bin/blender_browser.deferred.wasm",
      bundleNames: ["bin/blender_browser.deferred.wasm"]}));
  const transportPositive = analyzeCriticalTransport(
    observedTransport, 100, mandatoryTransport, transportBundle, mainGlueUrl);
  check(transportPositive.failures.length === 0 &&
    JSON.stringify(transportPositive.criticalPaths) === JSON.stringify(mandatoryTransport),
  "observed critical transport does not preserve the mandatory request set");
  const extra = transportRow("/extra.js", 90, {bundleNames: ["extra.js"]});
  const dynamicTransport = analyzeCriticalTransport(
    [...observedTransport, extra], 100, mandatoryTransport,
    [...transportBundle, "extra.js", "extra.js.br"], mainGlueUrl);
  check(dynamicTransport.failures.length === 0 && dynamicTransport.criticalPaths.includes("/extra.js"),
    "an observed early bundle response is not counted dynamically");
  for (const [name, rows, bundle] of [
    ["unknown_early_response", [...observedTransport, extra], transportBundle],
    ["duplicate_early_response", [...observedTransport,
      observedTransport.find((row) => row.path !== "/bin/blender_browser.js")], transportBundle],
    ["queried_early_response", [...observedTransport,
      transportRow("/extra.js?v=1", 90, {path: "/extra.js", bundleNames: ["extra.js"]})],
     [...transportBundle, "extra.js", "extra.js.br"]],
    ["missing_early_response", [...observedTransport, {...extra, response_count: 0}],
     [...transportBundle, "extra.js", "extra.js.br"]],
  ]) {
    const result = analyzeCriticalTransport(rows, 100, mandatoryTransport, bundle, mainGlueUrl);
    if (result.failures.length) negative++;
    else throw new Error(`M8 performance self-check false green: ${name}`);
  }

  const blobOrigin = "https://fixture.invalid";
  const blobExpected = {bytes: 1234, sha256: "c".repeat(64)};
  const blobProof = {contract: "pthread-main-script-cache-v2",
    sourcePath: "/bin/blender_browser.js", sourceUrl: mainGlueUrl, phase: "ready",
    bytes: blobExpected.bytes, sha256: blobExpected.sha256, factoryCalls: 1, error: null};
  const blobWorkers = Array.from({length: 9}, (_, index) => ({
    url: `blob:${blobOrigin}/${index}`, protocol: "blob:", origin: blobOrigin,
    kind: "dedicated-worker", at_ms: 20 + index,
  }));
  check(analyzePthreadBlobTransport(
    blobWorkers, blobProof, 100, blobExpected, mainGlueUrl, blobOrigin).length === 0,
  "pthread Blob transport rejected the exact in-memory worker closure");
  for (const [name, rows, proof] of [
    ["blob_missing_worker", blobWorkers.slice(1), blobProof],
    ["blob_http_scheme", blobWorkers.map((row, index) => index ? row :
      {...row, protocol: "http:"}), blobProof],
    ["blob_wrong_origin", blobWorkers.map((row, index) => index ? row :
      {...row, origin: "https://other.invalid"}), blobProof],
    ["blob_not_worker", blobWorkers.map((row, index) => index ? row :
      {...row, kind: "shared-worker"}), blobProof],
    ["blob_after_interaction", blobWorkers.map((row) => ({...row, at_ms: 101})), blobProof],
    ["blob_wrong_hash", blobWorkers, {...blobProof, sha256: "d".repeat(64)}],
    ["blob_factory_twice", blobWorkers, {...blobProof, factoryCalls: 2}],
  ]) {
    if (analyzePthreadBlobTransport(
      rows, proof, 100, blobExpected, mainGlueUrl, blobOrigin).length) negative++;
    else throw new Error(`M8 performance self-check false green: ${name}`);
  }
  const cacheProof = {contract: "pthread-page-glue-http-cache-v1",
    source_url: mainGlueUrl, source_path: "/bin/blender_browser.js", origin_request_count: 1,
    resource_entries: [
      {name: mainGlueUrl, initiator_type: "script", transfer_size: 123,
        decoded_body_size: blobExpected.bytes},
      {name: mainGlueUrl, initiator_type: "fetch", transfer_size: 0,
        decoded_body_size: blobExpected.bytes},
    ]};
  check(analyzePthreadSourceCache(cacheProof, mainGlueUrl, blobExpected).length === 0,
    "content-addressed page glue did not prove one origin body plus one cache hit");
  let cacheCountBaseline = 0;
  for (const cumulative of [1, 2, 3]) {
    const delta = originRequestDelta(cumulative, cacheCountBaseline);
    check(delta.count === 1 && delta.next === cumulative,
      "per-run origin request count was not isolated from cumulative server state");
    cacheCountBaseline = delta.next;
  }
  check(originRequestDelta(2, 3).count === null && originRequestDelta(-1, 0).count === null,
    "invalid cumulative origin request state did not fail closed");
  const transportProofDigest = "d".repeat(64);
  let transportProofCalls = 0;
  const transportProofCount = await readMainOriginCount(
    "https://fixture.invalid", transportProofDigest, async (url, options) => {
      transportProofCalls++;
      check(url === "https://fixture.invalid/.well-known/bw-transport-proof" &&
        options.cache === "no-store", "transport proof request is not exact/no-store");
      return {ok: true, status: 200, json: async () => ({schema: 1,
        served_bundle_sha256: transportProofDigest,
        asset_get_counts: {"/bin/blender_browser.js": 7}})};
    });
  check(transportProofCalls === 1 && transportProofCount === 7,
    "transport proof counter snapshot is not exact");
  for (const [name, proof] of [
    ["cache_two_origin_bodies", {...cacheProof, origin_request_count: 2}],
    ["cache_missing_entry", {...cacheProof, resource_entries: cacheProof.resource_entries.slice(1)}],
    ["cache_two_transfers", {...cacheProof, resource_entries:
      cacheProof.resource_entries.map((entry) => ({...entry, transfer_size: 123}))}],
    ["cache_wrong_identity", {...cacheProof, resource_entries:
      cacheProof.resource_entries.map((entry) => ({...entry, decoded_body_size: 99}))}],
  ]) {
    if (analyzePthreadSourceCache(proof, mainGlueUrl, blobExpected).length) negative++;
    else throw new Error(`M8 performance self-check false green: ${name}`);
  }

  const artifactRoot = resolve(HERE, "../m8-staged-deploy/artifacts");
  const output = join(artifactRoot, "measure_staged-4g.json");
  check(isRepositoryDescendant(artifactRoot) && dirname(output) === artifactRoot,
    "canonical receipt path escaped the repository");
  const source = readFileSync(fileURLToPath(import.meta.url), "utf8");
  check(!source.includes("/Users/" + "paws") &&
    source.includes("browserIdentityContract(\"chrome\", HOST_PLATFORM)") &&
    source.includes("officialChromeVersion(HOST_PLATFORM)"),
  "producer retains the old host root or bypasses a platform contract");

  let liveLibraryRoot = null;
  if (process.env.BW_NODE_MODULES || process.env.NODE_PATH) {
    const live = resolveBrowserDependencies();
    check(MODULE_ROOTS.includes(live.root) && live.playwrightVersion === PLAYWRIGHT_VERSION &&
      live.pngjsVersion === PNGJS_VERSION, "live browser dependency resolution drifted");
    liveLibraryRoot = live.root;
  }
  console.log(`M8_PERFORMANCE_SELFCHECK_PASS positive=${positive} negative=${negative} ` +
    `platforms=darwin+linux node=${NODE_VERSION} playwright=${PLAYWRIGHT_VERSION} ` +
    `pngjs=${PNGJS_VERSION} live=${liveLibraryRoot || "not-requested"} browser_launches=0`);
}

const invocation = parseInvocation();
if (invocation.selfcheck) {
  await runSelfcheck();
  process.exit(0);
}
requireNodeVersion();
const {chromium, PNG} = resolveBrowserDependencies();
const PORT = invocation.port;
const EXECUTABLE = invocation.executable;
const RUNS = invocation.runs;
const HOST_PLATFORM = process.platform;
const identityContract = browserIdentityContract("chrome", HOST_PLATFORM);
const BASE = `http://localhost:${PORT}`;
const ART = resolve(HERE, "../m8-staged-deploy/artifacts");
const OUT = join(ART, "measure_staged-4g.json");
if (!isRepositoryDescendant(ART) || dirname(OUT) !== ART) {
  throw new Error(`refusing receipt path outside the repository: ${OUT}`);
}
const collectedRuntimeIdentity = collectBrowserRuntimeIdentity(EXECUTABLE, identityContract);
const signing = legacySigning(collectedRuntimeIdentity);
const artifactContract = loadArtifactContract(ROOT);
const sourceArtifacts = collectArtifacts(artifactContract.buildBase, artifactContract.sourceNames);
const bundleArtifacts = collectArtifacts(artifactContract.bundleBase, artifactContract.bundleNames);
const expectedBundleDigest = canonicalBundleDigest(bundleArtifacts);

async function pixels(page) {
  const png = PNG.sync.read(await page.locator("#canvas").screenshot());
  let samples = 0, nonblack = 0;
  const colors = new Set();
  for (let y = 0; y < png.height; y += 8) {
    for (let x = 0; x < png.width; x += 8) {
      const i = (y * png.width + x) * 4;
      const r = png.data[i], g = png.data[i + 1], b = png.data[i + 2];
      samples++;
      if (r + g + b > 30) nonblack++;
      colors.add(`${r >> 3},${g >> 3},${b >> 3}`);
    }
  }
  return {width: png.width, height: png.height, nonblack_ratio: nonblack / samples,
          quantized_colors: colors.size,
          pass: png.width >= 1000 && png.height >= 600 && nonblack / samples > 0.1 && colors.size > 128};
}

function visualSignature(buffer) {
  const png = PNG.sync.read(buffer);
  const values = [];
  for (let y = 0; y < png.height; y += 8) {
    for (let x = 0; x < png.width; x += 8) {
      const i = (y * png.width + x) * 4;
      values.push((png.data[i] + png.data[i + 1] + png.data[i + 2]) / 3);
    }
  }
  return values;
}

function meanAbsDiff(a, b) {
  if (!a || !b || a.length !== b.length) return null;
  return a.reduce((total, value, index) => total + Math.abs(value - b[index]), 0) / a.length;
}

async function proveSemanticInteraction(page) {
  const bridgeReady = await page.evaluate(async () =>
    !!window.BWFileBridge && await window.BWFileBridge.ready());
  if (!bridgeReady) return {pass: false, semantic: false, visible_difference: null,
    scene: null, error: "file bridge not ready"};
  const scene = await page.evaluate(() => window.BWFileBridge?.inspectScene());
  const semantic = scene?.ok === true && scene?.active === "Cube" && scene?.meshVertices === 8 &&
    ["Camera", "Cube", "Light"].every((name) => scene.objects?.includes(name));
  const canvas = page.locator("#canvas");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(100);
  const box = await canvas.boundingBox();
  if (!box) return {pass: false, semantic, visible_difference: null, scene};
  const before = visualSignature(await canvas.screenshot());
  const x = box.x + box.width * 0.55, y = box.y + box.height * 0.5;
  await page.mouse.move(x - 30, y - 15);
  await page.mouse.down({button: "middle"});
  await page.mouse.move(x + 30, y + 15, {steps: 5});
  await page.mouse.up({button: "middle"});
  await page.waitForTimeout(100);
  const difference = meanAbsDiff(before, visualSignature(await canvas.screenshot()));
  return {pass: semantic && difference !== null && difference > 0.25,
    semantic, visible_difference: difference, scene};
}

const browser = await chromium.launch({executablePath: EXECUTABLE, headless: false});
const browserVersion = browser.version();
const runtimeIdentity = bindRuntimeVersion(collectedRuntimeIdentity, browserVersion);
const adapterContext = await browser.newContext();
let runtimeAdapter;
try {
  runtimeAdapter = await requireHardwareRuntimeAdapter(adapterContext, HOST_PLATFORM);
}
catch (error) {
  await adapterContext.close().catch(() => {});
  await browser.close().catch(() => {});
  throw error;
}
await adapterContext.close();
const official = await officialChromeVersion(HOST_PLATFORM);
const rows = [];
const baseOrigin = new URL(BASE).origin;
const mandatoryCriticalPaths = [
  ...BOOT_CRITICAL_URLS, ...artifactContract.criticalWasmUrls,
].sort();
const mainGlueUrl = artifactContract.mainGlueUrl;
for (let run = 0; run < RUNS; run++) {
  const context = await browser.newContext({viewport: {width: 1280, height: 720}, deviceScaleFactor: 1});
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    downloadThroughput: 1.5 * 1e6,
    uploadThroughput: 0.75 * 1e6,
    latency: 40,
  });
  const encodings = {};
  const requestTimelineMs = {};
  const responseHeaderPromises = [];
  const wasmRequests = [];
  const sameOriginRequests = [];
  const sameOriginRequestRows = new Map();
  const responseCaptureFailures = [];
  const pthreadBlobWorkers = [];
  const nonWireBlobRequestEvents = [];
  const externalRequests = [];
  const pageErrors = [];
  const start = Date.now();
  const mainOriginRequestBaseline = await readMainOriginCount(BASE, expectedBundleDigest);
  context.on("request", (request) => {
    const url = new URL(request.url());
    const path = url.pathname;
    const at = Date.now() - start;
    if (url.protocol === "blob:") {
      nonWireBlobRequestEvents.push({url: request.url(), method: request.method(),
        resource_type: request.resourceType(), at_ms: at});
      return;
    }
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== baseOrigin) {
      externalRequests.push(request.url());
    }
    else {
      const row = {url: `${path}${url.search}`, path, method: request.method(),
        resource_type: request.resourceType(), at_ms: at,
        bundle_artifact: bundleArtifactForPath(path, artifactContract.bundleNames),
        response_count: 0, response_url: null, response_status: null, content_encoding: null};
      sameOriginRequests.push(row);
      sameOriginRequestRows.set(request, row);
      if (requestTimelineMs[path] === undefined) requestTimelineMs[path] = at;
    }
    if (/^\/bin\/blender_browser.*\.wasm(?:\.orig)?$/.test(path)) {
      wasmRequests.push({url: path + url.search, path, at_ms: at});
    }
  });
  page.on("worker", (worker) => {
    const rawUrl = worker.url();
    let protocol = null, origin = null;
    try {
      const parsed = new URL(rawUrl);
      protocol = parsed.protocol;
      origin = parsed.origin;
    }
    catch {}
    pthreadBlobWorkers.push({url: rawUrl, protocol, origin,
      kind: "dedicated-worker", at_ms: Date.now() - start});
  });
  page.on("pageerror", (error) => pageErrors.push(String(error && error.message || error)));
  page.on("crash", () => pageErrors.push("PAGE CRASH"));
  context.on("response", (response) => {
    const url = new URL(response.url());
    if (url.protocol === "blob:") return;
    if (url.origin !== baseOrigin) return;
    const path = url.pathname;
    const row = sameOriginRequestRows.get(response.request());
    if (!row) {
      responseCaptureFailures.push(`same-origin response has no captured request: ${path}${url.search}`);
      return;
    }
    row.response_count++;
    row.response_url = `${path}${url.search}`;
    row.response_status = response.status();
    responseHeaderPromises.push(response.allHeaders().then((headers) => {
      row.content_encoding = headers["content-encoding"] || null;
      if (encodings[path] === undefined) encodings[path] = row.content_encoding;
    }, (error) => {
      row.content_encoding = null;
      if (encodings[path] === undefined) encodings[path] = null;
      responseCaptureFailures.push(`response headers unavailable for ${path}: ${error?.message || error}`);
    }));
  });
  const navigationResponse = await page.goto(`${BASE}/index.html`,
    {waitUntil: "domcontentloaded", timeout: 60_000});
  const servedBundleSha256 = await requireServedBundle(navigationResponse, expectedBundleDigest);
  await page.waitForFunction(() => {
    const state = document.querySelector("#state");
    return state && state.textContent.includes("main loop (WM_main)") && window.__bwModule;
  }, null, {timeout: 300_000});
  const wm = Date.now() - start;
  let proof = null;
  for (let i = 0; i < 80; i++) {
    proof = await pixels(page);
    if (proof.pass) break;
    await page.waitForTimeout(250);
  }
  const fp = proof?.pass ? Date.now() - start : null;
  const interaction = proof?.pass ? await proveSemanticInteraction(page) : {pass: false};
  const semanticInteractionMs = interaction.pass ? Date.now() - start : null;
  // The phase claim is evidence only if every shipped shard was actually
  // observed.  Wait for dispatch (not the throttled body download), then require
  // one exact URL per finalizer-owned shipping row.
  const expectedShardRequests = artifactContract.shippedWasm.map((row) =>
    row.role === "deferred" ?
      `/bin/${row.filename}?sha256=${row.sha256}` : `/bin/${row.filename}`);
  const requestDeadline = Date.now() + 15_000;
  while (Date.now() < requestDeadline &&
         !expectedShardRequests.every((url) => wasmRequests.some((request) => request.url === url))) {
    await page.waitForTimeout(25);
  }
  const pthreadSourceCache = await page.evaluate(async (sourceUrl) => {
    const absolute = new URL(sourceUrl, location.href).href;
    const resourceEntries = performance.getEntriesByName(absolute).map((entry) => {
      const parsed = new URL(entry.name);
      return {
        name: parsed.pathname + parsed.search,
        initiator_type: entry.initiatorType,
        transfer_size: entry.transferSize,
        encoded_body_size: entry.encodedBodySize,
        decoded_body_size: entry.decodedBodySize,
      };
    });
    const response = await fetch("/.well-known/bw-transport-proof", {cache: "no-store"});
    if (!response.ok) throw new Error(`transport proof fetch failed with ${response.status}`);
    const origin = await response.json();
    return {
      contract: "pthread-page-glue-http-cache-v1",
      source_url: sourceUrl,
      source_path: "/bin/blender_browser.js",
      origin_request_count_total: origin?.asset_get_counts?.["/bin/blender_browser.js"] ?? null,
      resource_entries: resourceEntries,
    };
  }, mainGlueUrl);
  const originDelta = originRequestDelta(
    pthreadSourceCache.origin_request_count_total, mainOriginRequestBaseline);
  pthreadSourceCache.origin_request_count = originDelta.count;
  await Promise.all(responseHeaderPromises);
  const observedShardRequests = wasmRequests.map((request) => request.url).sort();
  const exactShardRequests = observedShardRequests.length === expectedShardRequests.length &&
    [...expectedShardRequests].sort().every((url, index) => url === observedShardRequests[index]);
  const observedCriticalWasm = artifactContract.shippedWasmUrls.filter((path) =>
    requestTimelineMs[path] !== undefined && semanticInteractionMs !== null &&
    requestTimelineMs[path] <= semanticInteractionMs);
  const criticalTransport = analyzeCriticalTransport(
    sameOriginRequests, semanticInteractionMs, mandatoryCriticalPaths,
    artifactContract.bundleNames, mainGlueUrl);
  criticalTransport.failures.push(...responseCaptureFailures);
  const pthreadBlobProof = await page.evaluate(() => {
    const state = globalThis.__bwPthreadMainScript;
    return state ? {...state} : null;
  });
  const pthreadBlobFailures = analyzePthreadBlobTransport(
    pthreadBlobWorkers, pthreadBlobProof, semanticInteractionMs,
    bundleArtifacts["bin/blender_browser.js"], mainGlueUrl, baseOrigin);
  const pthreadSourceCacheFailures = analyzePthreadSourceCache(
    pthreadSourceCache, mainGlueUrl, bundleArtifacts["bin/blender_browser.js"]);
  const criticalPaths = criticalTransport.criticalPaths;
  const declaredCritical = [...artifactContract.criticalWasmUrls].sort();
  const observedCritical = [...observedCriticalWasm].sort();
  const bootCriticalPhaseValid = BOOT_CRITICAL_URLS.every((path) =>
    requestTimelineMs[path] !== undefined && semanticInteractionMs !== null &&
    requestTimelineMs[path] <= semanticInteractionMs);
  const manifestPhaseValid = exactShardRequests && bootCriticalPhaseValid &&
    JSON.stringify(declaredCritical) === JSON.stringify(observedCritical) &&
    artifactContract.shippedWasm.filter((row) => row.role === "deferred").every((row) =>
      semanticInteractionMs !== null &&
      wasmRequests.some((request) =>
        request.url === `/bin/${row.filename}?sha256=${row.sha256}` &&
        request.at_ms > semanticInteractionMs));
  const wireBr = criticalTransport.failures.length === 0 &&
    criticalPaths.every((path) => encodings[path] === "br");
  const earlyDiagnostics = await requireEmptyEarlyDiagnostics(page, `performance:cold-${run + 1}`);
  rows.push({wm, fp, pixel_proof: proof, semantic_interaction: interaction,
    semantic_interaction_ms: semanticInteractionMs, request_timeline_ms: requestTimelineMs,
    expected_shard_requests: [...expectedShardRequests].sort(),
    wasm_requests: wasmRequests,
    page_origin: baseOrigin, same_origin_requests: sameOriginRequests,
    pthread_blob_workers: pthreadBlobWorkers,
    non_wire_blob_request_events: nonWireBlobRequestEvents,
    pthread_blob_proof: pthreadBlobProof,
    pthread_blob_transport_valid: pthreadBlobFailures.length === 0,
    pthread_blob_transport_failures: pthreadBlobFailures,
    pthread_source_cache: pthreadSourceCache,
    pthread_source_cache_valid: pthreadSourceCacheFailures.length === 0,
    pthread_source_cache_failures: pthreadSourceCacheFailures,
    critical_paths: criticalPaths, manifest_phase_valid: manifestPhaseValid,
    critical_transport_valid: criticalTransport.failures.length === 0,
    critical_transport_failures: criticalTransport.failures,
    content_encoding: encodings, wire_brotli: wireBr,
    external_request_count: externalRequests.length, external_requests: externalRequests,
    page_error_count: pageErrors.length, page_errors: pageErrors,
    served_bundle_sha256: servedBundleSha256, early_diagnostics: earlyDiagnostics});
  console.log(`[m8-perf] run=${run + 1} wm=${wm}ms fp=${fp}ms ` +
    `semantic=${semanticInteractionMs}ms wireBr=${wireBr} ` +
    `critical=${criticalPaths.length} splitPhase=${manifestPhaseValid}`);
  await context.close();
}
await browser.close();
revalidateBrowserRuntimeIdentity(runtimeIdentity, identityContract);

const median = (values) => {
  const sorted = values.filter((value) => value !== null).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
const summary = {
  schema: 1,
  label: "staged-4g",
  port: PORT,
  runs: RUNS,
  at: new Date().toISOString(),
  browser: {channel: "chrome", executable: EXECUTABLE, version: browserVersion,
    official_version: official.version, official_version_source: official.source,
    current_at_test: browserVersion === official.version, signing,
    runtime_identity: runtimeIdentity, runtime_adapter: runtimeAdapter,
    checked_at: new Date().toISOString()},
  source_artifacts: sourceArtifacts,
  bundle_artifacts: bundleArtifacts,
  served_bundle_sha256: expectedBundleDigest,
  profile: {download_bytes_per_second: 1_500_000, upload_bytes_per_second: 750_000, latency_ms: 40},
  scenarios: {
    "cold-1.5mbps": {
      wm: rows.map((row) => row.wm),
      fp: rows.map((row) => row.fp),
      wm_median: median(rows.map((row) => row.wm)),
      fp_median: median(rows.map((row) => row.fp)),
      runs: rows,
    },
  },
};
mkdirSync(ART, {recursive: true});
writeFileSync(OUT, JSON.stringify(summary, null, 2) + "\n");
const pass = signing.valid && browserVersion === official.version && rows.length === RUNS &&
  rows.every((row) => row.fp !== null && row.pixel_proof?.pass === true && row.wire_brotli &&
    row.semantic_interaction?.pass === true && row.manifest_phase_valid === true &&
    row.critical_transport_valid === true &&
    row.pthread_blob_transport_valid === true && row.pthread_source_cache_valid === true &&
    row.external_request_count === 0 && row.page_error_count === 0 &&
    row.served_bundle_sha256 === expectedBundleDigest);
console.log(`M8_PERF_MEASURE_${pass ? "PASS" : "FAIL"} median=${summary.scenarios["cold-1.5mbps"].fp_median}ms -> ${OUT}`);
process.exit(pass ? 0 : 1);

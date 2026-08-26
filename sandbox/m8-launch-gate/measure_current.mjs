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
  check(BOOT_CRITICAL_URLS.length === 9 && new Set(BOOT_CRITICAL_URLS).size === 9 &&
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
const transportUrls = new Set([
  ...BOOT_CRITICAL_URLS, ...artifactContract.shippedWasmUrls,
]);
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
  const externalRequests = [];
  const pageErrors = [];
  const start = Date.now();
  context.on("request", (request) => {
    const url = new URL(request.url());
    const path = url.pathname;
    if (url.origin !== new URL(BASE).origin) externalRequests.push(request.url());
    if (transportUrls.has(path) && requestTimelineMs[path] === undefined) {
      requestTimelineMs[path] = Date.now() - start;
    }
    if (/^\/bin\/blender_browser.*\.wasm(?:\.orig)?$/.test(path)) {
      wasmRequests.push({url: path + url.search, path, at_ms: Date.now() - start});
    }
  });
  page.on("pageerror", (error) => pageErrors.push(String(error && error.message || error)));
  page.on("crash", () => pageErrors.push("PAGE CRASH"));
  context.on("response", async (response) => {
    const path = new URL(response.url()).pathname;
    if (transportUrls.has(path)) {
      responseHeaderPromises.push(response.allHeaders().then((headers) => {
        encodings[path] = headers["content-encoding"] || null;
      }, () => {
        encodings[path] = null;
      }));
    }
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
  await Promise.all(responseHeaderPromises);
  const observedShardRequests = wasmRequests.map((request) => request.url).sort();
  const exactShardRequests = observedShardRequests.length === expectedShardRequests.length &&
    [...expectedShardRequests].sort().every((url, index) => url === observedShardRequests[index]);
  const observedCriticalWasm = artifactContract.shippedWasmUrls.filter((path) =>
    requestTimelineMs[path] !== undefined && semanticInteractionMs !== null &&
    requestTimelineMs[path] <= semanticInteractionMs);
  const criticalPaths = [...BOOT_CRITICAL_URLS, ...observedCriticalWasm].sort();
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
  const wireBr = criticalPaths.every((path) => encodings[path] === "br");
  const earlyDiagnostics = await requireEmptyEarlyDiagnostics(page, `performance:cold-${run + 1}`);
  rows.push({wm, fp, pixel_proof: proof, semantic_interaction: interaction,
    semantic_interaction_ms: semanticInteractionMs, request_timeline_ms: requestTimelineMs,
    expected_shard_requests: [...expectedShardRequests].sort(),
    wasm_requests: wasmRequests,
    critical_paths: criticalPaths, manifest_phase_valid: manifestPhaseValid,
    content_encoding: encodings, wire_brotli: wireBr,
    external_request_count: externalRequests.length, external_requests: externalRequests,
    page_error_count: pageErrors.length, page_errors: pageErrors,
    served_bundle_sha256: servedBundleSha256, early_diagnostics: earlyDiagnostics});
  console.log(`[m8-perf] run=${run + 1} wm=${wm}ms fp=${fp}ms ` +
    `semantic=${semanticInteractionMs}ms wireBr=${wireBr} splitPhase=${manifestPhaseValid}`);
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
    row.external_request_count === 0 && row.page_error_count === 0 &&
    row.served_bundle_sha256 === expectedBundleDigest);
console.log(`M8_PERF_MEASURE_${pass ? "PASS" : "FAIL"} median=${summary.scenarios["cold-1.5mbps"].fp_median}ms -> ${OUT}`);
process.exit(pass ? 0 : 1);

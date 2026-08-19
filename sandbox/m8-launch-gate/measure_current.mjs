// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Cold current-bundle launch measurement at the pinned mid-laptop network profile.
// Uses a decoded canvas pixel-content gate; release builds need not retain a
// diagnostic presentBackbuffer log.

import {createRequire} from "module";
import {writeFileSync} from "fs";
import {
  canonicalBundleDigest, collectArtifacts, loadArtifactContract, requireServedBundle,
} from "./bundle_identity.mjs";
import {
  bindRuntimeVersion, collectBrowserRuntimeIdentity, legacySigning,
  requireEmptyEarlyDiagnostics, revalidateBrowserRuntimeIdentity,
} from "./runtime_evidence.mjs";

const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const {chromium} = require("playwright");
const {PNG} = require("pngjs");

const ROOT = "/Users/paws/blender-web";
const PORT = Number.parseInt(process.argv[2] || "8168", 10);
const EXECUTABLE = process.argv[3] || `${ROOT}/sandbox/m8-launch-gate/.browsers/Google Chrome.app/Contents/MacOS/Google Chrome`;
const RUNS = Number.parseInt(process.argv[4] || "3", 10);
if (!Number.isSafeInteger(RUNS) || RUNS < 3) throw new Error("at least 3 cold runs are required");
const BASE = `http://localhost:${PORT}`;
const OUT = `${ROOT}/sandbox/m8-staged-deploy/artifacts/measure_staged-4g.json`;
const artifactContract = loadArtifactContract(ROOT);
const sourceArtifacts = collectArtifacts(artifactContract.buildBase, artifactContract.sourceNames);
const bundleArtifacts = collectArtifacts(artifactContract.bundleBase, artifactContract.bundleNames);
const expectedBundleDigest = canonicalBundleDigest(bundleArtifacts);

const collectedRuntimeIdentity = collectBrowserRuntimeIdentity(EXECUTABLE,
  {identifier: "com.google.Chrome", team: "EQHXZ8M8AV"});
const signing = legacySigning(collectedRuntimeIdentity);

async function officialChromeVersion() {
  const source = "https://versionhistory.googleapis.com/v1/chrome/platforms/mac/channels/stable/versions?page_size=1";
  const response = await fetch(source);
  if (!response.ok) throw new Error(`Chrome version lookup ${response.status}`);
  const body = await response.json();
  return {version: body.versions[0].version, source};
}

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
const official = await officialChromeVersion();
const rows = [];
const transportUrls = new Set([
  "/bin/blender_browser.js", "/bin/blender_browser.data", ...artifactContract.shippedWasmUrls,
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
  const wasmRequests = [];
  const externalRequests = [];
  const pageErrors = [];
  const start = Date.now();
  page.on("request", (request) => {
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
  page.on("response", async (response) => {
    const path = new URL(response.url()).pathname;
    if (transportUrls.has(path)) {
      encodings[path] = (await response.allHeaders())["content-encoding"] || null;
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
  const observedShardRequests = wasmRequests.map((request) => request.url).sort();
  const exactShardRequests = observedShardRequests.length === expectedShardRequests.length &&
    [...expectedShardRequests].sort().every((url, index) => url === observedShardRequests[index]);
  const observedCriticalWasm = artifactContract.shippedWasmUrls.filter((path) =>
    requestTimelineMs[path] !== undefined && semanticInteractionMs !== null &&
    requestTimelineMs[path] <= semanticInteractionMs);
  const criticalPaths = ["/bin/blender_browser.js", "/bin/blender_browser.data", ...observedCriticalWasm];
  const declaredCritical = [...artifactContract.criticalWasmUrls].sort();
  const observedCritical = [...observedCriticalWasm].sort();
  const manifestPhaseValid = exactShardRequests &&
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
revalidateBrowserRuntimeIdentity(runtimeIdentity,
  {identifier: "com.google.Chrome", team: "EQHXZ8M8AV"});

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
    runtime_identity: runtimeIdentity, checked_at: new Date().toISOString()},
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
writeFileSync(OUT, JSON.stringify(summary, null, 2) + "\n");
const pass = signing.valid && browserVersion === official.version && rows.length === RUNS &&
  rows.every((row) => row.fp !== null && row.pixel_proof?.pass === true && row.wire_brotli &&
    row.semantic_interaction?.pass === true && row.manifest_phase_valid === true &&
    row.external_request_count === 0 && row.page_error_count === 0 &&
    row.served_bundle_sha256 === expectedBundleDigest);
console.log(`M8_PERF_MEASURE_${pass ? "PASS" : "FAIL"} median=${summary.scenarios["cold-1.5mbps"].fp_median}ms -> ${OUT}`);
process.exit(pass ? 0 : 1);

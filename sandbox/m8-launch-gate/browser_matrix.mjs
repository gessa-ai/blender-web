// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Run once with `chrome` and once with `edge` against the SAME staged bundle.
// Playwright's branded channels are required: bundled Chromium is not accepted as
// either launch browser. The receipt is merged only while source hashes stay exact.

import {createRequire} from "module";
import {existsSync, mkdirSync, readFileSync, writeFileSync} from "fs";
import {delimiter, dirname, join, resolve} from "path";
import {fileURLToPath} from "url";
import {
  canonicalBundleDigest, collectArtifacts, loadArtifactContract, requireServedBundle,
} from "./bundle_identity.mjs";
import {
  bindRuntimeVersion, browserIdentityContract, browserMatrixInvocationPass, browserMatrixRowPass,
  collectBrowserRuntimeIdentity, legacySigning,
  requireEmptyEarlyDiagnostics, revalidateBrowserRuntimeIdentity, validatePriorBrowserMatrix,
} from "./runtime_evidence.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..");
const OUT = join(HERE, "artifacts/current-browser-matrix.json");
const NODE_VERSION = "v22.16.0";
const PLAYWRIGHT_VERSION = "1.61.1";
const PNGJS_VERSION = "7.0.0";
const MODULE_ROOTS = Object.freeze([...new Set([
  process.env.BW_NODE_MODULES,
  process.env.NODE_PATH,
  join(ROOT, ".m4-node/node_modules"),
  join(ROOT, "node_modules"),
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

const PORT = Number.parseInt(process.argv[2] || "8168", 10);
const CHANNEL = process.argv[3] || "";
const EXECUTABLE = process.argv[4] || "";
const SELF_CHECK = process.argv.length === 3 && process.argv[2] === "--selfcheck";
const HOST_PLATFORM = process.platform;
if (SELF_CHECK) {
  await selfcheck();
  process.exit(0);
}
requireNodeVersion();
if (!new Set(["chrome", "edge"]).has(CHANNEL)) {
  throw new Error("usage: browser_matrix.mjs PORT chrome|edge /absolute/path/to/canonical-branded-executable");
}
if (!EXECUTABLE) {
  throw new Error("an explicit canonical branded executable is required for runtime identity verification");
}
if (!Number.isSafeInteger(PORT) || PORT < 1 || PORT > 65535) throw new Error(`invalid port: ${PORT}`);
const {chromium, PNG} = resolveBrowserDependencies();
const identityContract = browserIdentityContract(CHANNEL, HOST_PLATFORM);

async function officialVersion(channel, platform, fetcher = fetch) {
  if (channel === "chrome") {
    const apiPlatform = platform === "darwin" ? "mac" : platform === "linux" ? "linux" : null;
    if (!apiPlatform) throw new Error(`unsupported Chrome release platform: ${platform}`);
    const url = `https://versionhistory.googleapis.com/v1/chrome/platforms/${apiPlatform}/channels/stable/versions?page_size=1`;
    const response = await fetcher(url);
    if (!response.ok) throw new Error(`Chrome version lookup ${response.status}`);
    const body = await response.json();
    const version = body?.versions?.[0]?.version;
    if (!/^[0-9]+(?:\.[0-9]+){3}$/.test(version || "")) {
      throw new Error("Chrome stable API returned no canonical version");
    }
    return {version, source: url};
  }
  const url = "https://edgeupdates.microsoft.com/api/products?view=enterprise";
  const response = await fetcher(url);
  if (!response.ok) throw new Error(`Edge version lookup ${response.status}`);
  const body = await response.json();
  const stable = body.find((product) => product.Product === "Stable");
  const apiPlatform = platform === "darwin" ? "MacOS" : platform === "linux" ? "Linux" : null;
  if (!apiPlatform) throw new Error(`unsupported Edge release platform: ${platform}`);
  const releases = stable?.Releases?.filter((release) => release.Platform === apiPlatform)
    .sort((a, b) => Date.parse(b.PublishedTime) - Date.parse(a.PublishedTime));
  const version = releases?.[0]?.ProductVersion;
  if (!/^[0-9]+(?:\.[0-9]+){3}$/.test(version || "")) {
    throw new Error("Edge stable API returned no canonical platform version");
  }
  return {version, source: url};
}

async function selfcheck() {
  let positive = 0;
  let negative = 0;
  const check = (condition, message) => {
    if (!condition) throw new Error(`M8 browser matrix self-check: ${message}`);
    positive++;
  };
  const reject = async (name, action) => {
    try {
      await action();
    }
    catch (_) {
      negative++;
      return;
    }
    throw new Error(`M8 browser matrix self-check false green: ${name}`);
  };

  check(resolve(HERE, "..", "..") === ROOT && readFileSync(join(ROOT, "GOAL.md"), "utf8").length > 0,
    "repository root is not producer-derived");
  requireNodeVersion(NODE_VERSION);
  check(true, "exact Node acceptance");
  await reject("wrong_node", () => requireNodeVersion("v25.1.0"));
  const dependency = resolveBrowserDependencies(["/fixture/modules"], () => ({
    chromium: {}, PNG: {}, playwrightVersion: PLAYWRIGHT_VERSION, pngjsVersion: PNGJS_VERSION,
  }));
  check(dependency.root === "/fixture/modules", "dependency root mismatch");
  await reject("wrong_playwright", () => resolveBrowserDependencies(["/fixture/modules"], () => ({
    chromium: {}, PNG: {}, playwrightVersion: "1.61.0", pngjsVersion: PNGJS_VERSION,
  })));
  const chromeContract = browserIdentityContract("chrome", "linux");
  const edgeContract = browserIdentityContract("edge", "linux");
  check(chromeContract.executablePath === "/opt/google/chrome/chrome" &&
    edgeContract.executablePath === "/opt/microsoft/msedge/msedge", "Linux ELF contracts drifted");
  check(chromeContract.packageName === "google-chrome-stable" &&
    edgeContract.packageName === "microsoft-edge-stable", "Linux package contracts drifted");

  const urls = [];
  const fakeFetch = async (url) => {
    urls.push(url);
    return url.includes("versionhistory") ?
      {ok: true, json: async () => ({versions: [{version: "151.0.7922.173"}]})} :
      {ok: true, json: async () => ([{Product: "Stable", Releases: [
        {Platform: "MacOS", ProductVersion: "151.0.0.1", PublishedTime: "2026-08-19T00:00:00Z"},
        {Platform: "Linux", ProductVersion: "151.0.4129.92", PublishedTime: "2026-08-18T00:00:00Z"},
        {Platform: "Linux", ProductVersion: "151.0.4129.93", PublishedTime: "2026-08-20T00:00:00Z"},
      ]}])};
  };
  const chrome = await officialVersion("chrome", "linux", fakeFetch);
  const edge = await officialVersion("edge", "linux", fakeFetch);
  check(chrome.version === "151.0.7922.173" && chrome.source.includes("/platforms/linux/"),
    "Chrome Linux release selection drifted");
  check(edge.version === "151.0.4129.93", "Edge newest Linux release selection drifted");
  check(urls.length === 2 && urls.every((url) => !url.includes("platforms/mac/")),
    "self-check contacted a macOS release selector");
  await reject("unsupported_platform", () => officialVersion("chrome", "win32", fakeFetch));
  await reject("missing_release", () => officialVersion("edge", "linux", async () => ({
    ok: true, json: async () => [],
  })));
  const source = readFileSync(fileURLToPath(import.meta.url), "utf8");
  check(!source.includes("/Users/" + "paws") &&
    source.includes("browserIdentityContract(CHANNEL, HOST_PLATFORM)"),
    "producer retains a macOS root or bypasses the host identity contract");
  console.log(`M8_BROWSER_MATRIX_SELFCHECK_PASS positive=${positive} negative=${negative} ` +
    `platforms=darwin+linux node=${NODE_VERSION} playwright=${PLAYWRIGHT_VERSION} pngjs=${PNGJS_VERSION}`);
}

const collectedRuntimeIdentity = collectBrowserRuntimeIdentity(EXECUTABLE, identityContract);
const signing = legacySigning(collectedRuntimeIdentity);
const official = await officialVersion(CHANNEL, HOST_PLATFORM);
const artifactContract = loadArtifactContract(ROOT);
const sourceArtifacts = collectArtifacts(artifactContract.buildBase, artifactContract.sourceNames);
const bundleArtifacts = collectArtifacts(artifactContract.bundleBase, artifactContract.bundleNames);
const expectedBundleDigest = canonicalBundleDigest(bundleArtifacts);
mkdirSync(join(HERE, "artifacts"), {recursive: true});
const launchOptions = {headless: false, executablePath: EXECUTABLE};
const browser = await chromium.launch(launchOptions);
const actualVersion = browser.version();
const runtimeIdentity = bindRuntimeVersion(collectedRuntimeIdentity, actualVersion);
const context = await browser.newContext({viewport: {width: 1280, height: 720}, deviceScaleFactor: 1});
const page = await context.newPage();
const errors = [];
const requests = [];
let unsafeMarker = false;
page.on("request", (request) => requests.push(request.url()));
page.on("console", (message) => {
  const text = message.text();
  if (text.includes("M8_UNSAFE_QUERY_EXECUTED")) unsafeMarker = true;
  if (/GPU-ERROR|ValidationError|Dawn:\s/i.test(text)) errors.push(text.slice(0, 400));
});
page.on("pageerror", (error) => errors.push("pageerror: " + String(error && error.message || error)));
page.on("crash", () => errors.push("PAGE CRASH"));

const pyexpr = 'print("M8_UNSAFE_QUERY_EXECUTED")';
const url = `http://localhost:${PORT}/index.html?pyexpr=${encodeURIComponent(pyexpr)}` +
  `&args=${encodeURIComponent("--debug-gpu")}&gate=1x1&keepalive=0&ka_active=999999&stage1=manual`;
const start = Date.now();
const navigationResponse = await page.goto(url, {waitUntil: "domcontentloaded", timeout: 60_000});
const servedBundleSha256 = await requireServedBundle(navigationResponse, expectedBundleDigest);
await page.waitForFunction(() => {
  const el = document.querySelector("#state");
  return el && el.textContent.includes("main loop (WM_main)") && window.__bwModule;
}, null, {timeout: 240_000});
const wmMainMs = Date.now() - start;
await page.waitForFunction(() => {
  const stage = window.__bwStage1;
  return stage && stage.phase === "done" && !stage.error &&
    stage.filesDone === stage.filesTotal && stage.bytesDone === stage.bytesTotal;
}, null, {timeout: 600_000});
await page.waitForFunction(() => window.__bwServiceWorker?.phase === "done", null, {timeout: 600_000});
async function pixelGate() {
  const shot = await page.locator("#canvas").screenshot();
  const png = PNG.sync.read(shot);
  let samples = 0;
  let nonblack = 0;
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
async function visualSignature() {
  const png = PNG.sync.read(await page.locator("#canvas").screenshot());
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
  if (a.length !== b.length) return 0;
  let total = 0;
  for (let i = 0; i < a.length; i++) total += Math.abs(a[i] - b[i]);
  return total / a.length;
}
let pixels = null;
for (let i = 0; i < 40; i++) {
  pixels = await pixelGate();
  if (pixels.pass) break;
  await page.waitForTimeout(250);
}
const argv = await page.locator("#argv").textContent();
const publicControls = await page.evaluate(() => ({
  allowed: window.__bwDevHooksAllowed,
  keepalive: window.__bwKeepaliveConfig,
  canvas: [document.getElementById("canvas")?.width, document.getElementById("canvas")?.height],
  stage1: window.__bwStage1?.phase,
}));
const querySafe = !unsafeMarker && publicControls.allowed === false &&
  !argv.includes("--python-expr") && !argv.includes("--debug-gpu") &&
  publicControls.canvas[0] === 1280 && publicControls.canvas[1] === 720 &&
  publicControls.keepalive?.enabled === 1 && publicControls.keepalive?.active === 0 &&
  publicControls.keepalive?.idle === 0 &&
  publicControls.stage1 === "done";

const rect = await page.locator("#canvas").boundingBox();
const cx = rect ? rect.x + rect.width / 2 : 640;
const cy = rect ? rect.y + rect.height / 2 : 360;
const bridgeReady = await page.evaluate(() => window.BWFileBridge?.ready());
const initialScene = bridgeReady ? await page.evaluate(() => window.BWFileBridge.inspectScene()) : null;
await page.locator("#canvas").focus();
await page.keyboard.press("Escape"); // dismiss the real splash into the default workspace
await page.waitForTimeout(250);
const beforeInteraction = await visualSignature();
await page.mouse.move(cx - 25, cy - 15);
await page.mouse.down({button: "middle"});
await page.mouse.move(cx + 25, cy + 15, {steps: 4});
await page.mouse.up({button: "middle"});
await page.waitForTimeout(200);
const interactionPixelDifference = meanAbsDiff(beforeInteraction, await visualSignature());
await page.keyboard.press("Tab");
await page.keyboard.press("3");
await page.keyboard.press("e");
await page.keyboard.type("1");
await page.keyboard.press("Enter");
await page.keyboard.press("Tab");
const afterInput = bridgeReady ? await page.evaluate(() => window.BWFileBridge.inspectScene()) : null;
const liveAfterInput = await page.evaluate(() => Boolean(window.__bwModule &&
  document.querySelector("#state")?.textContent.includes("main loop (WM_main)"))) &&
  bridgeReady === true && initialScene?.ok === true && afterInput?.ok === true &&
  initialScene.objects.includes("Cube") && afterInput.mode === "OBJECT" &&
  afterInput.meshVertices > 8 && interactionPixelDifference > 0.5;
const onlineDiagnostics = await requireEmptyEarlyDiagnostics(page, `${CHANNEL}:online`);

await context.setOffline(true);
let offline = false;
let offlineDiagnostics = null;
try {
  await page.reload({waitUntil: "domcontentloaded", timeout: 60_000});
  await page.waitForFunction(() => {
    const el = document.querySelector("#state");
    return el && el.textContent.includes("main loop (WM_main)") && window.__bwModule && self.crossOriginIsolated;
  }, null, {timeout: 240_000});
  await page.keyboard.press("Escape");
  const offlineRect = await page.locator("#canvas").boundingBox();
  const offlineBefore = await visualSignature();
  if (offlineRect) {
    const ox = offlineRect.x + offlineRect.width * 0.45;
    const oy = offlineRect.y + offlineRect.height * 0.5;
    await page.mouse.move(ox, oy);
    await page.mouse.down({button: "middle"});
    await page.mouse.move(ox + 40, oy + 20, {steps: 4});
    await page.mouse.up({button: "middle"});
    await page.waitForTimeout(200);
  }
  const offlinePixels = await pixelGate();
  const offlineBridge = await page.evaluate(() => window.BWFileBridge?.ready());
  const offlineInteractionDifference = meanAbsDiff(offlineBefore, await visualSignature());
  offline = offlinePixels.pass === true && offlineBridge === true &&
    offlineRect !== null && offlineInteractionDifference > 0.5;
  offlineDiagnostics = await requireEmptyEarlyDiagnostics(page, `${CHANNEL}:offline-reload`);
}
finally {
  await context.setOffline(false);
}

const external = requests.filter((value) => {
  try { return new URL(value).origin !== new URL(`http://localhost:${PORT}`).origin; }
  catch (_) { return true; }
});
await context.close();
await browser.close();
revalidateBrowserRuntimeIdentity(runtimeIdentity, identityContract);
const checkedAt = new Date().toISOString();
const row = {
  channel: CHANNEL,
  executable: EXECUTABLE || `playwright-channel:${CHANNEL}`,
  actual_version: actualVersion,
  official_version: official.version,
  official_version_source: official.source,
  signing,
  runtime_identity: runtimeIdentity,
  early_diagnostics: {online: onlineDiagnostics, offline_reload: offlineDiagnostics},
  served_bundle_sha256: servedBundleSha256,
  checked_at: checkedAt,
  current_at_test: actualVersion === official.version,
  wm_main: true,
  wm_main_ms: wmMainMs,
  first_pixels: pixels?.pass === true,
  pixel_proof: pixels,
  interaction_smoke: liveAfterInput,
  interaction_proof: {bridge_ready: bridgeReady, initial_scene: initialScene,
    after_input: afterInput, pixel_mean_abs_diff: interactionPixelDifference,
    public_query_controls: publicControls},
  offline_reload: offline,
  query_hooks_disabled: querySafe,
  external_request_count: external.length,
  external_requests: external,
  gpu_errors: errors.length,
  errors,
};

let receipt = {schema: 1, source_artifacts: sourceArtifacts, bundle_artifacts: bundleArtifacts,
  served_bundle_sha256: expectedBundleDigest, engines: {}, verdict: "INCOMPLETE"};
const priorExists = existsSync(OUT);
if (priorExists) {
  const prior = JSON.parse(readFileSync(OUT, "utf8"));
  try {
    validatePriorBrowserMatrix(
      prior, CHANNEL, sourceArtifacts, bundleArtifacts, expectedBundleDigest,
      Object.keys(row), (identity, channel) => {
        revalidateBrowserRuntimeIdentity(identity, browserIdentityContract(channel, HOST_PLATFORM));
      });
    receipt.engines = prior.engines;
  }
  catch (error) {
    console.error(`M8_BROWSER_${CHANNEL.toUpperCase()}_FAIL prior=${String(error?.message || error)}`);
    process.exit(1);
  }
}
receipt.schema = 1;
receipt.source_artifacts = sourceArtifacts;
receipt.bundle_artifacts = bundleArtifacts;
receipt.served_bundle_sha256 = expectedBundleDigest;
receipt.engines[CHANNEL] = row;
receipt.updated_at = checkedAt;
const matrixRows = Object.entries(receipt.engines);
const matrixPass = matrixRows.length === 2 &&
  JSON.stringify(matrixRows.map(([channel]) => channel).sort()) === JSON.stringify(["chrome", "edge"]) &&
  matrixRows.every(([, engine]) => browserMatrixRowPass(engine));
receipt.verdict = matrixPass ? "PASS" : "INCOMPLETE";
writeFileSync(OUT, JSON.stringify(receipt, null, 2) + "\n");

const pass = browserMatrixRowPass(row);
console.log(`M8_BROWSER_${CHANNEL.toUpperCase()}_${pass ? "PASS" : "FAIL"} matrix=${receipt.verdict} actual=${actualVersion} official=${official.version} wm=${wmMainMs}ms`);
process.exit(browserMatrixInvocationPass(priorExists, matrixPass, pass) ? 0 : 1);

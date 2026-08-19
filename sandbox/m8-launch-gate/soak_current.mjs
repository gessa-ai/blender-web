// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Current-artifact M8 soak. The measurement window begins only after stage-1 and
// service-worker precache complete, so one-time downloads/cache growth cannot hide a
// steady-state leak. Browser-process RSS covers wasm/GPU/process memory that V8's JS
// heap counter cannot see.

import {execFileSync} from "child_process";
import {createRequire} from "module";
import {existsSync, mkdirSync, readdirSync, writeFileSync} from "fs";
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
const OUT = `${ROOT}/sandbox/m8-launch-gate/artifacts/current-soak-result.json`;
// Keep transient browser state at a repository-root ignored path.  REUSE 6.2's
// Git walker does not reliably prune nested ignored directories when their
// parent also contains source, so a nested profile would pollute compliance.
const PROFILE = `${ROOT}/.m8-soak-profile`;
const PORT = Number.parseInt(process.argv[2] || "8168", 10);
const MINUTES = Number.parseFloat(process.argv[3] || "30");
const EXECUTABLE = process.argv[4] ||
  `${ROOT}/sandbox/m8-launch-gate/.browsers/Google Chrome.app/Contents/MacOS/Google Chrome`;
const BASE = `http://localhost:${PORT}`;
const WINDOW_MS = Math.round(MINUTES * 60_000);
const SAMPLE_MS = 30_000;
const WATCH_MS = 2_000;
const STALL_MS = 5_000;
const BURST_MS = 15_000;
if (!Number.isFinite(MINUTES) || MINUTES <= 0) throw new Error("minutes must be positive");
if (existsSync(PROFILE) && readdirSync(PROFILE).length !== 0) {
  throw new Error(`soak profile must be fresh and empty: ${PROFILE}`);
}
mkdirSync(`${ROOT}/sandbox/m8-launch-gate/artifacts`, {recursive: true});
mkdirSync(PROFILE, {recursive: true});

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

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const now = () => new Date().toISOString();
const artifactContract = loadArtifactContract(ROOT);
const sourceArtifacts = collectArtifacts(artifactContract.buildBase, artifactContract.sourceNames);
const bundleArtifacts = collectArtifacts(artifactContract.bundleBase, artifactContract.bundleNames);
const expectedBundleDigest = canonicalBundleDigest(bundleArtifacts);

const state = {
  schema: 1,
  started_at: now(),
  source_artifacts: sourceArtifacts,
  bundle_artifacts: bundleArtifacts,
  served_bundle_sha256: null,
  browser: {},
  early_diagnostics: null,
  duration_seconds: 0,
  sample_count: 0,
  visible_interaction_count: 0,
  interaction_attempt_count: 0,
  interaction_failures: [],
  external_requests: [],
  samples: [],
  errors: [],
  stalls: [],
  verdict: null,
};
const blocking = [];
let gpuErrors = 0;
let rafLastChanged = Date.now();
let previousRaf = null;

async function canvasSignature() {
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

function save() {
  writeFileSync(OUT, JSON.stringify(state, null, 2) + "\n");
}

function browserRssBytes() {
  // Chromium propagates the unique user-data-dir to its process tree. Sum every
  // matching row; this includes renderer/GPU/utility processes and therefore wasm.
  try {
    const rows = execFileSync("ps", ["-axo", "rss=,command="], {encoding: "utf8"}).split("\n");
    let kib = 0;
    for (const row of rows) {
      if (!row.includes(PROFILE)) continue;
      const match = /^\s*(\d+)\s+/.exec(row);
      if (match) kib += Number.parseInt(match[1], 10);
    }
    return kib * 1024;
  }
  catch (error) {
    state.errors.push("rss sample failed: " + String(error && error.message || error));
    return 0;
  }
}

const context = await chromium.launchPersistentContext(PROFILE, {
  headless: false,
  executablePath: EXECUTABLE,
  viewport: {width: 1280, height: 720},
  deviceScaleFactor: 1,
});
const pages = context.pages();
const page = pages[0] || await context.newPage();
const actualVersion = context.browser()?.version() || "unknown";
const runtimeIdentity = bindRuntimeVersion(collectedRuntimeIdentity, actualVersion);
const official = await officialChromeVersion();
state.browser = {engine: "chrome", executable: EXECUTABLE, version: actualVersion,
  official_version: official.version, official_version_source: official.source,
  current_at_test: actualVersion === official.version, signing,
  runtime_identity: runtimeIdentity, checked_at: now(), fresh_profile: true};

page.on("console", (message) => {
  const text = message.text();
  if (/GPU-ERROR|ValidationError|Dawn:\s/i.test(text)) gpuErrors++;
  if (/\b(?:Aborted|abort\(|memory access out of bounds|out of memory|OOM|device\s+lost|GPUDeviceLost|PAGE CRASH|renderer process gone)\b/i.test(text)) blocking.push(text.slice(0, 400));
});
page.on("request", (request) => {
  try {
    if (new URL(request.url()).origin !== new URL(BASE).origin) {
      state.external_requests.push(request.url());
    }
  }
  catch (_) { state.external_requests.push(request.url()); }
});
page.on("pageerror", (error) => blocking.push("pageerror: " + String(error && error.message || error)));
page.on("crash", () => blocking.push("PAGE CRASH"));

let bootOk = false;
try {
  const navigationResponse = await page.goto(`${BASE}/index.html`,
    {waitUntil: "domcontentloaded", timeout: 60_000});
  state.served_bundle_sha256 = await requireServedBundle(navigationResponse, expectedBundleDigest);
  await page.waitForFunction(() => {
    const el = document.querySelector("#state");
    return el && el.textContent.includes("main loop (WM_main)") && window.__bwModule;
  }, null, {timeout: 240_000});
  await page.waitForFunction(() => {
    const stage = window.__bwStage1;
    return stage && stage.phase === "done" && !stage.error &&
      stage.filesDone === stage.filesTotal && stage.bytesDone === stage.bytesTotal;
  }, null, {timeout: 600_000});
  await page.waitForFunction(() => window.__bwServiceWorker && window.__bwServiceWorker.phase === "done",
    null, {timeout: 600_000});
  let pixelProof = null;
  for (let attempt = 0; attempt < 120; attempt++) {
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
    pixelProof = {width: png.width, height: png.height, nonblack_ratio: nonblack / samples,
      quantized_colors: colors.size};
    if (pixelProof.nonblack_ratio > 0.1 && pixelProof.quantized_colors > 128) break;
    await page.waitForTimeout(500);
  }
  state.pixel_proof = pixelProof;
  if (pixelProof.nonblack_ratio <= 0.1 || pixelProof.quantized_colors <= 128) {
    throw new Error("displayed canvas lacks product pixels: " + JSON.stringify(pixelProof));
  }
  bootOk = true;
}
catch (error) {
  blocking.push("boot/readiness: " + String(error && error.message || error));
}

if (bootOk) {
  await page.bringToFront();
  await page.locator("#canvas").focus();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  await page.evaluate(() => {
    window.__m8Raf = 0;
    (function tick() { window.__m8Raf++; requestAnimationFrame(tick); })();
  });
  const rect = await page.locator("#canvas").boundingBox();
  const cx = rect ? rect.x + rect.width / 2 : 640;
  const cy = rect ? rect.y + rect.height / 2 : 360;
  const begin = Date.now();
  rafLastChanged = begin;
  let nextSample = begin;
  let nextBurst = begin;
  previousRaf = await page.evaluate(() => window.__m8Raf || 0);

  while (Date.now() - begin < WINDOW_MS && blocking.length === 0) {
    await sleep(WATCH_MS);
    const wall = Date.now();
    let raf = null;
    try { raf = await page.evaluate(() => window.__m8Raf || 0); }
    catch (error) { blocking.push("page evaluate: " + String(error && error.message || error)); }
    if (raf !== null && raf !== previousRaf) {
      previousRaf = raf;
      rafLastChanged = wall;
    }
    else if (wall - rafLastChanged > STALL_MS) {
      state.stalls.push({t_seconds: Math.round((wall - begin) / 1000), gap_ms: wall - rafLastChanged});
      rafLastChanged = wall;
    }

    if (wall >= nextBurst) {
      nextBurst = wall + BURST_MS;
      try {
        state.interaction_attempt_count++;
        const beforeVisibleInput = await canvasSignature();
        await page.mouse.move(cx, cy);
        await page.mouse.click(cx, cy);
        await page.keyboard.press("a");
        await page.keyboard.press("g");
        await page.mouse.move(cx + 48, cy + 24, {steps: 4});
        await page.mouse.click(cx + 48, cy + 24);
        await page.keyboard.press("Tab");
        await page.keyboard.press("a");
        await page.keyboard.press("Tab");
        await page.keyboard.press("Control+z");
        await page.mouse.move(cx - 32, cy - 16);
        await page.mouse.down({button: "middle"});
        await page.mouse.move(cx + 32, cy + 16, {steps: 4});
        await page.mouse.up({button: "middle"});
        await page.waitForTimeout(200);
        const visibleDiff = meanAbsDiff(beforeVisibleInput, await canvasSignature());
        if (visibleDiff > 0.5) state.visible_interaction_count++;
        else state.interaction_failures.push({
          t_seconds: Math.round((wall - begin) / 1000), pixel_mean_abs_diff: visibleDiff,
        });
      }
      catch (error) { blocking.push("interaction: " + String(error && error.message || error)); }
    }

    if (wall >= nextSample) {
      nextSample = wall + SAMPLE_MS;
      let probe = {};
      try {
        probe = await page.evaluate(() => ({
          js_heap_bytes: Number(performance.memory && performance.memory.usedJSHeapSize || 0),
          raf: window.__m8Raf || 0,
          module_alive: Boolean(window.__bwModule && window.__bwModule.FS &&
            window.__bwModule.FS.stat("/projects")),
        }));
      }
      catch (error) { blocking.push("sample: " + String(error && error.message || error)); }
      const sample = {
        t_seconds: Math.round((wall - begin) / 1000),
        js_heap_bytes: probe.js_heap_bytes || 0,
        process_rss_bytes: browserRssBytes(),
        raf: probe.raf || 0,
        module_alive: probe.module_alive === true,
        gpu_errors: gpuErrors,
        fatals: blocking.length,
      };
      state.samples.push(sample);
      state.sample_count = state.samples.length;
      state.duration_seconds = Math.round((wall - begin) / 1000);
      save();
      console.log(`[m8-soak] t=${sample.t_seconds}s js=${(sample.js_heap_bytes / 1e6).toFixed(1)}MB rss=${(sample.process_rss_bytes / 1e6).toFixed(1)}MB gpu=${gpuErrors} fatal=${blocking.length}`);
    }
  }
  state.duration_seconds = Math.round((Date.now() - begin) / 1000);
}

function halfGrowth(key) {
  const values = state.samples.map((sample) => sample[key]).filter((value) => value > 0);
  if (values.length < 4) return 999;
  const half = Math.floor(values.length / 2);
  const mean = (xs) => xs.reduce((sum, value) => sum + value, 0) / xs.length;
  const front = mean(values.slice(0, half));
  const back = mean(values.slice(half));
  return Number((((back - front) / front) * 100).toFixed(2));
}

const jsGrowth = halfGrowth("js_heap_bytes");
const rssGrowth = halfGrowth("process_rss_bytes");
try {
  state.early_diagnostics = await requireEmptyEarlyDiagnostics(page, "soak:terminal");
}
catch (error) {
  blocking.push("early diagnostics: " + String(error && error.message || error));
}
const enoughDuration = state.duration_seconds >= 1800;
const enoughSamples = state.samples.length >= 60;
const sampleTimes = state.samples.map((sample) => sample.t_seconds);
const sampleGaps = sampleTimes.slice(1).map((value, index) => value - sampleTimes[index]);
const maximumSampleGapSeconds = sampleGaps.length ? Math.max(...sampleGaps) : null;
const sampleIntegrity = enoughSamples &&
  state.samples.every((sample) => sample.js_heap_bytes > 0 &&
    sample.process_rss_bytes > 0 && sample.module_alive === true) &&
  maximumSampleGapSeconds !== null && maximumSampleGapSeconds <= 45 &&
  state.duration_seconds - sampleTimes.at(-1) <= 45;
// Screenshot decoding and input settle time are inside the loop; allow three
// seconds of harness overhead beyond the nominal 15-second burst cadence.
const minimumVisibleInteractions = Math.max(1,
  Math.floor(state.duration_seconds * 1000 / (BURST_MS + 3_000)) - 2);
const verdict = {
  boot_ok: bootOk,
  js_heap_ok: jsGrowth < 10,
  process_rss_ok: rssGrowth < 10,
  sample_integrity_ok: sampleIntegrity,
  live_ok: state.stalls.length === 0 && state.samples.every((sample) => sample.module_alive) &&
    state.interaction_failures.length === 0 &&
    state.visible_interaction_count >= minimumVisibleInteractions,
  gpu_ok: gpuErrors === 0,
  no_fatal: blocking.length === 0,
  external_ok: state.external_requests.length === 0,
  js_heap_growth_pct: jsGrowth,
  process_rss_growth_pct: rssGrowth,
  stalls: state.stalls.length,
  gpu_errors: gpuErrors,
  fatals: blocking.length,
  visible_interactions: state.visible_interaction_count,
  interaction_attempts: state.interaction_attempt_count,
  minimum_visible_interactions: minimumVisibleInteractions,
  interaction_failures: state.interaction_failures.length,
  external_requests: state.external_requests.length,
  maximum_sample_gap_seconds: maximumSampleGapSeconds,
};
verdict.pass = state.browser.current_at_test && state.browser.signing.valid &&
  enoughDuration && enoughSamples && Object.entries(verdict)
  .filter(([key]) => key.endsWith("_ok") || key === "no_fatal")
  .every(([, value]) => value === true);
state.errors.push(...blocking);
await context.close();
try {
  revalidateBrowserRuntimeIdentity(runtimeIdentity,
    {identifier: "com.google.Chrome", team: "EQHXZ8M8AV"});
}
catch (error) {
  state.errors.push(String(error && error.message || error));
  verdict.pass = false;
}
state.verdict = verdict;
state.ended_at = now();
save();
console.log(`[m8-soak] ${verdict.pass ? "PASS" : "FAIL"} duration=${state.duration_seconds}s samples=${state.sample_count} jsGrowth=${jsGrowth}% rssGrowth=${rssGrowth}%`);
process.exit(verdict.pass ? 0 : 1);

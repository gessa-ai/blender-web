// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

/**
 * Hardware-only P0-E acceptance producer.
 *
 * Ten fresh browser contexts dismiss the startup splash, establish a painted
 * VIEW_3D baseline, shrink 1280x720 -> 1100x640, and then send no more input.
 * The run passes only when all ten shrinks recover non-flat VIEW_3D pixels
 * within the calibrated 24-second bound with no page or WebGPU transaction
 * errors. Software/fallback adapters are rejected before evidence allocation.
 */

import {createHash} from "node:crypto";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  statSync,
  writeFileSync,
} from "node:fs";
import {createRequire} from "node:module";
import {delimiter, dirname, join, relative, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../..");
const DEFAULT_OUT_ROOT = join(HERE, "hardware-evidence");
const DEFAULT_BIN_DIR = resolve(
  process.env.BLENDER_WEB_BIN || join(REPO, "build-wasm-windowed-opt/bin"),
);
const LOCAL_MODULE_ROOTS = Object.freeze([
  join(REPO, ".m4-node/node_modules"),
  join(REPO, "node_modules"),
]);
const MODULE_ROOTS = Object.freeze([...new Set([
  process.env.BW_NODE_MODULES,
  process.env.NODE_PATH,
  ...LOCAL_MODULE_ROOTS,
].filter(Boolean).flatMap((entry) => entry.split(delimiter)).filter(Boolean)
  .map((entry) => resolve(entry)))]);

const NODE_VERSION = "v22.16.0";
const PLAYWRIGHT_VERSION = "1.61.1";
const PNGJS_VERSION = "7.0.0";
const CHROMIUM_VERSION = "149.0.7827.55";
const ADAPTER_CONTRACT = "hardware-webgpu-adapter-v1";
const REQUIRED_ATTEMPTS = 10;
const INITIAL_EXTENT = Object.freeze([1280, 720]);
const SHRUNK_EXTENT = Object.freeze([1100, 640]);
const BOOT_POLLS = 20;
const BOOT_POLL_MS = 2000;
const POST_DISMISS_POLLS = 20;
const POST_DISMISS_POLL_MS = 1000;
const SHRINK_POLLS = 12;
const SHRINK_POLL_MS = 2000;
const DOMINANT_FRACTION_LIMIT = 0.95;
const SOFTWARE_ADAPTER_TOKENS = Object.freeze([
  "swiftshader",
  "llvmpipe",
  "lavapipe",
  "softpipe",
  "software rasterizer",
  "microsoft basic render",
  "warp",
]);
const REQUIRED_PRODUCT_FILES = Object.freeze([
  "blender_browser.js",
  "blender_browser.wasm",
  "blender_browser.wasm.orig",
  "blender_browser.data",
  "blender_browser.split-build.json",
]);
const RELEVANT_ERROR_PATTERNS = Object.freeze([
  ["scissorRejected", /Scissor rect.*not contained/i],
  ["encodingRejected", /draw encoding rejected/i],
  ["submissionRejected", /queue submission rejected/i],
  ["transactionRejected", /present transaction rejected/i],
  ["deviceLost", /\[bw\]\[GPU-LOST\]/],
]);

function isDescendant(parent, candidate) {
  const rel = relative(resolve(parent), resolve(candidate));
  return rel !== "" && !rel.startsWith(`..${process.platform === "win32" ? "\\" : "/"}`) && rel !== "..";
}

function requireDirectDescendantPath(
  parent,
  candidate,
  label,
  pathExists = existsSync,
  pathLstat = lstatSync,
) {
  if (!isDescendant(parent, candidate)) {
    throw new Error(`${label} escapes the checkout: ${candidate}`);
  }
  const parts = relative(resolve(parent), resolve(candidate)).split(/[\\/]+/);
  let cursor = resolve(parent);
  for (const part of parts) {
    cursor = join(cursor, part);
    if (pathExists(cursor) && pathLstat(cursor).isSymbolicLink()) {
      throw new Error(`${label} traverses a symlink: ${cursor}`);
    }
  }
}

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function requireNodeVersion(version = process.version) {
  if (version !== NODE_VERSION) {
    throw new Error(`Node ${NODE_VERSION} required, got ${version}`);
  }
}

function requireBrowserVersion(version) {
  if (version !== CHROMIUM_VERSION) {
    throw new Error(`Chromium ${CHROMIUM_VERSION} required, got ${version}`);
  }
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
      if (!loaded?.chromium || !loaded?.PNG) {
        throw new Error("browser dependency exports are absent");
      }
      if (loaded.playwrightVersion !== PLAYWRIGHT_VERSION ||
          loaded.pngjsVersion !== PNGJS_VERSION) {
        throw new Error(
          `versions playwright=${loaded.playwrightVersion} pngjs=${loaded.pngjsVersion}`,
        );
      }
      return {...loaded, root};
    }
    catch (error) {
      failures.push(`${root}: ${error.message}`);
    }
  }
  throw new Error(
    `cannot resolve exact browser dependencies; set BW_NODE_MODULES\n${failures.join("\n")}`,
  );
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    selfcheck: false,
    port: 8165,
    run: null,
    outRoot: DEFAULT_OUT_ROOT,
    binDir: DEFAULT_BIN_DIR,
    expectedWasmOrigSha256: null,
  };
  for (let index = 0; index < argv.length; index++) {
    const flag = argv[index];
    if (flag === "--selfcheck") {
      options.selfcheck = true;
      continue;
    }
    const value = argv[++index];
    if (value === undefined) throw new Error(`missing value for ${flag}`);
    if (flag === "--port") options.port = Number(value);
    else if (flag === "--run") options.run = value;
    else if (flag === "--out-root") options.outRoot = resolve(value);
    else if (flag === "--bin-dir") options.binDir = resolve(value);
    else if (flag === "--expected-wasm-orig-sha256") {
      options.expectedWasmOrigSha256 = value.toLowerCase();
    }
    else throw new Error(`unknown argument: ${flag}`);
  }

  if (options.selfcheck) {
    if (argv.length !== 1) throw new Error("--selfcheck cannot be combined with live arguments");
    return options;
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(options.run || "")) {
    throw new Error("--run must be a safe 1-80 character evidence label");
  }
  if (!Number.isInteger(options.port) || options.port < 1 || options.port > 65535) {
    throw new Error(`invalid --port: ${options.port}`);
  }
  if (!/^[0-9a-f]{64}$/.test(options.expectedWasmOrigSha256 || "")) {
    throw new Error("--expected-wasm-orig-sha256 must be an exact lowercase SHA-256");
  }
  requireDirectDescendantPath(REPO, options.outRoot, "--out-root");
  requireDirectDescendantPath(REPO, options.binDir, "--bin-dir");
  return options;
}

function parseGenerationManifest(source) {
  const manifest = typeof source === "string" ? JSON.parse(source) : source;
  const fields = {
    mode: manifest?.mode,
    originalWasmSha256: manifest?.original?.sha256,
    instrumentedWasmSha256: manifest?.instrumented?.sha256,
    javascriptSha256: manifest?.js?.sha256,
  };
  if (fields.mode !== "capture") {
    throw new Error(`split manifest mode is not capture: ${fields.mode}`);
  }
  for (const [name, value] of Object.entries(fields).slice(1)) {
    if (!/^[0-9a-f]{64}$/.test(value || "")) {
      throw new Error(`split manifest ${name} is not an exact SHA-256`);
    }
  }
  return fields;
}

function readProductIdentity(binDir, expectedWasmOrigSha256) {
  const files = {};
  for (const name of REQUIRED_PRODUCT_FILES) {
    const path = join(binDir, name);
    if (!existsSync(path)) throw new Error(`canonical product file is absent: ${path}`);
    const info = lstatSync(path);
    if (!info.isFile() || info.isSymbolicLink()) {
      throw new Error(`canonical product file is not a direct regular file: ${path}`);
    }
    files[name] = {bytes: statSync(path).size};
  }
  const wasmOrigPath = join(binDir, "blender_browser.wasm.orig");
  files["blender_browser.wasm.orig"].sha256 = sha256File(wasmOrigPath);
  if (files["blender_browser.wasm.orig"].sha256 !== expectedWasmOrigSha256) {
    throw new Error(
      `wasm.orig generation mismatch: expected ${expectedWasmOrigSha256}, ` +
      `got ${files["blender_browser.wasm.orig"].sha256}`,
    );
  }
  const generation = parseGenerationManifest(
    readFileSync(join(binDir, "blender_browser.split-build.json"), "utf8"),
  );
  if (generation.originalWasmSha256 !== expectedWasmOrigSha256) {
    throw new Error(
      `split manifest generation mismatch: expected ${expectedWasmOrigSha256}, ` +
      `got ${generation.originalWasmSha256}`,
    );
  }
  return {binDir: relative(REPO, binDir), files, generation};
}

async function fetchServedGeneration(
  origin,
  expectedWasmOrigSha256,
  fetchImpl = fetch,
) {
  const url = `${origin}/blender_browser.split-build.json`;
  const response = await fetchImpl(url, {cache: "no-store"});
  if (!response.ok) throw new Error(`served split manifest returned HTTP ${response.status}`);
  const generation = parseGenerationManifest(await response.text());
  if (generation.originalWasmSha256 !== expectedWasmOrigSha256) {
    throw new Error(
      `served generation mismatch: expected ${expectedWasmOrigSha256}, ` +
      `got ${generation.originalWasmSha256}`,
    );
  }
  return {url: "/blender_browser.split-build.json", ...generation};
}

function rawAdapterRecord(adapter) {
  if (!adapter) return {present: false, isFallbackAdapter: null, info: null};
  const info = adapter.info || {};
  return {
    present: true,
    isFallbackAdapter: typeof info.isFallbackAdapter === "boolean" ?
      info.isFallbackAdapter :
      (typeof adapter.isFallbackAdapter === "boolean" ? adapter.isFallbackAdapter : null),
    info: Object.fromEntries(["vendor", "architecture", "device", "description"]
      .map((key) => [key, typeof info[key] === "string" ? info[key] : ""])),
  };
}

function classifyAdapterProbe(raw, platform = process.platform) {
  const info = Object.fromEntries(["vendor", "architecture", "device", "description"]
    .map((key) => [key, typeof raw?.info?.[key] === "string" ? raw.info[key] : ""]));
  const identity = Object.values(info).join(" ").trim().toLowerCase();
  const detailIdentity = [info.architecture, info.device, info.description].join(" ").trim();
  const softwareMatches = SOFTWARE_ADAPTER_TOKENS.filter((token) => identity.includes(token));
  if (/(^|[^a-z0-9])cpu([^a-z0-9]|$)/.test(identity)) softwareMatches.push("cpu");
  const present = raw?.present === true;
  const isFallbackAdapter = typeof raw?.isFallbackAdapter === "boolean" ?
    raw.isFallbackAdapter : null;
  let reason = "accepted-hardware";
  if (!present) reason = "adapter-absent";
  else if (isFallbackAdapter === true) reason = "fallback-adapter";
  else if (isFallbackAdapter !== false) reason = "fallback-status-absent";
  else if (!identity || !detailIdentity) reason = "adapter-info-absent";
  else if (softwareMatches.length) reason = "software-adapter";
  return {
    contract: ADAPTER_CONTRACT,
    status: reason === "accepted-hardware" ? "ACCEPTED" : "REJECTED",
    present,
    platform,
    powerPreference: "high-performance",
    isFallbackAdapter,
    info,
    softwareMatches,
    reason,
  };
}

async function probeAdapter(page) {
  const raw = await page.evaluate(async () => {
    const adapter = await navigator.gpu?.requestAdapter({powerPreference: "high-performance"});
    if (!adapter) return {present: false, isFallbackAdapter: null, info: null};
    const info = adapter.info || {};
    return {
      present: true,
      isFallbackAdapter: typeof info.isFallbackAdapter === "boolean" ?
        info.isFallbackAdapter :
        (typeof adapter.isFallbackAdapter === "boolean" ? adapter.isFallbackAdapter : null),
      info: Object.fromEntries(["vendor", "architecture", "device", "description"]
        .map((key) => [key, typeof info[key] === "string" ? info[key] : ""])),
    };
  });
  return classifyAdapterProbe(raw);
}

function semanticView3DRaw({width, height, data}, expectedExtent = SHRUNK_EXTENT) {
  const x0 = Math.floor(width * 0.12);
  const x1 = Math.floor(width * 0.55);
  const y0 = Math.floor(height * 0.28);
  const y1 = Math.floor(height * 0.56);
  const counts = new Map();
  let total = 0;
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const at = (width * y + x) * 4;
      /* Preserve the driver's calibrated six-bit collision key exactly. The acceptance
       * threshold and its 0.867 good-frame calibration were measured with this mapping. */
      const key = ((data[at] >> 2) << 10) |
        ((data[at + 1] >> 2) << 5) |
        (data[at + 2] >> 2);
      counts.set(key, (counts.get(key) || 0) + 1);
      total++;
    }
  }
  let dominant = 0;
  for (const count of counts.values()) dominant = Math.max(dominant, count);
  const dominantFraction = total ? dominant / total : 1;
  return {
    width,
    height,
    roi: {x0, x1, y0, y1},
    samples: total,
    dominantFraction,
    painted: width === expectedExtent[0] && height === expectedExtent[1] &&
      dominantFraction < DOMINANT_FRACTION_LIMIT,
  };
}

function semanticView3D(PNG, buffer, expectedExtent) {
  return semanticView3DRaw(PNG.sync.read(buffer), expectedExtent);
}

function emptyErrorCounts() {
  return Object.fromEntries(RELEVANT_ERROR_PATTERNS.map(([name]) => [name, 0]));
}

function classifyConsoleLine(line, counts) {
  let relevant = false;
  for (const [name, pattern] of RELEVANT_ERROR_PATTERNS) {
    if (pattern.test(line)) {
      counts[name]++;
      relevant = true;
    }
  }
  return relevant;
}

function hasRelevantErrors(counts) {
  return Object.values(counts).some((count) => count !== 0);
}

async function waitForSemanticPaint(page, PNG, expectedExtent, polls, delayMs) {
  let lastBuffer = null;
  let lastProof = null;
  for (let index = 0; index < polls; index++) {
    await page.waitForTimeout(delayMs);
    lastBuffer = await page.screenshot({timeout: 20000});
    lastProof = semanticView3D(PNG, lastBuffer, expectedExtent);
    if (lastProof.painted) return {buffer: lastBuffer, proof: lastProof, poll: index + 1};
  }
  return {buffer: lastBuffer, proof: lastProof, poll: polls};
}

function finalVerdict(results) {
  return results.length === REQUIRED_ATTEMPTS && results.every((result) =>
    result.ok && result.postResizeInputEvents === 0 && result.pageErrors.length === 0 &&
    !hasRelevantErrors(result.relevantErrors));
}

async function runSelfcheck() {
  let positive = 0;
  let negative = 0;
  const check = (condition, message) => {
    if (!condition) throw new Error(`P0-E acceptance self-check: ${message}`);
    positive++;
  };
  const reject = (name, action) => {
    try {
      action();
    }
    catch (_) {
      negative++;
      return;
    }
    throw new Error(`P0-E acceptance self-check false green: ${name}`);
  };
  const rejectAsync = async (name, action) => {
    try {
      await action();
    }
    catch (_) {
      negative++;
      return;
    }
    throw new Error(`P0-E acceptance self-check false green: ${name}`);
  };

  requireNodeVersion();
  check(REQUIRED_ATTEMPTS === 10 && SHRINK_POLLS * SHRINK_POLL_MS === 24000,
    "10-attempt/24-second acceptance bar drifted");
  check(DOMINANT_FRACTION_LIMIT === 0.95, "semantic threshold drifted");
  check(parseArgs(["--selfcheck"]).selfcheck === true, "self-check parsing drifted");
  const parsed = parseArgs([
    "--port", "8165",
    "--run", "apple-r1",
    "--out-root", DEFAULT_OUT_ROOT,
    "--bin-dir", DEFAULT_BIN_DIR,
    "--expected-wasm-orig-sha256", "a".repeat(64),
  ]);
  check(parsed.port === 8165 && parsed.run === "apple-r1" &&
    parsed.expectedWasmOrigSha256 === "a".repeat(64), "live argument parsing drifted");
  for (const [name, args] of [
    ["combined_selfcheck", ["--selfcheck", "--run", "bad"]],
    ["missing_run", ["--expected-wasm-orig-sha256", "a".repeat(64)]],
    ["escaped_run", ["--run", "../bad", "--expected-wasm-orig-sha256", "a".repeat(64)]],
    ["bad_port", ["--run", "bad", "--port", "65536", "--expected-wasm-orig-sha256", "a".repeat(64)]],
    ["bad_sha", ["--run", "bad", "--expected-wasm-orig-sha256", "abc"]],
    ["escaped_output", ["--run", "bad", "--out-root", resolve(REPO, ".."),
      "--expected-wasm-orig-sha256", "a".repeat(64)]],
    ["escaped_binary", ["--run", "bad", "--bin-dir", resolve(REPO, ".."),
      "--expected-wasm-orig-sha256", "a".repeat(64)]],
  ]) reject(name, () => parseArgs(args));
  reject("symlinked_output", () => requireDirectDescendantPath(
    REPO,
    DEFAULT_OUT_ROOT,
    "--out-root",
    (path) => path === DEFAULT_OUT_ROOT,
    () => ({isSymbolicLink: () => true}),
  ));

  const chromiumToken = {};
  const pngToken = {};
  const resolved = resolveBrowserDependencies(["/missing", "/fixture"], (root) => {
    if (root === "/missing") throw new Error("fixture miss");
    return {
      chromium: chromiumToken,
      PNG: pngToken,
      playwrightVersion: PLAYWRIGHT_VERSION,
      pngjsVersion: PNGJS_VERSION,
    };
  });
  check(resolved.chromium === chromiumToken && resolved.PNG === pngToken &&
    resolved.root === "/fixture", "dependency fallback drifted");
  reject("wrong_playwright", () => resolveBrowserDependencies(["/fixture"], () => ({
    chromium: chromiumToken,
    PNG: pngToken,
    playwrightVersion: "1.61.0",
    pngjsVersion: PNGJS_VERSION,
  })));
  reject("wrong_pngjs", () => resolveBrowserDependencies(["/fixture"], () => ({
    chromium: chromiumToken,
    PNG: pngToken,
    playwrightVersion: PLAYWRIGHT_VERSION,
    pngjsVersion: "6.0.0",
  })));
  reject("missing_exports", () => resolveBrowserDependencies(["/fixture"], () => ({
    playwrightVersion: PLAYWRIGHT_VERSION,
    pngjsVersion: PNGJS_VERSION,
  })));
  reject("wrong_node", () => requireNodeVersion("v25.0.0"));
  reject("wrong_chromium", () => requireBrowserVersion("150.0.0.0"));

  const generationFixture = {
    mode: "capture",
    original: {sha256: "a".repeat(64)},
    instrumented: {sha256: "b".repeat(64)},
    js: {sha256: "c".repeat(64)},
  };
  const generation = parseGenerationManifest(generationFixture);
  check(generation.mode === "capture" && generation.originalWasmSha256 === "a".repeat(64),
    "capture generation parsing drifted");
  reject("apply_generation", () => parseGenerationManifest({...generationFixture, mode: "apply"}));
  reject("missing_generation_sha", () => parseGenerationManifest({
    ...generationFixture, instrumented: {},
  }));
  const servedGeneration = await fetchServedGeneration(
    "http://127.0.0.1:8165",
    "a".repeat(64),
    async () => ({ok: true, status: 200, text: async () => JSON.stringify(generationFixture)}),
  );
  check(servedGeneration.originalWasmSha256 === "a".repeat(64) &&
    servedGeneration.url === "/blender_browser.split-build.json",
  "served generation parsing drifted");
  await rejectAsync("stale_served_generation", () => fetchServedGeneration(
    "http://127.0.0.1:8165",
    "d".repeat(64),
    async () => ({ok: true, status: 200, text: async () => JSON.stringify(generationFixture)}),
  ));
  await rejectAsync("missing_served_manifest", () => fetchServedGeneration(
    "http://127.0.0.1:8165",
    "a".repeat(64),
    async () => ({ok: false, status: 404}),
  ));

  const hardwareInfo = {
    vendor: "apple", architecture: "metal-3", device: "M4 Pro", description: "",
  };
  for (const adapter of [
    {info: {...hardwareInfo, isFallbackAdapter: false}},
    {isFallbackAdapter: false, info: hardwareInfo},
    {isFallbackAdapter: true, info: {...hardwareInfo, isFallbackAdapter: false}},
  ]) {
    const verdict = classifyAdapterProbe(rawAdapterRecord(adapter), "darwin");
    check(verdict.status === "ACCEPTED" && verdict.reason === "accepted-hardware",
      "hardware adapter fixture was rejected");
  }
  for (const [name, adapter, reason] of [
    ["absent", null, "adapter-absent"],
    ["fallback", {info: {...hardwareInfo, isFallbackAdapter: true}}, "fallback-adapter"],
    ["missing_status", {info: hardwareInfo}, "fallback-status-absent"],
    ["masked", {info: {vendor: "", architecture: "", device: "", description: "",
      isFallbackAdapter: false}}, "adapter-info-absent"],
    ["software", {info: {vendor: "google", architecture: "swiftshader", device: "CPU",
      description: "", isFallbackAdapter: false}}, "software-adapter"],
  ]) {
    const verdict = classifyAdapterProbe(rawAdapterRecord(adapter), "darwin");
    check(verdict.status === "REJECTED" && verdict.reason === reason,
      `${name} adapter fixture false green`);
  }

  const makePixels = (variant) => {
    const width = SHRUNK_EXTENT[0];
    const height = SHRUNK_EXTENT[1];
    const data = new Uint8Array(width * height * 4);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const at = (width * y + x) * 4;
        const value = variant === "flat" ? 128 : (x * 17 + y * 29) & 255;
        data[at] = value;
        data[at + 1] = variant === "flat" ? value : (x * 7 + y * 13) & 255;
        data[at + 2] = variant === "flat" ? value : (x * 31 + y * 3) & 255;
        data[at + 3] = 255;
      }
    }
    return {width, height, data};
  };
  const flat = semanticView3DRaw(makePixels("flat"));
  const scene = semanticView3DRaw(makePixels("scene"));
  check(!flat.painted && flat.dominantFraction === 1, "flat overdraw fixture was accepted");
  check(scene.painted && scene.dominantFraction < DOMINANT_FRACTION_LIMIT,
    "non-flat scene fixture was rejected");
  check(!semanticView3DRaw(makePixels("scene"), INITIAL_EXTENT).painted,
    "wrong expected extent was accepted");
  check(!semanticView3DRaw({width: 1, height: 1, data: new Uint8Array(4)}).painted,
    "wrong-extent pixel fixture was accepted");

  const errors = emptyErrorCounts();
  check(classifyConsoleLine("Scissor rect is not contained", errors) &&
    errors.scissorRejected === 1, "scissor rejection was not counted");
  check(classifyConsoleLine("WGPUWeb: present transaction rejected", errors) &&
    errors.transactionRejected === 1, "present rejection was not counted");
  check(!classifyConsoleLine("[bw] ordinary resize", errors), "ordinary log was rejected");
  const passingAttempt = {
    ok: true,
    postResizeInputEvents: 0,
    pageErrors: [],
    relevantErrors: emptyErrorCounts(),
  };
  check(finalVerdict(Array.from({length: REQUIRED_ATTEMPTS}, () => ({...passingAttempt,
    relevantErrors: emptyErrorCounts()}))), "10 clean attempts were rejected");
  check(!finalVerdict(Array.from({length: REQUIRED_ATTEMPTS - 1}, () => passingAttempt)),
    "nine attempts were accepted");
  check(!finalVerdict(Array.from({length: REQUIRED_ATTEMPTS}, (_, index) => ({
    ...passingAttempt,
    pageErrors: index === 9 ? [{name: "Error", message: "fixture"}] : [],
  }))), "page-error attempt was accepted");

  if (process.env.BW_NODE_MODULES || process.env.NODE_PATH) {
    const live = resolveBrowserDependencies();
    check(live.playwrightVersion === PLAYWRIGHT_VERSION && live.pngjsVersion === PNGJS_VERSION,
      "live browser dependency resolution drifted");
  }
  console.log(
    `BW_P0E_HARDWARE_RESIZE_SELFCHECK_PASS positive=${positive} negative=${negative} ` +
    `attempts=${REQUIRED_ATTEMPTS} bound_ms=${SHRINK_POLLS * SHRINK_POLL_MS}`,
  );
}

async function runLive(options) {
  requireNodeVersion();
  const product = readProductIdentity(options.binDir, options.expectedWasmOrigSha256);
  const dependencies = resolveBrowserDependencies();
  const browser = await dependencies.chromium.launch({
    headless: false,
    args: [
      "--enable-unsafe-webgpu",
      ...(process.platform === "darwin" ? ["--use-angle=metal"] : []),
    ],
  });
  let receipt = null;
  let runDir = null;
  try {
    const browserVersion = browser.version();
    requireBrowserVersion(browserVersion);
    const origin = `http://127.0.0.1:${options.port}`;
    const probeContext = await browser.newContext();
    const probePage = await probeContext.newPage();
    await probePage.route(`${origin}/__bw_p0e_adapter_probe__`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "<!doctype html><meta charset=utf-8><title>adapter probe</title>",
      });
    });
    await probePage.goto(`${origin}/__bw_p0e_adapter_probe__`, {waitUntil: "domcontentloaded"});
    const adapter = await probeAdapter(probePage);
    await probeContext.close();
    if (adapter.status !== "ACCEPTED") {
      throw new Error(`hardware adapter rejected: ${adapter.reason}`);
    }
    product.servedGeneration = await fetchServedGeneration(
      origin, options.expectedWasmOrigSha256,
    );

    runDir = join(options.outRoot, options.run);
    if (existsSync(runDir)) throw new Error(`immutable evidence run already exists: ${runDir}`);
    mkdirSync(runDir, {recursive: true});
    receipt = {
      schema: "blender-web.p0e-hardware-resize.v1",
      status: "RUNNING",
      run: options.run,
      startedAt: new Date().toISOString(),
      source: relative(REPO, fileURLToPath(import.meta.url)),
      product,
      browser: {
        nodeVersion: process.version,
        playwrightVersion: dependencies.playwrightVersion,
        pngjsVersion: dependencies.pngjsVersion,
        chromiumVersion: browserVersion,
        moduleSource: isDescendant(REPO, dependencies.root) ?
          relative(REPO, dependencies.root) : "external",
        platform: process.platform,
      },
      adapter,
      contract: {
        attempts: REQUIRED_ATTEMPTS,
        initialExtent: INITIAL_EXTENT,
        shrunkExtent: SHRUNK_EXTENT,
        dominantFractionLimit: DOMINANT_FRACTION_LIMIT,
        shrinkTimeoutMs: SHRINK_POLLS * SHRINK_POLL_MS,
        postResizeInputEvents: 0,
      },
      results: [],
    };
    const writeReceipt = () => writeFileSync(
      join(runDir, "receipt.json"), `${JSON.stringify(receipt, null, 2)}\n`,
    );
    writeReceipt();

    for (let attempt = 1; attempt <= REQUIRED_ATTEMPTS; attempt++) {
      const context = await browser.newContext({
        viewport: {width: INITIAL_EXTENT[0], height: INITIAL_EXTENT[1]},
        deviceScaleFactor: 1,
      });
      const page = await context.newPage();
      const startedAt = Date.now();
      const relevantErrors = emptyErrorCounts();
      const relevantConsole = [];
      const pageErrors = [];
      page.on("console", (message) => {
        const line = message.text();
        if (classifyConsoleLine(line, relevantErrors)) relevantConsole.push(line);
      });
      page.on("pageerror", (error) => {
        pageErrors.push({name: error.name || "Error", message: error.message || String(error)});
      });
      let result;
      try {
        await page.goto(`${origin}/`, {waitUntil: "domcontentloaded", timeout: 60000});
        const boot = await waitForSemanticPaint(
          page, dependencies.PNG, INITIAL_EXTENT, BOOT_POLLS, BOOT_POLL_MS,
        );
        writeFileSync(join(runDir, `${String(attempt).padStart(2, "0")}-boot.png`), boot.buffer);
        if (!boot.proof?.painted) throw new Error("VIEW_3D never painted during boot bound");

        await page.mouse.click(640, 360);
        await page.waitForTimeout(1500);
        const baseline = await waitForSemanticPaint(
          page, dependencies.PNG, INITIAL_EXTENT, POST_DISMISS_POLLS, POST_DISMISS_POLL_MS,
        );
        writeFileSync(
          join(runDir, `${String(attempt).padStart(2, "0")}-pre-resize.png`),
          baseline.buffer,
        );
        if (!baseline.proof?.painted) {
          throw new Error("VIEW_3D baseline absent after splash dismissal");
        }

        await page.setViewportSize({width: SHRUNK_EXTENT[0], height: SHRUNK_EXTENT[1]});
        /* Acceptance boundary: no keyboard or pointer operation may occur after this call. */
        const shrink = await waitForSemanticPaint(
          page, dependencies.PNG, SHRUNK_EXTENT, SHRINK_POLLS, SHRINK_POLL_MS,
        );
        writeFileSync(
          join(runDir, `${String(attempt).padStart(2, "0")}-shrink.png`),
          shrink.buffer,
        );
        const postResizeInputEvents = 0;
        const clean = pageErrors.length === 0 && !hasRelevantErrors(relevantErrors);
        result = {
          attempt,
          ok: Boolean(shrink.proof?.painted) && clean,
          elapsedMs: Date.now() - startedAt,
          shrinkPaintAtMs: shrink.proof?.painted ?
            shrink.poll * SHRINK_POLL_MS : null,
          boot: boot.proof,
          baseline: baseline.proof,
          shrink: shrink.proof,
          postResizeInputEvents,
          pageErrors,
          relevantErrors,
          relevantConsole,
        };
      }
      catch (error) {
        result = {
          attempt,
          ok: false,
          elapsedMs: Date.now() - startedAt,
          error: {name: error.name || "Error", message: error.message || String(error)},
          postResizeInputEvents: 0,
          pageErrors,
          relevantErrors,
          relevantConsole,
        };
      }
      finally {
        await context.close();
      }
      receipt.results.push(result);
      writeReceipt();
      console.log(
        `[attempt ${attempt}] ${result.ok ? "PASS" : "FAIL"} ` +
        `dominant=${result.shrink?.dominantFraction ?? "absent"} ` +
        `pageErrors=${result.pageErrors.length} relevantErrors=${
          Object.values(result.relevantErrors).reduce((sum, count) => sum + count, 0)}`,
      );
    }

    receipt.status = finalVerdict(receipt.results) ? "PASS" : "FAIL";
    receipt.completedAt = new Date().toISOString();
    receipt.passed = receipt.results.filter((result) => result.ok).length;
    writeReceipt();
    if (receipt.status !== "PASS") {
      throw new Error(
        `BW_P0E_HARDWARE_RESIZE_FAIL passed=${receipt.passed}/${REQUIRED_ATTEMPTS}`,
      );
    }
    console.log(
      `BW_P0E_HARDWARE_RESIZE_PASS attempts=${receipt.passed}/${REQUIRED_ATTEMPTS} ` +
      `wasm_orig_sha256=${options.expectedWasmOrigSha256}`,
    );
  }
  catch (error) {
    if (receipt && runDir) {
      receipt.status = "FAIL";
      receipt.completedAt = new Date().toISOString();
      receipt.fatal = {name: error.name || "Error", message: error.message || String(error)};
      writeFileSync(join(runDir, "receipt.json"), `${JSON.stringify(receipt, null, 2)}\n`);
    }
    throw error;
  }
  finally {
    await browser.close();
  }
}

const options = parseArgs();
if (options.selfcheck) await runSelfcheck();
else await runLive(options);

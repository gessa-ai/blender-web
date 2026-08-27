// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

/** Independently verify one completed P0-E hardware resize receipt. */

import {createHash} from "node:crypto";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import {createRequire} from "node:module";
import {tmpdir} from "node:os";
import {basename, delimiter, dirname, join, relative, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../..");
const PRODUCER = join(HERE, "hardware_resize_acceptance.mjs");
const DEFAULT_BIN_DIR = join(REPO, "build-wasm-windowed-opt/bin");
const NODE_VERSION = "v22.16.0";
const PLAYWRIGHT_VERSION = "1.61.1";
const PNGJS_VERSION = "7.0.0";
const CHROMIUM_VERSION = "149.0.7827.55";
const ADAPTER_CONTRACT = "hardware-webgpu-adapter-v1";
const REQUIRED_ATTEMPTS = 10;
const INITIAL_EXTENT = Object.freeze([1280, 720]);
const SHRUNK_EXTENT = Object.freeze([1100, 640]);
const DOMINANT_FRACTION_LIMIT = 0.95;
const STABLE_PAINT_POLLS = 3;
const SHRINK_TIMEOUT_MS = 24000;
const REQUIRED_PRODUCT_FILES = Object.freeze([
  "blender_browser.js",
  "blender_browser.wasm",
  "blender_browser.wasm.orig",
  "blender_browser.data",
  "blender_browser.split-build.json",
]);
const IMAGE_SUFFIXES = Object.freeze({
  boot: "boot.png",
  baseline: "pre-resize.png",
  shrink: "shrink.png",
});
const ERROR_KEYS = Object.freeze([
  "scissorRejected",
  "encodingRejected",
  "submissionRejected",
  "transactionRejected",
  "deviceLost",
]);
const SHA256_RE = /^[0-9a-f]{64}$/;
const SAFE_RUN_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
const MODULE_ROOTS = Object.freeze([...new Set([
  process.env.BW_NODE_MODULES,
  process.env.NODE_PATH,
  join(REPO, ".m4-node/node_modules"),
  join(REPO, "node_modules"),
].filter(Boolean).flatMap((entry) => entry.split(delimiter)).filter(Boolean)
  .map((entry) => resolve(entry)))]);

function fail(message) {
  throw new Error(`P0-E hardware receipt rejected: ${message}`);
}

function portableRelative(parent, path) {
  return relative(parent, path).replaceAll("\\", "/");
}

function sha256Bytes(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function sha256File(path) {
  return sha256Bytes(readFileSync(path));
}

function requireRegularFile(path, label) {
  if (!existsSync(path)) fail(`${label} is absent: ${path}`);
  const info = lstatSync(path);
  if (!info.isFile() || info.isSymbolicLink()) {
    fail(`${label} is not a direct regular file: ${path}`);
  }
  return info;
}

function fileIdentity(path, parent = null) {
  const info = requireRegularFile(path, "identity target");
  return {
    ...(parent === null ? {} : {path: portableRelative(parent, path)}),
    bytes: info.size,
    sha256: sha256File(path),
  };
}

function exactKeys(value, expected, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail(`${label} is not an object`);
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) {
    fail(`${label} keys differ: ${actual.join(",")}`);
  }
}

function sameJSON(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    fail(`${label} differs`);
  }
}

function requireIdentity(record, path, expectedRelative, label) {
  exactKeys(record, ["path", "bytes", "sha256"], `${label} identity`);
  if (record.path !== expectedRelative) fail(`${label} path differs: ${record.path}`);
  const actual = fileIdentity(path, dirname(path));
  if (record.bytes !== actual.bytes || record.sha256 !== actual.sha256) {
    fail(`${label} bytes/hash differ`);
  }
}

function loadPNG() {
  const failures = [];
  for (const root of MODULE_ROOTS) {
    try {
      const require = createRequire(join(root, "package.json"));
      const version = require("pngjs/package.json").version;
      if (version !== PNGJS_VERSION) throw new Error(`pngjs=${version}`);
      return require("pngjs").PNG;
    }
    catch (error) {
      failures.push(`${root}: ${error.message}`);
    }
  }
  fail(`cannot resolve pngjs ${PNGJS_VERSION}; set BW_NODE_MODULES\n${failures.join("\n")}`);
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    selfcheck: false,
    evidence: null,
    binDir: resolve(process.env.BLENDER_WEB_BIN || DEFAULT_BIN_DIR),
    expectedWasmOrigSha256: null,
  };
  for (let index = 0; index < argv.length; index++) {
    const flag = argv[index];
    if (flag === "--selfcheck") {
      options.selfcheck = true;
      continue;
    }
    const value = argv[++index];
    if (value === undefined) fail(`missing value for ${flag}`);
    if (flag === "--evidence") options.evidence = resolve(value);
    else if (flag === "--bin-dir") options.binDir = resolve(value);
    else if (flag === "--expected-wasm-orig-sha256") {
      options.expectedWasmOrigSha256 = value.toLowerCase();
    }
    else fail(`unknown argument: ${flag}`);
  }
  if (options.selfcheck) {
    if (argv.length !== 1) fail("--selfcheck cannot be combined with live arguments");
    return options;
  }
  if (!options.evidence) fail("--evidence is required");
  if (!SHA256_RE.test(options.expectedWasmOrigSha256 || "")) {
    fail("--expected-wasm-orig-sha256 must be an exact lowercase SHA-256");
  }
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
  if (fields.mode !== "capture") fail(`split manifest mode is ${fields.mode}`);
  for (const [name, value] of Object.entries(fields).slice(1)) {
    if (!SHA256_RE.test(value || "")) fail(`split manifest ${name} is invalid`);
  }
  return fields;
}

function semanticView3D({width, height, data}, expectedExtent) {
  const x0 = Math.floor(width * 0.12);
  const x1 = Math.floor(width * 0.55);
  const y0 = Math.floor(height * 0.28);
  const y1 = Math.floor(height * 0.56);
  const counts = new Map();
  let samples = 0;
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const at = (width * y + x) * 4;
      const key = ((data[at] >> 2) << 10) |
        ((data[at + 1] >> 2) << 5) |
        (data[at + 2] >> 2);
      counts.set(key, (counts.get(key) || 0) + 1);
      samples++;
    }
  }
  let dominant = 0;
  for (const count of counts.values()) dominant = Math.max(dominant, count);
  const dominantFraction = samples ? dominant / samples : 1;
  return {
    width,
    height,
    roi: {x0, x1, y0, y1},
    samples,
    dominantFraction,
    painted: width === expectedExtent[0] && height === expectedExtent[1] &&
      dominantFraction < DOMINANT_FRACTION_LIMIT,
  };
}

function verifyProof(record, decoded, expectedExtent, label, stable = false) {
  const expected = semanticView3D(decoded, expectedExtent);
  exactKeys(record,
    ["width", "height", "roi", "samples", "dominantFraction", "painted",
      ...(stable ? ["stablePaintPolls"] : [])],
    `${label} proof`);
  for (const key of ["width", "height", "roi", "samples", "dominantFraction", "painted"]) {
    sameJSON(record[key], expected[key], `${label} proof ${key}`);
  }
  if (!record.painted) fail(`${label} is not semantically painted`);
  if (stable && record.stablePaintPolls !== STABLE_PAINT_POLLS) {
    fail(`${label} stable-paint count differs`);
  }
}

function verifyProduct(product, binDir, expectedWasmOrigSha256) {
  exactKeys(product, ["binDir", "files", "generation", "servedGeneration"], "product");
  if (product.binDir !== portableRelative(REPO, binDir)) fail("product binDir differs");
  exactKeys(product.files, REQUIRED_PRODUCT_FILES, "product files");
  for (const name of REQUIRED_PRODUCT_FILES) {
    const path = join(binDir, name);
    const actual = fileIdentity(path);
    exactKeys(product.files[name], ["bytes", "sha256"], `product ${name}`);
    if (product.files[name].bytes !== actual.bytes || product.files[name].sha256 !== actual.sha256) {
      fail(`product file differs: ${name}`);
    }
  }
  const generation = parseGenerationManifest(
    readFileSync(join(binDir, "blender_browser.split-build.json"), "utf8"),
  );
  sameJSON(product.generation, generation, "local generation");
  if (generation.originalWasmSha256 !== expectedWasmOrigSha256 ||
      product.files["blender_browser.wasm.orig"].sha256 !== expectedWasmOrigSha256) {
    fail("wasm.orig generation differs");
  }
  if (generation.instrumentedWasmSha256 !== product.files["blender_browser.wasm"].sha256 ||
      generation.javascriptSha256 !== product.files["blender_browser.js"].sha256) {
    fail("generation manifest does not bind JS/instrumented Wasm");
  }
  sameJSON(product.servedGeneration, {
    url: "/blender_browser.split-build.json",
    ...generation,
  }, "served generation");
}

function verifySource(source) {
  const expectedPath = portableRelative(REPO, PRODUCER);
  exactKeys(source, ["path", "bytes", "sha256"], "producer source");
  const expected = fileIdentity(PRODUCER, REPO);
  sameJSON(source, expected, "producer source identity");
  if (source.path !== expectedPath) fail("producer source path differs");
}

function verifyBrowser(browser) {
  exactKeys(browser, ["nodeVersion", "playwrightVersion", "pngjsVersion",
    "chromiumVersion", "moduleSource", "platform"], "browser");
  if (browser.nodeVersion !== NODE_VERSION || browser.playwrightVersion !== PLAYWRIGHT_VERSION ||
      browser.pngjsVersion !== PNGJS_VERSION || browser.chromiumVersion !== CHROMIUM_VERSION) {
    fail("browser toolchain identity differs");
  }
  if (!["darwin", "linux", "win32"].includes(browser.platform)) {
    fail(`unsupported browser platform: ${browser.platform}`);
  }
  if (typeof browser.moduleSource !== "string" || !browser.moduleSource) {
    fail("browser module source is absent");
  }
}

function verifyAdapter(adapter, platform) {
  exactKeys(adapter, ["contract", "status", "present", "platform", "powerPreference",
    "isFallbackAdapter", "info", "softwareMatches", "reason"], "adapter");
  if (adapter.contract !== ADAPTER_CONTRACT || adapter.status !== "ACCEPTED" ||
      adapter.present !== true || adapter.platform !== platform ||
      adapter.powerPreference !== "high-performance" || adapter.isFallbackAdapter !== false ||
      adapter.reason !== "accepted-hardware") {
    fail("hardware adapter contract was not accepted");
  }
  exactKeys(adapter.info, ["vendor", "architecture", "device", "description"], "adapter info");
  if (![adapter.info.vendor, adapter.info.architecture, adapter.info.device]
      .some((value) => typeof value === "string" && value.trim())) {
    fail("adapter identity is absent");
  }
  if (!Array.isArray(adapter.softwareMatches) || adapter.softwareMatches.length !== 0) {
    fail("adapter matches a software token");
  }
}

function expectedImageNames() {
  const names = [];
  for (let attempt = 1; attempt <= REQUIRED_ATTEMPTS; attempt++) {
    const prefix = String(attempt).padStart(2, "0");
    for (const suffix of Object.values(IMAGE_SUFFIXES)) names.push(`${prefix}-${suffix}`);
  }
  return names;
}

function verifyImage(PNG, evidenceDir, record, expectedName, expectedExtent, proof, label, stable) {
  requireIdentity(record, join(evidenceDir, expectedName), expectedName, label);
  const decoded = PNG.sync.read(readFileSync(join(evidenceDir, expectedName)));
  verifyProof(proof, decoded, expectedExtent, label, stable);
}

function verifyResult(PNG, evidenceDir, result, attempt) {
  exactKeys(result, ["attempt", "ok", "elapsedMs", "shrinkPaintAtMs", "boot", "baseline",
    "shrink", "images", "postResizeInputEvents", "pageErrors", "relevantErrors",
    "relevantConsole"], `result ${attempt}`);
  if (result.attempt !== attempt || result.ok !== true || result.postResizeInputEvents !== 0) {
    fail(`attempt ${attempt} verdict/input differs`);
  }
  if (!Number.isInteger(result.elapsedMs) || result.elapsedMs <= 0 ||
      !Number.isInteger(result.shrinkPaintAtMs) || result.shrinkPaintAtMs < 6000 ||
      result.shrinkPaintAtMs > SHRINK_TIMEOUT_MS || result.shrinkPaintAtMs % 2000 !== 0 ||
      result.elapsedMs < result.shrinkPaintAtMs) {
    fail(`attempt ${attempt} timing differs`);
  }
  if (!Array.isArray(result.pageErrors) || result.pageErrors.length !== 0 ||
      !Array.isArray(result.relevantConsole) || result.relevantConsole.length !== 0) {
    fail(`attempt ${attempt} recorded browser/WebGPU errors`);
  }
  exactKeys(result.relevantErrors, ERROR_KEYS, `attempt ${attempt} error counts`);
  if (Object.values(result.relevantErrors).some((count) => count !== 0)) {
    fail(`attempt ${attempt} has nonzero WebGPU errors`);
  }
  exactKeys(result.images, Object.keys(IMAGE_SUFFIXES), `attempt ${attempt} images`);
  const prefix = String(attempt).padStart(2, "0");
  verifyImage(PNG, evidenceDir, result.images.boot, `${prefix}-${IMAGE_SUFFIXES.boot}`,
    INITIAL_EXTENT, result.boot, `attempt ${attempt} boot`, false);
  verifyImage(PNG, evidenceDir, result.images.baseline, `${prefix}-${IMAGE_SUFFIXES.baseline}`,
    INITIAL_EXTENT, result.baseline, `attempt ${attempt} baseline`, false);
  verifyImage(PNG, evidenceDir, result.images.shrink, `${prefix}-${IMAGE_SUFFIXES.shrink}`,
    SHRUNK_EXTENT, result.shrink, `attempt ${attempt} shrink`, true);
}

function verifyReceipt(options, PNG) {
  if (!existsSync(options.evidence)) fail(`evidence directory is absent: ${options.evidence}`);
  const evidenceInfo = lstatSync(options.evidence);
  if (!evidenceInfo.isDirectory() || evidenceInfo.isSymbolicLink()) {
    fail("evidence path is not a direct directory");
  }
  const receiptPath = join(options.evidence, "receipt.json");
  requireRegularFile(receiptPath, "receipt");
  const receipt = JSON.parse(readFileSync(receiptPath, "utf8"));
  exactKeys(receipt, ["schema", "status", "run", "startedAt", "source", "product", "browser",
    "adapter", "contract", "results", "completedAt", "passed"], "receipt");
  if (receipt.schema !== "blender-web.p0e-hardware-resize.v1" || receipt.status !== "PASS" ||
      receipt.passed !== REQUIRED_ATTEMPTS || !SAFE_RUN_RE.test(receipt.run || "") ||
      basename(options.evidence) !== receipt.run) {
    fail("receipt identity/verdict differs");
  }
  const started = Date.parse(receipt.startedAt);
  const completed = Date.parse(receipt.completedAt);
  if (!Number.isFinite(started) || !Number.isFinite(completed) || completed < started) {
    fail("receipt timestamps differ");
  }
  verifySource(receipt.source);
  verifyProduct(receipt.product, options.binDir, options.expectedWasmOrigSha256);
  verifyBrowser(receipt.browser);
  verifyAdapter(receipt.adapter, receipt.browser.platform);
  sameJSON(receipt.contract, {
    attempts: REQUIRED_ATTEMPTS,
    initialExtent: INITIAL_EXTENT,
    shrunkExtent: SHRUNK_EXTENT,
    dominantFractionLimit: DOMINANT_FRACTION_LIMIT,
    shrinkTimeoutMs: SHRINK_TIMEOUT_MS,
    requiredStablePaintPolls: STABLE_PAINT_POLLS,
    postResizeInputEvents: 0,
  }, "acceptance contract");
  if (!Array.isArray(receipt.results) || receipt.results.length !== REQUIRED_ATTEMPTS) {
    fail("receipt does not contain ten attempts");
  }
  receipt.results.forEach((result, index) =>
    verifyResult(PNG, options.evidence, result, index + 1));
  const actualFiles = readdirSync(options.evidence).sort();
  const expectedFiles = ["receipt.json", ...expectedImageNames()].sort();
  sameJSON(actualFiles, expectedFiles, "immutable evidence inventory");
  return receipt;
}

function makeScenePNG(PNG, extent, flat = false) {
  const image = new PNG({width: extent[0], height: extent[1]});
  for (let y = 0; y < image.height; y++) {
    for (let x = 0; x < image.width; x++) {
      const at = (y * image.width + x) * 4;
      const high = flat ? 128 : (((x >> 4) + (y >> 4)) & 1 ? 196 : 54);
      image.data[at] = high;
      image.data[at + 1] = flat ? high : 96;
      image.data[at + 2] = flat ? high : 138;
      image.data[at + 3] = 255;
    }
  }
  return PNG.sync.write(image);
}

function fixtureProduct(binDir) {
  mkdirSync(binDir, {recursive: true});
  writeFileSync(join(binDir, "blender_browser.js"), "fixture javascript\n");
  writeFileSync(join(binDir, "blender_browser.wasm"), Buffer.from("fixture wasm"));
  writeFileSync(join(binDir, "blender_browser.wasm.orig"), Buffer.from("fixture original wasm"));
  writeFileSync(join(binDir, "blender_browser.data"), Buffer.from("fixture data"));
  const generation = {
    mode: "capture",
    original: {sha256: sha256File(join(binDir, "blender_browser.wasm.orig"))},
    instrumented: {sha256: sha256File(join(binDir, "blender_browser.wasm"))},
    js: {sha256: sha256File(join(binDir, "blender_browser.js"))},
  };
  writeFileSync(join(binDir, "blender_browser.split-build.json"),
    `${JSON.stringify(generation)}\n`);
  const fields = parseGenerationManifest(generation);
  return {
    expectedWasmOrigSha256: fields.originalWasmSha256,
    product: {
      binDir: portableRelative(REPO, binDir),
      files: Object.fromEntries(REQUIRED_PRODUCT_FILES.map((name) => [name,
        fileIdentity(join(binDir, name))])),
      generation: fields,
      servedGeneration: {url: "/blender_browser.split-build.json", ...fields},
    },
  };
}

function fixtureReceipt(PNG, evidenceDir, product) {
  mkdirSync(evidenceDir, {recursive: true});
  const initial = makeScenePNG(PNG, INITIAL_EXTENT);
  const shrunk = makeScenePNG(PNG, SHRUNK_EXTENT);
  const initialProof = semanticView3D(PNG.sync.read(initial), INITIAL_EXTENT);
  const shrinkProof = semanticView3D(PNG.sync.read(shrunk), SHRUNK_EXTENT);
  const results = [];
  for (let attempt = 1; attempt <= REQUIRED_ATTEMPTS; attempt++) {
    const prefix = String(attempt).padStart(2, "0");
    const images = {};
    for (const [key, suffix] of Object.entries(IMAGE_SUFFIXES)) {
      const name = `${prefix}-${suffix}`;
      writeFileSync(join(evidenceDir, name), key === "shrink" ? shrunk : initial);
      images[key] = fileIdentity(join(evidenceDir, name), evidenceDir);
    }
    results.push({
      attempt,
      ok: true,
      elapsedMs: 10000,
      shrinkPaintAtMs: 6000,
      boot: structuredClone(initialProof),
      baseline: structuredClone(initialProof),
      shrink: {...structuredClone(shrinkProof), stablePaintPolls: STABLE_PAINT_POLLS},
      images,
      postResizeInputEvents: 0,
      pageErrors: [],
      relevantErrors: Object.fromEntries(ERROR_KEYS.map((key) => [key, 0])),
      relevantConsole: [],
    });
  }
  return {
    schema: "blender-web.p0e-hardware-resize.v1",
    status: "PASS",
    run: basename(evidenceDir),
    startedAt: "2026-08-27T12:00:00.000Z",
    source: fileIdentity(PRODUCER, REPO),
    product,
    browser: {
      nodeVersion: NODE_VERSION,
      playwrightVersion: PLAYWRIGHT_VERSION,
      pngjsVersion: PNGJS_VERSION,
      chromiumVersion: CHROMIUM_VERSION,
      moduleSource: "fixture",
      platform: "darwin",
    },
    adapter: {
      contract: ADAPTER_CONTRACT,
      status: "ACCEPTED",
      present: true,
      platform: "darwin",
      powerPreference: "high-performance",
      isFallbackAdapter: false,
      info: {vendor: "apple", architecture: "metal-3", device: "M4 Pro", description: ""},
      softwareMatches: [],
      reason: "accepted-hardware",
    },
    contract: {
      attempts: REQUIRED_ATTEMPTS,
      initialExtent: INITIAL_EXTENT,
      shrunkExtent: SHRUNK_EXTENT,
      dominantFractionLimit: DOMINANT_FRACTION_LIMIT,
      shrinkTimeoutMs: SHRINK_TIMEOUT_MS,
      requiredStablePaintPolls: STABLE_PAINT_POLLS,
      postResizeInputEvents: 0,
    },
    results,
    completedAt: "2026-08-27T12:03:00.000Z",
    passed: REQUIRED_ATTEMPTS,
  };
}

function runSelfcheck(PNG) {
  if (process.version !== NODE_VERSION) fail(`Node ${NODE_VERSION} required, got ${process.version}`);
  const scratch = mkdtempSync(join(tmpdir(), "bw-p0e-receipt-"));
  let positive = 0;
  let negative = 0;
  try {
    const binDir = join(scratch, "checkout", "build-wasm-windowed-opt", "bin");
    const productFixture = fixtureProduct(binDir);
    const evidenceDir = join(scratch, "apple-fixture-r1");
    const canonical = fixtureReceipt(PNG, evidenceDir, productFixture.product);
    const receiptPath = join(evidenceDir, "receipt.json");
    const options = {
      evidence: evidenceDir,
      binDir,
      expectedWasmOrigSha256: productFixture.expectedWasmOrigSha256,
    };
    const writeReceipt = (receipt) => writeFileSync(receiptPath,
      `${JSON.stringify(receipt, null, 2)}\n`);
    writeReceipt(canonical);
    verifyReceipt(options, PNG);
    positive++;

    const rejectReceipt = (name, mutate) => {
      const candidate = structuredClone(canonical);
      mutate(candidate);
      writeReceipt(candidate);
      try {
        verifyReceipt(options, PNG);
      }
      catch (_) {
        negative++;
        writeReceipt(canonical);
        return;
      }
      fail(`self-check false green: ${name}`);
    };
    rejectReceipt("failed status", (receipt) => { receipt.status = "FAIL"; });
    rejectReceipt("nine attempts", (receipt) => { receipt.results.pop(); });
    rejectReceipt("fallback adapter", (receipt) => { receipt.adapter.isFallbackAdapter = true; });
    rejectReceipt("post-resize input", (receipt) => {
      receipt.results[0].postResizeInputEvents = 1;
    });
    rejectReceipt("page error", (receipt) => {
      receipt.results[0].pageErrors = [{name: "Error", message: "fixture"}];
    });
    rejectReceipt("unstable shrink", (receipt) => {
      receipt.results[0].shrink.stablePaintPolls = 2;
    });
    rejectReceipt("threshold drift", (receipt) => {
      receipt.contract.dominantFractionLimit = 1;
    });
    rejectReceipt("stale producer", (receipt) => { receipt.source.sha256 = "0".repeat(64); });
    rejectReceipt("stale product", (receipt) => {
      receipt.product.files["blender_browser.data"].sha256 = "0".repeat(64);
    });
    rejectReceipt("image identity", (receipt) => {
      receipt.results[0].images.shrink.sha256 = "0".repeat(64);
    });

    const shrinkPath = join(evidenceDir, "01-shrink.png");
    const shrinkBytes = readFileSync(shrinkPath);
    writeFileSync(shrinkPath, Buffer.concat([shrinkBytes, Buffer.from([0])]));
    let rejected = false;
    try {
      verifyReceipt(options, PNG);
    }
    catch (_) {
      rejected = true;
    }
    if (!rejected) fail("self-check false green: mutated image bytes");
    negative++;
    writeFileSync(shrinkPath, shrinkBytes);

    const flat = makeScenePNG(PNG, SHRUNK_EXTENT, true);
    writeFileSync(shrinkPath, flat);
    const flatReceipt = structuredClone(canonical);
    flatReceipt.results[0].images.shrink = fileIdentity(shrinkPath, evidenceDir);
    writeReceipt(flatReceipt);
    rejected = false;
    try {
      verifyReceipt(options, PNG);
    }
    catch (_) {
      rejected = true;
    }
    if (!rejected) fail("self-check false green: flat semantic image");
    negative++;
    writeFileSync(shrinkPath, shrinkBytes);
    writeReceipt(canonical);

    const extraPath = join(evidenceDir, "unexpected.txt");
    writeFileSync(extraPath, "unexpected\n");
    rejected = false;
    try {
      verifyReceipt(options, PNG);
    }
    catch (_) {
      rejected = true;
    }
    if (!rejected) fail("self-check false green: unexpected inventory file");
    negative++;
    rmSync(extraPath);

    verifyReceipt(options, PNG);
    positive++;
  }
  finally {
    rmSync(scratch, {recursive: true, force: true});
  }
  console.log(
    `BW_P0E_HARDWARE_RESIZE_RECEIPT_SELFCHECK_PASS positive=${positive} negative=${negative} ` +
    `attempts=${REQUIRED_ATTEMPTS} images=${REQUIRED_ATTEMPTS * 3}`,
  );
}

const options = parseArgs();
const PNG = loadPNG();
if (options.selfcheck) {
  runSelfcheck(PNG);
}
else {
  if (process.version !== NODE_VERSION) fail(`Node ${NODE_VERSION} required, got ${process.version}`);
  const receipt = verifyReceipt(options, PNG);
  console.log(
    `BW_P0E_HARDWARE_RESIZE_RECEIPT_PASS attempts=${receipt.passed}/${REQUIRED_ATTEMPTS} ` +
    `wasm_orig_sha256=${options.expectedWasmOrigSha256}`,
  );
}

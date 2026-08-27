// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Browser contract for the public pthread transport. It serves the current
// CAPTURE product through an in-memory, explicitly nonreceipt shell transform:
// the normal page script and pthread-main-loader use one content-addressed URL.
// No APPLY artifact, profile, milestone receipt, or build-tree byte is written.

import {createHash} from "node:crypto";
import {createReadStream, existsSync, readFileSync, statSync} from "node:fs";
import http from "node:http";
import {createRequire} from "node:module";
import {delimiter, dirname, extname, isAbsolute, join, relative, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "../..");
const BIN = resolve(process.env.BLENDER_WEB_BIN || join(ROOT, "build-wasm-windowed-opt/bin"));
const SHELL = join(ROOT, "platform_web/shell");
const LOADER_TEMPLATE = join(HERE, "pthread-main-loader.js");
const PLATFORM_PROFILE = join(ROOT, "patches/platform_wasm.cmake");
const NODE_VERSION = "v22.16.0";
const PLAYWRIGHT_VERSION = "1.61.1";
const TOKEN = "__BW_PAGE_GLUE_SHA256__";
const MAIN_PATH = "/bin/blender_browser.js";
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
const BASE_HEADERS = Object.freeze({
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
  "Cross-Origin-Resource-Policy": "same-origin",
  "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy": "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; " +
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; " +
    "worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
});
const MIME = Object.freeze({
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".wasm": "application/wasm",
  ".data": "application/octet-stream",
  ".woff2": "font/woff2",
});
const poolMatches = [...readFileSync(PLATFORM_PROFILE, "utf8").matchAll(
  /-sPTHREAD_POOL_SIZE=(\d+)/g,
)];
if (poolMatches.length !== 1 || !Number.isSafeInteger(Number(poolMatches[0][1]))) {
  throw new Error("browser pthread pool size is absent/ambiguous");
}
const PTHREAD_POOL_SIZE = Number(poolMatches[0][1]);

function isRepositoryDescendant(path) {
  const rel = relative(ROOT, resolve(path));
  return rel !== "" && !isAbsolute(rel) && rel.split(/[\\/]/)[0] !== "..";
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function resolvePlaywright(roots = MODULE_ROOTS) {
  const errors = [];
  for (const root of roots) {
    try {
      const require = createRequire(join(root, "package.json"));
      const version = require("playwright/package.json").version;
      const chromium = require("playwright").chromium;
      if (version !== PLAYWRIGHT_VERSION || !chromium) {
        throw new Error(`playwright=${version || "missing"}`);
      }
      return {chromium, version, root};
    }
    catch (error) {
      errors.push(`${root}: ${error.message}`);
    }
  }
  throw new Error(`cannot resolve Playwright; set BW_NODE_MODULES\n${errors.join("\n")}`);
}

function deriveDocuments(digest) {
  if (!/^[0-9a-f]{64}$/.test(digest)) {
    throw new Error("page-glue SHA-256 is not canonical");
  }
  const mainUrl = `${MAIN_PATH}?sha256=${digest}`;
  const loaderTemplate = readFileSync(LOADER_TEMPLATE, "utf8");
  if (loaderTemplate.split(TOKEN).length - 1 !== 1) {
    throw new Error("pthread loader identity token is absent/ambiguous");
  }
  const loader = loaderTemplate.replace(TOKEN, digest);
  const sourceIndex = readFileSync(join(SHELL, "windowed.html"), "utf8");
  const mainTag = `<script src="${MAIN_PATH}"></script>`;
  if (sourceIndex.split(mainTag).length - 1 !== 1) {
    throw new Error("windowed page main-script seam is absent/ambiguous");
  }
  const injected = `<script src="${mainUrl}"></script>\n` +
    "  <script src=\"/pthread-main-loader.js\"></script>";
  return {digest, mainUrl, loader, index: sourceIndex.replace(mainTag, injected)};
}

function deriveSources() {
  const main = join(BIN, "blender_browser.js");
  return {main, ...deriveDocuments(sha256(main))};
}

function selfcheck() {
  if (process.version !== NODE_VERSION) {
    throw new Error(`Node ${NODE_VERSION} required, got ${process.version}`);
  }
  if (HERE !== join(ROOT, "sandbox/m8-staged-deploy") ||
      !isRepositoryDescendant(LOADER_TEMPLATE) || !existsSync(join(ROOT, "GOAL.md"))) {
    throw new Error("repository/source roots are not derived and confined");
  }
  for (const path of [join(SHELL, "windowed.html"), LOADER_TEMPLATE, PLATFORM_PROFILE]) {
    if (!existsSync(path) || !statSync(path).isFile()) throw new Error(`missing input: ${path}`);
  }
  const derived = deriveDocuments("0123456789abcdef".repeat(4));
  if (!derived.loader.includes(derived.mainUrl) || !derived.index.includes(derived.mainUrl) ||
      derived.loader.includes(TOKEN) || derived.index.includes(TOKEN)) {
    throw new Error("derived page and loader do not share one content-addressed URL");
  }
  resolvePlaywright();
  console.log(
    `M8_PTHREAD_SHARED_MAIN_CACHE_SELFCHECK_PASS node=${process.version} ` +
    `playwright=${PLAYWRIGHT_VERSION} source_only=true writes=0 receipts=0`,
  );
}

if (process.argv.length !== 2 && !(process.argv.length === 3 && process.argv[2] === "--selfcheck")) {
  throw new Error("usage: test_pthread_shared_main_cache.mjs [--selfcheck]");
}
if (process.argv[2] === "--selfcheck") {
  selfcheck();
  process.exit(0);
}
if (process.version !== NODE_VERSION) {
  throw new Error(`Node ${NODE_VERSION} required, got ${process.version}`);
}

const derived = deriveSources();
for (const path of [
  derived.main, join(BIN, "blender_browser.wasm"), join(BIN, "blender_browser.data"),
]) {
  if (!existsSync(path) || !statSync(path).isFile()) throw new Error(`missing product input: ${path}`);
}
const originCounts = new Map();
const memoryFiles = new Map([
  ["/windowed.html", Buffer.from(derived.index)],
  ["/pthread-main-loader.js", Buffer.from(derived.loader)],
]);
const diskFiles = new Map([
  [MAIN_PATH, derived.main],
  ["/bin/blender_browser.wasm", join(BIN, "blender_browser.wasm")],
  ["/bin/blender_browser.data", join(BIN, "blender_browser.data")],
  ["/diagnostics-bootstrap.js", join(SHELL, "diagnostics-bootstrap.js")],
  ["/file-bridge.js", join(SHELL, "file-bridge.js")],
  ["/boot-windowed.js", join(SHELL, "boot-windowed.js")],
  ["/fonts/bw-interface-sans.woff2", join(SHELL, "fonts/bw-interface-sans.woff2")],
]);

const server = http.createServer((request, response) => {
  const url = new URL(request.url || "/", "http://127.0.0.1");
  const path = url.pathname === "/" ? "/windowed.html" : url.pathname;
  for (const [name, value] of Object.entries(BASE_HEADERS)) response.setHeader(name, value);
  if (path === MAIN_PATH) {
    if (url.pathname + url.search !== derived.mainUrl) {
      response.writeHead(400); response.end("noncanonical page-glue URL"); return;
    }
    response.setHeader("Cache-Control", "public, max-age=31536000, immutable");
    originCounts.set(path, (originCounts.get(path) || 0) + 1);
  }
  const memory = memoryFiles.get(path);
  const disk = diskFiles.get(path);
  if (memory) {
    response.writeHead(200, {"Content-Type": MIME[extname(path)] || "application/octet-stream",
      "Content-Length": memory.length});
    response.end(memory); return;
  }
  if (disk && existsSync(disk)) {
    const bytes = statSync(disk).size;
    response.writeHead(200, {"Content-Type": MIME[extname(path)] || "application/octet-stream",
      "Content-Length": bytes});
    createReadStream(disk).pipe(response); return;
  }
  response.writeHead(404); response.end();
});
await new Promise((resolvePromise) => server.listen(0, "127.0.0.1", resolvePromise));
const port = server.address().port;
const {chromium} = resolvePlaywright();
const browser = await chromium.launch({headless: true, args: ["--enable-unsafe-webgpu"]});
const context = await browser.newContext({viewport: {width: 1280, height: 720}, deviceScaleFactor: 1});
const page = await context.newPage();
const pageErrors = [];
const workers = [];
page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
page.on("worker", (worker) => workers.push(worker.url()));
try {
  await page.goto(`http://127.0.0.1:${port}/windowed.html`, {
    waitUntil: "domcontentloaded", timeout: 60_000,
  });
  await page.waitForFunction(() => {
    const state = document.querySelector("#state");
    return state?.textContent.includes("main loop (WM_main)") && globalThis.__bwModule;
  }, null, {timeout: 180_000});
  const proof = await page.evaluate((sourceUrl) => {
    const absolute = new URL(sourceUrl, location.href).href;
    const entries = performance.getEntriesByName(absolute).map((entry) => ({
      name: new URL(entry.name).pathname + new URL(entry.name).search,
      initiator_type: entry.initiatorType,
      transfer_size: entry.transferSize,
      decoded_body_size: entry.decodedBodySize,
    }));
    return {isolated: crossOriginIsolated, state: {...globalThis.__bwPthreadMainScript}, entries};
  }, derived.mainUrl);
  const initiators = proof.entries.map((entry) => entry.initiator_type).sort();
  const transfers = proof.entries.map((entry) => entry.transfer_size);
  const decoded = proof.entries.map((entry) => entry.decoded_body_size);
  const pageOrigin = `http://127.0.0.1:${port}`;
  const validWorkers = workers.filter((url) => url.startsWith(`blob:${pageOrigin}/`));
  const pass = proof.isolated === true && pageErrors.length === 0 &&
    originCounts.get(MAIN_PATH) === 1 && proof.entries.length === 2 &&
    JSON.stringify(initiators) === JSON.stringify(["fetch", "script"]) &&
    transfers.filter((value) => value === 0).length === 1 &&
    transfers.filter((value) => value > 0).length === 1 &&
    decoded.every((value) => value === statSync(derived.main).size) &&
    proof.state?.contract === "pthread-main-script-cache-v2" &&
    proof.state?.sourceUrl === derived.mainUrl && proof.state?.sha256 === derived.digest &&
    proof.state?.factoryCalls === 1 && proof.state?.phase === "ready" &&
    workers.length === PTHREAD_POOL_SIZE && validWorkers.length === PTHREAD_POOL_SIZE;
  if (!pass) {
    throw new Error("shared-main cache browser proof failed: " + JSON.stringify({
      proof, origin_gets: originCounts.get(MAIN_PATH) || 0,
      workers: workers.length, valid_workers: validWorkers.length, page_errors: pageErrors,
    }));
  }
  console.log(
    `M8_PTHREAD_SHARED_MAIN_CACHE_BROWSER_PASS main=${derived.digest.slice(0, 12)} ` +
    `origin_gets=1 consumers=script+fetch transfers=1+cache workers=${validWorkers.length}/${PTHREAD_POOL_SIZE} ` +
    `csp=strict page_errors=0 receipt=none`,
  );
}
finally {
  await context.close().catch(() => {});
  await browser.close().catch(() => {});
  await new Promise((resolvePromise) => server.close(resolvePromise));
}

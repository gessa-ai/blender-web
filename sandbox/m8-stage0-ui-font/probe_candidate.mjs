// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

// Diagnostic-only A/B for the Stage-0 UI-font bootstrap candidate. This does
// not produce a launch, pixel, adapter, or performance receipt.

import {createHash} from "node:crypto";
import {createRequire} from "node:module";
import {mkdirSync, readFileSync, writeFileSync} from "node:fs";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const moduleRoots = [
  process.env.BW_NODE_MODULES,
  resolve(root, ".m4-node/node_modules"),
].filter(Boolean);
let chromium = null;
let PNG = null;
for (const candidate of moduleRoots) {
  try {
    const require = createRequire(resolve(candidate, "package.json"));
    chromium = require("playwright").chromium;
    PNG = require("pngjs").PNG;
    break;
  }
  catch (_) {}
}
if (!chromium || !PNG) {
  throw new Error(`playwright/pngjs unavailable; checked ${moduleRoots.join(", ")}`);
}

const baselinePort = Number(process.argv[2] || 8136);
const candidatePort = Number(process.argv[3] || 8137);
const artifactDir = resolve(root, "sandbox/m8-stage0-ui-font/artifacts");
const stage1Loader = resolve(root, "sandbox/m8-staged-deploy/stage1-loader.js");
mkdirSync(artifactDir, {recursive: true});

const fontPath = "/bw/datafiles/fonts/Inter.woff2";
const monoFontPath = "/bw/datafiles/fonts/DejaVuSansMono.woff2";
const fullInterControl = readFileSync(resolve(root, "upstream/release/datafiles/fonts/Inter.woff2"));
const fullMonoControl = readFileSync(
  resolve(root, "upstream/release/datafiles/fonts/DejaVuSansMono.woff2"));
const monoSubsetControl = readFileSync(
  resolve(root, "platform_web/shell/fonts/bw-console-mono.woff2"));

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function pixelDelta(leftBytes, rightBytes) {
  const left = PNG.sync.read(leftBytes);
  const right = PNG.sync.read(rightBytes);
  if (left.width !== right.width || left.height !== right.height) {
    throw new Error(`image extent mismatch ${left.width}x${left.height} / ${right.width}x${right.height}`);
  }
  let changed = 0;
  let maxChannelDelta = 0;
  let totalChannelDelta = 0;
  for (let i = 0; i < left.data.length; i += 4) {
    let pixelChanged = false;
    for (let channel = 0; channel < 4; channel++) {
      const delta = Math.abs(left.data[i + channel] - right.data[i + channel]);
      maxChannelDelta = Math.max(maxChannelDelta, delta);
      totalChannelDelta += delta;
      if (delta !== 0) pixelChanged = true;
    }
    if (pixelChanged) changed += 1;
  }
  return {
    width: left.width,
    height: left.height,
    changed,
    ratio: changed / (left.width * left.height),
    maxChannelDelta,
    totalChannelDelta,
  };
}

async function waitForProduct(page) {
  await page.waitForFunction(() => {
    const state = document.querySelector("#state")?.dataset.state;
    if (state === "error" || state === "aborted") {
      throw new Error(`boot entered ${state}`);
    }
    const mod = window.__bwModule;
    return state === "running" && typeof mod?._bw_present_count === "function" &&
      Number(mod._bw_present_count()) > 0;
  }, null, {timeout: 180000, polling: 25});
  await page.waitForTimeout(2500);
}

async function browserFontRasterContract(page) {
  return page.evaluate(async () => {
    const full = new FontFace("BW Full Control",
      "url('/fonts/full-inter-control.woff2')", {style: "normal", weight: "400"});
    const subset = new FontFace("BW Subset Control",
      "url('/fonts/bw-interface-sans.woff2')", {style: "normal", weight: "400"});
    await Promise.all([full.load(), subset.load()]);
    document.fonts.add(full);
    document.fonts.add(subset);
    const corpus = [
      ...Array.from({length: 0x7f - 0x20}, (_, index) => index + 0x20),
      ...Array.from({length: 0x100 - 0xa0}, (_, index) => index + 0xa0),
    ].filter((codepoint) => codepoint !== 0xad)
      .map((codepoint) => String.fromCodePoint(codepoint)).join("");
    const render = (family, text = corpus) => {
      const canvas = new OffscreenCanvas(4096, 80);
      const context = canvas.getContext("2d", {alpha: false});
      context.fillStyle = "#000";
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = "#fff";
      context.textBaseline = "alphabetic";
      context.fontKerning = "normal";
      context.font = `400 14px "${family}"`;
      const width = context.measureText(text).width;
      context.fillText(text, 8, 40);
      return {width, pixels: context.getImageData(0, 0, canvas.width, canvas.height).data};
    };
    const left = render("BW Full Control");
    const right = render("BW Subset Control");
    let changedChannels = 0;
    let maxChannelDelta = 0;
    for (let index = 0; index < left.pixels.length; index++) {
      const delta = Math.abs(left.pixels[index] - right.pixels[index]);
      if (delta) changedChannels += 1;
      maxChannelDelta = Math.max(maxChannelDelta, delta);
    }
    const basicLatin = Array.from({length: 0x7f - 0x20}, (_, index) =>
      String.fromCodePoint(index + 0x20)).join("");
    const basicLeft = render("BW Full Control", basicLatin);
    const basicRight = render("BW Subset Control", basicLatin);
    let basicLatinChangedChannels = 0;
    for (let index = 0; index < basicLeft.pixels.length; index++) {
      if (basicLeft.pixels[index] !== basicRight.pixels[index]) basicLatinChangedChannels += 1;
    }
    const changedCodepoints = [];
    for (const character of corpus) {
      const renderGlyph = (family) => {
        const canvas = new OffscreenCanvas(48, 48);
        const context = canvas.getContext("2d", {alpha: false});
        context.fillStyle = "#000";
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.fillStyle = "#fff";
        context.textBaseline = "alphabetic";
        context.font = `400 14px "${family}"`;
        const width = context.measureText(character).width;
        context.fillText(character, 8, 28);
        return {width, pixels: context.getImageData(0, 0, canvas.width, canvas.height).data};
      };
      const fullGlyph = renderGlyph("BW Full Control");
      const subsetGlyph = renderGlyph("BW Subset Control");
      if (fullGlyph.width !== subsetGlyph.width ||
          fullGlyph.pixels.some((value, index) => value !== subsetGlyph.pixels[index])) {
        changedCodepoints.push(character.codePointAt(0));
      }
    }
    return {
      codepoints: [...corpus].length,
      fullWidth: left.width,
      subsetWidth: right.width,
      changedChannels,
      maxChannelDelta,
      changedCodepoints,
      basicLatinFullWidth: basicLeft.width,
      basicLatinSubsetWidth: basicRight.width,
      basicLatinChangedChannels,
    };
  });
}

async function browserMonoRasterContract(page) {
  return page.evaluate(async () => {
    const full = new FontFace("BW Mono Full Control",
      "url('/fonts/full-mono-control.woff2')", {style: "normal", weight: "400"});
    const subset = new FontFace("BW Mono Subset Control",
      "url('/fonts/subset-mono-control.woff2')", {style: "normal", weight: "400"});
    await Promise.all([full.load(), subset.load()]);
    document.fonts.add(full);
    document.fonts.add(subset);
    const corpus = [
      ...Array.from({length: 0x7f - 0x20}, (_, index) => index + 0x20),
      ...Array.from({length: 0x100 - 0xa0}, (_, index) => index + 0xa0),
    ].filter((codepoint) => codepoint !== 0xad)
      .map((codepoint) => String.fromCodePoint(codepoint)).join("");
    const basicLatin = Array.from({length: 0x7f - 0x20}, (_, index) =>
      String.fromCodePoint(index + 0x20)).join("");
    const render = (family, text, px) => {
      const canvas = new OffscreenCanvas(8192, 80);
      const context = canvas.getContext("2d", {alpha: false});
      context.fillStyle = "#000";
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = "#fff";
      context.textBaseline = "alphabetic";
      context.fontKerning = "normal";
      context.font = `400 ${px}px "${family}"`;
      const width = context.measureText(text).width;
      context.fillText(text, 8, 48);
      return {width, pixels: context.getImageData(0, 0, canvas.width, canvas.height).data};
    };
    const results = [];
    for (const px of [10, 11, 12, 14, 16, 24]) {
      const left = render("BW Mono Full Control", corpus, px);
      const right = render("BW Mono Subset Control", corpus, px);
      const basicLeft = render("BW Mono Full Control", basicLatin, px);
      const basicRight = render("BW Mono Subset Control", basicLatin, px);
      let changedChannels = 0;
      let maxChannelDelta = 0;
      let basicLatinChangedChannels = 0;
      for (let index = 0; index < left.pixels.length; index++) {
        const delta = Math.abs(left.pixels[index] - right.pixels[index]);
        if (delta) changedChannels += 1;
        maxChannelDelta = Math.max(maxChannelDelta, delta);
      }
      for (let index = 0; index < basicLeft.pixels.length; index++) {
        if (basicLeft.pixels[index] !== basicRight.pixels[index]) {
          basicLatinChangedChannels += 1;
        }
      }
      results.push({
        px,
        fullWidth: left.width,
        subsetWidth: right.width,
        changedChannels,
        maxChannelDelta,
        basicLatinFullWidth: basicLeft.width,
        basicLatinSubsetWidth: basicRight.width,
        basicLatinChangedChannels,
      });
    }
    const changedCodepoints = [];
    for (const character of corpus) {
      const renderGlyph = (family) => render(family, character, 14);
      const left = renderGlyph("BW Mono Full Control");
      const right = renderGlyph("BW Mono Subset Control");
      if (left.width !== right.width ||
          left.pixels.some((value, index) => value !== right.pixels[index])) {
        changedCodepoints.push(character.codePointAt(0));
      }
    }
    return {codepoints: [...corpus].length, results, changedCodepoints};
  });
}

async function fontIdentity(page, path) {
  return page.evaluate(async (path) => {
    const bytes = window.__bwModule.FS.readFile(path);
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    return {
      bytes: bytes.length,
      sha256: Array.from(digest, (value) => value.toString(16).padStart(2, "0")).join(""),
    };
  }, path);
}

async function run(browser, port, label, staged) {
  const context = await browser.newContext({
    viewport: {width: 1280, height: 720},
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  await page.route("**/fonts/full-inter-control.woff2", (route) => route.fulfill({
    status: 200, contentType: "font/woff2", body: fullInterControl,
  }));
  await page.route("**/fonts/full-mono-control.woff2", (route) => route.fulfill({
    status: 200, contentType: "font/woff2", body: fullMonoControl,
  }));
  await page.route("**/fonts/subset-mono-control.woff2", (route) => route.fulfill({
    status: 200, contentType: "font/woff2", body: monoSubsetControl,
  }));
  const consoleErrors = [];
  const pageErrors = [];
  page.on("console", (message) => {
    const text = message.text();
    if (/error|failed|exception/i.test(text) &&
        !/GPU stall due to ReadPixels|fallback adapter/i.test(text)) {
      consoleErrors.push(text);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(String(error?.message || error)));
  await page.addInitScript(({manual}) => {
    if (manual) window.__BW_STAGE1_MANUAL = true;
  }, {manual: staged});
  await page.goto(`http://127.0.0.1:${port}/index.html`, {
    waitUntil: "domcontentloaded",
    timeout: 180000,
  });
  await waitForProduct(page);
  const initialFont = await fontIdentity(page, fontPath);
  const initialMono = await fontIdentity(page, monoFontPath);
  const fontRaster = staged ? await browserFontRasterContract(page) : null;
  if (fontRaster && (fontRaster.basicLatinChangedChannels !== 0 ||
      fontRaster.basicLatinFullWidth !== fontRaster.basicLatinSubsetWidth ||
      fontRaster.fullWidth !== fontRaster.subsetWidth ||
      JSON.stringify(fontRaster.changedCodepoints) !== JSON.stringify([170, 179, 186]))) {
    throw new Error(`font raster mismatch: ${JSON.stringify(fontRaster)}`);
  }
  const monoRaster = staged ? await browserMonoRasterContract(page) : null;
  if (monoRaster && (monoRaster.results.some((row) =>
    row.fullWidth !== row.subsetWidth ||
    row.basicLatinFullWidth !== row.basicLatinSubsetWidth ||
    row.basicLatinChangedChannels !== 0) ||
      JSON.stringify(monoRaster.changedCodepoints) !== JSON.stringify([170, 179, 186]))) {
    throw new Error(`mono font raster mismatch: ${JSON.stringify(monoRaster)}`);
  }
  const initialPng = await page.locator("#canvas").screenshot();
  let restoredFont = null;
  let restoredMono = null;
  let stage1 = null;
  let restoredPng = null;
  if (staged) {
    await page.addScriptTag({path: stage1Loader});
    stage1 = await page.evaluate(() => window.__bwStage1Load());
    if (stage1?.phase !== "done" || stage1?.error !== null ||
        stage1?.bootstrapDone !== 2 || stage1?.fontRefresh !== "done") {
      throw new Error(`Stage 1 failed: ${JSON.stringify(stage1)}`);
    }
    await page.waitForFunction(() => !document.getElementById("bw-stage-progress"), null,
      {timeout: 10000});
    await page.waitForTimeout(500);
    restoredFont = await fontIdentity(page, fontPath);
    restoredMono = await fontIdentity(page, monoFontPath);
    restoredPng = await page.locator("#canvas").screenshot();
  }
  const result = {
    label,
    initialFont,
    initialMono,
    restoredFont,
    restoredMono,
    fontRaster,
    monoRaster,
    stage1,
    initialPng: {bytes: initialPng.length, sha256: sha256(initialPng)},
    restoredPng: restoredPng && {bytes: restoredPng.length, sha256: sha256(restoredPng)},
    consoleErrors,
    pageErrors,
  };
  await context.close();
  return {result, initialPng, restoredPng};
}

const browser = await chromium.launch({
  headless: false,
  args: [
    "--enable-unsafe-webgpu",
    "--use-webgpu-adapter=swiftshader",
    "--use-gpu-in-tests",
    ...(process.platform === "linux" && process.env.DISPLAY ? ["--ozone-platform=x11"] : []),
  ],
});
try {
  const baseline = await run(browser, baselinePort, "baseline", false);
  const candidate = await run(browser, candidatePort, "candidate", true);
  const result = {
    contract: "stage0-font-bootstrap-diagnostic-v2",
    diagnosticNonreceipt: true,
    baseline: baseline.result,
    candidate: candidate.result,
    initialDelta: pixelDelta(baseline.initialPng, candidate.initialPng),
    restoredDelta: pixelDelta(baseline.initialPng, candidate.restoredPng),
  };
  writeFileSync(resolve(artifactDir, "probe-result.json"), `${JSON.stringify(result, null, 2)}\n`);
  console.log(
    `BW_STAGE0_UI_FONT_DIAGNOSTIC initial_changed=${result.initialDelta.changed} ` +
    `restored_changed=${result.restoredDelta.changed} ` +
    `initial_font=${candidate.result.initialFont.bytes} ` +
    `restored_font=${candidate.result.restoredFont.bytes} ` +
    `initial_mono=${candidate.result.initialMono.bytes} ` +
    `restored_mono=${candidate.result.restoredMono.bytes} ` +
    `basic_latin_raster_changed=${candidate.result.fontRaster.basicLatinChangedChannels} ` +
    `mono_basic_raster_changed=${candidate.result.monoRaster.results.reduce((n, row) => n + row.basicLatinChangedChannels, 0)} ` +
    `mono_latin1_variants=${candidate.result.monoRaster.changedCodepoints.join(",")} ` +
    `page_errors=${candidate.result.pageErrors.length}`,
  );
}
finally {
  await browser.close();
}

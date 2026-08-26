// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

// Diagnostic-only A/B for the Stage-0 UI-font bootstrap candidate. This does
// not produce a launch, pixel, adapter, or performance receipt.

import {createHash} from "node:crypto";
import {createRequire} from "node:module";
import {mkdirSync, writeFileSync} from "node:fs";
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
mkdirSync(artifactDir, {recursive: true});

const fontPath = "/bw/datafiles/fonts/Inter.woff2";

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

async function fontIdentity(page) {
  return page.evaluate(async (path) => {
    const bytes = window.__bwModule.FS.readFile(path);
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    return {
      bytes: bytes.length,
      sha256: Array.from(digest, (value) => value.toString(16).padStart(2, "0")).join(""),
    };
  }, fontPath);
}

async function run(browser, port, label, staged) {
  const context = await browser.newContext({
    viewport: {width: 1280, height: 720},
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
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
  await page.goto(`http://127.0.0.1:${port}/windowed.html`, {
    waitUntil: "domcontentloaded",
    timeout: 180000,
  });
  await waitForProduct(page);
  const initialFont = await fontIdentity(page);
  const fontRaster = staged ? await browserFontRasterContract(page) : null;
  if (fontRaster && (fontRaster.basicLatinChangedChannels !== 0 ||
      fontRaster.basicLatinFullWidth !== fontRaster.basicLatinSubsetWidth ||
      fontRaster.fullWidth !== fontRaster.subsetWidth ||
      JSON.stringify(fontRaster.changedCodepoints) !== JSON.stringify([170, 179, 186]))) {
    throw new Error(`font raster mismatch: ${JSON.stringify(fontRaster)}`);
  }
  const initialPng = await page.locator("#canvas").screenshot();
  let restoredFont = null;
  let stage1 = null;
  let restoredPng = null;
  if (staged) {
    stage1 = await page.evaluate(() => window.__bwStage1Load());
    if (stage1?.phase !== "done" || stage1?.error !== null ||
        stage1?.bootstrapDone !== 1 || stage1?.fontRefresh !== "done") {
      throw new Error(`Stage 1 failed: ${JSON.stringify(stage1)}`);
    }
    await page.waitForFunction(() => !document.getElementById("bw-stage-progress"), null,
      {timeout: 10000});
    await page.waitForTimeout(500);
    restoredFont = await fontIdentity(page);
    restoredPng = await page.locator("#canvas").screenshot();
  }
  const result = {
    label,
    initialFont,
    restoredFont,
    fontRaster,
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
    contract: "stage0-ui-font-bootstrap-diagnostic-v1",
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
    `basic_latin_raster_changed=${candidate.result.fontRaster.basicLatinChangedChannels} ` +
    `page_errors=${candidate.result.pageErrors.length}`,
  );
}
finally {
  await browser.close();
}

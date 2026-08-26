#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0

import {createRequire} from "node:module";
import {readFileSync} from "node:fs";
import {resolve} from "node:path";

const ROOT = resolve(import.meta.dirname, "../..");
const require = createRequire(import.meta.url);
const {chromium} = require(resolve(ROOT, ".m4-node/node_modules/playwright"));
const port = Number(process.argv[2] || 8197);
const executablePath = process.argv[3] ||
  "/home/pc/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const screenshot = process.argv[4] || "/tmp/bw-loader-redesign.png";
const fullInter = readFileSync(resolve(ROOT, "upstream/release/datafiles/fonts/Inter.woff2"));
const base = `http://127.0.0.1:${port}`;
const failures = [];
const external = [];

function check(condition, message) {
  if (!condition) failures.push(message);
}

const browser = await chromium.launch({headless: true, executablePath});
try {
  const context = await browser.newContext({
    viewport: {width: 1280, height: 720}, deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  page.on("request", request => {
    const url = new URL(request.url());
    if (url.origin !== base) external.push(request.url());
  });
  await page.route(`${base}/**`, async route => {
    const pathname = new URL(route.request().url()).pathname;
    if (["/diagnostics-bootstrap.js", "/bin/blender_browser.js",
         "/file-bridge.js", "/boot-windowed.js"].includes(pathname)) {
      await route.fulfill({status: 200, contentType: "text/javascript", body: ""});
      return;
    }
    if (pathname === "/fonts/full-inter-control.woff2") {
      await route.fulfill({status: 200, contentType: "font/woff2", body: fullInter});
      return;
    }
    await route.continue();
  });
  await page.goto(`${base}/windowed.html`, {waitUntil: "domcontentloaded"});
  await page.evaluate(() => document.fonts.ready);
  const state = await page.evaluate(() => {
    const style = id => getComputedStyle(document.getElementById(id));
    const rect = id => {
      const value = document.getElementById(id).getBoundingClientRect();
      return {width: value.width, height: value.height};
    };
    const footer = document.getElementById("bw-legal-footer");
    return {
      background: style("loader").backgroundColor,
      spinner: {width: parseFloat(style("bw-spinner").width),
        height: parseFloat(style("bw-spinner").height)},
      spinnerTop: style("bw-spinner").borderTopColor,
      progress: rect("bw-progress"),
      fill: rect("bw-fill"),
      pct: document.getElementById("bw-pct").textContent.trim(),
      footerWhiteSpace: getComputedStyle(footer).whiteSpace,
      footerLines: Math.round(footer.scrollHeight / parseFloat(getComputedStyle(footer).lineHeight)),
      sourceText: document.getElementById("bw-source-link").textContent.trim(),
      sourceHref: document.getElementById("bw-source-link").href,
      fontLoaded: document.fonts.check('400 11px "BW Interface Sans"'),
      retired: ["bw-native-proof", "bw-offline-proof", "bw-desktop-limit",
        "bw-source-pending", "bw-license-link"].filter(id => document.getElementById(id)),
      spinners: document.querySelectorAll(".bw-spinner").length,
      bars: document.querySelectorAll('[role="progressbar"]').length,
      diagLeft: style("bw-diag").left,
    };
  });
  const raster = await page.evaluate(async () => {
    const full = new FontFace("BW Full Control",
      "url('/fonts/full-inter-control.woff2')", {style: "normal", weight: "400"});
    const subset = new FontFace("BW Subset Control",
      "url('/fonts/bw-interface-sans.woff2')", {style: "normal", weight: "400"});
    await Promise.all([full.load(), subset.load()]);
    document.fonts.add(full);
    document.fonts.add(subset);
    const text = Array.from({length: 0x7f - 0x20}, (_, index) =>
      String.fromCodePoint(index + 0x20)).join("");
    const render = (family) => {
      const canvas = new OffscreenCanvas(2048, 80);
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
    for (let index = 0; index < left.pixels.length; index++) {
      if (left.pixels[index] !== right.pixels[index]) changedChannels += 1;
    }
    return {codepoints: [...text].length, fullWidth: left.width,
      subsetWidth: right.width, changedChannels};
  });
  check(state.background === "rgb(23, 24, 27)", "loader background is not #17181b");
  check(state.spinner.width === 24 && state.spinner.height === 24,
    "spinner is not the 24px thin ring");
  check(state.spinnerTop === "rgb(211, 214, 220)", "spinner accent drifted");
  check(state.progress.width === 240 && state.progress.height === 2,
    "progress bar is not slim/determinate");
  check(state.fill.width === 0 && state.pct === "0%", "initial progress is not truthful 0%");
  check(state.footerWhiteSpace === "nowrap" && state.footerLines === 1,
    "legal footer is not a single line");
  check(state.sourceText === "Source code (GPL)" &&
    state.sourceHref === "https://github.com/gessa-ai/blender-web",
  "preferred-form source offer drifted");
  check(state.fontLoaded, "local loader font did not load");
  check(raster.codepoints === 95 && raster.fullWidth === raster.subsetWidth &&
    raster.changedChannels === 0,
  `layout-preserving Basic Latin font raster drifted: ${JSON.stringify(raster)}`);
  check(state.retired.length === 0 && state.spinners === 1 && state.bars === 1,
    "loader contains retired or duplicate visible elements");
  check(state.diagLeft === "-99999px", "hidden diagnostics contract became visible");
  check(external.length === 0, `loader made external requests: ${external.join(",")}`);
  await page.screenshot({path: screenshot});
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(`M4_LOADER_BROWSER_FAIL ${failures[0]}`);
  process.exit(1);
}
console.log(`M4_LOADER_BROWSER_PASS viewport=1280x720 spinner=1 progress=1 ` +
  `font=local basic_latin_raster=exact screenshot=${screenshot}`);

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r50 first-composite BEFORE/AFTER driver (P2 blocker #6).
//
// GENUINELY ZERO INPUT. Boots the windowed blender_browser build in the shell's
// ?gate=WxH exact-size mode (DPR forced to 1), NO pyexpr, and sends NO mouse or
// keyboard event whatsoever. Waits for the WM_main marker, then captures the
// #canvas clip + reads the bw_wm_tick_count / bw_present_count diagnostics at
// +10 s and +30 s. The whole point of blocker #6 is that a real user's fresh tab
// sends no input, so the rig must send none: no mouse-move workaround.
//
// PASS (AFTER, fixed): the +10 s capture shows the full UI (splash + workspace
// chrome), i.e. high colour variety + presents advanced past the boot burst.
// FAIL (BEFORE, defect): +10 s and +30 s stay background-only (near-uniform).
//
// Serve first (this lane = :8132):
//   BLENDER_WEB_BIN=$PWD/build-wasm-windowed-opt/bin \
//   BLENDER_WEB_SHELL=$PWD/platform_web/shell \
//     /opt/homebrew/bin/bash scripts/serve-web.sh 8132
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/ghost-r50-first-composite/drive-first-composite.mjs [label] [WxH] [port]

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");
const { PNG } = require("pngjs");

const LABEL = (process.argv[2] || "before").trim();
const SIZE = (process.argv[3] || "1600x900").trim();
const PORT = parseInt(process.argv[4] || "8132", 10);
const mm = /^(\d+)x(\d+)$/.exec(SIZE);
if (!mm) { console.error(`bad size "${SIZE}"`); process.exit(2); }
const W = parseInt(mm[1], 10), H = parseInt(mm[2], 10);

const BASE = `http://localhost:${PORT}`;
const OUTDIR = "/Users/paws/blender-web/sandbox/ghost-r50-first-composite";
fs.mkdirSync(OUTDIR, { recursive: true });
const BOOT_MS = 240000;
const LICENSE = "SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n";

function ts() { return new Date().toISOString().replace("T", " ").replace("Z", ""); }
const LOG = [];
function log(s) { const l = `[${ts()}] ${s}`; console.log(l); LOG.push(l); }
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
function writeLicense(p) { fs.writeFileSync(p + ".license", LICENSE); }

// Metrics over a captured PNG: non-black fraction AND colour variety (number of
// distinct 5-bit-per-channel buckets, and the modal-colour share). A blank /
// background-only canvas is near-uniform => few buckets, high modal share. A full
// UI (splash + chrome) has many buckets and a low modal share.
function analyze(pngPath) {
  const png = PNG.sync.read(fs.readFileSync(pngPath));
  const n = png.width * png.height;
  const hist = new Map();
  let nonBlack = 0;
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    const r = png.data[o], g = png.data[o + 1], b = png.data[o + 2];
    if (r > 12 || g > 12 || b > 12) nonBlack++;
    const key = ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3);
    hist.set(key, (hist.get(key) || 0) + 1);
  }
  let modal = 0;
  for (const c of hist.values()) if (c > modal) modal = c;
  return {
    w: png.width, h: png.height,
    nonBlackFrac: nonBlack / n,
    buckets: hist.size,
    modalShare: modal / n,
    bytes: fs.statSync(pngPath).size,
  };
}

async function readCounters(page) {
  return page.evaluate(() => {
    const m = window.__bwModule;
    if (!m) return null;
    return {
      tick: (typeof m._bw_wm_tick_count === "function") ? Number(m._bw_wm_tick_count()) : null,
      present: (typeof m._bw_present_count === "function") ? Number(m._bw_present_count()) : null,
    };
  });
}

async function captureCanvas(page, outPath) {
  const rect = await page.evaluate(() => {
    const r = document.getElementById("canvas").getBoundingClientRect();
    return { x: r.x, y: r.y };
  });
  await page.screenshot({ path: outPath, clip: { x: Math.round(rect.x), y: Math.round(rect.y), width: W, height: H } });
  writeLicense(outPath);
}

const url = `${BASE}/windowed.html?gate=${W}x${H}`;
const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 120, height: H + 120 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();

let presentMsgs = 0;
const con = [];
page.on("console", (m) => {
  const t = m.text();
  con.push(t);
  if (t.includes("presentBackbuffer")) presentMsgs++;
});
page.on("pageerror", (e) => con.push("pageerror: " + (e && e.message ? e.message : e)));

const result = { label: LABEL, size: SIZE };
try {
  log(`ZERO-INPUT boot: ${url}  (label=${LABEL})`);
  await page.goto(url, { waitUntil: "domcontentloaded" });
  const iso = await page.evaluate(() => ({ iso: self.crossOriginIsolated === true, sab: typeof SharedArrayBuffer !== "undefined" }));
  log(`crossOriginIsolated=${iso.iso} SAB=${iso.sab}`);
  const t0 = Date.now();
  await page.waitForFunction(() => {
    const s = document.querySelector("#state");
    return s && s.textContent.includes("main loop (WM_main)");
  }, { timeout: BOOT_MS });
  const bootMs = Date.now() - t0;
  log(`WM_main reached in ${bootMs} ms; NO input will be sent`);

  const gate = await page.evaluate(() => {
    const c = document.getElementById("canvas");
    return { bw: c.width, bh: c.height, dpr: window.devicePixelRatio };
  });
  log(`gate backing ${gate.bw}x${gate.bh} dpr ${gate.dpr}`);

  // +10 s from WM_main
  await sleep(10000);
  const c10 = await readCounters(page);
  const p10 = path.join(OUTDIR, `${LABEL}_${W}x${H}_t10.png`);
  await captureCanvas(page, p10);
  const a10 = analyze(p10);
  log(`+10s: tick=${c10 && c10.tick} present=${c10 && c10.present} presentMsgs=${presentMsgs} | ${p10}`);
  log(`+10s: nonBlack=${(a10.nonBlackFrac * 100).toFixed(1)}% buckets=${a10.buckets} modalShare=${(a10.modalShare * 100).toFixed(1)}% bytes=${a10.bytes}`);

  // +30 s from WM_main
  await sleep(20000);
  const c30 = await readCounters(page);
  const p30 = path.join(OUTDIR, `${LABEL}_${W}x${H}_t30.png`);
  await captureCanvas(page, p30);
  const a30 = analyze(p30);
  log(`+30s: tick=${c30 && c30.tick} present=${c30 && c30.present} presentMsgs=${presentMsgs} | ${p30}`);
  log(`+30s: nonBlack=${(a30.nonBlackFrac * 100).toFixed(1)}% buckets=${a30.buckets} modalShare=${(a30.modalShare * 100).toFixed(1)}% bytes=${a30.bytes}`);

  result.bootMs = bootMs;
  result.c10 = c10; result.c30 = c30; result.presentMsgs = presentMsgs;
  result.a10 = a10; result.a30 = a30;
  result.t10 = p10; result.t30 = p30;
  // Heuristic verdict: full UI => many colour buckets and modal share well under 90%.
  result.fullUI_10 = a10.buckets > 300 && a10.modalShare < 0.9;
  result.fullUI_30 = a30.buckets > 300 && a30.modalShare < 0.9;
  log(`VERDICT ${LABEL}: fullUI@10s=${result.fullUI_10} fullUI@30s=${result.fullUI_30}`);
} catch (e) {
  result.error = String(e && e.message ? e.message : e);
  log(`ERROR ${result.error}`);
} finally {
  fs.writeFileSync(path.join(OUTDIR, `${LABEL}-console.log`), con.join("\n"));
  fs.writeFileSync(path.join(OUTDIR, `${LABEL}-run.log`), LOG.join("\n"));
  fs.writeFileSync(path.join(OUTDIR, `${LABEL}-result.json`), JSON.stringify(result, null, 2));
  await ctx.close();
  await browser.close();
}
process.exit(result.error ? 1 : 0);

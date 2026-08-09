// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r51: single zero-input boot against a caller-supplied PERSISTENT profile dir,
// with a caller-supplied ?env string. Reports frame0/frame1 + cache hit/miss +
// verify (IDENTICAL/MISMATCH) counts. Lets us reuse one OPFS profile across a
// cold-populate boot, a timing+verify warm boot, and a cache-off control boot.
//
// Usage: node probe-one.mjs <port> <profileDir> <tag> [envstring]

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const { chromium } = require("playwright");
const fs = require("fs");

const PORT = parseInt(process.argv[2] || "8134", 10);
const PROFILE = process.argv[3];
const TAG = process.argv[4] || "one";
const ENVSTR = process.argv[5] || "";
const W = 1600, H = 900;
const OUTDIR = "/Users/paws/blender-web/sandbox/gpu-r51-shader-latency";
const HOLD_MS = parseInt(process.env.HOLD_MS || "34000", 10);
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
if (!PROFILE) { console.error("need profileDir"); process.exit(2); }
fs.mkdirSync(PROFILE, { recursive: true });

const ctx = await chromium.launchPersistentContext(PROFILE, {
  headless: false, viewport: { width: W + 120, height: H + 120 }, deviceScaleFactor: 1,
});
const page = ctx.pages()[0] || await ctx.newPage();
const con = [];
const t0 = Date.now();
page.on("console", (m) => { con.push(`+${((Date.now() - t0) / 1000).toFixed(3)}s ${m.text()}`); });
let u = `http://localhost:${PORT}/windowed.html?gate=${W}x${H}`;
if (ENVSTR) u += `&env=${encodeURIComponent(ENVSTR)}`;
console.log(`[r51] ${TAG} boot: ${u}`);
await page.goto(u, { waitUntil: "domcontentloaded" });
await page.waitForFunction(
  () => { const s = document.querySelector("#state"); return s && s.textContent.includes("main loop (WM_main)"); },
  { timeout: 240000 });
const tWM = ((Date.now() - t0) / 1000).toFixed(3);
await sleep(HOLD_MS);
fs.writeFileSync(`${OUTDIR}/${TAG}-console.log`, con.join("\n"));

const f0 = (con.find(l => /presentBackbuffer frame 0/.test(l)) || "").split(" ")[0] || null;
const f1 = (con.find(l => /presentBackbuffer frame 1/.test(l)) || "").split(" ")[0] || null;
const timing = con.filter(l => /BW_SHADER_TIMING name=/.test(l));
let hits = 0, misses = 0, shaderc = 0, tint = 0;
for (const l of timing) {
  if (/cache=hit/.test(l)) hits++; else if (/cache=miss/.test(l)) misses++;
  const s = l.match(/shaderc_us=([0-9]+)/); if (s) shaderc += parseInt(s[1], 10);
  const t = l.match(/tint_us=([0-9]+)/); if (t) tint += parseInt(t[1], 10);
}
const verify = con.filter(l => /BW_SHADER_CACHE_VERIFY/.test(l));
const vId = verify.filter(l => /IDENTICAL/.test(l)).length;
const vMis = verify.filter(l => /MISMATCH/.test(l)).length;
const rec = { tag: TAG, env: ENVSTR, wm_main_s: parseFloat(tWM), frame0: f0, frame1: f1,
  timing_lines: timing.length, cache_hits: hits, cache_misses: misses,
  shaderc_ms: +(shaderc / 1000).toFixed(1), tint_ms: +(tint / 1000).toFixed(1),
  verify_identical: vId, verify_mismatch: vMis };
fs.writeFileSync(`${OUTDIR}/${TAG}-result.json`, JSON.stringify(rec, null, 2));
console.log("[r51] RESULT " + JSON.stringify(rec));
await ctx.close(); process.exit(0);

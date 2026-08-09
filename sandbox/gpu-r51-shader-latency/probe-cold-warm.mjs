// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r51 Phase-2: cold vs warm boot time-to-first-UI-present with the OPFS WGSL
// translation cache. Uses a PERSISTENT browser profile so the OPFS mount (hence
// /projects/.shadercache) survives between boots:
//   - cold boot: fresh profile => empty cache => shaderc+Tint run, WGSL written.
//   - warm boot: same profile => cache hit => shaderc+Tint skipped.
// Zero input throughout; frame 1 = first real UI composite.
//
// Usage: node probe-cold-warm.mjs <port> <label> [envForBoth]
//   envForBoth e.g. "BW_SHADER_CACHE=0" to A/B the cache off (both boots cold).

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const { chromium } = require("playwright");
const fs = require("fs");
const os = require("os");
const path = require("path");

const PORT = parseInt(process.argv[2] || "8134", 10);
const LABEL = process.argv[3] || "cw";
const ENVBOTH = process.argv[4] || "";
const W = 1600, H = 900;
const OUTDIR = "/Users/paws/blender-web/sandbox/gpu-r51-shader-latency";
const HOLD_MS = parseInt(process.env.HOLD_MS || "34000", 10);
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), `bw-r51-${LABEL}-`));
console.log(`[r51] persistent profile: ${profileDir}`);

async function boot(tag, extraEnv) {
  const ctx = await chromium.launchPersistentContext(profileDir, {
    headless: false,
    viewport: { width: W + 120, height: H + 120 },
    deviceScaleFactor: 1,
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  const con = [];
  const t0 = Date.now();
  page.on("console", (m) => { con.push(`+${((Date.now() - t0) / 1000).toFixed(3)}s ${m.text()}`); });
  const envParts = [ENVBOTH, extraEnv].filter(Boolean).join(",");
  let u = `http://localhost:${PORT}/windowed.html?gate=${W}x${H}`;
  if (envParts) u += `&env=${encodeURIComponent(envParts)}`;
  console.log(`[r51] ${tag} boot: ${u}`);
  await page.goto(u, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => { const s = document.querySelector("#state"); return s && s.textContent.includes("main loop (WM_main)"); },
    { timeout: 240000 });
  const tWM = ((Date.now() - t0) / 1000).toFixed(3);
  await sleep(HOLD_MS);
  fs.writeFileSync(`${OUTDIR}/${LABEL}-${tag}-console.log`, con.join("\n"));
  const f0 = (con.find(l => /presentBackbuffer frame 0/.test(l)) || "").split(" ")[0] || null;
  const f1 = (con.find(l => /presentBackbuffer frame 1/.test(l)) || "").split(" ")[0] || null;
  const timing = con.filter(l => /BW_SHADER_TIMING name=/.test(l));
  let hits = 0, misses = 0;
  for (const l of timing) { if (/cache=hit/.test(l)) hits++; else if (/cache=miss/.test(l)) misses++; }
  const verify = con.filter(l => /BW_SHADER_CACHE_VERIFY/.test(l));
  const vId = verify.filter(l => /IDENTICAL/.test(l)).length;
  const vMis = verify.filter(l => /MISMATCH/.test(l)).length;
  const m7 = (con.find(l => /M7 store:/.test(l)) || "").replace(/^\+[0-9.]+s\s*/, "");
  await ctx.close();
  const rec = { tag, wm_main_s: parseFloat(tWM), frame0: f0, frame1: f1, timing_lines: timing.length, cache_hits: hits, cache_misses: misses, verify_identical: vId, verify_mismatch: vMis, m7 };
  console.log(`[r51] ${tag} RESULT ` + JSON.stringify(rec));
  return rec;
}

const cold = await boot("cold", process.env.COLD_ENV || "");
await sleep(1500);
const warm = await boot("warm", process.env.WARM_ENV || "");
await sleep(1500);
const warm2 = await boot("warm2", process.env.WARM_ENV || "");

fs.writeFileSync(`${OUTDIR}/${LABEL}-summary.json`, JSON.stringify({ label: LABEL, env_both: ENVBOTH, hold_ms: HOLD_MS, cold, warm, warm2 }, null, 2));
console.log(`[r51] ${LABEL} DONE cold.frame1=${cold.frame1} warm.frame1=${warm.frame1} warm2.frame1=${warm2.frame1}`);
process.exit(0);

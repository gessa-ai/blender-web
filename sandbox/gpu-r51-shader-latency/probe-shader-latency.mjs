// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r51 Phase-1: per-stage shader-latency breakdown of the boot compile block.
// Boots the windowed-opt build ZERO-INPUT with ?env=BW_SHADER_TIMING=1 so the
// wgpu_shader_compiler emits one BW_SHADER_TIMING line per shader (interface-map,
// shaderc GLSL->SPIR-V, Tint SPIR-V->WGSL micros + entry/exit steady timestamps).
// Also records "presentBackbuffer frame 0/1" (time-to-first-UI-present).
//
// Usage: node probe-shader-latency.mjs <port> <outtag> [envstring]
//   envstring default "BW_SHADER_TIMING=1"; pass "" for a clean baseline run.

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const { chromium } = require("playwright");
const fs = require("fs");

const PORT = parseInt(process.argv[2] || "8134", 10);
const TAG = process.argv[3] || "run";
const ENVSTR = process.argv[4] !== undefined ? process.argv[4] : "BW_SHADER_TIMING=1";
const W = 1600, H = 900;
const OUTDIR = "/Users/paws/blender-web/sandbox/gpu-r51-shader-latency";
const HOLD_MS = parseInt(process.env.HOLD_MS || "26000", 10);
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

let u = `http://localhost:${PORT}/windowed.html?gate=${W}x${H}`;
if (ENVSTR && ENVSTR.length) u += `&env=${encodeURIComponent(ENVSTR)}`;

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 120, height: H + 120 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const con = [];
const t0 = Date.now();
page.on("console", (m) => { con.push(`+${((Date.now() - t0) / 1000).toFixed(3)}s ${m.text()}`); });
console.log(`[r51] boot: ${u}`);
await page.goto(u, { waitUntil: "domcontentloaded" });
const tNav = Date.now();
await page.waitForFunction(
  () => { const s = document.querySelector("#state"); return s && s.textContent.includes("main loop (WM_main)"); },
  { timeout: 240000 });
const tWM = ((Date.now() - t0) / 1000).toFixed(3);
console.log(`[r51] WM_main at +${tWM}s; holding ${HOLD_MS}ms ZERO input`);
await sleep(HOLD_MS);

fs.writeFileSync(`${OUTDIR}/${TAG}-console.log`, con.join("\n"));

// Extract present frames + timing lines.
const present = con.filter(l => /presentBackbuffer frame/.test(l));
const timing = con.filter(l => /BW_SHADER_TIMING name=/.test(l));
const compiling = con.filter(l => /Compiling Shader/.test(l));
present.forEach(l => console.log("PRESENT: " + l));
console.log(`[r51] WM_main=+${tWM}s  timing_lines=${timing.length}  compiling_lines=${compiling.length}  total_console=${con.length}`);

// Summarise the per-stage breakdown if timing present.
if (timing.length) {
  let iface = 0, shaderc = 0, tint = 0, stages = 0, words = 0;
  let firstEntry = null, lastExit = null;
  const parsed = [];
  for (const l of timing) {
    const g = (k) => { const m = l.match(new RegExp(k + "=([0-9]+)")); return m ? parseInt(m[1], 10) : 0; };
    const nm = (l.match(/name=(\S+)/) || [])[1] || "?";
    const rec = { name: nm, entry: g("entry_us"), exit: g("exit_us"), iface: g("iface_us"), shaderc: g("shaderc_us"), tint: g("tint_us"), nstages: g("nstages"), words: g("spirv_words") };
    parsed.push(rec);
    iface += rec.iface; shaderc += rec.shaderc; tint += rec.tint; stages += rec.nstages; words += rec.words;
    if (firstEntry === null) firstEntry = rec.entry;
    lastExit = rec.exit;
  }
  // Derive the createShaderModule + backend gap: sum of (next.entry - this.exit).
  let gap = 0;
  for (let i = 1; i < parsed.length; i++) gap += Math.max(0, parsed[i].entry - parsed[i - 1].exit);
  const wallSpan = lastExit - firstEntry; // us, first compile entry -> last compile exit
  const cpuTotal = iface + shaderc + tint;
  const summary = {
    tag: TAG, shaders: parsed.length, stages,
    wm_main_s: parseFloat(tWM),
    iface_ms: (iface / 1000).toFixed(1),
    shaderc_ms: (shaderc / 1000).toFixed(1),
    tint_ms: (tint / 1000).toFixed(1),
    cpu_total_ms: (cpuTotal / 1000).toFixed(1),
    intershader_gap_ms: (gap / 1000).toFixed(1),
    wall_span_ms: (wallSpan / 1000).toFixed(1),
    spirv_words: words,
    present_frame0: (present.find(l => /frame 0/.test(l)) || "").split(" ")[0] || null,
    present_frame1: (present.find(l => /frame 1/.test(l)) || "").split(" ")[0] || null,
  };
  fs.writeFileSync(`${OUTDIR}/${TAG}-summary.json`, JSON.stringify(summary, null, 2));
  fs.writeFileSync(`${OUTDIR}/${TAG}-timing.tsv`,
    "name\tentry_us\texit_us\tiface_us\tshaderc_us\ttint_us\tnstages\tspirv_words\n" +
    parsed.map(r => `${r.name}\t${r.entry}\t${r.exit}\t${r.iface}\t${r.shaderc}\t${r.tint}\t${r.nstages}\t${r.words}`).join("\n"));
  console.log("[r51] SUMMARY " + JSON.stringify(summary));
  // Top 12 costliest by shaderc+tint.
  parsed.sort((a, b) => (b.shaderc + b.tint) - (a.shaderc + a.tint));
  console.log("[r51] TOP 12 by CPU (shaderc+tint us):");
  parsed.slice(0, 12).forEach(r => console.log(`  ${r.name}  shaderc=${r.shaderc} tint=${r.tint} words=${r.words}`));
}

await ctx.close(); await browser.close(); process.exit(0);

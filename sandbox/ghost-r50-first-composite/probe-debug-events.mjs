// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Capture the exact GHOST event flow reaching the WM at boot with ZERO input,
// via Blender's own --debug-events (G_DEBUG_EVENTS) printed to stderr->console.
// No rebuild: uses the shell's ?args dev hook. Runs ~20 s past WM_main, no input.

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const { chromium } = require("playwright");
const fs = require("fs");
const PORT = parseInt(process.argv[2] || "8132", 10);
const W=1600,H=900;
const BASE=`http://localhost:${PORT}`;
const OUTDIR="/Users/paws/blender-web/sandbox/ghost-r50-first-composite";
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
function ts(){return new Date().toISOString().slice(11,23);}

const args = encodeURIComponent("--debug-events");
const u = `${BASE}/windowed.html?gate=${W}x${H}&args=${args}`;
const browser = await chromium.launch({ headless:false });
const ctx = await browser.newContext({ viewport:{width:W+120,height:H+120}, deviceScaleFactor:1 });
const page = await ctx.newPage();
const con=[];
page.on("console",(m)=>{ con.push(`[${ts()}] ${m.text()}`); });
page.on("pageerror",(e)=>con.push(`[${ts()}] pageerror: ${e&&e.message?e.message:e}`));

console.log(`debug-events boot: ${u}`);
await page.goto(u,{waitUntil:"domcontentloaded"});
await page.waitForFunction(()=>{const s=document.querySelector("#state");return s&&s.textContent.includes("main loop (WM_main)");},{timeout:240000});
console.log(`WM_main reached; capturing 22s of --debug-events, ZERO input`);
await sleep(22000);
fs.writeFileSync(`${OUTDIR}/debug-events-console.log`, con.join("\n"));
// print the window/ghost/handle-related lines
const interesting = con.filter(l=>/ghost|GHOST|window|handle|redraw|drawable|MOUSEMOVE|WINDOW|event|activate|expose|refresh/i.test(l));
console.log(`--- ${interesting.length} event-ish lines (first 60) ---`);
console.log(interesting.slice(0,60).join("\n"));
await ctx.close(); await browser.close();
process.exit(0);

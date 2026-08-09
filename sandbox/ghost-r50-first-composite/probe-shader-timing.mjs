// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Confirms the ~10 s blank period is the inline shader compile on the WM worker
// (r25 finding), by timestamping gpu.shader logs across boot with ZERO input.
// No rebuild: shell ?args hook -> --debug-gpu --log gpu.shader --log-level 4.

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const { chromium } = require("playwright");
const fs = require("fs");
const PORT=parseInt(process.argv[2]||"8132",10);
const W=1600,H=900;
const OUTDIR="/Users/paws/blender-web/sandbox/ghost-r50-first-composite";
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
const args=encodeURIComponent("--debug-gpu --log gpu.shader --log-level 4").replace(/%20/g,"%20");
const u=`http://localhost:${PORT}/windowed.html?gate=${W}x${H}&args=${args}`;
const browser=await chromium.launch({headless:false});
const ctx=await browser.newContext({viewport:{width:W+120,height:H+120},deviceScaleFactor:1});
const page=await ctx.newPage();
const con=[]; const t0=Date.now();
page.on("console",(m)=>{con.push(`+${((Date.now()-t0)/1000).toFixed(2)}s ${m.text()}`);});
console.log(`shader-timing boot: ${u}`);
await page.goto(u,{waitUntil:"domcontentloaded"});
await page.waitForFunction(()=>{const s=document.querySelector("#state");return s&&s.textContent.includes("main loop (WM_main)");},{timeout:240000});
console.log("WM_main; capturing 24s of gpu.shader logs, ZERO input");
await sleep(24000);
fs.writeFileSync(`${OUTDIR}/shader-timing-console.log`,con.join("\n"));
const compileLines=con.filter(l=>/compil|shader|GLSL|WGSL|Tint|link/i.test(l));
console.log(`total console lines=${con.length}  shader/compile lines=${compileLines.length}`);
console.log("--- first shader line, last shader line, present frames ---");
if(compileLines.length){console.log("FIRST: "+compileLines[0]);console.log("LAST : "+compileLines[compileLines.length-1]);}
con.filter(l=>/presentBackbuffer/.test(l)).forEach(l=>console.log("PRESENT: "+l));
await ctx.close(); await browser.close(); process.exit(0);

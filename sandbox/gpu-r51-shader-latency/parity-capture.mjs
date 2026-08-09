// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Whole-window parity capture for r50 (mirrors sandbox/m4-fullscreen-parity/
// capture_web.mjs: show_splash=False + VIEW_3D kick + gate WxH + canvas clip),
// but writes into THIS lane's sandbox so the shared parity artifact is untouched.
// Output is fed to compare_fullscreen.sh <out> workspace WxH.

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const { chromium } = require("playwright");
const SIZE=(process.argv[2]||"1600x900").trim();
const PORT=parseInt(process.argv[3]||"8132",10);
const SETTLE=parseInt(process.argv[4]||"55000",10);
const m=/^(\d+)x(\d+)$/.exec(SIZE); const W=+m[1],H=+m[2];
const OUT=`/Users/paws/blender-web/sandbox/gpu-r51-shader-latency/r51_parity_web_${W}x${H}.png`;
const PYEXPR=[
  "import bpy",
  "bpy.context.preferences.view.show_splash = False",
  "def _k():",
  "    for w in bpy.context.window_manager.windows:",
  "        s=w.screen",
  "        if not s: continue",
  "        for a in s.areas:",
  "            if a.type=='VIEW_3D':",
  "                for r in a.regions:",
  "                    if r.type=='WINDOW': r.tag_redraw()",
  "    return 1.0",
  "bpy.app.timers.register(_k, first_interval=1.0)",
].join("\n");
const url=`http://localhost:${PORT}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PYEXPR)}`;
function ts(){return new Date().toISOString().slice(11,23);}
const browser=await chromium.launch({headless:false});
const ctx=await browser.newContext({viewport:{width:W+100,height:H+100},deviceScaleFactor:1});
const page=await ctx.newPage();
let present=0; page.on("console",(m)=>{if(m.text().includes("presentBackbuffer"))present++;});
console.log(`[${ts()}] parity boot ${SIZE} settle ${SETTLE}ms`);
await page.goto(url,{waitUntil:"domcontentloaded"});
await page.waitForFunction(()=>{const s=document.querySelector("#state");return s&&s.textContent.includes("main loop (WM_main)");},{timeout:240000});
const g=await page.evaluate(()=>{const c=document.getElementById("canvas");return{bw:c.width,bh:c.height,dpr:window.devicePixelRatio};});
console.log(`[${ts()}] WM_main; gate ${g.bw}x${g.bh} dpr ${g.dpr}; settling...`);
await page.waitForTimeout(SETTLE);
const rect=await page.evaluate(()=>{const r=document.getElementById("canvas").getBoundingClientRect();return{x:r.x,y:r.y};});
await page.screenshot({path:OUT,clip:{x:Math.round(rect.x),y:Math.round(rect.y),width:W,height:H}});
require("fs").writeFileSync(OUT+".license","SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n");
console.log(`[${ts()}] captured -> ${OUT} (presentBackbuffer x${present})`);
await ctx.close(); await browser.close(); process.exit(0);

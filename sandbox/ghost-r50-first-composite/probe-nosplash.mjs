// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Zero-input timeline with show_splash=False (NO redraw kick, NO input). Tests
// whether the splash popup is what triggers the first composite: if this stays
// blank while the no-pyexpr (splash ON) boot composites, the splash is the
// load-bearing trigger and the golden-capture path (splash off) is the one that
// genuinely needs the mouse-move workaround.

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const { chromium } = require("playwright");
const fs = require("fs");

const PORT = parseInt(process.argv[2] || "8132", 10);
const KICK = process.argv[3] === "kick"; // add a VIEW_3D kick timer (still NO input)
const W = 1600, H = 900;
const INTERVAL = 2000, DURATION = 46000;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = "/Users/paws/blender-web/sandbox/ghost-r50-first-composite";
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
function ts(){return new Date().toISOString().slice(11,23);}
const LOG=[]; function log(s){const l=`[${ts()}] ${s}`;console.log(l);LOG.push(l);}

let py = "import bpy\nbpy.context.preferences.view.show_splash = False\n";
if (KICK) {
  py += [
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
}
const label = KICK ? "nosplash_kick" : "nosplash";
const u = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(py)}`;

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport:{width:W+120,height:H+120}, deviceScaleFactor:1 });
const page = await ctx.newPage();
let pMsgs=0; page.on("console",(m)=>{ if(m.text().includes("presentBackbuffer")) pMsgs++; });

async function sample(){
  const c = await page.evaluate(()=>{const m=window.__bwModule;return {tick:(m&&m._bw_wm_tick_count)?Number(m._bw_wm_tick_count()):null,present:(m&&m._bw_present_count)?Number(m._bw_present_count()):null};});
  const v = await page.evaluate(()=>{const cv=document.getElementById("canvas");const oc=document.createElement("canvas");oc.width=64;oc.height=36;const g=oc.getContext("2d");g.drawImage(cv,0,0,64,36);const d=g.getImageData(0,0,64,36).data;const s=new Set();let nb=0;for(let i=0;i<d.length;i+=4){const r=d[i],gg=d[i+1],b=d[i+2];if(r>12||gg>12||b>12)nb++;s.add(((r>>4)<<8)|((gg>>4)<<4)|(b>>4));}return {buckets:s.size,nb:nb/(64*36)};});
  return {...c,...v};
}

log(`ZERO-INPUT ${label}: ${u.slice(0,80)}...`);
await page.goto(u,{waitUntil:"domcontentloaded"});
const t0=Date.now();
await page.waitForFunction(()=>{const s=document.querySelector("#state");return s&&s.textContent.includes("main loop (WM_main)");},{timeout:240000});
log(`WM_main in ${Date.now()-t0} ms`);
let first=null;
for(let e=0;e<=DURATION;e+=INTERVAL){
  const s=await sample();
  const full=s.buckets>40&&s.nb>0.5;
  if(full&&first===null)first=e;
  log(`+${(e/1000).toFixed(0)}s\ttick=${s.tick}\tpresent=${s.present}\tpMsgs=${pMsgs}\tbuckets=${s.buckets}\tnb=${(s.nb*100).toFixed(0)}%\t${full?"FULL-UI":"blank"}`);
  await sleep(INTERVAL);
}
log(`firstFullUI(${label}, zero-input) = ${first===null?"NEVER within "+DURATION/1000+"s":"+"+first/1000+"s"}`);
fs.writeFileSync(`${OUTDIR}/${label}.log`, LOG.join("\n"));
// keep a final capture
const rect=await page.evaluate(()=>{const r=document.getElementById("canvas").getBoundingClientRect();return {x:r.x,y:r.y};});
await page.screenshot({path:`${OUTDIR}/${label}_final.png`,clip:{x:Math.round(rect.x),y:Math.round(rect.y),width:W,height:H}});
fs.writeFileSync(`${OUTDIR}/${label}_final.png.license`,"SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n");
await ctx.close(); await browser.close();
process.exit(0);

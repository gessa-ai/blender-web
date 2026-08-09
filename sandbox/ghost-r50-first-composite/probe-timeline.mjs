// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Zero-input first-composite TIMELINE probe. Samples (tick, present, canvas colour
// variety) every INTERVAL ms for DURATION ms after WM_main, sending NO input. Prints
// the first sample at which the full UI appears. Optional: ?keepalive=0 via arg.

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const { chromium } = require("playwright");
const fs = require("fs");

const LABEL = (process.argv[2] || "timeline").trim();
const PORT = parseInt(process.argv[3] || "8132", 10);
const EXTRA = (process.argv[4] || "").trim(); // e.g. "keepalive=0"
const W = 1600, H = 900;
const INTERVAL = 2000, DURATION = 50000;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = "/Users/paws/blender-web/sandbox/ghost-r50-first-composite";
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
function ts(){return new Date().toISOString().slice(11,23);}
const LOG=[]; function log(s){const l=`[${ts()}] ${s}`;console.log(l);LOG.push(l);}

let u = `${BASE}/windowed.html?gate=${W}x${H}`;
if (EXTRA) u += `&${EXTRA}`;

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport:{width:W+120,height:H+120}, deviceScaleFactor:1 });
const page = await ctx.newPage();
let presentMsgs=0;
page.on("console",(m)=>{ if(m.text().includes("presentBackbuffer")) presentMsgs++; });

// In-page canvas colour-variety sampler via toDataURL decode -> distinct 4-bit buckets.
async function sample(){
  const counters = await page.evaluate(()=>{
    const m=window.__bwModule;
    return { tick:(m&&m._bw_wm_tick_count)?Number(m._bw_wm_tick_count()):null,
             present:(m&&m._bw_present_count)?Number(m._bw_present_count()):null };
  });
  const variety = await page.evaluate(()=>{
    const c=document.getElementById("canvas");
    // downscale to a 64x36 offscreen for a cheap variety estimate
    const oc=document.createElement("canvas"); oc.width=64; oc.height=36;
    const g=oc.getContext("2d"); g.drawImage(c,0,0,64,36);
    const d=g.getImageData(0,0,64,36).data; const set=new Set(); let nonblack=0;
    for(let i=0;i<d.length;i+=4){ const r=d[i],gg=d[i+1],b=d[i+2];
      if(r>12||gg>12||b>12)nonblack++;
      set.add(((r>>4)<<8)|((gg>>4)<<4)|(b>>4)); }
    return { buckets:set.size, nonblack:nonblack/(64*36) };
  });
  return { ...counters, ...variety };
}

log(`ZERO-INPUT timeline: ${u}`);
await page.goto(u,{waitUntil:"domcontentloaded"});
const t0=Date.now();
await page.waitForFunction(()=>{const s=document.querySelector("#state");return s&&s.textContent.includes("main loop (WM_main)");},{timeout:240000});
log(`WM_main in ${Date.now()-t0} ms`);
const tMark=Date.now();
let firstFullUI=null;
for(let elapsed=0; elapsed<=DURATION; elapsed+=INTERVAL){
  const s=await sample();
  const full = s.buckets>40 && s.nonblack>0.5;
  if(full && firstFullUI===null) firstFullUI=elapsed;
  log(`+${(elapsed/1000).toFixed(0)}s\ttick=${s.tick}\tpresent=${s.present}\tpMsgs=${presentMsgs}\tbuckets=${s.buckets}\tnonblack=${(s.nonblack*100).toFixed(0)}%\t${full?"FULL-UI":"blank"}`);
  await sleep(INTERVAL);
}
log(`firstFullUI(zero-input) = ${firstFullUI===null?"NEVER within "+DURATION/1000+"s":"+"+firstFullUI/1000+"s"}`);
fs.writeFileSync(`${OUTDIR}/${LABEL}.log`, LOG.join("\n"));
await ctx.close(); await browser.close();
process.exit(0);

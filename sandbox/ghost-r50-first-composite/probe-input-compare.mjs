// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Does a FIRST mouse event change first-composite timing? Boots two fresh tabs:
//   (a) zero input
//   (b) one mouse-move over the canvas at +2 s (before the first WM tick), then nothing
// Samples both timelines. If (b) does NOT composite earlier than (a), the first
// composite is gated on boot progress (the inline shader compile), NOT on input.

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const { chromium } = require("playwright");
const fs = require("fs");
const W=1600,H=900,PORT=parseInt(process.argv[2]||"8132",10);
const BASE=`http://localhost:${PORT}`;
const OUTDIR="/Users/paws/blender-web/sandbox/ghost-r50-first-composite";
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
function ts(){return new Date().toISOString().slice(11,23);}
const LOG=[];function log(s){const l=`[${ts()}] ${s}`;console.log(l);LOG.push(l);}

async function run(browser,label,injectMove){
  const ctx=await browser.newContext({viewport:{width:W+120,height:H+120},deviceScaleFactor:1});
  const page=await ctx.newPage();
  const u=`${BASE}/windowed.html?gate=${W}x${H}`;
  log(`${label}: ${u}`);
  await page.goto(u,{waitUntil:"domcontentloaded"});
  const t0=Date.now();
  await page.waitForFunction(()=>{const s=document.querySelector("#state");return s&&s.textContent.includes("main loop (WM_main)");},{timeout:240000});
  log(`${label}: WM_main in ${Date.now()-t0} ms`);
  const tMark=Date.now();
  let injected=false, first=null;
  for(let e=0;e<=34000;e+=1000){
    if(injectMove && !injected && e>=2000){
      // ONE mouse move over the canvas center, then never again.
      const r=await page.evaluate(()=>{const b=document.getElementById("canvas").getBoundingClientRect();return{x:b.x+b.width/2,y:b.y+b.height/2};});
      await page.mouse.move(r.x,r.y);
      injected=true; log(`${label}: injected ONE mouse move @+${(e/1000).toFixed(0)}s at (${Math.round(r.x)},${Math.round(r.y)})`);
    }
    const s=await page.evaluate(()=>{const m=window.__bwModule;const cv=document.getElementById("canvas");const oc=document.createElement("canvas");oc.width=64;oc.height=36;const g=oc.getContext("2d");g.drawImage(cv,0,0,64,36);const d=g.getImageData(0,0,64,36).data;const set=new Set();let nb=0;for(let i=0;i<d.length;i+=4){const rr=d[i],gg=d[i+1],b=d[i+2];if(rr>12||gg>12||b>12)nb++;set.add(((rr>>4)<<8)|((gg>>4)<<4)|(b>>4));}return{tick:(m&&m._bw_wm_tick_count)?Number(m._bw_wm_tick_count()):null,present:(m&&m._bw_present_count)?Number(m._bw_present_count()):null,buckets:set.size,nb:nb/(64*36)};});
    const composited=s.nb>0.5;
    if(composited && first===null) first=e;
    log(`${label}\t+${(e/1000).toFixed(0)}s\ttick=${s.tick}\tpresent=${s.present}\tnb=${(s.nb*100).toFixed(0)}%\t${composited?"COMPOSITED":"blank"}`);
    await sleep(1000);
  }
  log(`${label}: firstComposite = ${first===null?"NEVER":"+"+first/1000+"s"}`);
  await ctx.close();
  return first;
}

const browser=await chromium.launch({headless:false});
const a=await run(browser,"A_zeroinput",false);
const b=await run(browser,"B_one_move",true);
log(`RESULT: zeroInput firstComposite=${a===null?"NEVER":"+"+a/1000+"s"}  oneMove firstComposite=${b===null?"NEVER":"+"+b/1000+"s"}`);
fs.writeFileSync(`${OUTDIR}/input-compare.log`,LOG.join("\n"));
await browser.close();
process.exit(0);

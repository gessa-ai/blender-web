// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Tree-health re-checks post-i18n (no code change this lane; confirms the tree is
// sound around first-composite):
//   1. keepalive liveness + no idle burn (mirror of drive-keepalive.mjs scenario A,
//      run in THIS sandbox so keepalive evidence is untouched).
//   2. interaction: after the zero-input composite, a click + Esc changes the
//      composite (splash dismissed) -> present advances.
//   3. resize recomposite (r28-era): non-gate boot, shrink the viewport, the canvas
//      backing changes and a new present lands.

import { createRequire } from "module";
const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const { chromium } = require("playwright");
const fs = require("fs");
const PORT=parseInt(process.argv[2]||"8132",10);
const BASE=`http://localhost:${PORT}`;
const OUTDIR="/Users/paws/blender-web/sandbox/ghost-r50-first-composite";
const LIC="SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n";
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
function ts(){return new Date().toISOString().slice(11,23);}
const LOG=[];function log(s){const l=`[${ts()}] ${s}`;console.log(l);LOG.push(l);}
async function counters(page){return page.evaluate(()=>{const m=window.__bwModule;return{tick:(m&&m._bw_wm_tick_count)?Number(m._bw_wm_tick_count()):null,present:(m&&m._bw_present_count)?Number(m._bw_present_count()):null};});}
async function waitComposite(page,capMs){const t0=Date.now();while(Date.now()-t0<capMs){const nb=await page.evaluate(()=>{const cv=document.getElementById("canvas");const oc=document.createElement("canvas");oc.width=32;oc.height=18;const g=oc.getContext("2d");g.drawImage(cv,0,0,32,18);const d=g.getImageData(0,0,32,18).data;let nb=0;for(let i=0;i<d.length;i+=4)if(d[i]>12||d[i+1]>12||d[i+2]>12)nb++;return nb/(32*18);});if(nb>0.5)return Date.now()-t0;await sleep(1000);}return -1;}
const res={};

const browser=await chromium.launch({headless:false});

// --- 1 + 2: keepalive liveness + interaction (gate 1600x900, splash ON) ---
{
  const W=1600,H=900;
  const ctx=await browser.newContext({viewport:{width:W+120,height:H+120},deviceScaleFactor:1});
  const page=await ctx.newPage();
  let pMsg=0; page.on("console",(m)=>{if(m.text().includes("presentBackbuffer"))pMsg++;});
  await page.goto(`${BASE}/windowed.html?gate=${W}x${H}`,{waitUntil:"domcontentloaded"});
  await page.waitForFunction(()=>{const s=document.querySelector("#state");return s&&s.textContent.includes("main loop (WM_main)");},{timeout:240000});
  const comp=await waitComposite(page,40000);
  log(`[1/2] zero-input composite at +${comp}ms`);
  // keepalive liveness: idle 12s, tick must advance, present ~flat
  const a=await counters(page); await sleep(12000); const b=await counters(page);
  const tickD=b.tick-a.tick, presD=b.present-a.present;
  res.keepalive={tickDelta:tickD,presentDelta:presD,presentPerSec:presD/12,alive:tickD>10,noBurn:presD<12*5};
  log(`[1] keepalive idle 12s: tickDelta=${tickD} presentDelta=${presD} (${(presD/12).toFixed(2)}/s) alive=${res.keepalive.alive} noBurn=${res.keepalive.noBurn}`);
  // interaction: click Continue on splash then Esc; present must advance & canvas change
  const pre=`${OUTDIR}/health_interaction_pre.png`; await page.screenshot({path:pre,clip:{x:0,y:0,width:W,height:H}}); fs.writeFileSync(pre+".license",LIC);
  const c0=await counters(page);
  const rect=await page.evaluate(()=>{const r=document.getElementById("canvas").getBoundingClientRect();return{x:r.x,y:r.y};});
  await page.mouse.click(rect.x+800, rect.y+648); // Continue button
  await sleep(1500);
  await page.keyboard.press("Escape");
  await sleep(1500);
  const c1=await counters(page);
  const post=`${OUTDIR}/health_interaction_post.png`; await page.screenshot({path:post,clip:{x:0,y:0,width:W,height:H}}); fs.writeFileSync(post+".license",LIC);
  res.interaction={presentDelta:c1.present-c0.present,responded:(c1.present-c0.present)>0};
  log(`[2] interaction click+Esc: presentDelta=${c1.present-c0.present} responded=${res.interaction.responded}`);
  await ctx.close();
}

// --- 3: resize recomposite (non-gate) ---
{
  const ctx=await browser.newContext({viewport:{width:1400,height:850},deviceScaleFactor:1});
  const page=await ctx.newPage();
  await page.goto(`${BASE}/windowed.html`,{waitUntil:"domcontentloaded"});
  await page.waitForFunction(()=>{const s=document.querySelector("#state");return s&&s.textContent.includes("main loop (WM_main)");},{timeout:240000});
  const comp=await waitComposite(page,40000);
  const g0=await page.evaluate(()=>{const c=document.getElementById("canvas");return{w:c.width,h:c.height};});
  const c0=await counters(page);
  log(`[3] non-gate composite at +${comp}ms; backing ${g0.w}x${g0.h} present=${c0.present}`);
  await page.setViewportSize({width:1000,height:700});
  await sleep(3000);
  const g1=await page.evaluate(()=>{const c=document.getElementById("canvas");return{w:c.width,h:c.height};});
  const c1=await counters(page);
  const shot=`${OUTDIR}/health_resize_after.png`; await page.screenshot({path:shot}); fs.writeFileSync(shot+".license",LIC);
  res.resize={before:g0,after:g1,backingChanged:(g0.w!==g1.w||g0.h!==g1.h),presentDelta:c1.present-c0.present,recomposited:(c1.present-c0.present)>0};
  log(`[3] after resize->1000x700: backing ${g1.w}x${g1.h} backingChanged=${res.resize.backingChanged} presentDelta=${c1.present-c0.present} recomposited=${res.resize.recomposited}`);
  await ctx.close();
}

await browser.close();
fs.writeFileSync(`${OUTDIR}/health-result.json`,JSON.stringify(res,null,2));
fs.writeFileSync(`${OUTDIR}/health-run.log`,LOG.join("\n"));
log(`SUMMARY keepalive(alive=${res.keepalive.alive},noBurn=${res.keepalive.noBurn}) interaction(responded=${res.interaction.responded}) resize(recomposited=${res.resize.recomposited},backingChanged=${res.resize.backingChanged})`);
process.exit(0);

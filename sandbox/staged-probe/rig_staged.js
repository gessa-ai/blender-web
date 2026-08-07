// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M8 staged-loading probe rig. Headed bundled-Chromium (per notes/gpu-r23).
//   (A) Boot the opt windowed binary to WM_main; env receipts.
//   (B) LAZY-LOAD PROOF: after boot, fetch a synthetic module ABSENT from the
//       baked blender_browser.data over the wire, mount it into the live WASMFS
//       via the exported FS API, and prove the running interpreter imports it
//       (a bpy.app.timer writes the marker to a WASMFS file we read main-thread).
//   (C) THROTTLE: CDP-emulate 4G, fetch the real 4.5 MB stage0.data.br, measure
//       effective throughput to validate the analytic time-to-interactive model.
const path = require("path");
const { chromium } = require(process.env.PW);

const URL = "http://localhost:8125/windowed.html";
const TGT = "/bw/python/lib/python3.13/bw_stage1_probe.py"; // existing on-sys.path dir
const PYEXPR = [
  "import bpy,os,sys,importlib",
  "def _p():",
  "  if os.path.exists('/bw/_stage1_ready'):",
  "    importlib.invalidate_caches()",
  "    ex=os.path.exists('" + TGT + "')",
  "    try:",
  "      import bw_stage1_probe as m; r='OK '+m.MARKER+' file='+m.__file__",
  "    except Exception as e: r='FAIL exists='+str(ex)+' '+repr(e)",
  "    f=open('/bw/_stage1_result','w'); f.write(r); f.close(); return None",
  "  return 0.2",
  "bpy.app.timers.register(_p,first_interval=0.5)",
].join("\n");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch({
    headless: false,
    args: ["--enable-unsafe-webgpu", "--enable-features=Vulkan"],
  });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await ctx.newPage();
  const logs = [];
  page.on("console", (m) => logs.push(m.text()));
  page.on("pageerror", (e) => logs.push("PAGEERR " + e.message));

  // seed the boot python-expr before the shell reads it
  await page.addInitScript((expr) => { window.__BW_PYEXPR = expr; }, PYEXPR);

  await page.goto(URL, { waitUntil: "load" });
  // env receipts
  const env = await page.evaluate(() => ({
    coi: self.crossOriginIsolated,
    gpu: !!navigator.gpu,
    vis: document.visibilityState,
    canvas: (() => { const c = document.querySelector("#canvas"); return c ? c.width + "x" + c.height : "none"; })(),
  }));
  console.log("ENV", JSON.stringify(env));

  // click Boot
  await page.click("#run");
  // wait for module to resolve (boot reached WM_main)
  let booted = false;
  for (let i = 0; i < 120; i++) {
    booted = await page.evaluate(() => !!window.__bwModule);
    if (booted) break;
    await sleep(1000);
  }
  console.log("BOOTED_MODULE", booted, "at ~" + "poll");
  if (!booted) { console.log("RESULT boot-failed"); console.log(logs.slice(-25).join("\n")); await browser.close(); return; }

  // give BPY + the --python-expr timer a moment to register
  await sleep(4000);

  // (B) LAZY-LOAD: fetch synthetic module over the wire, mount into live WASMFS
  const mount = await page.evaluate(async () => {
    const mod = window.__bwModule, FS = mod.FS;
    const t0 = performance.now();
    const resp = await fetch("/bw_stage1_probe.py");
    const buf = new Uint8Array(await resp.arrayBuffer());
    const fetchMs = performance.now() - t0;
    let w = "ok";
    try {
      FS.writeFile("/bw/python/lib/python3.13/bw_stage1_probe.py", buf);
      FS.writeFile("/bw/_stage1_ready", new Uint8Array([49]));
    } catch (e) { w = "writeErr:" + e; }
    return { bytes: buf.length, fetchMs, w };
  });
  console.log("MOUNT", JSON.stringify(mount));

  // poll the WASMFS result file the interpreter's timer writes
  let result = null;
  for (let i = 0; i < 40; i++) {
    result = await page.evaluate(() => {
      try { return window.__bwModule.FS.readFile("/bw/_stage1_result", { encoding: "utf8" }); }
      catch (e) { return null; }
    });
    if (result) break;
    await sleep(500);
  }
  console.log("LAZY_LOAD_RESULT", result);

  // (C) THROTTLE: emulate 4G, fetch the real 4.5MB stage0.data.br, measure throughput
  try {
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Network.enable");
    // 4G-ish: ~12 Mbit/s down = 1.5 MB/s, 60ms RTT
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false, downloadThroughput: 1.5e6, uploadThroughput: 750e3, latency: 60,
    });
    const thr = await page.evaluate(async () => {
      const t0 = performance.now();
      const r = await fetch("/stage0.data.br?cachebust=" + Math.random());
      const b = await r.arrayBuffer();
      const ms = performance.now() - t0;
      return { bytes: b.byteLength, ms, mbps: (b.byteLength / (ms / 1000) / 1e6) };
    });
    console.log("THROTTLE_4G_stage0", JSON.stringify(thr));
  } catch (e) { console.log("THROTTLE_ERR", e.message); }

  console.log("--- console tail ---");
  console.log(logs.filter(l => /BPY|Blender|WM|WebGPU|surface|Python|multiprocessing|stage1|error/i.test(l)).slice(-20).join("\n"));
  await browser.close();
})().catch((e) => { console.error("RIG_FATAL", e); process.exit(1); });

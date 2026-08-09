// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r53 (L-A) - LIFETIME STRESS for M5.readback-callback-lifetime. Reproduces the r25
// section 3 table-OOB repro class: back-to-back in-app snapshot/readback ops in a loop.
// Each render.opengl + screen.screenshot funnels through WGPUTexture::read (the seam whose
// old WaitAnyOnly `[&]` lambda captured the caller stack and could fire after read()
// returned). With the heap-owned kick/latch primitive (wgpu_readback) that dangling
// callback no longer exists in the wasm binary, so N>=20 iterations must survive with no
// `table index is out of bounds` / RuntimeError / abort, and the WM loop must keep ticking.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/gpu-r53-readback/probe_lifetime_stress.mjs [port] [iters]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const PORT = parseInt(process.argv[2] || '8136', 10);
const ITERS = parseInt(process.argv[3] || '24', 10);
const GW = 1280, GH = 720;
const BASE = `http://localhost:${PORT}`;
const OUT = '/Users/paws/blender-web/sandbox/gpu-r53-readback/evidence';
const BOOT_MS = 240000;
const SETTLE_MS = 180000;

const PY = [
  'import bpy, os',
  'bpy.context.preferences.view.show_splash = False',
  '_s = {"n": 0, "i": 0, "beat": 0}',
  'N = ' + ITERS,
  'def _ctx_area():',
  '    win = bpy.context.window_manager.windows[0]',
  '    scr = win.screen',
  '    area = next((a for a in scr.areas if a.type == "VIEW_3D"), None)',
  '    region = None',
  '    if area:',
  '        region = next((r for r in area.regions if r.type == "WINDOW"), None)',
  '    return win, area, region',
  'def _iter():',
  '    win, area, region = _ctx_area()',
  '    try:',
  '        with bpy.context.temp_override(window=win, area=area, region=region):',
  '            bpy.ops.render.opengl(write_still=False, view_context=True)',
  '    except Exception as e:',
  '        os.write(2, ("[stress] render.opengl EXC " + repr(e) + "\\n").encode())',
  '    try:',
  '        with bpy.context.temp_override(window=win, area=area, region=region):',
  '            bpy.ops.screen.screenshot(filepath="/tmp/stress_shot.png")',
  '    except Exception as e:',
  '        os.write(2, ("[stress] screenshot EXC " + repr(e) + "\\n").encode())',
  'def _tick():',
  '    _s["n"] += 1',
  '    if _s["n"] < 25:',
  '        return 0.3',
  '    if _s["i"] < N:',
  '        _s["i"] += 1',
  '        os.write(2, ("[stress] iter %d/%d\\n" % (_s["i"], N)).encode())',
  '        _iter()',
  '        return 0.25',
  '    # post-loop heartbeat: prove the WM loop still ticks after the barrage',
  '    _s["beat"] += 1',
  '    os.write(2, ("[stress] heartbeat %d loop-alive\\n" % _s["beat"]).encode())',
  '    if _s["beat"] >= 8:',
  '        os.write(2, b"[stress] STRESS_COMPLETE\\n")',
  '        return None',
  '    return 0.3',
  'bpy.app.timers.register(_tick, first_interval=1.0)',
].join('\n');

const url = `${BASE}/windowed.html?gate=${GW}x${GH}&pyexpr=${encodeURIComponent(PY)}`;

const logs = [];
let crashed = false, crashMsg = '';
const browser = await chromium.launch({
  headless: false,
  executablePath: '/Users/paws/Library/Caches/ms-playwright/chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
  args: ['--enable-unsafe-webgpu', '--use-angle=metal'],
});
const ctx = await browser.newContext({ viewport: { width: GW, height: GH } });
const page = await ctx.newPage();
function flag(t) { if (/table index is out of bounds|RuntimeError|Aborted|abort\(/.test(t)) { crashed = true; if (!crashMsg) crashMsg = t; } }
page.on('console', (m) => { const t = m.text(); logs.push(`[c.${m.type()}] ${t}`); flag(t); });
page.on('pageerror', (e) => { logs.push(`[pageerror] ${e.message}`); flag(e.message); });

console.log('boot ->', `iters=${ITERS}`);
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });

const t0 = Date.now();
let complete = false;
while (Date.now() - t0 < SETTLE_MS) {
  if (logs.some((l) => l.includes('STRESS_COMPLETE'))) { complete = true; break; }
  if (crashed) break;
  await page.waitForTimeout(1000);
}
await page.waitForTimeout(3000);

writeFileSync(`${OUT}/lifetime_stress_console.log`, logs.join('\n') + '\n');
const iters = logs.filter((l) => /\[stress\] iter/.test(l)).length;
const beats = logs.filter((l) => /heartbeat/.test(l)).length;
console.log(`complete=${complete} crashed=${crashed} iters_run=${iters} heartbeats=${beats}`);
if (crashed) console.log('CRASH:', crashMsg);
console.log(logs.filter((l) => /\[stress\]|table index|pageerror/.test(l)).slice(-20).join('\n'));
await browser.close();

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r49 (design lane) - READ-ONLY probe: reproduce the caller-facing sync-readback
// failure first-hand at tree b7dd8f2. Boots the windowed-opt build with BW_DIAG
// UNSET (the honest production path), registers a bpy timer that runs
// render.opengl(write_still) + screen.screenshot back-to-back (the exact r25 §2/§3
// repro), pulls the two PNGs via FS.readFile to the host sandbox, and captures the
// console/stderr for the wasm table-OOB crash (r25 §3). Nothing is written to the
// tree; the build is untouched. Bounded: one boot, ~90s settle.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node sandbox/m5-readback-design/probe_sync_readback.mjs [port]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const PORT = parseInt(process.argv[2] || '8133', 10);
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUT = '/Users/paws/blender-web/sandbox/m5-readback-design/evidence';
const BOOT_MS = 240000;
const SETTLE_MS = 90000;

// pyexpr runs pre-WM_main. Register a timer that fires the two readback ops once,
// with a VIEW_3D context override, then flags done via os.write(2).
const PY = [
  'import bpy, os',
  'bpy.context.preferences.view.show_splash = False',
  '_s = {"n": 0, "done": False}',
  'def _probe():',
  '    _s["n"] += 1',
  '    if _s["n"] < 20:',   // ~ boot settle before firing (0.4s * 20 = 8s)
  '        return 0.4',
  '    if _s["done"]:',
  '        return None',
  '    _s["done"] = True',
  '    win = bpy.context.window_manager.windows[0]',
  '    scr = win.screen',
  '    area = next((a for a in scr.areas if a.type == "VIEW_3D"), None)',
  '    region = None',
  '    if area:',
  '        region = next((r for r in area.regions if r.type == "WINDOW"), None)',
  '    os.write(2, ("[probe] firing ops area=%r region=%r\\n" % (area is not None, region is not None)).encode())',
  '    try:',
  '        with bpy.context.temp_override(window=win, area=area, region=region):',
  '            r = bpy.ops.render.opengl(write_still=True, view_context=True)',
  '            os.write(2, ("[probe] render.opengl -> %r\\n" % (r,)).encode())',
  '    except Exception as e:',
  '        os.write(2, ("[probe] render.opengl EXC " + repr(e) + "\\n").encode())',
  '    try:',
  '        bpy.data.images["Render Result"].save_render("/tmp/vp0.png")',
  '        os.write(2, b"[probe] saved /tmp/vp0.png\\n")',
  '    except Exception as e:',
  '        os.write(2, ("[probe] save vp0 EXC " + repr(e) + "\\n").encode())',
  '    try:',
  '        with bpy.context.temp_override(window=win, area=area, region=region):',
  '            r2 = bpy.ops.screen.screenshot(filepath="/tmp/win.png")',
  '            os.write(2, ("[probe] screen.screenshot -> %r\\n" % (r2,)).encode())',
  '    except Exception as e:',
  '        os.write(2, ("[probe] screenshot EXC " + repr(e) + "\\n").encode())',
  '    os.write(2, b"[probe] OPS_COMPLETE\\n")',
  '    return None',
  'bpy.app.timers.register(_probe, first_interval=1.0)',
].join('\n');

const url = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PY)}`;

const logs = [];
let crashed = false;

const browser = await chromium.launch({
  headless: false,
  executablePath: '/Users/paws/Library/Caches/ms-playwright/chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
  args: ['--enable-unsafe-webgpu', '--use-angle=metal'],
});
const ctx = await browser.newContext({ viewport: { width: W, height: H } });
const page = await ctx.newPage();
page.on('console', (m) => {
  const t = `[console.${m.type()}] ${m.text()}`;
  logs.push(t);
  if (/table index is out of bounds|RuntimeError|Aborted|abort\(/.test(m.text())) crashed = true;
});
page.on('pageerror', (e) => { logs.push(`[pageerror] ${e.message}`); if (/table index/.test(e.message)) crashed = true; });

console.log('boot ->', url.slice(0, 90) + '...');
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });

// Wait for OPS_COMPLETE or crash or settle timeout.
const t0 = Date.now();
let complete = false;
while (Date.now() - t0 < SETTLE_MS) {
  if (logs.some((l) => l.includes('OPS_COMPLETE'))) { complete = true; break; }
  if (crashed) break;
  await page.waitForTimeout(1000);
}
// give a few more ticks after ops to let any deferred crash surface
await page.waitForTimeout(4000);

// Pull the two PNGs via FS.readFile.
async function pull(name, dest) {
  try {
    const b64 = await page.evaluate((fn) => {
      const m = window.__bwModule;
      if (!m || !m.FS) return null;
      try {
        const d = m.FS.readFile(fn); // Uint8Array
        let s = '';
        for (let i = 0; i < d.length; i++) s += String.fromCharCode(d[i]);
        return btoa(s);
      } catch (e) { return 'ERR:' + e.message; }
    }, name);
    if (!b64) { logs.push(`[pull] ${name}: no __bwModule.FS`); return null; }
    if (b64.startsWith('ERR:')) { logs.push(`[pull] ${name}: ${b64}`); return null; }
    const buf = Buffer.from(b64, 'base64');
    writeFileSync(dest, buf);
    logs.push(`[pull] ${name} -> ${dest} (${buf.length} bytes)`);
    return buf.length;
  } catch (e) { logs.push(`[pull] ${name} EXC ${e.message}`); return null; }
}
await pull('/tmp/vp0.png', `${OUT}/probe_vp0.png`);
await pull('/tmp/win.png', `${OUT}/probe_win.png`);

// A CDP compositor screenshot as the "the window DID composite" control.
try { await page.screenshot({ path: `${OUT}/probe_cdp_composite.png` }); logs.push('[cdp] composite screenshot saved'); }
catch (e) { logs.push('[cdp] screenshot EXC ' + e.message); }

writeFileSync(`${OUT}/probe_console.log`, logs.join('\n') + '\n');
console.log(`complete=${complete} crashed=${crashed} logLines=${logs.length}`);
console.log(logs.filter((l) => /\[probe\]|table index|pageerror|\[pull\]|\[cdp\]/.test(l)).join('\n'));

await browser.close();

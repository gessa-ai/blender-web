// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r44r2 interactive-matcap repro: boot the default startup, switch the 3D viewport shading
// to MATCAP light mode (sh.light='MATCAP'), redraw and capture. Before the namespace fix the
// matcap deferred-resolve variant fails createBindGroup (6-vs-10) -> black/no cube + GPU
// errors; after the fix it must render with zero GPU errors.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules node matcap_interactive.mjs [label] [port] [settleMs]

import { createRequire } from 'module';
import { writeFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const LABEL = (process.argv[2] || 'matcap').trim();
const PORT = parseInt(process.argv[3] || '8128', 10);
const SETTLE_MS = parseInt(process.argv[4] || '35000', 10);
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/gpu-r44-r2';
const BOOT_MS = 240000;

const PY = [
  'import bpy, os',
  'os.environ["BW_DIAG"] = "1"',
  'bpy.context.preferences.view.show_splash = False',
  '_bw = {"n": 0}',
  'def _apply_matcap():',
  '    for win in bpy.context.window_manager.windows:',
  '        scr = win.screen',
  '        if not scr: continue',
  '        for area in scr.areas:',
  '            if area.type == "VIEW_3D":',
  '                sh = area.spaces.active.shading',
  '                sh.type = "SOLID"',
  '                sh.light = "MATCAP"',
  '                try:',
  '                    sh.studio_light = bpy.context.preferences.studio_lights[0].name',
  '                except Exception: pass',
  '                os.write(2, ("[bw-r44r2] matcap set light=" + sh.light + " studio=" + sh.studio_light + "\\n").encode())',
  'def _kick():',
  '    _bw["n"] += 1; n = _bw["n"]',
  '    try:',
  '        if n == 3: _apply_matcap()',
  '        for win in bpy.context.window_manager.windows:',
  '            scr = win.screen',
  '            if not scr: continue',
  '            for area in scr.areas:',
  '                if area.type == "VIEW_3D":',
  '                    for region in area.regions:',
  '                        if region.type == "WINDOW":',
  '                            region.tag_redraw()',
  '        if n == 30:',
  '            open("/tmp/bw_diag_cmd", "w").write("readback viewport_color\\n")',
  '            os.write(2, b"[bw-r44r2] scheduled viewport_color readback\\n")',
  '    except Exception as e:',
  '        os.write(2, ("[bw-r44r2-kick-err] " + repr(e) + "\\n").encode())',
  '    return 0.3',
  'bpy.app.timers.register(_kick, first_interval=1.0)',
].join('\n');

const url = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PY)}`;
function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] ${s}`); }

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 100, height: H + 100 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const all = [], gpuErrors = [], dones = [];
page.on('console', (m) => {
  const t = m.text();
  all.push(t);
  if (t.includes('GPU-ERROR') || t.includes('GPU-LOST') || t.includes('ValidationError') || t.includes('did not match')) gpuErrors.push(t);
  if (t.includes('BW_READBACK_DONE')) dones.push(t);
});
page.on('pageerror', (e) => all.push('[pageerror] ' + String(e)));

log(`booting ${LABEL} port=${PORT}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, { timeout: BOOT_MS });
log('WM_main up; settling');
try {
  const box = await page.evaluate(() => { const c = document.querySelector('canvas'); const r = c.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
  await page.mouse.move(box.x, box.y); await page.mouse.move(box.x + 3, box.y + 3);
} catch (e) {}
await page.waitForTimeout(SETTLE_MS);

await page.screenshot({ path: `${OUTDIR}/matcap_${LABEL}.png` }).catch(() => {});
// decode viewport_color center region: is the cube rendered (non-uniform, not black)?
const px = await page.evaluate((dones) => {
  try {
    const M = window.__bwModule;
    const kv = {}; const last = dones.filter((d) => d.includes('viewport_color')).pop();
    if (!last) return { err: 'no viewport_color readback' };
    for (const m of last.matchAll(/(\w+)=([^\s]+)/g)) kv[m[1]] = m[2];
    const b = M.FS.readFile(kv.file);
    const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
    const w = dv.getUint32(8, true), h = dv.getUint32(12, true), pitch = dv.getUint32(24, true), texel = dv.getUint32(20, true);
    // sample a grid across the viewport interior, count distinct luminances (cube present => variety)
    const B = 32; const vals = new Set(); let sum = 0, nn = 0, mn = 255, mx = 0;
    for (let y = Math.floor(h * 0.3); y < h * 0.7; y += 8) for (let x = Math.floor(w * 0.3); x < w * 0.7; x += 8) {
      const off = B + y * pitch + x * texel; const l = Math.round((b[off] + b[off + 1] + b[off + 2]) / 3);
      vals.add(l); sum += l; nn++; mn = Math.min(mn, l); mx = Math.max(mx, l);
    }
    return { w, h, meanLum: +(sum / nn).toFixed(1), distinct: vals.size, min: mn, max: mx };
  } catch (e) { return { err: String(e) }; }
}, dones);

writeFileSync(`${OUTDIR}/matcap_${LABEL}.all.log`, all.join('\n') + '\n');
console.log('\n==== INTERACTIVE MATCAP ====');
console.log('gpuErrors :', gpuErrors.length);
if (gpuErrors.length) gpuErrors.slice(0, 3).forEach((e) => console.log('   ', e));
console.log('matcap-set:', all.filter((l) => l.includes('matcap set')).slice(-1)[0] || '(none)');
console.log('viewport  :', JSON.stringify(px));
console.log('screenshot:', `${OUTDIR}/matcap_${LABEL}.png`);
await browser.close();

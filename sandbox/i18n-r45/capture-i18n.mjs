// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// r45 Phase 2 i18n capture rig. Boots the WITH_INTERNATIONAL windowed build in headed
// bundled Chromium (Playwright) at ?gate=WxH (DPR 1), does a neutral mouse nudge to force
// the first composite (P2 blocker), settles, and captures the canvas at exactly WxH -
// modelled on sandbox/m4-fullscreen-parity/capture_web.mjs.
//
// Modes:
//   splash     - default boot (splash shows); capture -> splash_WxH.png
//   workspace  - show_splash=False; capture -> workspace_WxH.png  (en_US, catalog-free)
//   langswitch - boot in ja_JP; capture ja_WxH.png (~settle), then a one-shot timer flips
//                back to en_US at t=30s; capture en_restored_WxH.png (~40s). Proves the
//                Japanese catalog renders (real Noto Sans CJK) AND the round-trip back to
//                the catalog-free English path.
//
// Usage: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//          node capture-i18n.mjs <splash|workspace|langswitch> [port] [WxH] [settleMs]

import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const MODE = (process.argv[2] || 'splash').trim();
const PORT = parseInt(process.argv[3] || '8130', 10);
const SIZE = (process.argv[4] || '1280x720').trim();
const SETTLE_MS = parseInt(process.argv[5] || '22000', 10);
const mm = /^(\d+)x(\d+)$/.exec(SIZE);
if (!mm) { console.error(`bad size "${SIZE}"`); process.exit(2); }
const W = parseInt(mm[1], 10), H = parseInt(mm[2], 10);
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/i18n-r45/captures';
const BOOT_MS = 300000;

const KICK = [
  'def _bw_kick():',
  '    try:',
  '        for win in bpy.context.window_manager.windows:',
  '            scr = win.screen',
  '            if not scr: continue',
  '            for area in scr.areas:',
  '                for region in area.regions:',
  '                    region.tag_redraw()',
  '    except Exception as e:',
  '        print("[bw-kick] " + repr(e))',
  '    return 1.0',
  'bpy.app.timers.register(_bw_kick, first_interval=1.0)',
];

function pyexpr(mode) {
  const L = ['import bpy'];
  if (mode === 'workspace' || mode === 'langswitch') {
    L.push('bpy.context.preferences.view.show_splash = False');
  }
  if (mode === 'langswitch') {
    // Enable interface + tooltip translation THEN set the language: view.language alone
    // loads the catalog but the UI stays English unless use_translate_interface is on
    // (Blender's factory default). This is what makes the real JA glyphs render.
    L.push([
      'try:',
      '    _v = bpy.context.preferences.view',
      '    _v.use_translate_interface = True',
      '    _v.use_translate_tooltips = True',
      '    _v.use_translate_new_dataname = True',
      '    _v.language = "ja_JP"',
      'except Exception as e:',
      '    print("[bw-lang] set ja_JP failed: " + repr(e))',
    ].join('\n'));
    L.push('import os; os.write(2, b"BW_LANG set ja_JP\\n")');
    L.push('def _bw_to_en():');
    L.push('    try:');
    L.push('        bpy.context.preferences.view.language = "en_US"');
    L.push('        os.write(2, b"BW_LANG restored en_US\\n")');
    L.push('    except Exception as e:');
    L.push('        print("[bw-lang] restore failed: " + repr(e))');
    L.push('    return None');
    L.push('bpy.app.timers.register(_bw_to_en, first_interval=30.0)');
  }
  L.push(...KICK);
  return L.join('\n');
}

function ts() { return new Date().toISOString().replace('T', ' ').replace('Z', ''); }
function log(s) { console.log(`[${ts()}] [${MODE}] ${s}`); }

const url = `${BASE}/windowed.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(pyexpr(MODE))}`;
const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 120, height: H + 120 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const present = { count: 0 };
const errs = [];
const langLog = [];
page.on('console', (m) => {
  const t = m.text();
  if (t.includes('presentBackbuffer')) present.count++;
  if (t.includes('BW_LANG')) langLog.push(t);
  if (m.type() === 'error' || t.includes('GPU-ERROR') || t.includes('ValidationError')) errs.push(t);
});

log(`boot ${url.slice(0, 80)}...`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
const t0 = Date.now();
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });
log(`WM_main in ${Date.now() - t0} ms`);

const gate = await page.evaluate(() => {
  const c = document.getElementById('canvas');
  return { bw: c.width, bh: c.height };
});
if (gate.bw !== W || gate.bh !== H) { console.error(`FATAL gate ${gate.bw}x${gate.bh} != ${W}x${H}`); await browser.close(); process.exit(1); }

const rect = await page.evaluate(() => {
  const r = document.getElementById('canvas').getBoundingClientRect();
  return { x: r.x, y: r.y, width: r.width, height: r.height };
});
// Neutral composite nudge: move over the canvas, bottom-left (away from splash buttons /
// topbar menus), so the WM gets a mouse event and composites without a hover highlight.
async function nudge() {
  await page.mouse.move(Math.round(rect.x + 12), Math.round(rect.y + rect.height - 12));
  await page.waitForTimeout(400);
  await page.mouse.move(Math.round(rect.x + 16), Math.round(rect.y + rect.height - 16));
}
async function grab(name) {
  await nudge();
  const out = `${OUTDIR}/${name}_${W}x${H}.png`;
  await page.screenshot({ path: out, clip: { x: Math.round(rect.x), y: Math.round(rect.y), width: W, height: H } });
  log(`captured -> ${out}  (present x${present.count})`);
  return out;
}

log(`settle ${SETTLE_MS} ms`);
await page.waitForTimeout(SETTLE_MS);

if (MODE === 'langswitch') {
  await grab('ja');
  log('waiting for the one-shot en_US restore timer (t=30s) ...');
  await page.waitForTimeout(Math.max(0, 42000 - SETTLE_MS));
  await grab('en_restored');
  log(`lang log: ${JSON.stringify(langLog)}`);
} else {
  await grab(MODE);
}

if (errs.length) { log(`console errors (${errs.length}):`); errs.slice(0, 5).forEach((e) => console.log('  ! ' + e.slice(0, 140))); }
else log('no console/GPU errors during boot+settle');
await ctx.close();
await browser.close();
log('done');

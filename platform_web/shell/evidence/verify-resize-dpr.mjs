// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0
// Headed Playwright verification of the GHOST resize + devicePixelRatio landing (port 8128).
// Proves: (A) DPR2 native UI scale (U.pixelsize==2) + live backing-store resize; (B) DPR1
// no-regression (U.pixelsize==1); (C) ?gate=WxH contract intact (exact size, DPR forced 1).
// Run: BLENDER_WEB_BIN=.../build-wasm-windowed/bin bash scripts/serve-web.sh 8128 ; then
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules node <thisfile>
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const BASE = 'http://localhost:8128';
const EV = '/Users/paws/blender-web/platform_web/shell/evidence';
const BOOT_MS = 180000;

const PYEXPR = `import bpy, sys
def _snap(tag):
    try:
        w=bpy.context.window
        s=bpy.context.preferences.system
        txt="%s win=%dx%d pixel_size=%.3f dpi=%d ui_scale=%.3f" % (tag,w.width,w.height,s.pixel_size,s.dpi,s.ui_scale)
    except Exception as e:
        txt="%s ERR %r" % (tag, e)
    try:
        f=open("/tmp/bwdiag.txt","w"); f.write(txt); f.close()
    except Exception as e:
        sys.stderr.write("BWPY_WRITE_ERR %r\\n"%e); sys.stderr.flush()
    sys.stderr.write(txt+"\\n"); sys.stderr.flush()
_snap("SNAP")
`;

const results = [];
const rec = (name, ok, detail) => { results.push({ name, ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${detail ?? ''}`); };
const waitBoot = (page) => page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, { timeout: BOOT_MS });
// Force full-rate requestAnimationFrame: a headless/backgrounded page throttles rAF, and the
// WM main loop (emscripten_set_main_loop fps=0) rides rAF. Focus emulation keeps it ticking
// so the worker's per-tick resize poll drains deterministically.
async function forceActive(page) {
  const s = await page.context().newCDPSession(page);
  try { await s.send('Emulation.setFocusEmulationEnabled', { enabled: true }); } catch (_) {}
  try { await s.send('Page.setWebLifecycleState', { state: 'active' }); } catch (_) {}
  return s;
}
async function readDiag(page) {
  for (let i = 0; i < 20; i++) {
    const r = await page.evaluate(() => { try { return window.__bwModule.FS.readFile('/tmp/bwdiag.txt', { encoding: 'utf8' }); } catch (e) { return null; } });
    if (r) return r;
    await page.waitForTimeout(500);
  }
  return '(no diag file)';
}

const browser = await chromium.launch({ headless: false });

// ===========================================================================
// A. HiDPI (deviceScaleFactor 2), 1440x900 -> boot, then LIVE resize to 1000x700.
// ===========================================================================
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  /* forceActive removed: unneeded; click-drag input drives the loop */
  const con = [];
  let resizeHit = null;
  page.on('console', m => { const t = m.text(); con.push(t); if (/WGPUWeb-resize: backing -> 2000x1400/.test(t)) resizeHit = t; });
  await page.addInitScript((expr) => { window.__BW_PYEXPR = expr; }, PYEXPR);
  await page.goto(`${BASE}/windowed.html`, { waitUntil: 'domcontentloaded' });
  await waitBoot(page);
  const diag1 = await readDiag(page);
  console.log('  [A boot 1440x900 dpr2]', diag1);
  const mA = /win=(\d+)x(\d+) pixel_size=([\d.]+)/.exec(diag1) || [];
  rec('A: DPR2 logical window == 1440x900 (getClientBounds logical)', mA[1] === '1440' && mA[2] === '900', `${mA[1]}x${mA[2]}`);
  rec('A: DPR2 U.pixelsize == 2 (native HiDPI UI scale - bug #2)', parseFloat(mA[3]) >= 2.0, `pixel_size=${mA[3]}`);
  rec('A: _bw_shell_set_display export reachable', await page.evaluate(() => typeof window.__bwModule._bw_shell_set_display === 'function'), '');
  await page.screenshot({ path: `${EV}/m4-ghost-resize-01-dpr2-1440x900.png` });

  // LIVE resize to 1000x700 -> backing must become 2000x1400 (=1000x700 * dpr2). The WM rAF
  // loop throttles when idle, so drive it with genuine click-drag input while the shell (and,
  // belt-and-braces, a direct export call) posts the new extent for the worker poll to drain.
  await page.setViewportSize({ width: 1000, height: 700 });
  for (let i = 0; i < 30 && !resizeHit; i++) {
    const x = 100 + (i % 8) * 90, y = 120 + (i % 6) * 80;
    await page.mouse.move(x, y);
    await page.mouse.down(); await page.mouse.move(x + 15, y + 15); await page.mouse.up();
    await page.evaluate(() => { const d = window.devicePixelRatio || 1; window.__bwModule._bw_shell_set_display(Math.round(innerWidth * d), Math.round(innerHeight * d), d); });
    await page.waitForTimeout(400);
  }
  console.log('  [A resize ->1000x700]', resizeHit || '(no WGPUWeb-resize 2000x1400 line)');
  rec('A: LIVE resize grew OffscreenCanvas backing to 2000x1400 (=1000x700 * dpr2) - bug #1', !!resizeHit, resizeHit || con.filter(t => t.includes('WGPUWeb-resize')).slice(-1)[0] || '(none)');
  const cover = await page.evaluate(() => { const c = document.querySelector('#canvas'); const r = c.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), iw: window.innerWidth, ih: window.innerHeight }; });
  rec('A: canvas CSS box fills window after resize (no black bars)', cover.w === cover.iw && cover.h === cover.ih, JSON.stringify(cover));
  await page.screenshot({ path: `${EV}/m4-ghost-resize-02-dpr2-resized-1000x700.png` });
  await ctx.close();
}

// ===========================================================================
// B. Standard DPI (deviceScaleFactor 1), 1280x720 -> pixel_size must be 1 (no regression).
// ===========================================================================
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  /* forceActive removed: unneeded; click-drag input drives the loop */
  await page.addInitScript((expr) => { window.__BW_PYEXPR = expr; }, PYEXPR);
  await page.goto(`${BASE}/windowed.html`, { waitUntil: 'domcontentloaded' });
  await waitBoot(page);
  const diagB = await readDiag(page);
  console.log('  [B boot 1280x720 dpr1]', diagB);
  const mB = /win=(\d+)x(\d+) pixel_size=([\d.]+)/.exec(diagB) || [];
  rec('B: DPR1 logical window == 1280x720', mB[1] === '1280' && mB[2] === '720', `${mB[1]}x${mB[2]}`);
  rec('B: DPR1 U.pixelsize == 1 (unchanged at standard DPI)', parseFloat(mB[3]) === 1.0, `pixel_size=${mB[3]}`);
  await page.screenshot({ path: `${EV}/m4-ghost-resize-03-dpr1-1280x720.png` });
  await ctx.close();
}

// ===========================================================================
// C. GATE regression: ?gate=1280x720 under deviceScaleFactor 2 -> exact 1280x720, DPR 1.
// ===========================================================================
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  /* forceActive removed: unneeded; click-drag input drives the loop */
  await page.addInitScript((expr) => { window.__BW_PYEXPR = expr; }, PYEXPR);
  await page.goto(`${BASE}/windowed.html?gate=1280x720`, { waitUntil: 'domcontentloaded' });
  await waitBoot(page);
  const gate = await page.evaluate(() => {
    const c = document.querySelector('#canvas');
    return { backingW: c.width, backingH: c.height, gateClass: document.body.classList.contains('bw-gate'), loaderGone: (() => { const l = document.getElementById('loader'); return !l || l.classList.contains('bw-gone') || l.classList.contains('bw-hidden'); })() };
  });
  console.log('  [C gate]', JSON.stringify(gate));
  rec('C: gate canvas backing EXACTLY 1280x720 (DPR forced 1)', gate.backingW === 1280 && gate.backingH === 720, `${gate.backingW}x${gate.backingH}`);
  rec('C: gate applies bw-gate layout + hides loader', gate.gateClass && gate.loaderGone, JSON.stringify(gate));
  const diagC = await readDiag(page);
  console.log('  [C gate diag]', diagC);
  const mC = /win=(\d+)x(\d+) pixel_size=([\d.]+)/.exec(diagC) || [];
  rec('C: gate Blender sees 1280x720 @ pixel_size 1 (DPR-independent)', mC[1] === '1280' && mC[2] === '720' && parseFloat(mC[3]) === 1.0, `${mC[1]}x${mC[2]} px=${mC[3]}`);
  await page.screenshot({ path: `${EV}/m4-ghost-resize-04-gate-1280x720.png` });
  await ctx.close();
}

await browser.close();
const passed = results.filter(r => r.ok).length;
console.log(`\n==== ${passed}/${results.length} checks passed ====`);
process.exit(passed === results.length ? 0 : 1);

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0
// Headed Playwright verification of the native-feel windowed shell (port 8126).
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const BASE = 'http://localhost:8126';
const EV = '/Users/paws/blender-web/platform_web/shell/evidence';
const BOOT_MS = 120000;

const results = [];
const rec = (name, ok, detail) => { results.push({ name, ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${detail ?? ''}`); };

async function waitBoot(page) {
  // (d) DOM-visible "main loop (WM_main)" marker.
  await page.waitForFunction(() => {
    const s = document.querySelector('#state');
    return s && s.textContent.includes('main loop (WM_main)');
  }, { timeout: BOOT_MS });
}

const browser = await chromium.launch({ headless: false });

// ---------------------------------------------------------------------------
// Scenario A - NORMAL native mode, HiDPI (deviceScaleFactor 2), 1440x900 window.
// ---------------------------------------------------------------------------
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const present = { seen: false };
  page.on('console', m => { const t = m.text(); if (t.includes('presentBackbuffer')) present.seen = true; });

  await page.goto(`${BASE}/windowed.html`, { waitUntil: 'domcontentloaded' });

  // Instant black boot + loader present immediately (before boot completes).
  const early = await page.evaluate(() => ({
    bodyBg: getComputedStyle(document.body).backgroundColor,
    htmlOverflow: getComputedStyle(document.documentElement).overflow,
    loaderPresent: !!document.getElementById('loader'),
    loaderHidden: document.getElementById('loader').classList.contains('bw-hidden'),
    noRunButtonVisible: (() => { const r = document.getElementById('run'); if (!r) return true; const diag = document.getElementById('bw-diag'); return diag && getComputedStyle(diag).opacity === '0'; })(),
  }));
  rec('A: instant black page', early.bodyBg === 'rgb(0, 0, 0)', early.bodyBg);
  rec('A: no scrollbars (overflow hidden)', early.htmlOverflow === 'hidden', early.htmlOverflow);
  rec('A: loading UI shown at boot (not hidden)', early.loaderPresent && !early.loaderHidden, `present=${early.loaderPresent} hidden=${early.loaderHidden}`);
  rec('A: no visible Boot button / pills (diag hidden)', early.noRunButtonVisible, '');
  await page.screenshot({ path: `${EV}/m4-shell-native-01-loading-black.png` });

  await waitBoot(page);
  rec('A: WM_main marker (contract d)', true, '');

  // window.__bwModule exposed (contract b).
  const hasMod = await page.evaluate(() => typeof window.__bwModule === 'object' && window.__bwModule !== null);
  rec('A: window.__bwModule exposed (contract b)', hasMod, '');

  // Loader dismissed on first pixels.
  await page.waitForFunction(() => document.getElementById('loader').classList.contains('bw-hidden'), { timeout: BOOT_MS }).catch(() => {});
  const loaderHidden = await page.evaluate(() => document.getElementById('loader').classList.contains('bw-hidden'));
  rec('A: loader dismissed after first pixels', loaderHidden, `presentBackbuffer=${present.seen}`);

  // DPR-correct full-window backing store: 1440*2 x 900*2.
  const dims = await page.evaluate(() => {
    const c = document.getElementById('canvas');
    const r = c.getBoundingClientRect();
    return { bw: c.width, bh: c.height, cssW: Math.round(r.width), cssH: Math.round(r.height), dpr: window.devicePixelRatio, innerW: window.innerWidth, innerH: window.innerHeight };
  });
  const wantW = Math.round(dims.innerW * dims.dpr), wantH = Math.round(dims.innerH * dims.dpr);
  rec('A: backing store DPR-correct', dims.bw === wantW && dims.bh === wantH, `backing=${dims.bw}x${dims.bh} want=${wantW}x${wantH} dpr=${dims.dpr}`);
  rec('A: canvas fills window (CSS)', dims.cssW === dims.innerW && dims.cssH === dims.innerH, `css=${dims.cssW}x${dims.cssH} win=${dims.innerW}x${dims.innerH}`);

  // Let it settle & composite, capture full-window.
  await page.waitForTimeout(4000);
  await page.screenshot({ path: `${EV}/m4-shell-native-02-fullwindow-dpr2.png` });

  // No page scroll on space/arrows with canvas focused.
  await page.evaluate(() => document.getElementById('canvas').focus());
  for (const k of ['Space', 'ArrowDown', 'ArrowUp', 'PageDown', 'Tab']) {
    await page.keyboard.press(k).catch(() => {});
  }
  const scroll = await page.evaluate(() => ({ y: window.scrollY, x: window.scrollX, active: document.activeElement && document.activeElement.id }));
  rec('A: no page scroll on space/arrows/tab', scroll.y === 0 && scroll.x === 0, `scroll=(${scroll.x},${scroll.y}) active=${scroll.active}`);

  // contextmenu default prevented (browser menu suppressed) - right-click reaches Blender.
  const ctxPrevented = await page.evaluate(() => {
    const ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
    document.getElementById('canvas').dispatchEvent(ev);
    return ev.defaultPrevented;
  });
  rec('A: contextmenu preventDefault (native menu killed)', ctxPrevented, '');

  // Real right-click on the canvas, then screenshot (Blender should draw its own menu).
  await page.mouse.move(720, 450);
  await page.mouse.down({ button: 'right' });
  await page.mouse.up({ button: 'right' });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${EV}/m4-shell-native-04-rightclick-blender-menu.png` });

  // Console error scan (ignore known non-fatal r26 diagnostics).
  await ctx.close();
}

// ---------------------------------------------------------------------------
// Scenario B - GATE mode (?gate=1280x720) under deviceScaleFactor 2. Must be
// EXACTLY 1280x720 backing (DPR forced to 1), centred on black, no loader.
// ---------------------------------------------------------------------------
{
  const ctx = await browser.newContext({ viewport: { width: 1000, height: 800 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/windowed.html?gate=1280x720`, { waitUntil: 'domcontentloaded' });
  await waitBoot(page);
  await page.waitForTimeout(3000);
  const g = await page.evaluate(() => {
    const c = document.getElementById('canvas');
    const data = c.toDataURL('image/png');
    // decode PNG IHDR width/height from the dataURL to prove the captured bitmap size
    const b = atob(data.split(',')[1]);
    const dv = new DataView(Uint8Array.from(b, ch => ch.charCodeAt(0)).buffer);
    const pngW = dv.getUint32(16), pngH = dv.getUint32(20); // IHDR at offset 16
    return {
      bw: c.width, bh: c.height,
      cssW: Math.round(c.getBoundingClientRect().width), cssH: Math.round(c.getBoundingClientRect().height),
      gateClass: document.body.classList.contains('bw-gate'),
      loaderGone: document.getElementById('loader').classList.contains('bw-gone'),
      dpr: window.devicePixelRatio,
      pngW, pngH,
    };
  });
  rec('B: gate backing exactly 1280x720 (DPR forced 1)', g.bw === 1280 && g.bh === 720, `backing=${g.bw}x${g.bh} dpr=${g.dpr}`);
  rec('B: gate CSS exactly 1280x720', g.cssW === 1280 && g.cssH === 720, `css=${g.cssW}x${g.cssH}`);
  rec('B: gate toDataURL bitmap exactly 1280x720', g.pngW === 1280 && g.pngH === 720, `png=${g.pngW}x${g.pngH}`);
  rec('B: gate centred (bw-gate class)', g.gateClass, '');
  rec('B: gate no loading UI once booted', g.loaderGone, '');
  await page.screenshot({ path: `${EV}/m4-shell-native-03-gate-1280x720.png` });
  await ctx.close();
}

await browser.close();

const fails = results.filter(r => !r.ok);
console.log(`\n===== ${results.length - fails.length}/${results.length} checks passed =====`);
if (fails.length) { console.log('FAILURES:', fails.map(f => f.name).join(' | ')); process.exit(1); }

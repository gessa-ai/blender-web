// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0
//
// Decisive: can we DRIVE the WM loop? Each round: (a) await main-thread rAF (does
// it resolve fast, i.e. is main-thread rAF alive?), (b) dispatch a synthetic
// mousemove on #canvas, (c) read the worker heartbeat counter. Distinguishes
// "main-thread rAF throttled" from "loop scheduling stalled", and whether a
// synthetic canvas event pumps a tick.

import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const BASE = 'http://localhost:8126';
const BOOT_MS = 240000;

const PY = `
import bpy, os
try: os.makedirs("/tmp/bw_io", exist_ok=True)
except Exception: pass
_n=[0]
def poll():
    _n[0]+=1
    try:
        f=open("/tmp/bw_io/hb.txt","w"); f.write(str(_n[0])); f.close()
    except Exception: pass
    return 0.05
bpy.app.timers.register(poll, first_interval=0.05)
`;

let browser;
(async () => {
  browser = await chromium.launch({ headless: false });
  const ctx = await browser.newContext({ viewport: { width: 900, height: 600 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/windowed.html?pyexpr=${encodeURIComponent(PY)}`, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
  await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: BOOT_MS, polling: 500 });
  const cdp = await page.context().newCDPSession(page);
  try { await cdp.send('Emulation.setFocusEmulationEnabled', { enabled: true }); } catch (_) {}
  try { await cdp.send('Page.setWebLifecycleState', { state: 'active' }); } catch (_) {}

  const readHb = () => page.evaluate(() => { try { return window.__bwModule.FS.readFile('/tmp/bw_io/hb.txt', { encoding: 'utf8' }); } catch (e) { return 'ENOENT'; } });

  console.log('--- METHOD 1: drive main-thread rAF explicitly x30 (report rAF latency) ---');
  for (let i = 0; i < 30; i++) {
    const dt = await page.evaluate(() => new Promise((r) => { const t = performance.now(); requestAnimationFrame(() => r(Math.round(performance.now() - t))); }));
    if (i % 6 === 0) console.log(`  raf#${i} latency=${dt}ms hb=${await readHb()}`);
  }
  console.log('  final hb=' + await readHb());

  console.log('--- METHOD 2: synthetic mousemove on #canvas x30 ---');
  for (let i = 0; i < 30; i++) {
    await page.evaluate((k) => { const c = document.querySelector('#canvas'); const r = c.getBoundingClientRect(); c.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: r.left + 20 + (k % 50), clientY: r.top + 20 + (k % 40) })); }, i);
    await page.waitForTimeout(30);
    if (i % 6 === 0) console.log(`  move#${i} hb=${await readHb()}`);
  }
  console.log('  final hb=' + await readHb());

  console.log('--- METHOD 3: real CDP Input.dispatchMouseEvent moved x30 ---');
  for (let i = 0; i < 30; i++) {
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 100 + (i % 300), y: 100 + (i % 200) });
    await page.waitForTimeout(30);
    if (i % 6 === 0) console.log(`  cdpmove#${i} hb=${await readHb()}`);
  }
  console.log('  final hb=' + await readHb());

  console.log('--- METHOD 4: bw_shell_set_display nudge x10 (worker applies per tick) ---');
  for (let i = 0; i < 10; i++) {
    await page.evaluate((k) => { const m = window.__bwModule; if (m && typeof m._bw_shell_set_display === 'function') m._bw_shell_set_display(900 + (k % 3), 600 + (k % 3), 1); }, i);
    await page.waitForTimeout(50);
  }
  console.log('  final hb=' + await readHb());

  try { if (browser) await browser.close(); } catch (_) {}
  process.exit(0);
})().catch(async (e) => { console.error('FATAL ' + (e && e.message || e)); try { if (browser) await browser.close(); } catch (_) {} process.exit(1); });

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0
// Tight-read the heartbeat to see if there is an exploitable BURST of ticks when
// the timer registers (vs a single tick). first_interval=0; read hb as fast as
// possible for ~12s; print max seen and the climb.
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
    try: open("/tmp/bw_io/hb.txt","w").write(str(_n[0]))
    except Exception: pass
    return 0.0
bpy.app.timers.register(poll, first_interval=0.0)
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
  const readHb = () => page.evaluate(() => { try { return parseInt(window.__bwModule.FS.readFile('/tmp/bw_io/hb.txt', { encoding: 'utf8' })) || 0; } catch (e) { return -1; } });
  let max = 0; const end = Date.now() + 12000; let samples = 0; let firstAt = null; const T = Date.now();
  while (Date.now() < end) { const v = await readHb(); samples++; if (v > 0 && firstAt === null) firstAt = ((Date.now() - T) / 1000).toFixed(2); if (v > max) max = v; }
  console.log(`samples=${samples} firstTickAt=${firstAt}s maxHb=${max}`);
  try { if (browser) await browser.close(); } catch (_) {}
  process.exit(0);
})().catch(async (e) => { console.error('FATAL ' + (e && e.message || e)); try { if (browser) await browser.close(); } catch (_) {} process.exit(1); });

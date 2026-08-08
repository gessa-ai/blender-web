// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0
// Diagnostic: one boot, full console capture + #log dump + /tmp readback.
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const BASE = 'http://localhost:8126';
const PY = `
import sys
sys.stderr.write("BW-DIAG PYEXPR-RAN\\n"); sys.stderr.flush()
try:
    open("/tmp/bwdiag2.txt","w").write("PYEXPR-RAN\\n")
    sys.stderr.write("BW-DIAG WROTE-TMP\\n"); sys.stderr.flush()
except Exception as e:
    sys.stderr.write("BW-DIAG TMP-ERR %r\\n"%e); sys.stderr.flush()
`;
const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const all = [];
page.on('console', (m) => { all.push(m.text()); });
page.on('pageerror', (e) => { all.push('PAGEERROR ' + e.message); });
const url = `${BASE}/windowed.html?pyexpr=${encodeURIComponent(PY)}`;
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 180000 });
// let it boot for up to 90s, polling for markers
let mountSeen = '', abortSeen = '', pyRan = false, tmp = '';
for (let i = 0; i < 90; i++) {
  await page.waitForTimeout(1000);
  const s = await page.evaluate(() => { const e = document.querySelector('#state'); return e ? e.textContent : ''; });
  const mnt = all.filter((l) => l.includes('M7 store'));
  if (mnt.length) mountSeen = mnt[mnt.length - 1];
  const ab = all.filter((l) => /onAbort|aborted|Aborted|RuntimeError|abort\(/.test(l));
  if (ab.length) abortSeen = ab[ab.length - 1];
  if (all.some((l) => l.includes('BW-DIAG PYEXPR-RAN'))) pyRan = true;
  tmp = await page.evaluate(() => { try { return window.__bwModule.FS.readFile('/tmp/bwdiag2.txt', { encoding: 'utf8' }); } catch (e) { return ''; } });
  if (pyRan && tmp) break;
  if ((i + 1) % 15 === 0) console.log(`t=${i + 1}s state="${s}" mount="${mountSeen}" pyRan=${pyRan} tmp=${JSON.stringify(tmp)} abort="${abortSeen}"`);
}
console.log('\n=== SUMMARY ===');
console.log('mount line   :', mountSeen || '(none)');
console.log('abort line   :', abortSeen || '(none)');
console.log('pyexpr ran   :', pyRan);
console.log('/tmp readback:', JSON.stringify(tmp));
console.log('\n=== last 40 console lines ===');
console.log(all.slice(-40).join('\n'));
try { await page.screenshot({ path: '/Users/paws/blender-web/sandbox/m7-store-wire/evidence/diag-boot.png' }); } catch (_) {}
await browser.close();
process.exit(0);

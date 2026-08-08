// SPDX-License-Identifier: GPL-3.0-or-later
// Comprehensive channel probe (windowed build). Answers, in one boot:
//   (A) does raw os.write(2,..) reach the JS console?  (signaling channel)
//   (B) do CLOG "Started bpy.ops.." lines appear while the WM loop pumps a timer
//       that runs a real operator?  (the operator-trace channel the session needs)
//   (C) Python worker FS write + readback of /m5/out.json  (result staging)
//   (D) browser-thread FS.readdir('/') / readFile('/m5/out.json')  (alt retrieval)
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const PORT = parseInt(process.argv[2] || '8126', 10);

const PY = [
  "import os,sys,bpy",
  "os.write(2, b'M5RAW boot fd2 ok\\n')",
  "try:",
  "    os.makedirs('/m5',exist_ok=True); open('/m5/out.json','w').write('TESTDUMP123'); os.write(2,b'M5RAW_FSWRITE ok\\n')",
  "except Exception as e:",
  "    os.write(2, ('M5RAW_FSWRITE_ERR %r\\n'%e).encode())",
  "def _tick():",
  "    try:",
  "        bpy.ops.object.select_all(action='DESELECT')",
  "        bpy.ops.object.select_all(action='SELECT')",
  "        data=open('/m5/out.json').read()",
  "        os.write(2, ('M5RAW_READBACK %s\\n'%data).encode())",
  "        os.write(2, b'M5RAW_TIMER_DONE\\n')",
  "    except Exception as e:",
  "        os.write(2, ('M5RAW_TIMER_ERR %r\\n'%e).encode())",
  "    return None",
  "bpy.app.timers.register(_tick, first_interval=1.0)",
  "os.write(2, b'M5RAW armed timer\\n')",
].join("\n");

const url = `http://localhost:${PORT}/windowed.html?args=${encodeURIComponent("--log operator --log-level debug")}&pyexpr=${encodeURIComponent(PY)}`;
const browser = await chromium.launch({ headless: false });
const page = await (await browser.newContext({ viewport: { width: 1380, height: 820 }, deviceScaleFactor: 1 })).newPage();
const lines = [];
page.on('console', (m) => { lines.push(m.text()); });
console.log('probe boot', url.slice(0, 60), '...');
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && (s.textContent.includes('main loop (WM_main)') || s.getAttribute('data-state') === 'aborted');
}, null, { timeout: 200000 });
console.log('WM_main; settling 10s...');
await page.waitForTimeout(10000);

for (const tag of ['M5RAW boot','M5RAW_FSWRITE','M5RAW armed','M5RAW_READBACK','M5RAW_TIMER_DONE','M5RAW_TIMER_ERR']) {
  const hit = lines.find((l) => l.includes(tag));
  console.log(`  A/C ${tag.padEnd(16)}: ${hit ? 'SEEN  ' + hit.slice(0, 90) : '-- not seen --'}`);
}
const ops = lines.filter((l) => /Started bpy\.ops\./.test(l));
console.log(`  B CLOG operator lines: ${ops.length}`);
ops.slice(0, 4).forEach((l) => console.log('     op>', l.slice(0, 100)));

const fs = await page.evaluate(() => {
  const out = {}; const m = window.__bwModule; out.hasFS = !!(m && m.FS);
  try { out.root = m.FS.readdir('/'); } catch (e) { out.root_err = String(e); }
  try { out.out = m.FS.readFile('/m5/out.json', { encoding: 'utf8' }); } catch (e) { out.out_err = String(e); }
  return out;
});
console.log('  D FS(browser thread):', JSON.stringify(fs));
await browser.close();

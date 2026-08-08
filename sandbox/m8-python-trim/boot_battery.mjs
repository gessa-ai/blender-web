// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// boot_battery.mjs - boot the ACTUAL browser build and directly exercise the
// stdlib imports the m8-staged-deploy note claimed were broken by a "dis.py trim":
//   import dis; import inspect; inspect.getsource(...); import pydoc; help()-style;
//   plus the hash modules. Results are written to /bw/_battery by a WM-worker timer
//   (print() inside a timer callback aborts the callback - see the staged note), then
//   read back over FS. The FULL console log is captured so any caught boot-time
//   ImportError/ModuleNotFoundError traceback (addon registration) is enumerated.
// Bundled Chromium via game-platform node_modules; port arg; screenshot + .license.
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = parseInt(process.argv[2] || '8130', 10);
const LABEL = process.argv[3] || 'mono';
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/m8-python-trim/artifacts';
fs.mkdirSync(OUTDIR, { recursive: true });
const OUT = `${OUTDIR}/battery_boot_${LABEL}_${W}x${H}.png`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const PYEXPR = [
  'import bpy,sys,io',
  'def _bat():',
  '    r=[]',
  '    try: bpy.context.preferences.view.show_splash=False',
  '    except Exception: pass',
  "    for m in ['dis','inspect','pydoc','dataclasses','opcode','_opcode']:",
  '        try: __import__(m); r.append("IMPORT_OK "+m)',
  '        except Exception as e: r.append("IMPORT_FAIL "+m+" "+repr(e))',
  '    try:',
  '        import inspect; s=inspect.getsource(inspect.getsource); r.append("GETSOURCE_OK len="+str(len(s)))',
  '    except Exception as e: r.append("GETSOURCE_FAIL "+repr(e))',
  '    try:',
  "        import dis; b=io.StringIO(); dis.dis(compile('x+1','<s>','eval'),file=b); r.append('DIS_OK chars='+str(len(b.getvalue())))",
  '    except Exception as e: r.append("DIS_FAIL "+repr(e))',
  '    try:',
  '        import pydoc; t=pydoc.render_doc(len,renderer=pydoc.plaintext); r.append("PYDOC_OK len="+str(len(t)))',
  '    except Exception as e: r.append("PYDOC_FAIL "+repr(e))',
  '    try:',
  "        import hashlib; hashlib.md5(b'x').hexdigest(); hashlib.sha3_256(b'x').hexdigest(); r.append('HASH_OK')",
  '    except Exception as e: r.append("HASH_FAIL "+repr(e))',
  '    f=open("/bw/_battery","w"); f.write(chr(10).join(r)); f.close(); return None',
  'bpy.app.timers.register(_bat, first_interval=0.5)',
].join('\n');

const url = `${BASE}/index.html?gate=${W}x${H}&pyexpr=${encodeURIComponent(PYEXPR)}`;
const log = (m) => console.log('[battery] ' + m);
let failed = false;
const fail = (m) => { failed = true; console.error('VERDICT-FAIL: ' + m); };

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 120, height: H + 120 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const allLines = [];
page.on('console', (m) => allLines.push(m.text()));
page.on('pageerror', (e) => allLines.push('PAGEERR ' + (e.message || e)));

log(`booting ${LABEL} @ ${url.slice(0, 80)}...`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
const iso = await page.evaluate(() => ({ coi: self.crossOriginIsolated === true, sab: typeof SharedArrayBuffer !== 'undefined' }));
if (!iso.coi) fail('not crossOriginIsolated'); if (!iso.sab) fail('no SharedArrayBuffer');
log(`crossOriginIsolated=${iso.coi} SAB=${iso.sab}`);

const t0 = Date.now();
try {
  await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 180000 });
  log(`WM_main reached in ${Date.now() - t0} ms`);
} catch (e) { fail('WM_main not reached: ' + e.message); }

// read the battery result file the WM-worker timer wrote (polling wakes the loop)
const readFile = (p) => page.evaluate((x) => { try { return window.__bwModule.FS.readFile(x, { encoding: 'utf8' }); } catch (e) { return null; } }, p);
let bat = null;
for (let i = 0; i < 60; i++) { bat = await readFile('/bw/_battery'); if (bat) break; await sleep(500); }
log('BATTERY RESULT:\n' + (bat || '(none)'));
if (!bat) fail('battery file not written');

// screenshot + license
try {
  const rect = await page.evaluate(() => { const r = document.getElementById('canvas').getBoundingClientRect(); return { x: r.x, y: r.y }; });
  await page.screenshot({ path: OUT, clip: { x: Math.round(rect.x), y: Math.round(rect.y), width: W, height: H } });
  fs.writeFileSync(OUT + '.license', 'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n');
  log('captured -> ' + OUT);
} catch (e) { fail('screenshot: ' + e.message); }

// enumerate boot-time caught tracebacks / import failures from the FULL console
fs.writeFileSync(OUTDIR + `/console_${LABEL}.log`, allLines.join('\n'));
const susp = allLines.filter((l) => /Traceback|ImportError|ModuleNotFoundError|No module named|import dis|inspect/i.test(l));
log(`console lines total=${allLines.length}; import/traceback-suspect lines=${susp.length}`);
susp.slice(0, 40).forEach((l) => console.log('   >> ' + l.slice(0, 160)));

await ctx.close(); await browser.close();
console.log(failed ? '[battery] VERDICT: FAIL' : '[battery] VERDICT: PASS');
process.exit(failed ? 1 : 0);

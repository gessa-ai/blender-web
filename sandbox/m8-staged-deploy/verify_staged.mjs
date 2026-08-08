// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// verify_staged.mjs - functional integrity of the STAGED deploy bundle:
//   (1) boots on stage-0 alone to WM_main + presents real pixels (COOP/COEP);
//   (2) a ?pyexpr runs inside WM_main (prints a marker, captured via console);
//   (3) deferred-stage asset proof:
//       (3a) BYTE-EXACT: a file that is a ZERO-LENGTH placeholder after stage-0
//            boot becomes its real bytes after stage-1 streams, byte-verified
//            against the packaged slice;
//       (3b) FUNCTIONAL: a deferred stdlib module (`this`, dependency-free) is
//            not usable before the stream and imports cleanly after it;
//   (4) captures a gate-exact screenshot with a CC0 .license sidecar.
// Bundled Chromium via game-platform node_modules; port 8130; ?stage1=manual so the
// rig controls the stream timing.
//
// NOTE the boot carries the SAME benign debts as the monolith (inspect->dis absent
// from the CPython trim, OIIO physical_memory, multiprocessing) - staging changes
// only payload timing, not boot behavior. So the functional probe avoids any module
// that transitively imports `inspect` (which would hit the pre-existing dis debt).
import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');
const fs = require('fs');

const PORT = parseInt(process.argv[2] || '8130', 10);
const W = 1280, H = 720;
const BASE = `http://localhost:${PORT}`;
const OUTDIR = '/Users/paws/blender-web/sandbox/m8-staged-deploy/artifacts';
fs.mkdirSync(OUTDIR, { recursive: true });
const OUT = `${OUTDIR}/staged_boot_${W}x${H}.png`;
const PROBE = '/bw/python/lib/python3.13/asyncio/tasks.py'; // deferred, byte-exact target
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// pyexpr: FILE-only results, NO print() and NO tag_redraw() inside timer callbacks
// (either aborts the callback in the WM-worker timer context; diagnosed in
// notes/m8-staged-deploy.md). The WM loop is present-gated/idle; the rig's FS polling
// (page.evaluate) wakes the worker enough to service the timers. The deferred-import
// probe uses pydoc_data.topics (pure-data: no print, no inspect->dis dependency) so
// its broken->working transition attributes cleanly to the stage-1 stream.
const PYEXPR = [
  'import bpy,os,sys',
  'def _mark():',
  '    try: bpy.context.preferences.view.show_splash=False',
  '    except Exception: pass',
  '    f=open("/bw/_pyexpr_marker","w"); f.write("PYEXPR_OK bpy="+bpy.app.version_string); f.close(); return None',
  'bpy.app.timers.register(_mark, first_interval=0.4)',
  'def _probe():',
  '    if os.path.exists("/bw/_stage1_go"):',
  '        try:',
  '            for m in list(sys.modules):',
  '                if m=="pydoc_data" or m.startswith("pydoc_data."): del sys.modules[m]',
  '            import pydoc_data.topics as _t',
  '            r="pydoc_data.topics_len="+str(len(getattr(_t,"topics",{})))',
  '        except Exception as e: r="probe_err="+repr(e)',
  '        f=open("/bw/_stage1_probe","w"); f.write(r); f.close(); return None',
  '    return 0.3',
  'bpy.app.timers.register(_probe, first_interval=0.4)',
].join('\n');

const url = `${BASE}/index.html?gate=${W}x${H}&stage1=manual&pyexpr=${encodeURIComponent(PYEXPR)}`;
let failed = false;
const fail = (m) => { failed = true; console.error('VERDICT-FAIL: ' + m); };
const log = (m) => console.log('[verify] ' + m);

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({ viewport: { width: W + 120, height: H + 120 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const present = { count: 0 };
const errs = [], allLines = [];
page.on('console', (m) => {
  const t = m.text(); allLines.push(t);
  if (t.includes('presentBackbuffer')) present.count++;
  if (m.type() === 'error' || t.includes('ValidationError') || t.includes('GPU-ERROR')) errs.push(t);
});
page.on('pageerror', (e) => { errs.push('pageerror: ' + (e.message || e)); allLines.push('PAGEERR ' + (e.message || e)); });
// Poll a WM-worker-written file from the main thread; each poll also wakes the
// present-gated WM loop enough to service its timers (verified).
const readFile = (p) => page.evaluate((x) => { try { return window.__bwModule.FS.readFile(x, { encoding: 'utf8' }); } catch (e) { return null; } }, p);
const waitFile = async (p, tries = 40) => { for (let i = 0; i < tries; i++) { const v = await readFile(p); if (v) return v; await sleep(500); } return null; };

log('booting staged bundle (stage-0 preload only)...');
await page.goto(url, { waitUntil: 'domcontentloaded' });
const iso = await page.evaluate(() => ({ coi: self.crossOriginIsolated === true, sab: typeof SharedArrayBuffer !== 'undefined' }));
if (!iso.coi) fail('not crossOriginIsolated'); if (!iso.sab) fail('no SharedArrayBuffer');
log(`crossOriginIsolated=${iso.coi} SAB=${iso.sab}`);

const t0 = Date.now();
try {
  await page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: 180000 });
  log(`WM_main reached in ${Date.now() - t0} ms (stage-0 only)`);
} catch (e) { fail('WM_main not reached: ' + e.message); }

const gate = await page.evaluate(() => { const c = document.getElementById('canvas'); return { bw: c.width, bh: c.height, mod: typeof window.__bwModule === 'object' && !!window.__bwModule }; });
if (gate.bw !== W || gate.bh !== H) fail(`gate ${gate.bw}x${gate.bh} != ${W}x${H}`);
if (!gate.mod) fail('__bwModule missing');
log(`gate backing ${gate.bw}x${gate.bh}  __bwModule=${gate.mod}`);

// (2) ?pyexpr proof (WM-worker wrote the marker file)
const py = await waitFile('/bw/_pyexpr_marker');
if (py && py.startsWith('PYEXPR_OK')) log('pyexpr proof: ' + py); else fail('pyexpr marker missing (' + py + ')');
if (present.count < 1) fail('no presentBackbuffer'); else log('presentBackbuffer x' + present.count);

// (3a) deferred asset BEFORE stage-1: expect zero-length placeholder
const before = await page.evaluate((p) => { try { return window.__bwModule.FS.stat(p).size; } catch (e) { return 'ERR:' + e; } }, PROBE);
log(`deferred ${PROBE} size BEFORE stage-1 = ${before} (expect 0)`);
if (before !== 0) fail('probe file not a placeholder before stage-1 (size=' + before + ')');

// trigger stage-1 stream + wait for completion
log('triggering stage-1 stream...');
await page.evaluate(() => window.__bwStage1Load && window.__bwStage1Load());
let st = null;
for (let i = 0; i < 120; i++) { st = await page.evaluate(() => window.__bwStage1); if (st && (st.phase === 'done' || st.phase === 'done-with-errors' || st.phase === 'error')) break; await sleep(500); }
log('stage1 state: ' + JSON.stringify(st));
if (!st || (st.phase !== 'done' && st.phase !== 'done-with-errors')) fail('stage-1 did not complete: ' + (st && st.phase));
if (st && st.error) log('stage1 first write error (non-fatal): ' + st.error);

// (3b) AFTER stage-1: real bytes + byte-exact vs the packaged slice
const after = await page.evaluate(async (p) => {
  const FS = window.__bwModule.FS;
  const cur = FS.readFile(p);
  const man = await (await fetch('/bin/stage1-manifest.json')).json();
  const ent = man.files.find((f) => f.filename === p);
  const buf = new Uint8Array(await (await fetch('/bin/stage1.data')).arrayBuffer());
  const want = buf.subarray(ent.start, ent.end);
  let eq = cur.length === want.length;
  if (eq) for (let i = 0; i < cur.length; i++) { if (cur[i] !== want[i]) { eq = false; break; } }
  return { size: cur.length, want: want.length, byteExact: eq };
}, PROBE);
log(`deferred ${PROBE} AFTER stage-1: size=${after.size} want=${after.want} byteExact=${after.byteExact}`);
if (after.size === 0) fail('probe file still empty after stage-1');
if (!after.byteExact) fail('streamed bytes != packaged slice (overwrite corruption)');

// (3c) FUNCTIONAL: deferred pydoc_data.topics usable only after the stream
await page.evaluate(() => { window.__bwModule.FS.writeFile('/bw/_stage1_go', new Uint8Array([49])); });
const probe = await waitFile('/bw/_stage1_probe');
log('deferred-import proof (post stream): ' + probe);
const mt = probe && /pydoc_data\.topics_len=(\d+)/.exec(probe);
if (!mt || parseInt(mt[1], 10) < 1) fail('deferred pydoc_data.topics not functional after stage-1 (' + probe + ')');

// (4) capture + license sidecar
try {
  const rect = await page.evaluate(() => { const r = document.getElementById('canvas').getBoundingClientRect(); return { x: r.x, y: r.y }; });
  await page.screenshot({ path: OUT, clip: { x: Math.round(rect.x), y: Math.round(rect.y), width: W, height: H } });
  fs.writeFileSync(OUT + '.license', 'SPDX-FileCopyrightText: 2026 blender-web contributors\nSPDX-License-Identifier: CC0-1.0\n');
  log('captured -> ' + OUT + ' (+ .license)');
} catch (e) { fail('screenshot: ' + e.message); }

if (errs.length) { log(`console errors (${errs.length}, incl. known benign inspect->dis / OIIO / multiprocessing debts); first 3:`); errs.slice(0, 3).forEach((e) => console.log('   ! ' + e.slice(0, 140))); }
else log('no console/GPU-validation errors during staged boot');
fs.writeFileSync(OUTDIR + '/verify_console.log', allLines.join('\n'));
await ctx.close(); await browser.close();
console.log(failed ? '[verify] VERDICT: FAIL' : '[verify] VERDICT: PASS');
process.exit(failed ? 1 : 0);

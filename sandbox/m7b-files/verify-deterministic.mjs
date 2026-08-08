// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0
//
// M7b DETERMINISTIC verifier. The windowed WM loop is redraw/rAF driven and stalls
// at idle (notes/m7b-files-io.md): a post-boot polling daemon gets 0-1 ticks, so a
// live post-boot DOM drop / picker click cannot be driven headlessly. But a command
// STAGED before WM_main is drained by the daemon's first-tick poll - the exact,
// proven-reliable one-shot pattern the M7 store-wire joint proof uses (13/13). This
// rig stages real .blend work through the SHIPPED file-bridge conduit + daemon and
// checks the acks, then exercises the SHIPPED FSA / drag-drop / fallback JS glue with
// the TEST playing the daemon over the same MEMFS conduit (pure browser-thread, so it
// needs no WM tick and cannot corrupt store state).
//
// P1 drag-drop OPEN path: stage default_cube bytes -> daemon copies to
//    /projects/imported + bpy.ops.wm.open_mainfile -> ack lists Camera,Cube,Light.
// P2 SAVE path + live edit: stage a save (startup scene + an added Empty marker) ->
//    daemon save_as_mainfile -> ack objects include the marker; out bytes valid .blend.
// P3 CONTENT SURVIVES a real reload: reload the SAME context (fresh wasm, OPFS
//    persists) -> daemon open_store the saved file from OPFS -> the marker survives.
// P4 FSA + fallback JS glue (test acts as daemon over the conduit; no WM loop):
//    FSA open, <input type=file> fallback, FSA save writable, download-blob fallback -
//    each round-trips real .blend bytes through the shipped file-bridge functions.
//
// AUTO-VERIFIED here: the whole conduit + daemon open/save/open_store paths with a
// real .blend, content survival across a reload, and all FSA/drag-drop/fallback JS.
// NEEDS ONE MANUAL CONFIRMATION (documented): the live post-boot DOM drop and the
// native OS picker dialogs, which need a continuously-compositing tab (real user) or
// the recommended WM keepalive - neither driveable by this headless harness.
//
// Run: NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//        node sandbox/m7b-files/verify-deterministic.mjs

import { createRequire } from 'module';
import { readFileSync, writeFileSync, mkdirSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const BASE = process.env.BW_BASE || 'http://localhost:8126';
const PAGE = '/windowed.html';
const BLEND = '/Users/paws/blender-web/sandbox/m4-goldens/default_cube.blend';
const EV = '/Users/paws/blender-web/sandbox/m7b-files/evidence';
const BOOT_MS = 240000;
const ACK_MS = 60000;
mkdirSync(EV, { recursive: true });
const b64 = readFileSync(BLEND).toString('base64');
const BLEN = readFileSync(BLEND).length;

const results = [];
const rec = (n, ok, d) => { results.push({ n, ok, d }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}  ${d ?? ''}`); };
const lines = [];

const waitBoot = (page) => page.waitForFunction(() => { const s = document.querySelector('#state'); return s && s.textContent.includes('main loop (WM_main)'); }, null, { timeout: BOOT_MS, polling: 500 });
async function forceActive(page) { const s = await page.context().newCDPSession(page); try { await s.send('Emulation.setFocusEmulationEnabled', { enabled: true }); } catch (_) {} try { await s.send('Page.setWebLifecycleState', { state: 'active' }); } catch (_) {} return s; }

async function readAck(page, tok) {
  const deadline = Date.now() + ACK_MS;
  while (Date.now() < deadline) {
    const txt = await page.evaluate((t) => { try { return window.__bwModule.FS.readFile('/tmp/bw_io/ack/' + t + '.json', { encoding: 'utf8' }); } catch (e) { return ''; } }, tok);
    if (txt) return JSON.parse(txt);
    await page.waitForTimeout(400);
  }
  return null;
}
const readOut = (page, tok) => page.evaluate((t) => { try { const b = window.__bwModule.FS.readFile('/tmp/bw_io/out/' + t + '.blend'); return Array.from(b.slice(0, 4)).map((x) => x.toString(16).padStart(2, '0')).join('') + ':' + b.length; } catch (e) { return 'ERR ' + e; } }, tok);

function stagerOpen(tok, name) {
  return `\nimport os, json, base64\nos.makedirs('/tmp/bw_io/in', exist_ok=True); os.makedirs('/tmp/bw_io/cmd', exist_ok=True)\nopen('/tmp/bw_io/in/${tok}.blend','wb').write(base64.b64decode(${JSON.stringify(b64)}))\nopen('/tmp/bw_io/cmd/${tok}.json','w').write(json.dumps({'op':'open','name':'${name}'}))\n`;
}
function stagerCmd(tok, spec) {
  return `\nimport os, json\nos.makedirs('/tmp/bw_io/cmd', exist_ok=True)\nopen('/tmp/bw_io/cmd/${tok}.json','w').write(json.dumps(${JSON.stringify(spec)}))\n`;
}

// The test playing the daemon: drain any conduit command on the BROWSER thread and
// answer it (ack + out bytes). Exercises the shipped file-bridge JS without a WM tick.
// Installed as a JS interval inside the page.
const INSTALL_FAKE_DAEMON = (b64in) => {
  window.__b64ToU8 = (s) => { const a = atob(s); const u = new Uint8Array(a.length); for (let i = 0; i < a.length; i++) u[i] = a.charCodeAt(i); return u; };
  const KNOWN = window.__b64ToU8(b64in);
  const FS = window.__bwModule.FS;
  const CD = '/tmp/bw_io/cmd';
  window.__fakeDaemon = setInterval(() => {
    let names = [];
    try { names = FS.readdir(CD).filter((f) => f.endsWith('.json')); } catch (e) { return; }
    for (const fn of names) {
      const tok = fn.slice(0, -5);
      let spec; try { spec = JSON.parse(FS.readFile(CD + '/' + fn, { encoding: 'utf8' })); } catch (e) { continue; }
      try { FS.unlink(CD + '/' + fn); } catch (_) {}
      if (spec.op === 'save') {
        try { FS.writeFile('/tmp/bw_io/out/' + tok + '.blend', KNOWN); } catch (_) {}
        FS.writeFile('/tmp/bw_io/ack/' + tok + '.json', JSON.stringify({ ok: true, op: 'save', name: spec.name, size: KNOWN.length, objects: ['Camera', 'Cube', 'Light'] }));
      } else if (spec.op === 'open') {
        let inLen = -1; try { inLen = FS.readFile('/tmp/bw_io/in/' + tok + '.blend').length; } catch (_) {}
        window.__lastOpenInLen = inLen; // record what the picker delivered to the conduit
        FS.writeFile('/tmp/bw_io/ack/' + tok + '.json', JSON.stringify({ ok: true, op: 'open', name: spec.name, size: inLen, objects: ['Camera', 'Cube', 'Light'] }));
      } else {
        FS.writeFile('/tmp/bw_io/ack/' + tok + '.json', JSON.stringify({ ok: true, op: spec.op }));
      }
    }
  }, 60);
};

let browser;
(async () => {
  browser = await chromium.launch({ headless: false });
  try {
    // ===================== Context 1: P1 open path =====================
    {
      const ctx = await browser.newContext({ viewport: { width: 1100, height: 760 }, deviceScaleFactor: 1 });
      const page = await ctx.newPage();
      page.on('console', (m) => { const t = m.text(); lines.push(t); if (/BW-FILEBRIDGE|storage\.persist/.test(t)) console.log('  [py] ' + t); });
      await page.addInitScript((s) => { window.__BW_PYEXPR = s; }, stagerOpen('A', 'dropped_cube.blend'));
      await page.goto(`${BASE}${PAGE}`, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
      console.log('[P1] booting (cold ~1 min)...');
      await waitBoot(page); await forceActive(page);
      const ack = await readAck(page, 'A');
      console.log('[P1] ack: ' + JSON.stringify(ack));
      const o = (ack && ack.objects) || [];
      rec('P1-dragdrop-open-path', !!ack && ack.ok && o.includes('Cube') && o.includes('Camera') && o.includes('Light'), 'objects=' + JSON.stringify(o) + ' store=' + (ack && ack.storePath));
      // P5: navigator.storage.persist() reported at boot (open item 6.4, first half)
      const pl = lines.find((l) => l.includes('storage.persist()')) || '';
      rec('P5-persist-reported', /storage\.persist\(\): granted=(true|false) persisted=(true|false) eviction=/.test(pl), pl.replace(/^\[[^\]]*\]\s*/, ''));
      try { await page.screenshot({ path: `${EV}/m7b-det-P1-open.png` }); } catch (_) {}
      await ctx.close();
    }

    // ============ Context 2: P2 save -> P3 reload survival -> P4 JS glue ============
    {
      const ctx = await browser.newContext({ viewport: { width: 1100, height: 760 }, deviceScaleFactor: 1, acceptDownloads: true });
      const page = await ctx.newPage();
      page.on('console', (m) => { const t = m.text(); lines.push(t); if (/BW-FILEBRIDGE/.test(t)) console.log('  [py] ' + t); });

      // ---- P2: boot, stage a save with an added Empty marker ----
      await page.addInitScript((s) => { window.__BW_PYEXPR = s; }, stagerCmd('B', { op: 'save', name: 'rt.blend', addEmpty: 'BW_RT_MARKER', sceneMarker: 20260808 }));
      await page.goto(`${BASE}${PAGE}`, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
      console.log('[P2] booting...');
      await waitBoot(page); await forceActive(page);
      const ackB = await readAck(page, 'B');
      console.log('[P2] ack: ' + JSON.stringify(ackB));
      const so = (ackB && ackB.objects) || [];
      rec('P2-save-path-live-edit', !!ackB && ackB.ok && so.includes('BW_RT_MARKER') && so.includes('Cube'), 'objects=' + JSON.stringify(so));
      rec('P2-save-out-valid-blend', /^28b52ffd:/.test(await readOut(page, 'B')), 'out=' + await readOut(page, 'B'));

      // ---- P3: reload SAME context (OPFS persists) -> open_store the saved file ----
      await page.addInitScript((s) => { window.__BW_PYEXPR = s; }, stagerCmd('C', { op: 'open_store', name: 'rt.blend' }));
      await page.goto(`${BASE}${PAGE}`, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
      console.log('[P3] reloaded; booting...');
      await waitBoot(page); await forceActive(page);
      const ackC = await readAck(page, 'C');
      console.log('[P3] ack: ' + JSON.stringify(ackC));
      const sv = (ackC && ackC.objects) || [];
      rec('P3-content-survives-reload', !!ackC && ackC.ok && sv.includes('BW_RT_MARKER') && sv.includes('Cube'), 'objects=' + JSON.stringify(sv));
      try { await page.screenshot({ path: `${EV}/m7b-det-P3-reopen.png` }); } catch (_) {}

      // ---- P4: shipped FSA / fallback JS glue, test-acts-as-daemon over the conduit ----
      await page.evaluate(INSTALL_FAKE_DAEMON, b64);

      // (a) FSA open: mock picker returns a real .blend -> importer delivers it to the conduit
      const fsaOpen = await page.evaluate(async (b64in) => {
        const u = window.__b64ToU8(b64in);
        window.__lastOpenInLen = -1;
        window.showOpenFilePicker = async () => [{ getFile: async () => new File([u], 'rt.blend') }];
        const ack = await window.BWFileBridge.openFromDisk();
        return { delivered: window.__lastOpenInLen, ok: ack && ack.ok };
      }, b64);
      rec('P4-fsa-open', fsaOpen.ok === true && fsaOpen.delivered === BLEN, 'deliveredLen=' + fsaOpen.delivered);

      // (b) <input type=file> fallback via Playwright filechooser
      await page.evaluate(() => { delete window.showOpenFilePicker; window.__lastOpenInLen = -1; window.__inp = null; });
      const [chooser] = await Promise.all([
        page.waitForEvent('filechooser', { timeout: 15000 }).catch(() => null),
        page.evaluate(() => { window.__inp = window.BWFileBridge.openFromDisk(); }),
      ]);
      let inDelivered = -1;
      if (chooser) { await chooser.setFiles(BLEND); await page.evaluate(async () => { try { await window.__inp; } catch (e) {} }); inDelivered = await page.evaluate(() => window.__lastOpenInLen); }
      rec('P4-input-fallback-open', inDelivered === BLEN, 'deliveredLen=' + inDelivered);

      // (c) FSA save: writable receives the exact bytes the (faked) daemon returned
      const fsaSave = await page.evaluate(async () => {
        let cap = null;
        window.showSaveFilePicker = async () => ({ createWritable: async () => ({ _c: [], write: async function (d) { this._c.push(d); }, close: async function () { cap = this._c[0]; } }) });
        const r = await window.BWFileBridge.saveToDisk('out_fsa.blend');
        return { via: r.via, len: cap ? cap.length : -1, magic: cap ? Array.from(cap.slice(0, 4)).map((x) => x.toString(16).padStart(2, '0')).join('') : 'none' };
      });
      rec('P4-fsa-save-writable', fsaSave.via === 'fsa' && fsaSave.len === BLEN && fsaSave.magic === '28b52ffd', JSON.stringify(fsaSave));

      // (d) download-blob save fallback via the real download event
      const [dl] = await Promise.all([
        page.waitForEvent('download', { timeout: 15000 }).catch(() => null),
        page.evaluate(() => { delete window.showSaveFilePicker; window.__dl = window.BWFileBridge.saveToDisk('out_dl.blend'); }),
      ]);
      let dlMagic = 'none', dlLen = -1;
      if (dl) { const p = `${EV}/det-download.blend`; await dl.saveAs(p); const b = readFileSync(p); dlMagic = b.slice(0, 4).toString('hex'); dlLen = b.length; }
      await page.evaluate(async () => { try { await window.__dl; } catch (e) {} });
      rec('P4-download-fallback', dlMagic === '28b52ffd' && dlLen === BLEN, 'magic=' + dlMagic + ' len=' + dlLen);

      await page.evaluate(() => { try { clearInterval(window.__fakeDaemon); } catch (_) {} });
      await ctx.close();
    }
  } catch (e) {
    rec('rig-ran', false, 'driver threw: ' + (e && e.message ? e.message : e));
  } finally {
    const pass = results.filter((r) => r.ok).length;
    const summary = `\n===== ${pass}/${results.length} PASS =====\n` + results.map((r) => `${r.ok ? 'PASS' : 'FAIL'}  ${r.n}  ${r.d ?? ''}`).join('\n') + '\n';
    console.log(summary);
    try { writeFileSync(`${EV}/verify-deterministic-run.txt`, summary); } catch (_) {}
    try { if (browser) await browser.close(); } catch (_) {}
    process.exit(pass === results.length ? 0 : 1);
  }
})();

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0
//
// M7b CHANNEL PROBE (v2): which browser-thread->worker byte channel actually
// lands bytes that the WM-worker's Python can read, under -sPROXY_TO_PTHREAD with
// the OPFS /projects mount?
//
// v1 finding: browser-thread FS.writeFile to the OPFS mount /projects reported
// "OK" but a browser-thread readBack THREW and the WM-worker daemon NEVER saw the
// file. OPFS sync access handles are worker-only (GOAL.md emscripten posture), so
// the OPFS backend cannot be driven from the main/browser thread.
//
// v2 tests two candidate channels head to head and lets a WM-worker bpy.app.timer
// daemon report, for each, what IT can see and whether it can open_mainfile it:
//   A) MEMFS  path  /tmp/bw_drop_memfs.blend   (in-memory backend, shared wasm mem)
//   B) OPFS   path  /projects/imported/bw_drop_opfs.blend
//
// Run (server up on :8126):
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//     node sandbox/m7b-files/probe-write-channel.mjs

import { createRequire } from 'module';
import { readFileSync } from 'fs';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const BASE = process.env.BW_BASE || 'http://localhost:8126';
const PAGE = '/windowed.html';
const BLEND = '/Users/paws/blender-web/sandbox/m4-goldens/default_cube.blend';
const BOOT_MS = 240000;
const ACK_MS = 60000;

// WM-worker daemon: poll /tmp/bw_probe_go; when present, report what the worker can
// see for both candidate paths and try to open each. Everything via os.write(2)
// (the reliable Python->console channel) and an ack file the browser can readFile.
const PY_DAEMON = `
import bpy, sys, os
def w(m):
    try: os.write(2, ("BW-PROBE "+m+"\\n").encode())
    except Exception: pass
ACK="/tmp/bw_probe_ack.txt"
_ackbuf=[]
def ack(m):
    _ackbuf.append(m); w(m)
    try:
        f=open(ACK,"w"); f.write("\\n".join(_ackbuf)+"\\n"); f.close()
    except Exception as e: w("ACK-ERR %r"%e)
MEMFS="/tmp/bw_drop_memfs.blend"
OPFS="/projects/imported/bw_drop_opfs.blend"
def probe_open(tag, p):
    try:
        ex=os.path.exists(p); sz=os.path.getsize(p) if ex else -1
        ack("%s SEEN exists=%s size=%s"%(tag,ex,sz))
        if not ex: return
        bpy.ops.wm.open_mainfile(filepath=p)
        names=sorted(o.name for o in bpy.data.objects)
        ack("%s OPENED objs=%d names=%s"%(tag,len(bpy.data.objects),",".join(names)))
    except Exception as e:
        ack("%s ERR %r"%(tag,e))
_done=[False]
def poll():
    if _done[0]: return None
    try:
        if os.path.exists("/tmp/bw_probe_go"):
            _done[0]=True
            probe_open("MEMFS", MEMFS)
            probe_open("OPFS", OPFS)
            ack("PROBE-DONE")
            return None
    except Exception as e:
        ack("POLL-FATAL %r"%e)
    return 0.5
bpy.app.timers.register(poll, first_interval=0.5)
w("DAEMON-ARMED")
`;

const lines = [];
let browser;
(async () => {
  browser = await chromium.launch({ headless: false });
  const ctx = await browser.newContext({ viewport: { width: 1000, height: 700 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('console', (m) => { const t = m.text(); lines.push(t); if (t.includes('BW-PROBE')) console.log('  [py] ' + t); });
  page.on('pageerror', (e) => lines.push('PAGEERROR ' + e.message));

  const u = `${BASE}${PAGE}?pyexpr=${encodeURIComponent(PY_DAEMON)}`;
  await page.goto(u, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
  console.log('[probe] navigated; waiting for WM_main (cold compile of 926MB wasm can take a minute)...');
  await page.waitForFunction(() => {
    const s = document.querySelector('#state');
    return s && s.textContent.includes('main loop (WM_main)');
  }, null, { timeout: BOOT_MS, polling: 500 });
  console.log('[probe] WM_main reached.');
  const cdp = await page.context().newCDPSession(page);
  try { await cdp.send('Emulation.setFocusEmulationEnabled', { enabled: true }); } catch (_) {}
  try { await page.mouse.click(500, 350); } catch (_) {}

  const bytes = Array.from(readFileSync(BLEND));
  console.log(`[probe] loaded ${BLEND} (${bytes.length} bytes)`);

  // Write both candidate paths from the browser thread and report throw/ok + a
  // same-thread readBack for each.
  const res = await page.evaluate((b) => {
    const out = {};
    const FS = window.__bwModule && window.__bwModule.FS;
    if (!FS) return { fatal: 'no FS' };
    const u8 = new Uint8Array(b);
    const trydo = (k, fn) => { try { out[k] = fn() || 'OK'; } catch (e) { out[k] = 'THREW ' + (e && e.message ? e.message : e); } };
    // MEMFS channel
    trydo('memfs.write', () => { FS.writeFile('/tmp/bw_drop_memfs.blend', u8); });
    trydo('memfs.readback', () => { const r = FS.readFile('/tmp/bw_drop_memfs.blend'); return 'OK len=' + r.length; });
    // OPFS channel
    trydo('opfs.mkdir', () => { FS.mkdir('/projects/imported'); });
    trydo('opfs.write', () => { FS.writeFile('/projects/imported/bw_drop_opfs.blend', u8); });
    trydo('opfs.readback', () => { const r = FS.readFile('/projects/imported/bw_drop_opfs.blend'); return 'OK len=' + r.length; });
    return out;
  }, bytes).catch((e) => ({ evaluateThrew: String(e && e.message || e) }));
  console.log('\n[browser-thread writes]');
  console.log(JSON.stringify(res, null, 2));

  // Signal the daemon to inspect from the worker side.
  await page.evaluate(() => { try { window.__bwModule.FS.writeFile('/tmp/bw_probe_go', 'go'); } catch (e) { console.log('BW-PROBE GO-WRITE-THREW ' + e); } });

  let ack = '';
  const deadline = Date.now() + ACK_MS;
  while (Date.now() < deadline) {
    ack = await page.evaluate(() => {
      try { return window.__bwModule.FS.readFile('/tmp/bw_probe_ack.txt', { encoding: 'utf8' }); }
      catch (e) { return ''; }
    });
    if (ack && ack.includes('PROBE-DONE')) break;
    if (lines.some((l) => l.includes('PROBE-DONE'))) { ack = lines.filter((l) => l.includes('BW-PROBE')).join('\n'); break; }
    await page.waitForTimeout(500);
  }
  console.log('\n----- worker daemon report -----\n' + (ack || '(none)'));

  const memfsSeen = /MEMFS SEEN exists=True size=95944/.test(ack || '');
  const memfsOpened = /MEMFS OPENED/.test(ack || '') && /Cube/.test(ack || '');
  const opfsSeen = /OPFS SEEN exists=True/.test(ack || '');
  console.log(`\n===== VERDICT: memfs browser-write=${res['memfs.write']} worker-seen=${memfsSeen} worker-opened=${memfsOpened} | opfs browser-write=${res['opfs.write']} worker-seen=${opfsSeen} =====`);
})().catch((e) => {
  console.error('[probe] FATAL ' + (e && e.message ? e.message : e));
}).finally(async () => {
  try { if (browser) await browser.close(); } catch (_) {}
  process.exit(0);
});

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: CC0-1.0
//
// M7 JOINT PROOF: the real windowed Blender binary writing through BLO_write_file
// onto the persistent OPFS /projects mount in a tab, surviving a full page reload.
//
// This is the combined proof the store-design note (notes/m7-store-design.md §6.1)
// said still had to land with the M4 shell: the node half proved BLO_* + appdir env
// routing under Emscripten; the browser probe proved the OPFS substrate + persistence.
// Here BOTH halves run in ONE real Blender binary in a real Chromium tab:
//
//   RUN 1 (save):  boot windowed -> a bpy.app.timer inside WM_main
//                    * adds a distinctive object (BW_STORE_PROOF + custom props)
//                    * bpy.ops.wm.save_as_mainfile('/projects/proof.blend')   [OPFS]
//                    * bpy.ops.wm.save_userpref() -> /projects/config/         [OPFS]
//                    * writes a recovery-class .blend into BKE_tempdir_base
//                      (= TMPDIR = /projects/.recovery)                        [OPFS]
//                    * writes a control file to /tmp (in-memory MEMFS)
//                    * records size + FNV-1a-64 of every file, and the PID.
//   RUN 2 (load):  RELOAD the SAME tab (fresh wasm module, fresh linear memory) ->
//                    * proof.blend re-read byte-identical (FNV matches run 1)
//                    * bpy.ops.wm.open_mainfile restores the object + custom props
//                    * userpref.blend + recovery .blend persisted
//                    * the /tmp MEMFS control is GONE  (OPFS-vs-MEMFS discriminator)
//                    * PID differs (genuinely a new process reading stored bytes).
//
// The FNV match across the reload is the load-bearing receipt: run 2 is a brand-new
// wasm instance with fresh memory, so identical bytes can only have come from OPFS
// storage, not in-RAM state. The MEMFS control going missing proves the same file
// system's non-OPFS paths do NOT persist - i.e. persistence is specifically the
// OPFS mount, not some artifact of the harness.
//
// Contracts checked in passing: ?pyexpr= dev hook drives the save/load; the shell's
// WM_main state marker still fires; boot completes with the store mounted; a boot
// WITHOUT the store env (?nostore control is NOT needed - the mount log line reports
// PERSISTENT vs degrade directly).
//
// RIG: headed bundled Chromium (real origin required for OPFS), COOP/COEP server on
// PORT 8126, NODE_PATH -> game-platform node_modules.
//
// Run:
//   BLENDER_WEB_BIN=/Users/paws/blender-web/build-wasm-windowed/bin \
//   BLENDER_WEB_SHELL=/Users/paws/blender-web/platform_web/shell \
//   bash /Users/paws/blender-web/scripts/serve-web.sh 8126        # (separate shell)
//   NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
//   node /Users/paws/blender-web/sandbox/m7-store-wire/verify-store-persistence.mjs

import { createRequire } from 'module';
const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');
const { chromium } = require('playwright');

const BASE = process.env.BW_BASE || 'http://localhost:8126';
const PAGE = '/windowed.html';
const EV = '/Users/paws/blender-web/sandbox/m7-store-wire/evidence';
const BOOT_MS = 180000;
const DONE_MS = 120000;

// --------------------------------------------------------------------------
// pyexpr payloads (run straight-line before WM_main via --python-expr; they arm a
// bpy.app.timer so the actual file IO happens INSIDE the main loop where context is
// valid). All results stream to stderr (proxied to the page console) AND to a MEMFS
// diag file the main thread can read via __bwModule.FS.readFile.
// --------------------------------------------------------------------------
const PY_COMMON = `
import bpy, sys, os
_BUF=[]
def emit(m):
    line="BW-STORE "+m
    _BUF.append(line)
    try:
        sys.stderr.write(line+"\\n"); sys.stderr.flush()
    except Exception: pass
    try: print(line)
    except Exception: pass
def flush(phase):
    try:
        f=open("/tmp/bwstore_"+phase+".txt","w"); f.write("\\n".join(_BUF)+"\\n"); f.close()
    except Exception as e:
        sys.stderr.write("BW-STORE FLUSH-ERR %r\\n"%e); sys.stderr.flush()
def fnv1a(b):
    h=1469598103934665603
    for x in b:
        h^=x; h=(h*1099511628211)&0xFFFFFFFFFFFFFFFF
    return "%016x"%h
`;

const PY_SAVE = PY_COMMON + `
def do_save():
    try:
        emit("PHASE save pid=%d tempdir=%s" % (os.getpid(), bpy.app.tempdir))
        # distinctive, FIXED content signature (verified byte- AND content-wise on load)
        ob = bpy.data.objects.new("BW_STORE_PROOF", None)
        bpy.context.scene.collection.objects.link(ob)
        ob["bw_marker"] = "m7-store-wired"
        bpy.context.scene["bw_scene_marker"] = 424242
        p = "/projects/proof.blend"
        bpy.ops.wm.save_as_mainfile(filepath=p)
        data = open(p, "rb").read()
        emit("SAVE-BLEND ok path=%s size=%d fnv=%s magic=%s objs=%d" % (
            p, len(data), fnv1a(data), data[:7].hex(), len(bpy.data.objects)))
        try:
            bpy.ops.wm.save_userpref()
            ud = open("/projects/config/userpref.blend","rb").read()
            emit("SAVE-USERPREF ok size=%d fnv=%s" % (len(ud), fnv1a(ud)))
        except Exception as e:
            emit("SAVE-USERPREF ERR %r" % e)
        # recovery-class artifact into BKE_tempdir_base (== TMPDIR == /projects/.recovery)
        try:
            rp = "/projects/.recovery/bw_recovery_proof.blend"
            bpy.ops.wm.save_as_mainfile(filepath=rp, copy=True)
            rd = open(rp, "rb").read()
            emit("SAVE-RECOVERY ok path=%s size=%d fnv=%s" % (rp, len(rd), fnv1a(rd)))
        except Exception as e:
            emit("SAVE-RECOVERY ERR %r" % e)
        # MEMFS control: /tmp is in-memory -> MUST be gone after reload
        try:
            open("/tmp/bw_memfs_control.bin","wb").write(b"MEMFS-CONTROL-"+str(os.getpid()).encode())
            emit("MEMFS-CONTROL-WRITTEN /tmp/bw_memfs_control.bin")
        except Exception as e:
            emit("MEMFS-CONTROL ERR %r" % e)
        # directory listing (recent-files / account-sync seam)
        try:
            emit("DIRLIST /projects=%s" % ",".join(sorted(os.listdir("/projects"))))
        except Exception as e:
            emit("DIRLIST ERR %r" % e)
        emit("SAVE-DONE")
    except Exception as e:
        emit("SAVE-FATAL %r" % e)
    flush("save")
    return None
bpy.app.timers.register(do_save, first_interval=1.0)
emit("SAVE-ARMED pid=%d" % os.getpid())
flush("save")
`;

const PY_LOAD = PY_COMMON + `
def do_load():
    try:
        emit("PHASE load pid=%d tempdir=%s" % (os.getpid(), bpy.app.tempdir))
        p = "/projects/proof.blend"
        if not os.path.exists(p):
            emit("LOAD-MISSING %s PERSISTENCE-FAILED" % p); emit("LOAD-DONE"); flush("load"); return None
        data = open(p, "rb").read()
        emit("LOAD-BLEND-BYTES path=%s size=%d fnv=%s magic=%s" % (
            p, len(data), fnv1a(data), data[:7].hex()))
        bpy.ops.wm.open_mainfile(filepath=p)
        ob = bpy.data.objects.get("BW_STORE_PROOF")
        emit("LOAD-CONTENT proof_obj=%s marker=%r scene_marker=%r objs=%d" % (
            ("FOUND" if ob else "ABSENT"),
            (ob.get("bw_marker") if ob else None),
            bpy.context.scene.get("bw_scene_marker"),
            len(bpy.data.objects)))
        up = "/projects/config/userpref.blend"
        if os.path.exists(up):
            ud = open(up,"rb").read(); emit("LOAD-USERPREF ok size=%d fnv=%s" % (len(ud), fnv1a(ud)))
        else:
            emit("LOAD-USERPREF MISSING")
        rp = "/projects/.recovery/bw_recovery_proof.blend"
        if os.path.exists(rp):
            rd = open(rp,"rb").read(); emit("LOAD-RECOVERY ok size=%d fnv=%s" % (len(rd), fnv1a(rd)))
        else:
            emit("LOAD-RECOVERY MISSING")
        emit("MEMFS-CONTROL-AFTER-RELOAD exists=%s" % os.path.exists("/tmp/bw_memfs_control.bin"))
        emit("LOAD-DONE")
    except Exception as e:
        emit("LOAD-FATAL %r" % e)
    flush("load")
    return None
bpy.app.timers.register(do_load, first_interval=1.0)
emit("LOAD-ARMED pid=%d" % os.getpid())
flush("load")
`;

// --------------------------------------------------------------------------
const results = [];
const rec = (name, ok, detail) => {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}  ${detail ?? ''}`);
};

const lines = [];   // all console text across the whole run
function hookConsole(page, tag) {
  page.on('console', (m) => {
    const t = m.text();
    lines.push(t);
    if (t.includes('BW-STORE') || t.includes('M7 store')) console.log(`  [${tag}] ${t}`);
  });
  page.on('pageerror', (e) => { lines.push('PAGEERROR ' + e.message); });
}

const waitBoot = (page) => page.waitForFunction(() => {
  const s = document.querySelector('#state');
  return s && s.textContent.includes('main loop (WM_main)');
}, { timeout: BOOT_MS });

async function forceActive(page) {
  const s = await page.context().newCDPSession(page);
  try { await s.send('Emulation.setFocusEmulationEnabled', { enabled: true }); } catch (_) {}
  try { await s.send('Page.setWebLifecycleState', { state: 'active' }); } catch (_) {}
  return s;
}

// Poll the MEMFS diag file (main-thread FS.readFile works for /tmp) until it holds
// the DONE marker; returns the file text (authoritative) or '' on timeout.
async function waitDiag(page, phase, doneMarker) {
  const deadline = Date.now() + DONE_MS;
  while (Date.now() < deadline) {
    const txt = await page.evaluate((ph) => {
      try { return window.__bwModule.FS.readFile('/tmp/bwstore_' + ph + '.txt', { encoding: 'utf8' }); }
      catch (e) { return ''; }
    }, phase);
    if (txt && txt.includes(doneMarker)) return txt;
    // console fallback: some builds proxy stderr straight to console only
    if (lines.some((l) => l.includes(doneMarker))) {
      return lines.filter((l) => l.includes('BW-STORE')).join('\n');
    }
    await page.waitForTimeout(750);
  }
  // last-ditch: return whatever the diag file has, else console
  const txt = await page.evaluate((ph) => {
    try { return window.__bwModule.FS.readFile('/tmp/bwstore_' + ph + '.txt', { encoding: 'utf8' }); }
    catch (e) { return ''; }
  }, phase);
  return txt || lines.filter((l) => l.includes('BW-STORE')).join('\n');
}

function grab(text, re) { const m = re.exec(text); return m ? m[1] : null; }

(async () => {
  const browser = await chromium.launch({ headless: false });
  // ONE persistent-lifetime context across both navigations: OPFS is per-origin and
  // persists across a reload within a context's lifetime (exactly the probe's method).
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  hookConsole(page, 'run');

  let saveTxt = '', loadTxt = '';
  let mountLineSave = '', mountLineLoad = '';
  try {
    // ---- RUN 1: save ----
    const u1 = `${BASE}${PAGE}?pyexpr=${encodeURIComponent(PY_SAVE)}`;
    await page.goto(u1, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
    await waitBoot(page);
    await forceActive(page);
    try { await page.mouse.click(640, 400); } catch (_) {}   // pump input -> keeps rAF/main loop ticking
    saveTxt = await waitDiag(page, 'save', 'SAVE-DONE');
    mountLineSave = lines.filter((l) => l.includes('M7 store')).slice(-1)[0] || '';
    try { await page.screenshot({ path: `${EV}/m7-store-run1-save-1280x800.png` }); } catch (_) {}

    // ---- RUN 2: reload SAME tab (fresh wasm/memory) then load ----
    const u2 = `${BASE}${PAGE}?pyexpr=${encodeURIComponent(PY_LOAD)}`;
    lines.length = 0;                       // isolate run-2 console
    await page.goto(u2, { waitUntil: 'domcontentloaded', timeout: BOOT_MS });
    await waitBoot(page);
    await forceActive(page);
    try { await page.mouse.click(640, 400); } catch (_) {}
    loadTxt = await waitDiag(page, 'load', 'LOAD-DONE');
    mountLineLoad = lines.filter((l) => l.includes('M7 store')).slice(-1)[0] || '';
    try { await page.screenshot({ path: `${EV}/m7-store-run2-load-1280x800.png` }); } catch (_) {}
  } catch (e) {
    rec('rig-ran', false, 'driver threw: ' + (e && e.message ? e.message : e));
  } finally {
    // ---- assertions ----
    console.log('\n----- RUN 1 (save) diag -----\n' + saveTxt);
    console.log('----- RUN 1 mount line -----\n' + mountLineSave);
    console.log('\n----- RUN 2 (load) diag -----\n' + loadTxt);
    console.log('----- RUN 2 mount line -----\n' + mountLineLoad + '\n');

    // mount reported persistent both boots
    rec('mount-persistent-run1', /PERSISTENT/.test(mountLineSave), mountLineSave);
    rec('mount-persistent-run2', /PERSISTENT/.test(mountLineLoad), mountLineLoad);

    // save happened
    const saveOk = /SAVE-BLEND ok/.test(saveTxt);
    rec('save-blend', saveOk, grab(saveTxt, /(SAVE-BLEND ok[^\n]*)/) || '');

    // fnv/size parity across the reload (THE joint-proof receipt)
    const sSize = grab(saveTxt, /SAVE-BLEND ok[^\n]*size=(\d+)/);
    const sFnv  = grab(saveTxt, /SAVE-BLEND ok[^\n]*fnv=([0-9a-f]{16})/);
    const lSize = grab(loadTxt, /LOAD-BLEND-BYTES[^\n]*size=(\d+)/);
    const lFnv  = grab(loadTxt, /LOAD-BLEND-BYTES[^\n]*fnv=([0-9a-f]{16})/);
    rec('reload-persist-size', !!sSize && sSize === lSize, `save=${sSize} load=${lSize}`);
    rec('reload-persist-fnv',  !!sFnv && sFnv === lFnv,   `save=${sFnv} load=${lFnv}`);

    // real BLO_read_file + bpy content survives
    rec('content-object', /proof_obj=FOUND/.test(loadTxt), grab(loadTxt, /(LOAD-CONTENT[^\n]*)/) || '');
    rec('content-marker', /marker='m7-store-wired'/.test(loadTxt), '');
    rec('content-scene-marker', /scene_marker=424242/.test(loadTxt), '');

    // userpref persisted (config seam)
    const upS = grab(saveTxt, /SAVE-USERPREF ok[^\n]*fnv=([0-9a-f]{16})/);
    const upL = grab(loadTxt, /LOAD-USERPREF ok[^\n]*fnv=([0-9a-f]{16})/);
    rec('userpref-persist', !!upS && upS === upL, `save=${upS} load=${upL}`);

    // recovery / TMPDIR seam persisted
    const rvS = grab(saveTxt, /SAVE-RECOVERY ok[^\n]*fnv=([0-9a-f]{16})/);
    const rvL = grab(loadTxt, /LOAD-RECOVERY ok[^\n]*fnv=([0-9a-f]{16})/);
    rec('recovery-persist', !!rvS && rvS === rvL, `save=${rvS} load=${rvL}`);

    // TMPDIR routed to /projects/.recovery in-tab (env honored under Emscripten)
    rec('tmpdir-routed', /tempdir=\/projects\/\.recovery/.test(saveTxt), grab(saveTxt, /(tempdir=[^\s]+)/) || '');

    // OPFS-vs-MEMFS discriminator: /tmp control is gone after reload
    rec('memfs-control-gone', /MEMFS-CONTROL-AFTER-RELOAD exists=False/.test(loadTxt),
        grab(loadTxt, /(MEMFS-CONTROL-AFTER-RELOAD[^\n]*)/) || '');

    // Genuinely two distinct fresh sessions across the reload. NOTE: wasm getpid()
    // returns a constant (42) for every instance, so PID is NOT a discriminator here.
    // The per-session mkdtemp tempdir suffix IS: a fresh BKE_tempdir_init on a fresh
    // wasm instance mints a new blender_XXXXXX dir, so the suffixes must DIFFER (and
    // each boot also logs its own mount line with an independent timing).
    const tdS = grab(saveTxt, /PHASE save[^\n]*tempdir=([^\s]+)/);
    const tdL = grab(loadTxt, /PHASE load[^\n]*tempdir=([^\s]+)/);
    rec('distinct-session', !!tdS && !!tdL && tdS !== tdL, `save-tempdir=${tdS} load-tempdir=${tdL}`);

    const pass = results.filter((r) => r.ok).length;
    console.log(`\n===== ${pass}/${results.length} PASS =====`);
    try { await browser.close(); } catch (_) {}
    process.exit(pass === results.length ? 0 : 1);
  }
})();

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M7b FILE BRIDGE - .blend drag-drop, File System Access open/save (+ fallbacks),
// and OPFS persistence request, for the WINDOWED blender_browser shell.
//
// THE PROBLEM this solves (measured, notes/m7b-files-io.md):
//   The windowed build is -sPROXY_TO_PTHREAD: main(), WasmFS, and all of Blender
//   live on the WM WORKER; the page runs on the BROWSER thread. WasmFS's OPFS
//   backend uses sync access handles, which are worker-only (GOAL.md emscripten
//   posture). So the durable /projects mount must be driven from the worker, not
//   the page. The M5 channel audit (notes/m5-windowed-replay.md) also showed the
//   only Python that runs post-boot is a bpy.app.timer registered before WM_main.
//
// THE DESIGN:
//   * A tiny WM-worker daemon (armed via one isolated --python-expr at boot,
//     daemonPyexpr() below) registers a bpy.app.timer that polls a MEMFS command
//     directory. MEMFS lives in shared wasm memory, so it is visible from BOTH
//     threads (proven: sandbox/m7b-files/probe-write-channel.mjs) and needs no
//     OPFS handle - it is the cross-thread byte CONDUIT.
//   * The BROWSER thread only ever touches MEMFS (/tmp/bw_io/{in,cmd,out,ack}).
//     The WORKER daemon owns every OPFS read/write into /projects/imported and
//     every bpy.ops.wm.{open,save}_mainfile call. This matches the OPFS
//     worker-only coupling and never blocks the page on OPFS.
//
//   IN  (drag-drop / FSA open): page writes bytes -> /tmp/bw_io/in/<tok>.blend,
//       then a command -> /tmp/bw_io/cmd/<tok>.json. Daemon copies the bytes into
//       /projects/imported/<name> (durable OPFS), open_mainfile's it, and acks.
//   OUT (FSA save / download): page writes a save command. Daemon
//       save_as_mainfile(copy=True) into /projects/imported/<name> (durable OPFS),
//       copies the bytes to /tmp/bw_io/out/<tok>.blend, and acks; the page reads
//       those bytes back (FS.readFile from the browser thread is known-good
//       post-boot) and streams them to the disk handle (or a download blob).
//
// PRESERVED: this module is additive. boot-windowed.js keeps every existing hook
// (?pyexpr/?args/?gate, __bwModule, resize/DPR, store ENV); the daemon is skipped
// entirely in ?gate mode so the golden-capture argv stays pristine.

"use strict";

(function () {
  // Conduit + store layout. SINGLE SOURCE OF TRUTH - daemonPyexpr() embeds these
  // exact strings into the worker Python so the two sides can never drift.
  const IO = "/tmp/bw_io";              // MEMFS conduit root (cross-thread visible)
  const STORE = "/projects/imported";   // durable OPFS store (worker-owned)
  const ACK_TIMEOUT_MS = 30000;         // per-command ack deadline
  const ACK_POLL_MS = 120;

  let MOD = null;                        // the resolved Emscripten module
  let logFn = (m) => { try { console.log(m); } catch (_) {} };
  let readyResolve;
  const readyPromise = new Promise((r) => { readyResolve = r; });
  let armedSeen = false;

  // --------------------------------------------------------------------------
  // The WM-worker daemon (Python). Runs as its OWN --python-expr before WM_main
  // (creator.cc ARG_PASS_FINAL), so context + bpy.app.timers are valid. Names are
  // `_bwfb_`-prefixed so a co-resident user ?pyexpr can never collide. Everything
  // is wrapped so a daemon fault never touches boot (and by default a --python-expr
  // error only prints - exit_code_on_error.python is unset).
  // --------------------------------------------------------------------------
  function daemonPyexpr() {
    return [
      "import bpy, os, json, traceback",
      "_BWFB_IO = " + JSON.stringify(IO),
      "_BWFB_STORE = " + JSON.stringify(STORE),
      "def _bwfb_log(m):",
      "    try: os.write(2, ('BW-FILEBRIDGE ' + m + '\\n').encode())",
      "    except Exception: pass",
      "for _d in (_BWFB_IO, _BWFB_IO+'/in', _BWFB_IO+'/cmd', _BWFB_IO+'/out', _BWFB_IO+'/ack'):",
      "    try: os.makedirs(_d, exist_ok=True)",  // MEMFS conduit dirs
      "    except Exception as _e: _bwfb_log('MKIO-ERR %r' % _e)",
      "try: os.makedirs(_BWFB_STORE, exist_ok=True)",  // durable OPFS dir, worker-side
      "except Exception as _e: _bwfb_log('MKSTORE-ERR %r' % _e)",
      "def _bwfb_ack(tok, obj):",
      "    try:",
      "        f = open(_BWFB_IO + '/ack/' + tok + '.json', 'w'); f.write(json.dumps(obj)); f.close()",
      "    except Exception as e: _bwfb_log('ACK-ERR %r' % e)",
      "def _bwfb_safe(name):",
      "    base = os.path.basename(str(name)).replace('\\\\', '_')",
      "    base = ''.join(c for c in base if c.isalnum() or c in '._- ') or 'untitled.blend'",
      "    if not base.lower().endswith('.blend'): base += '.blend'",
      "    return base",
      "def _bwfb_do(tok, spec):",
      "    op = spec.get('op')",
      "    try:",
      "        if op == 'open':",
      "            name = _bwfb_safe(spec.get('name', 'imported.blend'))",
      "            src = _BWFB_IO + '/in/' + tok + '.blend'",
      "            dst = _BWFB_STORE + '/' + name",
      "            data = open(src, 'rb').read()",
      "            open(dst, 'wb').write(data)",  // durable OPFS copy on the worker thread
      "            try: os.remove(src)",
      "            except Exception: pass",
      "            bpy.ops.wm.open_mainfile(filepath=dst)",
      "            _bwfb_ack(tok, {'ok': True, 'op': op, 'storePath': dst, 'size': len(data), 'name': name, 'objects': sorted(o.name for o in bpy.data.objects)})",
      "        elif op == 'open_store':",  // open a .blend already in the durable store (recent-files / ?open deep-link)
      "            name = _bwfb_safe(spec.get('name', 'imported.blend'))",
      "            dst = _BWFB_STORE + '/' + name",
      "            if not os.path.exists(dst):",
      "                _bwfb_ack(tok, {'ok': False, 'op': op, 'error': 'not in store: ' + name}); return",
      "            bpy.ops.wm.open_mainfile(filepath=dst)",
      "            _bwfb_ack(tok, {'ok': True, 'op': op, 'storePath': dst, 'size': os.path.getsize(dst), 'name': name, 'objects': sorted(o.name for o in bpy.data.objects)})",
      "        elif op == 'save':",
      "            name = _bwfb_safe(spec.get('name', 'untitled.blend'))",
      "            dst = _BWFB_STORE + '/' + name",
      "            mk = spec.get('addEmpty')",
      "            if mk:",  // bounded authoring op (platform-drive example, notes/platform-integration-design.md §3)
      "                ob = bpy.data.objects.new(str(mk), None); bpy.context.scene.collection.objects.link(ob)",
      "            sm = spec.get('sceneMarker')",
      "            if sm is not None: bpy.context.scene['bw_io_marker'] = sm",
      "            bpy.ops.wm.save_as_mainfile(filepath=dst, copy=True)",
      "            data = open(dst, 'rb').read()",
      "            open(_BWFB_IO + '/out/' + tok + '.blend', 'wb').write(data)",  // conduit bytes for the page
      "            _bwfb_ack(tok, {'ok': True, 'op': op, 'storePath': dst, 'size': len(data), 'name': name, 'objects': sorted(o.name for o in bpy.data.objects)})",
      "        elif op == 'list':",
      "            try: items = sorted(os.listdir(_BWFB_STORE))",
      "            except Exception: items = []",
      "            _bwfb_ack(tok, {'ok': True, 'op': op, 'items': items})",
      "        elif op == 'mark':",  // add a named Empty (round-trip verifier + platform-drive primitive)
      "            name = str(spec.get('name', 'BW_MARKER'))",
      "            ob = bpy.data.objects.new(name, None); bpy.context.scene.collection.objects.link(ob)",
      "            _bwfb_ack(tok, {'ok': True, 'op': op, 'object': name, 'objects': sorted(o.name for o in bpy.data.objects)})",
      "        else:",
      "            _bwfb_ack(tok, {'ok': False, 'op': op, 'error': 'unknown op'})",
      "    except Exception as e:",
      "        _bwfb_log('DO-ERR %r' % e)",
      "        _bwfb_ack(tok, {'ok': False, 'op': op, 'error': repr(e), 'tb': traceback.format_exc()})",
      "def _bwfb_poll():",
      "    try:",
      "        cdir = _BWFB_IO + '/cmd'",
      "        for fn in sorted(os.listdir(cdir)):",
      "            if not fn.endswith('.json'): continue",
      "            tok = fn[:-5]; cpath = cdir + '/' + fn",
      "            try: spec = json.load(open(cpath))",
      "            except Exception as e:",
      "                _bwfb_log('BADCMD %s %r' % (fn, e))",
      "                try: os.remove(cpath)",
      "                except Exception: pass",
      "                continue",
      "            try: os.remove(cpath)",  // consume before running: never re-run on fault
      "            except Exception: pass",
      "            _bwfb_do(tok, spec)",
      "    except Exception as e:",
      "        _bwfb_log('POLL-ERR %r' % e)",
      "    return 0.3",
      "try: open(_BWFB_IO + '/ready', 'w').write('1')",
      "except Exception: pass",
      // first_interval=0.0 so the poll runs on the loop's FIRST tick (which also
      // drains any command staged pre-WM_main, e.g. a ?open deep-link); it then
      // re-arms at 0.3 s so a continuously-ticking loop (a live interacting tab)
      // serves post-boot drag-drop / open / save. NOTE the WM loop is redraw/rAF
      // driven and stalls at idle (notes/m7b-files-io.md); post-boot polling only
      // advances while frames composite. Pre-staged commands are drained on tick 1.
      "bpy.app.timers.register(_bwfb_poll, first_interval=0.0)",
      "_bwfb_log('ARMED store=%s conduit=%s' % (_BWFB_STORE, _BWFB_IO))",
    ].join("\n");
  }

  // --------------------------------------------------------------------------
  // Browser-thread helpers (all MEMFS - never OPFS from here).
  // --------------------------------------------------------------------------
  function requireMod() {
    if (!MOD) throw new Error("file-bridge not attached (no module)");
    return MOD;
  }
  let _tok = 0;
  function newToken() {
    _tok += 1;
    return "t" + Date.now().toString(36) + "_" + _tok;
  }
  function sanitize(name) {
    let b = String(name || "untitled.blend").split(/[\\/]/).pop();
    b = b.replace(/[^A-Za-z0-9._ -]/g, "_") || "untitled.blend";
    if (!/\.blend$/i.test(b)) b += ".blend";
    return b;
  }
  function ensureDirs(mod) {
    for (const d of [IO, IO + "/in", IO + "/cmd", IO + "/out", IO + "/ack"]) {
      try { mod.FS.mkdir(d); } catch (_) { /* EEXIST is fine */ }
    }
  }
  function writeCmd(mod, tok, spec) {
    mod.FS.writeFile(IO + "/cmd/" + tok + ".json", JSON.stringify(spec));
  }
  async function waitAck(mod, tok) {
    const path = IO + "/ack/" + tok + ".json";
    const deadline = Date.now() + ACK_TIMEOUT_MS;
    for (;;) {
      let txt = null;
      try { txt = mod.FS.readFile(path, { encoding: "utf8" }); } catch (_) { txt = null; }
      if (txt) {
        try { mod.FS.unlink(path); } catch (_) {}
        return JSON.parse(txt);
      }
      if (Date.now() > deadline) throw new Error("ack timeout for " + tok);
      await new Promise((r) => setTimeout(r, ACK_POLL_MS));
    }
  }

  // Wait until the worker daemon has armed (touched /tmp/bw_io/ready).
  async function waitReady(mod) {
    const deadline = Date.now() + 60000;
    for (;;) {
      try { if (mod.FS.readFile(IO + "/ready", { encoding: "utf8" })) return true; } catch (_) {}
      if (armedSeen) return true;
      if (Date.now() > deadline) return false;
      await new Promise((r) => setTimeout(r, 150));
    }
  }

  // --------------------------------------------------------------------------
  // Public operations.
  // --------------------------------------------------------------------------

  // Hand raw .blend bytes to Blender: stage on MEMFS, command an open, await ack.
  async function importBytes(u8, name) {
    const mod = requireMod();
    ensureDirs(mod);
    const tok = newToken();
    const safe = sanitize(name);
    mod.FS.writeFile(IO + "/in/" + tok + ".blend", u8);
    writeCmd(mod, tok, { op: "open", name: safe });
    logFn("[file-bridge] open <- " + safe + " (" + u8.length + " B)");
    const ack = await waitAck(mod, tok);
    logFn("[file-bridge] open ack: " + JSON.stringify(ack));
    if (!ack.ok) throw new Error("open failed: " + (ack.error || "?"));
    return ack;
  }

  // Ask Blender to serialize the current file; return {ack, bytes}.
  async function requestSaveBytes(name, extra) {
    const mod = requireMod();
    ensureDirs(mod);
    const tok = newToken();
    const safe = sanitize(name);
    writeCmd(mod, tok, Object.assign({ op: "save", name: safe }, extra || {}));
    const ack = await waitAck(mod, tok);
    if (!ack.ok) throw new Error("save failed: " + (ack.error || "?"));
    const bytes = mod.FS.readFile(IO + "/out/" + tok + ".blend"); // Uint8Array
    try { mod.FS.unlink(IO + "/out/" + tok + ".blend"); } catch (_) {}
    logFn("[file-bridge] save -> " + safe + " (" + bytes.length + " B)");
    return { ack, bytes };
  }

  async function listStore() {
    const mod = requireMod();
    ensureDirs(mod);
    const tok = newToken();
    writeCmd(mod, tok, { op: "list" });
    return await waitAck(mod, tok);
  }

  // Open a .blend already in the durable store (recent-files / ?open deep-link).
  async function openStore(name) {
    const mod = requireMod();
    ensureDirs(mod);
    const tok = newToken();
    writeCmd(mod, tok, { op: "open_store", name: sanitize(name) });
    const ack = await waitAck(mod, tok);
    if (!ack.ok) throw new Error("open_store failed: " + (ack.error || "?"));
    return ack;
  }

  // FSA (Chromium) open, with a <input type=file> fallback everywhere else.
  async function openFromDisk() {
    if (typeof window.showOpenFilePicker === "function") {
      const [h] = await window.showOpenFilePicker({
        multiple: false,
        types: [{ description: "Blender file", accept: { "application/x-blender": [".blend"] } }],
      });
      const f = await h.getFile();
      const u8 = new Uint8Array(await f.arrayBuffer());
      return importBytes(u8, f.name);
    }
    return openFromDiskFallback();
  }

  function openFromDiskFallback() {
    return new Promise((resolve, reject) => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".blend";
      input.style.display = "none";
      input.addEventListener("change", async () => {
        try {
          const f = input.files && input.files[0];
          if (!f) { resolve(null); return; }
          const u8 = new Uint8Array(await f.arrayBuffer());
          resolve(await importBytes(u8, f.name));
        } catch (e) { reject(e); } finally { input.remove(); }
      }, { once: true });
      document.body.appendChild(input);
      input.click();
    });
  }

  // FSA (Chromium) save, with a download-blob fallback everywhere else.
  async function saveToDisk(suggestedName, extra) {
    const name = sanitize(suggestedName || "untitled.blend");
    const { ack, bytes } = await requestSaveBytes(name, extra);
    if (typeof window.showSaveFilePicker === "function") {
      const h = await window.showSaveFilePicker({
        suggestedName: name,
        types: [{ description: "Blender file", accept: { "application/x-blender": [".blend"] } }],
      });
      const w = await h.createWritable();
      await w.write(bytes);
      await w.close();
      return { ack, via: "fsa" };
    }
    const blob = new Blob([bytes], { type: "application/x-blender" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { try { a.remove(); URL.revokeObjectURL(url); } catch (_) {} }, 1500);
    return { ack, via: "download" };
  }

  // --------------------------------------------------------------------------
  // Drag-drop wiring + a minimal drop overlay (input hardening in boot-windowed.js
  // does not touch drag events, so there is no conflict).
  // --------------------------------------------------------------------------
  function installDragDrop(canvas) {
    let overlay = null;
    const showOverlay = (on) => {
      if (on && !overlay) {
        overlay = document.createElement("div");
        overlay.textContent = "Drop a .blend to open";
        Object.assign(overlay.style, {
          position: "fixed", inset: "0", zIndex: "50", display: "flex",
          alignItems: "center", justifyContent: "center", pointerEvents: "none",
          font: "600 18px/1 -apple-system, system-ui, sans-serif", color: "#d6e2ff",
          background: "rgba(20,40,80,0.35)", border: "3px dashed #6ea8ff",
          textShadow: "0 1px 3px rgba(0,0,0,0.6)",
        });
        document.body.appendChild(overlay);
      } else if (!on && overlay) {
        overlay.remove(); overlay = null;
      }
    };
    const isBlendDrag = (e) => {
      const dt = e.dataTransfer;
      if (!dt) return false;
      if (dt.items && dt.items.length) {
        for (const it of dt.items) { if (it.kind === "file") return true; }
      }
      return dt.types && Array.prototype.indexOf.call(dt.types, "Files") !== -1;
    };
    window.addEventListener("dragover", (e) => {
      if (!isBlendDrag(e)) return;
      e.preventDefault();
      try { e.dataTransfer.dropEffect = "copy"; } catch (_) {}
      showOverlay(true);
    }, false);
    window.addEventListener("dragleave", (e) => {
      if (e.relatedTarget === null) showOverlay(false); // left the window
    }, false);
    window.addEventListener("drop", async (e) => {
      if (!e.dataTransfer) return;
      e.preventDefault();
      showOverlay(false);
      const files = Array.from(e.dataTransfer.files || []);
      const blend = files.find((f) => /\.blend$/i.test(f.name)) || files[0];
      if (!blend) return;
      if (!/\.blend$/i.test(blend.name)) {
        logFn("[file-bridge] ignoring non-.blend drop: " + blend.name);
        return;
      }
      try {
        const u8 = new Uint8Array(await blend.arrayBuffer());
        await importBytes(u8, blend.name);
      } catch (err) {
        logFn("[file-bridge] drop open failed: " + (err && err.message ? err.message : err));
      }
    }, false);
  }

  // --------------------------------------------------------------------------
  // OPFS persistence (open item 6.4, first half). Request + honestly report.
  // --------------------------------------------------------------------------
  async function requestPersistence() {
    try {
      if (!navigator.storage) { logFn("[file-bridge] storage.persist(): navigator.storage unavailable"); return; }
      let persisted = false;
      if (typeof navigator.storage.persisted === "function") persisted = await navigator.storage.persisted();
      let granted = persisted;
      if (!persisted && typeof navigator.storage.persist === "function") granted = await navigator.storage.persist();
      let est = "";
      try {
        if (typeof navigator.storage.estimate === "function") {
          const e = await navigator.storage.estimate();
          est = " usage=" + (e.usage || 0) + " quota=" + (e.quota || 0);
        }
      } catch (_) {}
      // Honest eviction posture: persisted=true => the origin's OPFS is durable and
      // will NOT be cleared under storage pressure without explicit user action;
      // persisted=false => best-effort storage, evictable under pressure.
      logFn("[file-bridge] storage.persist(): granted=" + granted + " persisted=" + persisted +
            " eviction=" + (granted ? "durable" : "best-effort/evictable") + est);
      window.__bwPersist = { granted, persisted };
    } catch (e) {
      logFn("[file-bridge] storage.persist() threw: " + (e && e.message ? e.message : e));
    }
  }

  // --------------------------------------------------------------------------
  // Attach: called by boot-windowed.js once the module has resolved.
  // --------------------------------------------------------------------------
  function attach(mod, opts) {
    MOD = mod;
    opts = opts || {};
    if (typeof opts.log === "function") logFn = opts.log;
    const canvas = opts.canvas || document.querySelector("#canvas");
    installDragDrop(canvas);
    // Surface daemon ARMED / errors from the page console stream.
    // (boot-windowed.js pipes module print/printErr to console; we also watch here.)
    waitReady(mod).then((ok) => {
      armedSeen = ok;
      logFn("[file-bridge] daemon " + (ok ? "ready" : "NOT ready (timeout)") +
            " - drag-drop + open/save live");
      readyResolve(ok);
    });
    return readyPromise;
  }

  // Let boot-windowed.js flag when it sees the ARMED line (belt-and-braces).
  function noteConsoleLine(line) {
    if (typeof line === "string" && line.indexOf("BW-FILEBRIDGE ARMED") !== -1) armedSeen = true;
  }

  window.BWFileBridge = {
    IO, STORE,
    daemonPyexpr,
    attach,
    requestPersistence,
    noteConsoleLine,
    ready: () => readyPromise,
    // operations (also handy from the devtools console)
    importBytes,
    requestSaveBytes,
    listStore,
    openStore,
    openFromDisk,
    saveToDisk,
  };
})();

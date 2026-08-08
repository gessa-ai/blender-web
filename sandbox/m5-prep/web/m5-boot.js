// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M5 tier-(c) event-simulate REPLAY boot shell (browser half).
//
// A purpose-built, self-contained boot for the windowed blender_browser wasm
// module. It boots Blender WINDOWED (GHOST-web + WebGPU, no --background) with:
//   --enable-event-simulate --log operator --log-level debug --python-expr <S>
// where <S> is a STAGER expression that base64-decodes the ui_simulate DSL
// (modules package), the M5 session module (m5_core), state_dump and the runner
// into WasmFS at /m5 - from INSIDE Python on the WM worker - then runs the runner
// for the ?session= query param.
//
// WHY Python does the staging (not JS FS.writeFile in preRun): with
// -sPROXY_TO_PTHREAD the WasmFS is owned by the WM worker; FS.writeFile/readFile
// from the browser (main) thread ABORT (observed: Aborted()). Python file I/O on
// the worker is the only reliable channel, so the bundle rides in on the argv and
// the result rides back out on the console (the runner emits base64 chunks on
// stderr, unbuffered + flushed). No browser-thread FS access at all.
//
// PRESERVED contract markers: window.__bwModule exposed; "main loop (WM_main)"
// #state marker. Fixed 1280x720 backing, DPR forced 1 (event_simulate coords are
// window-relative; a stable size keeps them deterministic; the dump is
// window-size independent).

"use strict";

const CANVAS_SELECTOR = "#canvas";
const BIN_PREFIX = "/bin/";
const BACK_W = 1280, BACK_H = 720;

const ENV_VARS = {
  BLENDER_SYSTEM_RESOURCES: "/bw",
  BLENDER_SYSTEM_PYTHON: "/bw/python",
  BLENDER_SYSTEM_SCRIPTS: "/bw/scripts",
  BLENDER_SYSTEM_DATAFILES: "/bw/datafiles",
};

// Python bundle -> WasmFS path (dst) + fetch URL (src). gen/ copies are refreshed
// from the committed sources by stage-py.sh so nothing here drifts.
const BUNDLE = [
  { key: "runner", dst: "/m5/m5_wasm_runner.py",        url: "/py/m5_wasm_runner.py" },
  { key: "core",   dst: "/m5/m5_core.py",               url: "/py/gen/m5_core.py" },
  { key: "state",  dst: "/m5/state_dump.py",            url: "/py/gen/state_dump.py" },
  { key: "ek",     dst: "/m5/modules/easy_keys.py",     url: "/py/gen/easy_keys.py" },
  { key: "ui",     dst: "/m5/modules/ui_test_utils.py", url: "/py/gen/ui_test_utils.py" },
];

const canvasEl = document.querySelector(CANVAS_SELECTOR);
const stateEl = document.getElementById("state");
const logEl = document.getElementById("log");

const M5 = window.__m5 = {
  session: null, booted: false, log: [], markers: {}, error: null,
  outChunks: {}, outN: 0, outText: null, done: false,
};

function setState(name, label) {
  if (!stateEl) return;
  stateEl.className = "state-" + name;
  stateEl.setAttribute("data-state", name);
  stateEl.textContent = "state: " + label;
}

function b64utf8(text) { return btoa(unescape(encodeURIComponent(text))); }
function unb64utf8(b) { return decodeURIComponent(escape(atob(b))); }

function record(line) {
  if (typeof line !== "string") line = String(line);
  M5.log.push(line);
  if (logEl && M5.log.length < 6000) { logEl.textContent += line + "\n"; }

  // Reassemble the base64 dump chunks the runner emits on stderr.
  const c = /^M5_OUT (\d+) (\d+) (\S+)$/.exec(line);
  if (c) {
    M5.outN = parseInt(c[2], 10);
    M5.outChunks[parseInt(c[1], 10)] = c[3];
    return;
  }
  if (line.indexOf("M5_OUT_END") === 0 || line.indexOf("M5_DONE") === 0) {
    if (M5.outN > 0 && Object.keys(M5.outChunks).length >= M5.outN && !M5.outText) {
      let b = "";
      for (let i = 0; i < M5.outN; i++) b += (M5.outChunks[i] || "");
      try { M5.outText = unb64utf8(b); } catch (e) { M5.error = "reassemble"; }
    }
    if (line.indexOf("M5_DONE") === 0) M5.done = true;
    return;
  }
  const m = /\b(M5_[A-Z_]+)\b/.exec(line);
  if (m) M5.markers[m[1]] = line;
}

function getSession() {
  try { return new URLSearchParams(location.search).get("session"); }
  catch (e) { return null; }
}

async function fetchText(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error("fetch " + url + " -> " + r.status);
  return await r.text();
}

// Build the --python-expr STAGER (runs on the WM worker before WM_main pumps).
function buildStager(bundleTexts, session) {
  const lines = ["import base64,os,sys", "_B={}"];
  for (const b of BUNDLE) {
    lines.push("_B[" + JSON.stringify(b.key) + "]=" + JSON.stringify(b64utf8(bundleTexts[b.key])));
  }
  lines.push("os.makedirs('/m5/modules',exist_ok=True)");
  lines.push("open('/m5/modules/__init__.py','w').close()");
  lines.push("def _w(p,k):");
  lines.push("    with open(p,'wb') as f: f.write(base64.b64decode(_B[k]))");
  for (const b of BUNDLE) {
    lines.push("_w(" + JSON.stringify(b.dst) + "," + JSON.stringify(b.key) + ")");
  }
  lines.push("sys.path.insert(0,'/m5')");
  lines.push("sys.argv=['m5_wasm_runner','--'," + JSON.stringify(session) + "]");
  lines.push("g={'__name__':'__main__','__file__':'/m5/m5_wasm_runner.py'}");
  lines.push("exec(compile(open('/m5/m5_wasm_runner.py').read(),'/m5/m5_wasm_runner.py','exec'),g)");
  return lines.join("\n");
}

window.__m5_status = function () {
  return {
    session: M5.session, booted: M5.booted, error: M5.error,
    done: M5.done || !!M5.outText, hasOut: !!M5.outText,
    markers: Object.keys(M5.markers), nlog: M5.log.length,
  };
};

// Full result pull for the driver. Primary dump = console base64 reassembly
// (race-free). Cross-check = FS.readFile from the browser thread (works post-boot
// on this build); wrapped so a torn-down module after quit can't throw.
window.__m5_result = function () {
  let outFs = null;
  try {
    const m = window.__bwModule;
    if (m && m.FS) outFs = m.FS.readFile("/m5/out.json", { encoding: "utf8" });
  } catch (e) { outFs = null; }
  return {
    session: M5.session, done: M5.done, hasOut: !!M5.outText,
    out: M5.outText, outFs: outFs,
    fsMatches: (M5.outText != null && outFs != null && M5.outText === outFs),
    console: M5.log.join("\n"), markers: M5.markers, error: M5.error,
  };
};

async function boot() {
  const session = M5.session = getSession();
  if (!session) {
    setState("aborted", "no ?session= given");
    record("[m5] ERROR: no ?session= query param");
    M5.error = "no-session";
    return;
  }
  setState("loading", "fetch bundle + load module");
  record("[m5] session=" + session);

  let bundleTexts = {};
  try {
    await Promise.all(BUNDLE.map(async (b) => { bundleTexts[b.key] = await fetchText(b.url); }));
  } catch (e) {
    setState("aborted", "bundle fetch failed");
    record("[m5] bundle fetch error: " + (e && e.message ? e.message : e));
    M5.error = "bundle-fetch";
    return;
  }
  record("[m5] fetched " + BUNDLE.length + " python files");

  const stager = buildStager(bundleTexts, session);
  record("[m5] stager expr " + stager.length + " chars");

  const argv = [
    "--factory-startup",
    "--enable-event-simulate",
    "--log", "operator",
    "--log-level", "debug",
    "--python-expr", stager,
  ];

  const config = {
    arguments: argv,
    canvas: canvasEl,
    locateFile: (p) => BIN_PREFIX + p,
    print: (line) => { console.log(line); record(line); },
    printErr: (line) => { console.error(line); record(line); },
    preRun: [
      (mod) => {
        const env = mod.ENV || (mod.ENV = {});
        Object.assign(env, ENV_VARS);   // JS object only - no FS access here.
        try {
          if (typeof mod._bw_shell_set_display === "function") {
            mod._bw_shell_set_display(BACK_W, BACK_H, 1);
          }
        } catch (_) {}
      },
    ],
    onRuntimeInitialized: () => {
      setState("running", "running main()");
      record("[m5] runtime initialized; entering main()");
    },
    onAbort: (what) => { record("[m5] onAbort: " + what); },
    onExit: (code) => { record("[m5] process exited, code " + code); M5.done = true; },
  };

  try {
    const mod = await createBlenderModule(config);
    window.__bwModule = mod;
    M5.booted = true;
    setState("running", "main loop (WM_main)");
    record("[m5] module resolved; WM_main pumping");
  } catch (e) {
    if (e && typeof e.status === "number") {
      record("[m5] exited (" + e.status + ")");
      M5.done = true; M5.booted = true;
    } else {
      record("[m5] instantiation error: " + (e && e.message ? e.message : e));
      setState("aborted", "instantiation error");
      M5.error = "instantiate";
    }
  }
}

canvasEl.style.width = BACK_W + "px";
canvasEl.style.height = BACK_H + "px";
window.addEventListener("contextmenu", (e) => e.preventDefault(), false);
try { canvasEl.focus({ preventScroll: true }); } catch (_) {}

boot();

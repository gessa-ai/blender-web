// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M5 latency-budget boot shell (browser half). Boots the windowed
// blender_browser wasm module WINDOWED (GHOST-web + WebGPU, no --background)
// with:
//   --factory-startup --enable-event-simulate --log operator --log-level debug
//   --python-expr <STAGER>
// where <STAGER> base64-decodes the ui_simulate DSL (modules package), the probe
// module (m5_latency) and the runner into WasmFS at /m5lat - from INSIDE Python
// on the WM worker (browser-thread FS.writeFile aborts under PROXY_TO_PTHREAD) -
// then execs the runner with sys.argv = [_, '--', <session>, <N>, <SPACING>].
//
// Query: ?session=<mod.func>&n=<count>&spacing=<seconds>.
// The runner emits M5LAT_* markers on fd 2; --log operator emits CLOG "Started"
// lines on fd 2. Both surface here via printErr -> console.error, and the driver
// reads the EMBEDDED wall-clock values (not arrival time), so console jitter is
// immaterial. The visible half is CDP screencast, captured by the driver.

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

const BUNDLE = [
  { key: "runner", dst: "/m5lat/latency_runner.py",       url: "/py/gen/latency_runner.py" },
  { key: "probe",  dst: "/m5lat/m5_latency.py",           url: "/py/gen/m5_latency.py" },
  { key: "ek",     dst: "/m5lat/modules/easy_keys.py",    url: "/py/gen/easy_keys.py" },
  { key: "ui",     dst: "/m5lat/modules/ui_test_utils.py", url: "/py/gen/ui_test_utils.py" },
];

const canvasEl = document.querySelector(CANVAS_SELECTOR);
const stateEl = document.getElementById("state");
const logEl = document.getElementById("log");

const M5 = window.__m5lat = { session: null, booted: false, log: [], done: false, error: null };

function setState(name, label) {
  if (!stateEl) return;
  stateEl.className = "state-" + name;
  stateEl.setAttribute("data-state", name);
  stateEl.textContent = "state: " + label;
}

function b64utf8(text) { return btoa(unescape(encodeURIComponent(text))); }

// Only the lines the driver parses are retained (M5LAT markers + CLOG operator
// "Started" lines + a few boot markers). The dev build floods the console with
// per-shader WGSL source dumps ([bw-r28c-*]); storing those would blow memory.
const KEEP = /^M5LAT_|\| Started bpy\.ops\.|^\[m5lat\]|main loop \(WM_main\)|onAbort|instantiation/;
function record(line) {
  if (typeof line !== "string") line = String(line);
  if (line.indexOf("M5LAT_DONE") === 0 || line.indexOf("M5LAT_EXIT") === 0) M5.done = true;
  if (line.indexOf("M5LAT_FATAL") === 0) M5.error = "fatal";
  if (!KEEP.test(line)) return;
  M5.log.push(line);
  if (logEl && M5.log.length < 8000) { logEl.textContent += line + "\n"; }
}

function q(name, dflt) {
  try { const v = new URLSearchParams(location.search).get(name); return v == null ? dflt : v; }
  catch (e) { return dflt; }
}

async function fetchText(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error("fetch " + url + " -> " + r.status);
  return await r.text();
}

function buildStager(bundleTexts, session, n, spacing) {
  const lines = ["import base64,os,sys", "_B={}"];
  for (const b of BUNDLE) {
    lines.push("_B[" + JSON.stringify(b.key) + "]=" + JSON.stringify(b64utf8(bundleTexts[b.key])));
  }
  lines.push("os.makedirs('/m5lat/modules',exist_ok=True)");
  lines.push("open('/m5lat/modules/__init__.py','w').close()");
  lines.push("def _w(p,k):");
  lines.push("    with open(p,'wb') as f: f.write(base64.b64decode(_B[k]))");
  for (const b of BUNDLE) {
    lines.push("_w(" + JSON.stringify(b.dst) + "," + JSON.stringify(b.key) + ")");
  }
  lines.push("sys.path.insert(0,'/m5lat')");
  lines.push("sys.argv=['latency_runner','--'," + JSON.stringify(session)
    + "," + JSON.stringify(String(n)) + "," + JSON.stringify(String(spacing)) + "]");
  lines.push("g={'__name__':'__main__','__file__':'/m5lat/latency_runner.py'}");
  lines.push("exec(compile(open('/m5lat/latency_runner.py').read(),'/m5lat/latency_runner.py','exec'),g)");
  return lines.join("\n");
}

window.__m5lat_status = function () {
  return { session: M5.session, booted: M5.booted, done: M5.done, error: M5.error, nlog: M5.log.length };
};
window.__m5lat_console = function () { return M5.log.join("\n"); };

async function boot() {
  const session = M5.session = q("session", null);
  const n = q("n", "32");
  const spacing = q("spacing", "0.6");
  if (!session) {
    setState("aborted", "no ?session="); M5.error = "no-session";
    record("[m5lat] ERROR: no ?session="); return;
  }
  setState("loading", "fetch bundle + load module");
  record("[m5lat] session=" + session + " n=" + n + " spacing=" + spacing);

  let bundleTexts = {};
  try {
    await Promise.all(BUNDLE.map(async (b) => { bundleTexts[b.key] = await fetchText(b.url); }));
  } catch (e) {
    setState("aborted", "bundle fetch failed"); M5.error = "bundle-fetch";
    record("[m5lat] bundle fetch error: " + (e && e.message ? e.message : e)); return;
  }
  record("[m5lat] fetched " + BUNDLE.length + " python files");

  const stager = buildStager(bundleTexts, session, n, spacing);
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
        Object.assign(env, ENV_VARS);
        try {
          if (typeof mod._bw_shell_set_display === "function") {
            mod._bw_shell_set_display(BACK_W, BACK_H, 1);
          }
        } catch (_) {}
      },
    ],
    onRuntimeInitialized: () => { setState("running", "running main()"); record("[m5lat] runtime initialized"); },
    onAbort: (what) => { record("[m5lat] onAbort: " + what); },
    onExit: (code) => { record("[m5lat] process exited, code " + code); M5.done = true; },
  };

  try {
    const mod = await createBlenderModule(config);
    window.__bwModule = mod;
    M5.booted = true;
    setState("running", "main loop (WM_main)");
    record("[m5lat] module resolved; WM_main pumping");
  } catch (e) {
    if (e && typeof e.status === "number") {
      record("[m5lat] exited (" + e.status + ")"); M5.done = true; M5.booted = true;
    } else {
      record("[m5lat] instantiation error: " + (e && e.message ? e.message : e));
      setState("aborted", "instantiation error"); M5.error = "instantiate";
    }
  }
}

canvasEl.style.width = BACK_W + "px";
canvasEl.style.height = BACK_H + "px";
window.addEventListener("contextmenu", (e) => e.preventDefault(), false);
try { canvasEl.focus({ preventScroll: true }); } catch (_) {}

boot();

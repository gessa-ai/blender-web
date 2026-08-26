// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M4.pre browser boot shell — boot.js. Instantiates the browser-linked
// `blender_browser` wasm module (built via patches/platform_wasm.cmake's
// blender_web_browser_binary(): -sMODULARIZE=1 -sEXPORT_NAME=createBlenderModule,
// WasmFS + --preload-file payload), runs Blender headless, and mirrors stdout /
// stderr to the on-page <pre> AND the devtools console.
//
// Everything a human might want to tweak lives in the CONFIG block below.

"use strict";

// ===========================================================================
// CONFIG — edit argv / mounts here (the ONE place)
// ===========================================================================

// argv[0] is supplied by the runtime; these are the args after it. Mirrors the
// node boot recipe in notes/m2-python-boot.md.
const ARGV = [
  "--background",
  "--factory-startup",
  "--python-expr",
  "import bpy; print('BPY_OK', bpy.app.version_string, len(bpy.data.objects))",
];

// WasmFS mount points populated by the --preload-file packages baked into the
// binary (see the browser link profile). These MUST match the @<vpath> targets
// there. Exposed to Blender via getenv → the runtime ENV object.
const ENV_VARS = {
  // Umbrella base: appdir resolves the scripts dir as <RESOURCES>/scripts/modules
  // (the BLENDER_SYSTEM_SCRIPTS folder-id does NOT read its own env — see
  // appdir.cc:712 -> get_path_system_ex:568). Our preload mounts scripts/datafiles/
  // python under /bw, so /bw is the base. This is what makes `import bpy` resolve.
  BLENDER_SYSTEM_RESOURCES: "/bw",
  // CPython finds its stdlib at <BLENDER_SYSTEM_PYTHON>/lib/python3.13
  BLENDER_SYSTEM_PYTHON: "/bw/python",
  BLENDER_SYSTEM_SCRIPTS: "/bw/scripts",
  BLENDER_SYSTEM_DATAFILES: "/bw/datafiles",
};

// Where blender_browser.{js,wasm,data} + the pthread worker are served from.
const BIN_PREFIX = "/bin/";

// ===========================================================================
// Shell plumbing (no need to edit below)
// ===========================================================================

const logEl = document.getElementById("log");
const stateEl = document.getElementById("state");
const exitEl = document.getElementById("exit");
const wallEl = document.getElementById("wall");
const dlEl = document.getElementById("dl");
const runBtn = document.getElementById("run");
const argvEl = document.getElementById("argv");

argvEl.textContent = "argv: blender " + ARGV.join(" ");

let t0 = 0;
let finished = false;

function setState(name, label) {
  stateEl.className = "pill state-" + name;
  stateEl.innerHTML = "<b>state:</b> " + label;
}

function append(text, cls) {
  const atBottom =
    logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 40;
  const span = document.createElement("span");
  if (cls) span.className = cls;
  span.textContent = text + "\n";
  logEl.appendChild(span);
  if (atBottom) logEl.scrollTop = logEl.scrollHeight;
}

function elapsed() {
  return ((performance.now() - t0) / 1000).toFixed(2) + " s";
}

function finish(name, label, code) {
  if (finished) return;
  finished = true;
  wallEl.textContent = elapsed();
  exitEl.textContent = code === undefined ? "—" : String(code);
  setState(name, label);
  runBtn.disabled = false;
  runBtn.textContent = "Re-boot (reload)";
  runBtn.onclick = () => location.reload();
}

async function boot() {
  runBtn.disabled = true;
  finished = false;
  logEl.textContent = "";
  exitEl.textContent = "—";
  wallEl.textContent = "—";
  dlEl.textContent = "fetching…";
  setState("loading", "loading module");
  append("[shell] instantiating blender_browser (WasmFS + preload)…", "sys");
  append("[shell] argv: blender " + ARGV.join(" "), "sys");
  t0 = performance.now();

  const config = {
    arguments: ARGV,
    locateFile: (path) => BIN_PREFIX + path,
    print: (line) => {
      console.log(line);
      append(line);
    },
    printErr: (line) => {
      console.error(line);
      append(line, "err");
    },
    // callRuntimeCallbacks() invokes each preRun cb with the module instance;
    // ENV is exported (-sEXPORTED_RUNTIME_METHODS=ENV) so we can seed it here,
    // before main() runs. This is the browser equivalent of the node recipe's
    // BLENDER_SYSTEM_* environment.
    preRun: [
      (mod) => {
        const env = mod.ENV || (mod.ENV = {});
        Object.assign(env, ENV_VARS);
        append(
          "[shell] ENV " +
            Object.entries(ENV_VARS)
              .map(([k, v]) => k + "=" + v)
              .join("  "),
          "sys"
        );
      },
    ],
    setStatus: (s) => {
      if (s && /([\d.]+)\/([\d.]+)/.test(s)) dlEl.textContent = s;
      else if (s) dlEl.textContent = s;
    },
    onRuntimeInitialized: () => {
      dlEl.textContent = "loaded";
      setState("running", "running main()");
      append("[shell] runtime initialized; entering main()…", "sys");
    },
    onAbort: (what) => {
      append("[shell] onAbort: " + what, "err");
      finish("aborted", "aborted", undefined);
    },
    onExit: (code) => {
      append("[shell] process exited, code " + code, "sys");
      finish(code === 0 ? "exited" : "aborted", "exited (" + code + ")", code);
    },
  };

  try {
    await createBlenderModule(config);
  } catch (e) {
    // A non-zero exit throws an ExitStatus; treat that as a normal finish.
    if (e && typeof e.status === "number") {
      finish(
        e.status === 0 ? "exited" : "aborted",
        "exited (" + e.status + ")",
        e.status
      );
    } else {
      append("[shell] instantiation error: " + (e && e.message ? e.message : e), "err");
      finish("aborted", "instantiation error", undefined);
    }
  }
}

runBtn.onclick = boot;

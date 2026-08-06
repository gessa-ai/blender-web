// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M4 windowed browser boot shell — boot-windowed.js. Boots the browser-linked
// `blender_browser` wasm module in the WINDOWED profile (WITH_HEADLESS=OFF,
// WITH_GHOST_WEB + WITH_WEBGPU_BACKEND): drops `--background`, so creator.cc takes
// the `else` arm (WM_init_splash_on_startup + WM_main) and drives the GHOST-web
// window + WebGPU context onto a real <canvas>. Mirrors stdout/stderr to the
// on-page <pre> AND devtools console for boot characterization.
//
// Contrast with the headless boot.js (proven BPY_OK path). Design refs:
// notes/m4-windowed-boot-recon.md, notes/m4-integration.md.

"use strict";

// ===========================================================================
// CONFIG — edit argv / mounts here (the ONE place)
// ===========================================================================

// Windowed argv: NO `--background` (that is the whole point — take the windowed
// arm of creator.cc:643). `--factory-startup` loads the factory startup.blend
// (Layout workspace, default cube/camera/light) — the M4 first-pixels target.
const ARGV = [
  "--factory-startup",
];

// DEV-AFFORDANCE (M4.T20 capture rig, r23): optionally append a `--python-expr`
// to the boot argv so the verification rig can drive Blender's own screenshot
// path (bpy.ops.screen.screenshot via a bpy.app.timer) without a rebuild. The
// creator FINAL arg pass runs the expr straight-line before WM_main (creator.cc:
// 622), so a timer registered here fires INSIDE the main loop after first pixels
// (surface configured) — the only place WM_window_pixels_read has content. NOT
// shipped behaviour: only active when the rig sets `window.__BW_PYEXPR` (or the
// `?pyexpr=` URL param) before pressing Boot. Empty by default = pristine argv.
function bootPythonExpr() {
  try {
    if (typeof window.__BW_PYEXPR === "string" && window.__BW_PYEXPR.length) {
      return window.__BW_PYEXPR;
    }
    const u = new URLSearchParams(location.search);
    const p = u.get("pyexpr");
    if (p) return p;
  } catch (e) {}
  return null;
}

// The GHOST-web layer targets this canvas via emscripten_*_canvas_element_size()
// and the emdawnwebgpu EmscriptenSurfaceSourceCanvasHTMLSelector (default "#canvas"
// in GHOST_ContextWGPUWeb / GHOST_WindowWeb).
const CANVAS_SELECTOR = "#canvas";

// WasmFS mount points populated by the --preload-file packages baked into the
// binary. Identical to the headless boot — the windowed payload inventory is a
// superset that is already fully covered (recon §2).
const ENV_VARS = {
  BLENDER_SYSTEM_RESOURCES: "/bw",
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
const canvasEl = document.querySelector(CANVAS_SELECTOR);

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
  append("[shell] instantiating blender_browser (WINDOWED: no --background)…", "sys");
  append("[shell] argv: blender " + ARGV.join(" "), "sys");
  append("[shell] canvas: " + CANVAS_SELECTOR + " " +
    (canvasEl ? canvasEl.width + "x" + canvasEl.height : "(MISSING!)"), "sys");
  t0 = performance.now();

  const pyexpr = bootPythonExpr();
  const bootArgv = pyexpr ? ARGV.concat(["--python-expr", pyexpr]) : ARGV.slice();
  if (pyexpr) {
    append("[shell] DEV capture hook: appending --python-expr (" +
      pyexpr.length + " chars)", "sys");
  }

  const config = {
    arguments: bootArgv,
    // Emscripten binds the default GL/WebGPU canvas from Module.canvas; the
    // GHOST-web layer also drives it by the "#canvas" selector.
    canvas: canvasEl,
    locateFile: (path) => BIN_PREFIX + path,
    print: (line) => {
      console.log(line);
      append(line);
    },
    printErr: (line) => {
      console.error(line);
      append(line, "err");
    },
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
      if (s) dlEl.textContent = s;
    },
    onRuntimeInitialized: () => {
      dlEl.textContent = "loaded";
      setState("running", "running main() — windowed");
      append("[shell] runtime initialized; entering main() (WM_init → WM_main)…", "sys");
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
    const mod = await createBlenderModule(config);
    // Expose the runtime module so the verification rig can pull capture output
    // out of WasmFS from the main thread (mod.FS.readFile proxies to the shared
    // WasmFS the WM worker writes into — proven in notes/gpu-r22-cube-blocker.md).
    window.__bwModule = mod;
    // In the windowed profile WM_main is an emscripten_set_main_loop that keeps
    // running — createBlenderModule resolves once the runtime is up, NOT on quit.
    append("[shell] module resolved; WM_main loop should now be pumping.", "sys");
    setState("running", "main loop (WM_main)");
  } catch (e) {
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

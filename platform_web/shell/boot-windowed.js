// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// M4 windowed browser boot shell - boot-windowed.js, NATIVE-APP posture.
//
// Boots the browser-linked `blender_browser` wasm module in the WINDOWED profile
// (WITH_HEADLESS=OFF, WITH_GHOST_WEB + WITH_WEBGPU_BACKEND): drops `--background`,
// so creator.cc takes the `else` arm (WM_init_splash_on_startup + WM_main) and
// drives the GHOST-web window + WebGPU context onto a real <canvas>.
//
// What changed for the native feel (see notes/m4-shell-native.md for sources):
//   1. Auto-boot on load - no Boot button, no visible status pills / log panel.
//   2. Full-window canvas at a devicePixelRatio-correct backing store; window
//      resize keeps it sharp (GHOST reconfigures the WebGPU surface on resize).
//   3. A centred loading indicator that vanishes when first pixels composite.
//   4. Native input hardening: no HTML context menu (right-clicks reach Blender),
//      no page scroll / selection / pinch-zoom, focus-gated key capture.
//
// PRESERVED development/gate contract (the M4 rig depends on ALL of these):
//   (a) `?pyexpr=` and `?args=` URL dev hooks behave exactly as before in the
//       development shell. Public bundle assembly fail-closes them below.
//   (b) `window.__bwModule` is exposed after module init.
//   (c) `?gate=WxH` renders the canvas at EXACTLY that CSS+backing size (DPR
//       forced to 1), centred on black, no loading UI - for the golden capture.
//   (d) A DOM-visible "main loop (WM_main)" state marker is still emitted (the
//       hidden #state element) so existing waitForFunction rigs still match.

"use strict";

// ===========================================================================
// CONFIG - edit argv / mounts here (the ONE place)
// ===========================================================================

// Windowed argv: NO `--background` (that is the whole point - take the windowed
// arm of creator.cc:643). `--factory-startup` loads the factory startup.blend
// (Layout workspace, default cube/camera/light) - the M4 first-pixels target.
const ARGV = [
  "--factory-startup",
];

// The GHOST-web layer targets this canvas via emscripten_*_canvas_element_size()
// and the emdawnwebgpu EmscriptenSurfaceSourceCanvasHTMLSelector (default
// "#canvas" in GHOST_ContextWGPUWeb / GHOST_WindowWeb).
const CANVAS_SELECTOR = "#canvas";

// WasmFS mount points populated by the --preload-file packages baked into the
// binary. Identical to the headless boot - the windowed payload inventory is a
// superset that is already fully covered (recon §2).
const ENV_VARS = {
  BLENDER_SYSTEM_RESOURCES: "/bw",
  BLENDER_SYSTEM_PYTHON: "/bw/python",
  BLENDER_SYSTEM_SCRIPTS: "/bw/scripts",
  BLENDER_SYSTEM_DATAFILES: "/bw/datafiles",

  // M7 project store (notes/m7-store-design.md §1b/§1c, joint proof
  // notes/m7-store-wired.md). The persistent OPFS mount at /projects is created
  // pre-main on the WM worker by wgpu-preinit-worker.js -> bw_mount_opfs. These
  // two vars ROUTE Blender's own default user paths onto that mount so userpref,
  // recent-files, startup.blend, autosave, quit-recovery and user .blend saves
  // all persist across a page reload:
  //   BLENDER_USER_RESOURCES -> config/, datafiles/, scripts/, extensions/
  //                             (appdir.cc get_path_user_ex checks it FIRST)
  //   TMPDIR -> BKE_tempdir_base() = autosave <pid>_autosave.blend + quit.blend
  //             (a SEPARATE seam from config/; tempfile.cc reads TMPDIR).
  // Per-kind overrides (BLENDER_USER_CONFIG, ...) exist if finer control is
  // wanted. Both dirs are pre-created by the mount so the check_is_dir read-path
  // accepts them; write paths create missing sub-dirs themselves.
  BLENDER_USER_RESOURCES: "/projects",
  TMPDIR: "/projects/.recovery",
};

// Where blender_browser.{js,wasm,data} + the pthread worker are served from.
const BIN_PREFIX = "/bin/";

// ===========================================================================
// DEV HOOKS - PRESERVED contract (a): `?pyexpr=` and `?args=`
// ===========================================================================

// Development source defaults ON for local rigs. The public staged-bundle
// assembler rewrites this exact declaration to false in its COPY only. Keep it
// a literal so packaging can fail closed if the expected seam ever moves.
const BW_ALLOW_QUERY_DEV_HOOKS = true;
window.__bwDevHooksAllowed = BW_ALLOW_QUERY_DEV_HOOKS;

// `?pyexpr=` (or window.__BW_PYEXPR): append a `--python-expr` to the boot argv
// so the verification rig can drive Blender's own screenshot path
// (bpy.ops.screen.screenshot via a bpy.app.timer) without a rebuild. The creator
// FINAL arg pass runs the expr straight-line before WM_main (creator.cc:622), so
// a timer registered here fires INSIDE the main loop after first pixels. NOT
// shipped behaviour: empty by default = pristine argv.
function bootPythonExpr() {
  if (!BW_ALLOW_QUERY_DEV_HOOKS) return null;
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

// `?args=` (or window.__BW_ARGS): append raw whitespace-separated argv entries
// BEFORE the pyexpr - for boots that need Blender's own diagnostics
// (`--debug-gpu`, `--log "gpu.*" --log-level 4`, ...) without a rebuild. NOT
// shipped behaviour: empty by default. Quoting: `%20` separates args; there is
// deliberately NO shell-style quote handling - `--log gpu.*` is two entries.
function bootExtraArgs() {
  if (!BW_ALLOW_QUERY_DEV_HOOKS) return [];
  try {
    if (Array.isArray(window.__BW_ARGS) && window.__BW_ARGS.length) {
      return window.__BW_ARGS.slice();
    }
    const u = new URLSearchParams(location.search);
    const a = u.get("args");
    if (a) return a.split(/\s+/).filter(Boolean);
  } catch (e) {}
  return [];
}

// PRESERVED contract (c): `?gate=WxH` (e.g. ?gate=1280x720) - DPR-independent
// exact-size capture mode. DPR is forced to 1 for the backing store so the
// golden comparator captures the canvas at exactly WxH regardless of the test
// browser's deviceScaleFactor. Returns {w,h} or null.
function gateMode() {
  if (!BW_ALLOW_QUERY_DEV_HOOKS) return null;
  try {
    const u = new URLSearchParams(location.search);
    let g = u.get("gate");
    if (!g && typeof window.__BW_GATE === "string") g = window.__BW_GATE;
    if (!g) return null;
    const m = /^(\d+)x(\d+)$/i.exec(g.trim());
    if (!m) return null;
    const w = parseInt(m[1], 10);
    const h = parseInt(m[2], 10);
    if (w > 0 && h > 0) return { w, h };
  } catch (e) {}
  return null;
}

const GATE = gateMode();

// ghost-keepalive: idle main-loop keepalive control. The windowed WM_main is a
// present-gated rAF loop on the WM worker that STALLS at idle (notes/m7b-files-io.md §4);
// the GHOST keepalive (bw_shell_set_keepalive, consumed on the worker in processEvents)
// switches it to setTimeout scheduling so events / bpy.app.timers / GPU MapAsync futures
// keep resolving at idle WITHOUT forcing a present (no GPU burn at idle).
//   ?keepalive=0  -> OFF: leave the loop on rAF = the pre-fix, stalls-at-idle A/B baseline.
//   ?keepalive=1  -> ON  (also the default when the param is absent).
//   ?ka_active=<ms> / ?ka_idle=<ms> -> optional fast / idle interval overrides (experiments).
// Default ON so the idle stall is fixed out of the box. Returns {enabled, active, idle}.
function keepaliveConfig() {
  const cfg = { enabled: 1, active: 0, idle: 0 };
  if (!BW_ALLOW_QUERY_DEV_HOOKS) return cfg;
  try {
    const u = new URLSearchParams(location.search);
    let k = u.get("keepalive");
    if (k == null && typeof window.__BW_KEEPALIVE === "string") k = window.__BW_KEEPALIVE;
    if (k != null) {
      const s = String(k).trim().toLowerCase();
      cfg.enabled = (s === "0" || s === "off" || s === "false") ? 0 : 1;
    }
    const a = parseInt(u.get("ka_active"), 10);
    if (a > 0) cfg.active = a;
    const i = parseInt(u.get("ka_idle"), 10);
    if (i > 0) cfg.idle = i;
  } catch (e) {}
  return cfg;
}

const KEEPALIVE = keepaliveConfig();
window.__bwKeepaliveConfig = Object.freeze({...KEEPALIVE});

// ===========================================================================
// DOM handles (hidden diagnostics preserve the boot-windowed.js + rig contract)
// ===========================================================================

const canvasEl = document.querySelector(CANVAS_SELECTOR);
const loaderEl = document.getElementById("loader");
const progressEl = document.getElementById("bw-progress");
const fillEl = document.getElementById("bw-fill");
const pctEl = document.getElementById("bw-pct");

// Hidden diagnostics - may be absent in stripped rigs, so every access is guarded.
const logEl = document.getElementById("log");
const stateEl = document.getElementById("state");
const exitEl = document.getElementById("exit");
const wallEl = document.getElementById("wall");
const dlEl = document.getElementById("dl");
const runBtn = document.getElementById("run");
const argvEl = document.getElementById("argv");

if (argvEl) argvEl.textContent = "argv: blender " + ARGV.join(" ");

let t0 = 0;
let finished = false;
let booted = false;
let firstPixels = false;

// ---------------------------------------------------------------------------
// Diagnostics plumbing - writes to the HIDDEN elements only. The state marker
// text is contract (d): keep "main loop (WM_main)" byte-identical.
// ---------------------------------------------------------------------------

function setState(name, label) {
  if (!stateEl) return;
  stateEl.className = "state-" + name;
  stateEl.setAttribute("data-state", name);
  stateEl.textContent = "state: " + label;
}

function append(text, cls) {
  if (!logEl) return;
  const span = document.createElement("span");
  if (cls) span.className = cls;
  span.textContent = text + "\n";
  logEl.appendChild(span);
}

function elapsed() {
  return ((performance.now() - t0) / 1000).toFixed(2) + " s";
}

function finish(name, label, code) {
  if (finished) return;
  finished = true;
  if (wallEl) wallEl.textContent = elapsed();
  if (exitEl) exitEl.textContent = code === undefined ? "-" : String(code);
  setState(name, label);
  // A hard failure should surface, not sit behind a spinner forever.
  if (name === "aborted") {
    if (pctEl) pctEl.textContent = "boot failed - see console";
    if (loaderEl) loaderEl.setAttribute("aria-busy", "false");
    if (progressEl) progressEl.setAttribute("aria-valuetext", "boot failed");
  }
}

// ---------------------------------------------------------------------------
// Loading UI - progress via Emscripten setStatus, dismissed on first pixels.
// ---------------------------------------------------------------------------

function setProgress(fraction) {
  if (!fillEl) return;
  const pct = Math.max(0, Math.min(100, Math.round(fraction * 100)));
  fillEl.style.width = pct + "%";
  if (progressEl) progressEl.setAttribute("aria-valuenow", String(pct));
  if (pctEl) pctEl.textContent = pct + "%";
}

// Emscripten's default setStatus emits strings like "Downloading data... (x/y)".
function onStatus(s) {
  if (dlEl && s) dlEl.textContent = s;
  if (!s) return;
  const m = /\((\d+)\/(\d+)\)/.exec(s);
  if (m) {
    const cur = parseInt(m[1], 10);
    const tot = parseInt(m[2], 10);
    if (tot > 0) {
      setProgress(cur / tot);
      return;
    }
  }
  // Non-numeric statuses keep the last truthful byte-derived percentage. The
  // ring supplies activity without turning the progress bar indeterminate.
}

let loaderGoneTimer = 0;
function hideLoader() {
  if (!loaderEl || loaderEl.classList.contains("bw-hidden")) return;
  loaderEl.setAttribute("aria-busy", "false");
  loaderEl.classList.add("bw-hidden");
  // Drop it from the box tree after the fade so it can never eat input.
  loaderGoneTimer = setTimeout(() => loaderEl.classList.add("bw-gone"), 600);
}

// First pixels = the canvas has composited. GHOST prints "presentBackbuffer
// frame 0" (C printf) at the first present; that is the single reliable draw
// signal (notes/gpu-r24-present-seam.md). We also arm a settle fallback off the
// WM_main marker in case the print format shifts.
function noteFirstPixels(reason) {
  if (firstPixels) return;
  firstPixels = true;
  append("[shell] first pixels (" + reason + ") - dismissing loader", "sys");
  hideLoader();
}

function scanForPixels(line) {
  if (firstPixels || typeof line !== "string") return;
  if (line.indexOf("presentBackbuffer") !== -1) {
    noteFirstPixels("presentBackbuffer");
  }
}

// ===========================================================================
// Canvas sizing - full-window @ devicePixelRatio, or exact gate size.
// ===========================================================================

// Set the drawing-buffer (backing store). In the normal path this is
// cssPx * devicePixelRatio so the image is sharp on HiDPI; in gate mode it is
// exactly WxH with DPR forced to 1. GHOST reads this extent via
// emscripten_get_canvas_element_size and adopts it as the window client size
// (GHOST_WindowWeb ctor) / configures the WebGPU surface to match.
function computeBacking() {
  if (GATE) {
    return { w: GATE.w, h: GATE.h, css: { w: GATE.w, h: GATE.h }, dpr: 1 };
  }
  const dpr = window.devicePixelRatio || 1;
  const cssW = Math.max(1, window.innerWidth);
  const cssH = Math.max(1, window.innerHeight);
  return {
    w: Math.max(1, Math.round(cssW * dpr)),
    h: Math.max(1, Math.round(cssH * dpr)),
    css: { w: cssW, h: cssH },
    dpr,
  };
}

// Apply sizing to the DOM canvas BEFORE the module boots (before the canvas is
// transferred to the WM worker as an OffscreenCanvas - after transfer the
// main-thread element can no longer be resized directly). This is what makes the
// very first frame sharp and full-window.
function applyInitialSizing() {
  const b = computeBacking();
  canvasEl.width = b.w;
  canvasEl.height = b.h;
  if (GATE) {
    document.body.classList.add("bw-gate");
    canvasEl.style.width = b.css.w + "px";
    canvasEl.style.height = b.css.h + "px";
  }
  return b;
}

// After boot the backing store lives on the WM worker's OffscreenCanvas, so ONLY that
// worker may resize it (emscripten_set_canvas_element_size is legal on the canvas-owning
// thread). The main thread cannot proxy that call - the build exports neither `ccall` nor
// `_emscripten_set_canvas_element_size` (EXPORTED_RUNTIME_METHODS=ENV,FS,callMain). Instead
// GHOST exposes `bw_shell_set_display(backingW, backingH, dpr)` (EMSCRIPTEN_KEEPALIVE, so it
// lands in the module exports without touching the link flags): it stores the target extent
// + DPR into shared wasm memory, and the WM worker applies them in its per-tick poll
// (GHOST_SystemWeb::processEvents -> set canvas size + reconfigure surface + WindowSize
// event). This carries BOTH fixes: live resize (bug #1) AND the real DPR for UI scale
// (bug #2). Returns true if the export was reachable.
let displayPushSupported = null; // null=unknown, true/false once probed
let lastPushedW = 0, lastPushedH = 0, lastPushedDpr = 0;
function pushDisplayToWorker(mod, w, h, dpr) {
  mod = mod || window.__bwModule;
  if (!mod) return false;
  if (typeof mod._bw_shell_set_display !== "function") {
    if (displayPushSupported === null) {
      displayPushSupported = false;
      append("[shell] bw_shell_set_display export unavailable - resize/DPR degrade to " +
        "boot-time backing (see notes/m4-ghost-resize-dpr.md)", "sys");
    }
    return false;
  }
  try {
    mod._bw_shell_set_display(w | 0, h | 0, dpr);
    displayPushSupported = true;
    lastPushedW = w; lastPushedH = h; lastPushedDpr = dpr;
    return true;
  } catch (e) {
    append("[shell] bw_shell_set_display threw: " + (e && e.message ? e.message : e), "err");
    return false;
  }
}

// ghost-keepalive: push the resolved keepalive config to the WM worker. Safe from preRun on
// the main thread (relaxed atomic stores; constant-initialized on the C side). Mode-agnostic
// (called in gate and non-gate alike - it only changes loop SCHEDULING, never argv, size, or
// pixels, so every preserved contract is untouched). Guarded so an older binary without the
// export degrades to its built-in default (ON). Returns true if the export was reachable.
let keepalivePushSupported = null; // null=unknown, true/false once probed
function pushKeepaliveToWorker(mod) {
  mod = mod || window.__bwModule;
  if (!mod) return false;
  if (typeof mod._bw_shell_set_keepalive !== "function") {
    if (keepalivePushSupported === null) {
      keepalivePushSupported = false;
      append("[shell] bw_shell_set_keepalive export unavailable - idle keepalive uses the " +
        "binary's built-in default (see notes/ghost-keepalive.md)", "sys");
    }
    return false;
  }
  try {
    mod._bw_shell_set_keepalive(KEEPALIVE.enabled | 0, KEEPALIVE.active | 0, KEEPALIVE.idle | 0);
    keepalivePushSupported = true;
    return true;
  } catch (e) {
    append("[shell] bw_shell_set_keepalive threw: " + (e && e.message ? e.message : e), "err");
    return false;
  }
}

// Window resize handler. Compute the new PHYSICAL backing extent (innerW/H * DPR, DPR read
// fresh each time so moving the window between displays of different density is handled) and
// post it to the WM worker. rAF-coalesced. No-op in gate mode (fixed size, DPR 1).
let resizeRaf = 0;
function onWindowResize() {
  if (GATE || !booted) return;
  if (resizeRaf) return;
  resizeRaf = requestAnimationFrame(() => {
    resizeRaf = 0;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round(window.innerWidth * dpr));
    const h = Math.max(1, Math.round(window.innerHeight * dpr));
    if (w === lastPushedW && h === lastPushedH && dpr === lastPushedDpr) return;
    pushDisplayToWorker(null, w, h, dpr);
  });
}

// ===========================================================================
// Native input hardening (applied immediately, independent of the module).
// Sources are catalogued in notes/m4-shell-native.md.
// ===========================================================================

// Keys the browser would steal from a canvas app. We preventDefault ONLY when
// the canvas owns focus, and NEVER stopPropagation - Emscripten/GHOST's own
// listeners still receive the key, so Blender gets it; we only suppress the
// BROWSER default (scroll, quick-find, Save dialog, focus traversal).
const SCROLL_KEYS = new Set([
  " ", "Spacebar", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
  "PageUp", "PageDown", "Home", "End",
]);
function isDevReserved(e) {
  // Never intercept devtools / reload during development.
  if (e.key === "F12") return true;
  const meta = e.metaKey || e.ctrlKey;
  const k = (e.key || "").toLowerCase();
  if (meta && k === "r") return true;                 // reload / hard reload
  if (meta && e.altKey && (k === "i" || k === "j")) return true;    // devtools (mac)
  if (meta && e.shiftKey && (k === "i" || k === "j" || k === "c")) return true; // devtools
  return false;
}
function canvasHasFocus() {
  return document.activeElement === canvasEl ||
         document.pointerLockElement === canvasEl;
}
function onKeyDown(e) {
  if (isDevReserved(e)) return;
  if (!canvasHasFocus()) return; // gate the aggressive capture behind focus
  const meta = e.metaKey || e.ctrlKey;
  const isFnKey = /^F([1-9]|1[01])$/.test(e.key); // F1..F11 (F12 handled above)
  const isSave = meta && (e.key === "s" || e.key === "S");
  const isQuickFind = e.key === "'" || e.key === "/"; // Firefox quick-find keys
  const isTab = e.key === "Tab";
  const isBackspace = e.key === "Backspace";
  if (isFnKey || isSave || isQuickFind || isTab || isBackspace ||
      SCROLL_KEYS.has(e.key)) {
    e.preventDefault(); // NOT stopPropagation - Blender still receives it
  }
}

function installNativeHardening() {
  // (1) No HTML context menu anywhere - right-clicks still generate the
  // mousedown/up (button 2) that GHOST reads, so Blender opens its OWN menu.
  window.addEventListener("contextmenu", (e) => e.preventDefault(), false);

  // (2) Focus-gated key capture (see onKeyDown). Capture phase.
  window.addEventListener("keydown", onKeyDown, true);

  // (3) Pinch-zoom: trackpad pinch arrives as wheel+ctrlKey; block the browser
  // page-zoom. Normal wheel is left for GHOST (viewport zoom). passive:false so
  // preventDefault is honoured.
  window.addEventListener("wheel", (e) => {
    if (e.ctrlKey) e.preventDefault();
  }, { passive: false });

  // (4) Safari gesture events (pinch/rotate) - suppress page zoom.
  ["gesturestart", "gesturechange", "gestureend"].forEach((t) => {
    window.addEventListener(t, (e) => e.preventDefault(), { passive: false });
  });

  // (5) Belt-and-braces: kill iOS double-tap zoom (paired with touch-action:none
  // + user-scalable=no). Two taps < 300ms apart -> preventDefault the second.
  let lastTouchEnd = 0;
  document.addEventListener("touchend", (e) => {
    const now = Date.now();
    if (now - lastTouchEnd <= 300) e.preventDefault();
    lastTouchEnd = now;
  }, { passive: false });

  // (6) Pointer capture on press so a drag that leaves the window keeps
  // delivering move/up to the canvas. Also (re)focus the canvas so the key
  // capture above engages. Guarded - never throws the boot.
  canvasEl.addEventListener("pointerdown", (e) => {
    try { canvasEl.setPointerCapture(e.pointerId); } catch (_) {}
    if (document.activeElement !== canvasEl) {
      try { canvasEl.focus({ preventScroll: true }); } catch (_) { try { canvasEl.focus(); } catch (__) {} }
    }
  }, true);

  // (7) Take initial focus so keyboard input goes to Blender from the first
  // frame (autofocus is unreliable when a script steals focus during boot).
  try { canvasEl.focus({ preventScroll: true }); } catch (_) {}
}

// ===========================================================================
// Boot - auto-runs on load; idempotent so a rig clicking #run is a no-op.
// ===========================================================================

async function boot() {
  if (booted) return;
  booted = true;
  finished = false;
  if (logEl) logEl.textContent = "";
  setState("loading", "loading module");
  setIndeterminate("loading");
  append("[shell] instantiating blender_browser (WINDOWED: no --background)…", "sys");
  append("[shell] argv: blender " + ARGV.join(" "), "sys");
  append("[shell] canvas: " + CANVAS_SELECTOR + " " +
    (canvasEl ? canvasEl.width + "x" + canvasEl.height : "(MISSING!)") +
    (GATE ? " (GATE " + GATE.w + "x" + GATE.h + ", DPR forced 1)" : ""), "sys");
  t0 = performance.now();

  const pyexpr = bootPythonExpr();
  const extraArgs = bootExtraArgs();
  let bootArgv = ARGV.concat(extraArgs);
  // M7b FILE BRIDGE: arm the WM-worker file-bridge daemon as its OWN isolated
  // --python-expr (creator handles each occurrence independently, so this cannot
  // collide with a user ?pyexpr, which is appended AFTER). This is what makes
  // .blend drag-drop + FSA open/save work post-boot (notes/m7b-files-io.md).
  // SKIPPED in gate mode so the golden-capture argv stays byte-pristine.
  if (!GATE && window.BWFileBridge) {
    bootArgv = bootArgv.concat(["--python-expr", window.BWFileBridge.daemonPyexpr()]);
    append("[shell] file-bridge: arming WM-worker daemon (drag-drop + open/save)", "sys");
  }
  if (pyexpr) bootArgv = bootArgv.concat(["--python-expr", pyexpr]);
  if (extraArgs.length) {
    append("[shell] DEV args hook: appending " + JSON.stringify(extraArgs), "sys");
  }
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
      scanForPixels(line);
      if (window.BWFileBridge) window.BWFileBridge.noteConsoleLine(line);
    },
    printErr: (line) => {
      console.error(line);
      append(line, "err");
      scanForPixels(line);
      if (window.BWFileBridge) window.BWFileBridge.noteConsoleLine(line);
    },
    preRun: [
      (mod) => {
        const env = mod.ENV || (mod.ENV = {});
        Object.assign(env, ENV_VARS);
        append("[shell] ENV " +
          Object.entries(ENV_VARS).map(([k, v]) => k + "=" + v).join("  "), "sys");
        // Seed the real devicePixelRatio + initial backing extent BEFORE main() runs on the
        // WM worker (preRun executes on the main thread ahead of the proxied main), so the
        // very first getDPIHint / getClientBounds / WindowSize during WM_init already sees
        // the true DPR - the UI boots at native scale, not tiny-then-corrected. The atomics
        // are constant-initialized, so this is safe even before __wasm_call_ctors. Gate mode
        // keeps DPR 1 (default), so no seed is needed there.
        if (!GATE) {
          const b = computeBacking();
          pushDisplayToWorker(mod, b.w, b.h, b.dpr);
          append("[shell] DPR seed " + b.dpr + " backing " + b.w + "x" + b.h, "sys");
        }
        // ghost-keepalive: seed the keepalive config BEFORE main() so the WM worker's very
        // first processEvents tick already switches the loop to setTimeout (no reliance on
        // rAF, so it never stalls). Seeded in every mode - scheduling-only, no contract touched.
        pushKeepaliveToWorker(mod);
        append("[shell] keepalive " + (KEEPALIVE.enabled ? "ON" : "OFF (rAF baseline)") +
          (KEEPALIVE.active ? " active=" + KEEPALIVE.active + "ms" : "") +
          (KEEPALIVE.idle ? " idle=" + KEEPALIVE.idle + "ms" : ""), "sys");
      },
    ],
    setStatus: onStatus,
    onRuntimeInitialized: () => {
      if (dlEl) dlEl.textContent = "loaded";
      setState("running", "running main() - windowed");
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
    // PRESERVED contract (b): expose the runtime module so the verification rig
    // can pull capture output out of WasmFS from the main thread.
    window.__bwModule = mod;
    // In the windowed profile WM_main is an emscripten_set_main_loop that keeps
    // running - createBlenderModule resolves once the runtime is up, NOT on quit.
    append("[shell] module resolved; WM_main loop should now be pumping.", "sys");

    // M7b FILE BRIDGE: attach drag-drop + FSA open/save now that __bwModule (and
    // thus mod.FS) exists on the browser thread. No-op in gate mode (daemon not
    // armed there). Guarded so a bridge fault never breaks the boot.
    if (!GATE && window.BWFileBridge) {
      try {
        window.BWFileBridge.attach(mod, { canvas: canvasEl, log: (m) => append(m, "sys") });
      } catch (e) {
        append("[shell] file-bridge attach failed: " + (e && e.message ? e.message : e), "err");
      }
    }
    // PRESERVED contract (d): the DOM-visible "main loop (WM_main)" marker.
    setState("running", "main loop (WM_main)");

    // Now that the OffscreenCanvas is owned by the worker, wire live resize
    // (no-op in gate mode) and arm the first-pixels settle fallback.
    if (!GATE) {
      // Safety re-push now that exports are certainly attached (in case the preRun seed
      // raced module setup). Any push bumps the shared generation, so the worker's poll
      // re-applies DPR + backing and emits a fresh WindowSize -> WM_window_dpi_set_userdef,
      // self-healing the UI scale even if the pre-window seed was missed.
      {
        const b = computeBacking();
        pushDisplayToWorker(mod, b.w, b.h, b.dpr);
      }
      window.addEventListener("resize", onWindowResize, true);
      try {
        const ro = new ResizeObserver(onWindowResize);
        ro.observe(document.documentElement);
      } catch (_) {}
      // devicePixelRatio can change WITHOUT a resize event (e.g. dragging the window to a
      // display of different density, or an OS zoom change). Re-evaluate on the matching
      // media query so UI scale + backing track it.
      try {
        const mq = window.matchMedia("(resolution: " + (window.devicePixelRatio || 1) + "dppx)");
        if (mq && typeof mq.addEventListener === "function") {
          mq.addEventListener("change", onWindowResize);
        }
      } catch (_) {}
      // Fallback: if presentBackbuffer is never seen (format drift), dismiss the
      // loader a short settle after WM_main so the black boot screen can't stick.
      setTimeout(() => noteFirstPixels("WM_main settle"), 2500);
    } else {
      // Gate mode: never show loading UI once booted.
      if (loaderEl) { loaderEl.classList.add("bw-hidden", "bw-gone"); }
    }
  } catch (e) {
    if (e && typeof e.status === "number") {
      finish(e.status === 0 ? "exited" : "aborted",
        "exited (" + e.status + ")", e.status);
    } else {
      append("[shell] instantiation error: " + (e && e.message ? e.message : e), "err");
      finish("aborted", "instantiation error", undefined);
    }
  }
}

// ---------------------------------------------------------------------------
// Wire-up: harden input, size the canvas, then auto-boot.
// ---------------------------------------------------------------------------

// Gate mode hides the loading UI from the very first paint.
if (GATE && loaderEl) loaderEl.classList.add("bw-gone");

installNativeHardening();
applyInitialSizing();

// M7b: request OPFS persistence and report the eviction posture at boot (open item
// 6.4, first half). Browser-API only (independent of the wasm module), so fire it
// immediately; it logs one honest console line. Skipped in gate mode.
if (!GATE && window.BWFileBridge) {
  try { window.BWFileBridge.requestPersistence(); } catch (_) {}
}

// PRESERVED: a rig that clicks #run still works - boot() is idempotent.
if (runBtn) runBtn.onclick = boot;

// Auto-boot immediately (DOM is already parsed - scripts are at end of <body>).
boot();

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
// First-script diagnostics plus WM-worker cursor bridge. No layout/branding behavior.
"use strict";

(() => {
  const records = [];
  function text(value) {
    if (value === undefined || value === null) return null;
    try { return String(value); } catch (_) { return "<unprintable>"; }
  }
  function append(type, event) {
    const reason = type === "unhandledrejection" ? event.reason : null;
    records.push(Object.freeze({
      sequence: records.length + 1,
      type,
      message: type === "error" ? text(event.message) : text(reason),
      source: type === "error" ? text(event.filename) : null,
      line: type === "error" && Number.isInteger(event.lineno) ? event.lineno : null,
      column: type === "error" && Number.isInteger(event.colno) ? event.colno : null,
      reasonName: reason && typeof reason === "object" ? text(reason.name) : null,
    }));
  }
  const api = Object.freeze({
    schema: 1,
    installedBeforeProductScripts: true,
    count: () => records.length,
    snapshot: () => records.map((record) => ({...record})),
  });
  Object.defineProperty(window, "__bwEarlyDiagnostics", {
    value: api, writable: false, configurable: false, enumerable: false,
  });
  window.addEventListener("error", (event) => append("error", event));
  window.addEventListener("unhandledrejection", (event) => append("unhandledrejection", event));
})();

// A transferred OffscreenCanvas has no DOM style, while Blender's GHOST window runs on the
// PROXY_TO_PTHREAD worker. The worker therefore publishes cursor state through shared wasm
// atomics; this main-thread loop applies it to the original HTMLCanvasElement.
(() => {
  // Numeric order is bound to GHOST_TStandardCursor by cursor_bridge_contract.py.
  // GHOST_kStandardCursorCustom is deliberately excluded: arbitrary bitmap/mask cursors
  // have no lossless CSS equivalent and GHOST_WindowWeb reports them unsupported.
  const CSS_CURSOR_BY_GHOST_SHAPE = Object.freeze([
    "default", "default", "default", "help", "not-allowed", "help", "wait", "text",
    "crosshair", "crosshair", "crosshair", "crosshair", "crosshair", "n-resize", "s-resize",
    "ns-resize", "ew-resize", "crosshair", "crosshair", "crosshair", "zoom-in", "zoom-out",
    "move", "all-scroll", "ns-resize", "ew-resize", "not-allowed", "ns-resize", "ew-resize",
    "n-resize", "s-resize", "w-resize", "e-resize", "nw-resize", "ne-resize", "se-resize",
    "sw-resize", "copy", "w-resize", "e-resize", "ew-resize", "grab", "grabbing", "pointer",
    "crosshair", "move",
  ]);

  let lastGeneration = null;
  let lastSnapshot = null;

  function cssForShape(shape) {
    return Number.isInteger(shape) && shape >= 0 && shape < CSS_CURSOR_BY_GHOST_SHAPE.length ?
      CSS_CURSOR_BY_GHOST_SHAPE[shape] : "default";
  }

  function applyPublishedCursor() {
    const mod = window.__bwModule;
    if (!mod ||
        typeof mod._bw_shell_cursor_generation !== "function" ||
        typeof mod._bw_shell_cursor_shape !== "function" ||
        typeof mod._bw_shell_cursor_visible !== "function") {
      return false;
    }

    const generation = Number(mod._bw_shell_cursor_generation());
    if (!Number.isInteger(generation) || generation === lastGeneration) {
      return false;
    }
    const canvas = typeof document !== "undefined" ? document.getElementById("canvas") : null;
    if (!canvas || !canvas.style) {
      return false;
    }

    const shape = Number(mod._bw_shell_cursor_shape());
    const visible = Number(mod._bw_shell_cursor_visible()) !== 0;
    const css = visible ? cssForShape(shape) : "none";
    canvas.style.cursor = css;
    lastGeneration = generation;
    lastSnapshot = Object.freeze({generation, shape, visible, css});
    return true;
  }

  function frame() {
    try {
      applyPublishedCursor();
    } catch (_) {
      // Runtime startup/teardown can transiently invalidate an export. Retry next frame;
      // cursor styling must never become a boot-fatal diagnostics error.
    }
    window.requestAnimationFrame(frame);
  }

  const api = Object.freeze({
    schema: 1,
    standardShapeCount: CSS_CURSOR_BY_GHOST_SHAPE.length,
    cssForShape,
    snapshot: () => lastSnapshot && {...lastSnapshot},
  });
  Object.defineProperty(window, "__bwCursorBridge", {
    value: api, writable: false, configurable: false, enumerable: false,
  });
  window.requestAnimationFrame(frame);
})();

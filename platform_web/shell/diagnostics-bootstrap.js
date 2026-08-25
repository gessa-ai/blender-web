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
  // The final Custom sentinel is handled separately: GHOST publishes owned RGBA/XBM
  // pixels synchronously, this main-thread bridge rasterizes them to a PNG data URL,
  // and the ordinary release generation applies that image plus its exact hotspot.
  const CSS_CURSOR_BY_GHOST_SHAPE = Object.freeze([
    "default", "default", "default", "help", "not-allowed", "help", "wait", "text",
    "crosshair", "crosshair", "crosshair", "crosshair", "crosshair", "n-resize", "s-resize",
    "ns-resize", "ew-resize", "crosshair", "crosshair", "crosshair", "zoom-in", "zoom-out",
    "move", "all-scroll", "ns-resize", "ew-resize", "not-allowed", "ns-resize", "ew-resize",
    "n-resize", "s-resize", "w-resize", "e-resize", "nw-resize", "ne-resize", "se-resize",
    "sw-resize", "copy", "w-resize", "e-resize", "ew-resize", "grab", "grabbing", "pointer",
    "crosshair", "move",
  ]);
  const CUSTOM_CURSOR_SHAPE = CSS_CURSOR_BY_GHOST_SHAPE.length;
  // Chromium and Firefox reject CSS image cursors larger than 128x128. Blender's
  // ordinary SVG/time cursors are smaller; reject larger inputs instead of claiming
  // success for a browser cursor that will be ignored.
  const CUSTOM_CURSOR_MAX_DIMENSION = 128;

  let lastGeneration = null;
  let lastSnapshot = null;
  let customCursorCss = null;

  function heapSpanIsValid(heap, pointer, length) {
    return heap && typeof heap.length === "number" &&
      Number.isSafeInteger(pointer) && pointer > 0 &&
      Number.isSafeInteger(length) && length > 0 &&
      pointer <= heap.length && length <= heap.length - pointer;
  }

  function installCustomCursor(heap, bitmapPointer, maskPointer, width, height, hotX, hotY) {
    try {
      if (![bitmapPointer, maskPointer, width, height, hotX, hotY].every(Number.isSafeInteger) ||
          width <= 0 || height <= 0 ||
          width > CUSTOM_CURSOR_MAX_DIMENSION || height > CUSTOM_CURSOR_MAX_DIMENSION ||
          hotX < 0 || hotY < 0 || hotX >= width || hotY >= height) {
        return false;
      }

      const rowBytes = Math.ceil(width / 8);
      const sourceBytes = maskPointer === 0 ? width * height * 4 : rowBytes * height;
      if (!heapSpanIsValid(heap, bitmapPointer, sourceBytes) ||
          (maskPointer !== 0 && !heapSpanIsValid(heap, maskPointer, sourceBytes))) {
        return false;
      }

      const raster = typeof document !== "undefined" ? document.createElement("canvas") : null;
      if (!raster) {
        return false;
      }
      raster.width = width;
      raster.height = height;
      const context = raster.getContext("2d");
      if (!context) {
        return false;
      }
      const image = context.createImageData(width, height);
      if (maskPointer === 0) {
        image.data.set(heap.subarray(bitmapPointer, bitmapPointer + sourceBytes));
      }
      else {
        for (let y = 0; y < height; y++) {
          for (let x = 0; x < width; x++) {
            const bit = 1 << (x & 7);
            const sourceIndex = y * rowBytes + (x >> 3);
            const targetIndex = (y * width + x) * 4;
            const opaque = (heap[maskPointer + sourceIndex] & bit) !== 0;
            const white = (heap[bitmapPointer + sourceIndex] & bit) !== 0;
            image.data[targetIndex + 0] = white ? 255 : 0;
            image.data[targetIndex + 1] = white ? 255 : 0;
            image.data[targetIndex + 2] = white ? 255 : 0;
            image.data[targetIndex + 3] = opaque ? 255 : 0;
          }
        }
      }
      context.putImageData(image, 0, 0);
      const dataUrl = raster.toDataURL("image/png");
      if (typeof dataUrl !== "string" || !dataUrl.startsWith("data:image/png")) {
        return false;
      }
      customCursorCss = `url(${JSON.stringify(dataUrl)}) ${hotX} ${hotY}, default`;
      return true;
    }
    catch (_) {
      return false;
    }
  }

  function cssForShape(shape) {
    if (shape === CUSTOM_CURSOR_SHAPE && customCursorCss) {
      return customCursorCss;
    }
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
    const canvas = mod.canvas && mod.canvas.style ? mod.canvas :
      (typeof document !== "undefined" ? document.getElementById("canvas") : null);
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
    schema: 2,
    standardShapeCount: CSS_CURSOR_BY_GHOST_SHAPE.length,
    customShape: CUSTOM_CURSOR_SHAPE,
    customMaxDimension: CUSTOM_CURSOR_MAX_DIMENSION,
    installCustomCursor,
    cssForShape,
    snapshot: () => lastSnapshot && {...lastSnapshot},
  });
  Object.defineProperty(window, "__bwCursorBridge", {
    value: api, writable: false, configurable: false, enumerable: false,
  });
  window.requestAnimationFrame(frame);
})();

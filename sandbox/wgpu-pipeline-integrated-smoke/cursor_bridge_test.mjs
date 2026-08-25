#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const sourcePath = process.argv[2];
if (!sourcePath) {
  throw new Error("usage: cursor_bridge_test.mjs DIAGNOSTICS_BOOTSTRAP_JS");
}

const callbacks = [];
const canvas = {style: {cursor: "sentinel"}};
let canvasAvailable = true;
let lastRaster = null;
const windowObject = {
  addEventListener() {},
  requestAnimationFrame(callback) { callbacks.push(callback); },
};
const context = {
  window: windowObject,
  document: {
    getElementById(id) {
      assert.equal(id, "canvas");
      return canvasAvailable ? canvas : null;
    },
    createElement(tag) {
      assert.equal(tag, "canvas");
      let imageData = null;
      return {
        width: 0,
        height: 0,
        getContext(type) {
          assert.equal(type, "2d");
          return {
            createImageData(width, height) {
              return {data: new Uint8ClampedArray(width * height * 4)};
            },
            putImageData(value, x, y) {
              assert.equal(x, 0);
              assert.equal(y, 0);
              imageData = value;
            },
          };
        },
        toDataURL(type) {
          assert.equal(type, "image/png");
          lastRaster = {
            width: this.width,
            height: this.height,
            pixels: Array.from(imageData.data),
          };
          return "data:image/png;base64,Y3VzdG9tLWN1cnNvcg==";
        },
      };
    },
  },
};
vm.runInNewContext(fs.readFileSync(sourcePath, "utf8"), context, {filename: sourcePath});

assert.equal(windowObject.__bwCursorBridge.schema, 2);
assert.equal(windowObject.__bwCursorBridge.standardShapeCount, 46);
assert.equal(windowObject.__bwCursorBridge.customShape, 46);
assert.equal(windowObject.__bwCursorBridge.customMaxDimension, 128);
assert.equal(callbacks.length, 1);

const expectedCss = [
  "default", "default", "default", "help", "not-allowed", "help", "wait", "text",
  "crosshair", "crosshair", "crosshair", "crosshair", "crosshair", "n-resize", "s-resize",
  "ns-resize", "ew-resize", "crosshair", "crosshair", "crosshair", "zoom-in", "zoom-out",
  "move", "all-scroll", "ns-resize", "ew-resize", "not-allowed", "ns-resize", "ew-resize",
  "n-resize", "s-resize", "w-resize", "e-resize", "nw-resize", "ne-resize", "se-resize",
  "sw-resize", "copy", "w-resize", "e-resize", "ew-resize", "grab", "grabbing", "pointer",
  "crosshair", "move",
];
assert.deepEqual(
  Array.from({length: 46}, (_, shape) => windowObject.__bwCursorBridge.cssForShape(shape)),
  expectedCss,
);
assert.equal(windowObject.__bwCursorBridge.cssForShape(-1), "default");
assert.equal(windowObject.__bwCursorBridge.cssForShape(46), "default");
assert.equal(windowObject.__bwCursorBridge.cssForShape(Number.NaN), "default");

function frame() {
  assert.ok(callbacks.length > 0, "cursor bridge stopped polling");
  callbacks.shift()();
  assert.equal(callbacks.length, 1, "cursor bridge must schedule exactly one successor frame");
}

// The first script runs before the modularized runtime exists and must wait quietly.
frame();
assert.equal(canvas.style.cursor, "sentinel");

let generation = 1;
let shape = 0;
let visible = 1;
windowObject.__bwModule = {
  _bw_shell_cursor_generation: () => generation,
  _bw_shell_cursor_shape: () => shape,
  _bw_shell_cursor_visible: () => visible,
};
frame();
assert.equal(canvas.style.cursor, "default");
assert.deepEqual(JSON.parse(JSON.stringify(windowObject.__bwCursorBridge.snapshot())), {
  generation: 1, shape: 0, visible: true, css: "default",
});

// State is consumed only after the release-generation changes.
shape = 7;
frame();
assert.equal(canvas.style.cursor, "default");
generation += 1;
frame();
assert.equal(canvas.style.cursor, "text");

visible = 0;
generation += 1;
frame();
assert.equal(canvas.style.cursor, "none");
shape = 42;
generation += 1;
frame();
assert.equal(canvas.style.cursor, "none");
visible = 1;
generation += 1;
frame();
assert.equal(canvas.style.cursor, "grabbing");

// Do not consume a generation until the real DOM canvas is available.
canvasAvailable = false;
shape = 20;
generation += 1;
frame();
assert.equal(canvas.style.cursor, "grabbing");
canvasAvailable = true;
frame();
assert.equal(canvas.style.cursor, "zoom-in");

// Missing/throwing runtime exports are non-fatal and recover on a later frame.
const healthyModule = windowObject.__bwModule;
windowObject.__bwModule = {_bw_shell_cursor_generation: () => generation + 1};
frame();
assert.equal(canvas.style.cursor, "zoom-in");
windowObject.__bwModule = {
  ...healthyModule,
  _bw_shell_cursor_generation: () => { throw new Error("transient"); },
};
frame();
assert.equal(canvas.style.cursor, "zoom-in");
shape = 43;
generation += 1;
windowObject.__bwModule = healthyModule;
frame();
assert.equal(canvas.style.cursor, "pointer");

// RGBA cursors are copied before their Wasm caller returns, rasterized exactly,
// and published with the caller's hotspot on the next release generation.
const heap = new Uint8Array(64);
const rgba = [
  255, 0, 0, 255, 0, 255, 0, 128,
  0, 0, 255, 64, 255, 255, 255, 0,
];
heap.set(rgba, 8);
assert.equal(windowObject.__bwCursorBridge.installCustomCursor(heap, 8, 0, 2, 2, 1, 0), true);
assert.deepEqual(lastRaster, {width: 2, height: 2, pixels: rgba});
shape = windowObject.__bwCursorBridge.customShape;
generation += 1;
frame();
const rgbaCss = 'url("data:image/png;base64,Y3VzdG9tLWN1cnNvcg==") 1 0, default';
assert.equal(canvas.style.cursor, rgbaCss);

// Legacy XBM source/mask rows use low-bit-first GHOST semantics: transparent
// mask=0, black source=0, white source=1.
heap.set([0b01, 0b10], 32);
heap.set([0b11, 0b10], 40);
assert.equal(windowObject.__bwCursorBridge.installCustomCursor(heap, 32, 40, 2, 2, 0, 1), true);
assert.deepEqual(lastRaster, {
  width: 2,
  height: 2,
  pixels: [
    255, 255, 255, 255, 0, 0, 0, 255,
    0, 0, 0, 0, 255, 255, 255, 255,
  ],
});
generation += 1;
frame();
const xbmCss = 'url("data:image/png;base64,Y3VzdG9tLWN1cnNvcg==") 0 1, default';
assert.equal(canvas.style.cursor, xbmCss);

// Invalid geometry and out-of-range heap spans fail without replacing the last
// valid custom cursor. Visibility toggles retain that custom image.
assert.equal(windowObject.__bwCursorBridge.installCustomCursor(heap, 8, 0, 129, 1, 0, 0), false);
assert.equal(windowObject.__bwCursorBridge.installCustomCursor(heap, 63, 0, 2, 2, 0, 0), false);
visible = 0;
generation += 1;
frame();
assert.equal(canvas.style.cursor, "none");
visible = 1;
generation += 1;
frame();
assert.equal(canvas.style.cursor, xbmCss);

console.log("CURSOR_BRIDGE_CONTRACT PASS standard=46 custom=rgba,xbm invalid=closed visibility=hidden,visible recovery=module,canvas,error");

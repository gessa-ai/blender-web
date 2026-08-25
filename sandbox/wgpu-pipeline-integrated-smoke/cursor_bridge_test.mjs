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
  },
};
vm.runInNewContext(fs.readFileSync(sourcePath, "utf8"), context, {filename: sourcePath});

assert.equal(windowObject.__bwCursorBridge.schema, 1);
assert.equal(windowObject.__bwCursorBridge.standardShapeCount, 46);
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

console.log("CURSOR_BRIDGE_CONTRACT PASS standard=46 visibility=hidden,visible recovery=module,canvas,error");

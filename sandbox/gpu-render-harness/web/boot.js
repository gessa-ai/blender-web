// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Boot the GPU render harness. The wasm side calls globalThis.wgpuReport(line) for
// each step; we mirror to #log + console, expose a machine-readable array, and stamp
// document.title so a headless verifier can read progress via --dump-dom.
"use strict";

const logEl = document.getElementById("log");
globalThis.gpuResults = [];

globalThis.wgpuReport = function (line) {
  globalThis.gpuResults.push(line);
  const span = document.createElement("span");
  if (/\bOK\b|PASS/.test(line)) span.className = "ok";
  else if (/FAIL|null/.test(line)) span.className = "bad";
  else if (line.startsWith("[")) span.className = "sys";
  span.textContent = line + "\n";
  logEl.appendChild(span);
  console.log("[gpu] " + line);
  document.title = "GPU:" + globalThis.gpuResults.length + ":" + line.slice(0, 60);
  if (/RENDER (PASS|note)|FAIL|GPU_texture_read/.test(line)) globalThis.gpuDone = line;
};

createGpuHarness({
  canvas: document.getElementById("gpucanvas"),
  print: (l) => console.log(l),
  printErr: (l) => console.error(l),
}).then(() => {
  console.log("[boot] module instantiated");
}).catch((e) => {
  globalThis.wgpuReport("BOOT FAIL: " + (e && e.message ? e.message : e));
});

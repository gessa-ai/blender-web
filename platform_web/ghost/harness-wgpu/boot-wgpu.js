// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Boot the in-tab WebGPU harness. globalThis.wgpuReport is called from the wasm side
// with each step's result; we mirror to the page + console and expose a machine-
// readable result for the headless verifier.
"use strict";

const logEl = document.getElementById("log");
globalThis.wgpuResults = [];

globalThis.wgpuReport = function (line) {
  globalThis.wgpuResults.push(line);
  const span = document.createElement("span");
  if (/\bOK\b|PASS/.test(line)) span.className = "ok";
  else if (/FAIL/.test(line)) span.className = "bad";
  else if (line.startsWith("[")) span.className = "sys";
  span.textContent = line + "\n";
  logEl.appendChild(span);
  logEl.scrollTop = logEl.scrollHeight;
  console.log("[wgpu] " + line);
  if (/READBACK (PASS|FAIL)/.test(line)) {
    globalThis.wgpuDone = line.includes("PASS") ? "PASS" : "FAIL";
  }
};

createWgpuTest({
  canvas: document.getElementById("gpucanvas"),
  print: (l) => console.log(l),
  printErr: (l) => console.error(l),
});

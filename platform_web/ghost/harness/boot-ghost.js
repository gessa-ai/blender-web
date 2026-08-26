// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
//
// Boot the GHOST-web event harness. globalThis.ghostLog is called from the wasm
// side (EM_JS harness_log) with each decoded GHOST event; we also mirror the wasm
// stdout via print/printErr.
"use strict";

const logEl = document.getElementById("log");

globalThis.ghostLog = function (line) {
  const atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 40;
  const span = document.createElement("span");
  if (line.startsWith("[")) span.className = "sys";
  span.textContent = line + "\n";
  logEl.appendChild(span);
  if (atBottom) logEl.scrollTop = logEl.scrollHeight;
  // Also to devtools console for scripted verification.
  console.log(line);
};

document.getElementById("clear").onclick = () => {
  logEl.textContent = "";
};

const canvas = document.getElementById("blender-canvas");
canvas.addEventListener("click", () => canvas.focus());

let ghostModule = null;
document.getElementById("fullscreen").onclick = () => {
  if (!ghostModule) return;
  ghostModule._ghost_harness_request_window_state(document.fullscreenElement ? 0 : 3);
};

const moduleOptions = {
  canvas,
  // Events reach the page via the wasm-side EM_JS harness_log -> ghostLog. Route
  // plain stdout/stderr to the console only, so page lines aren't duplicated.
  print: (l) => console.log(l),
  printErr: (l) => console.error(l),
  onRuntimeInitialized: () => {
    ghostModule = moduleOptions;
    globalThis.ghostModule = moduleOptions;
    globalThis.__bwModule = moduleOptions;
  },
};

createGhostTest(moduleOptions).then((module) => {
  ghostModule = module;
  globalThis.ghostModule = module;
  globalThis.__bwModule = module;
  canvas.focus();
});

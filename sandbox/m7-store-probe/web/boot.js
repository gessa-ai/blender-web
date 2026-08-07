// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Boot the M7 project-store prototype. The wasm side (main() on the
// PROXY_TO_PTHREAD worker) reports via window.storeReport(). ?fresh=1 wipes OPFS
// first for a clean "first load"; reload without it to verify persistence across a
// fresh wasm instance (proves the .blend bytes + config/recovery artifacts came from
// OPFS storage, not stale in-RAM state).
"use strict";

const logEl = document.getElementById("log");
globalThis.storeResults = [];

globalThis.storeReport = function (line) {
  globalThis.storeResults.push(line);
  const span = document.createElement("span");
  if (/\bOK\b|SURVIVED OK/.test(line)) span.className = "ok";
  else if (/FAIL|UNEXPECTED|null|\bNO\b/.test(line)) span.className = "bad";
  else if (/FRESH|WARN|PARTIAL/.test(line)) span.className = "warn";
  else if (line.startsWith("[") || line.startsWith("    ") || /^DIRLIST /.test(line)) span.className = "sys";
  span.textContent = line + "\n";
  logEl.appendChild(span);
  console.log("[store] " + line);
  document.title = "M7STORE:" + globalThis.storeResults.length + ":" + line.slice(0, 60);
  if (/PROBE-DONE/.test(line)) globalThis.storeDone = true;
};

async function maybeReset() {
  if (!new URLSearchParams(location.search).has("fresh")) return;
  try {
    const root = await navigator.storage.getDirectory();
    const names = [];
    for await (const name of root.keys()) names.push(name);
    for (const name of names) await root.removeEntry(name, { recursive: true });
    globalThis.storeReport("[js] OPFS cleared (fresh=1): removed " + names.length + " entr(ies)");
  } catch (e) {
    globalThis.storeReport("[js] OPFS reset error: " + e.name + ": " + e.message);
  }
}

globalThis.__startStoreProbe = async function () {
  globalThis.storeReport("[js] boot: crossOriginIsolated=" + globalThis.crossOriginIsolated +
    " opfs=" + (navigator.storage && !!navigator.storage.getDirectory));
  await maybeReset();
  globalThis.storeReport("[js] instantiating wasm store probe (WasmFS+OPFS, PROXY_TO_PTHREAD)...");
  createStoreProbe({
    print: (l) => console.log(l),
    printErr: (l) => console.error(l),
  }).catch((e) => globalThis.storeReport("BOOT FAIL: " + (e && e.message ? e.message : e)));
};

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Boot the M7-prep OPFS probe. The wasm side (main() on the PROXY_TO_PTHREAD
// worker) reports via window.opfsReport(). Before instantiating the module we run
// the *web-platform* half of test 3 that cannot be done from wasm: prove that an
// OPFS FileSystemSyncAccessHandle can be created in a dedicated Worker but is
// REFUSED on the browser main thread (the "sync access handles are worker-only"
// coupling, GOAL.md Emscripten posture / ADR-003). Non-blocking: the main-thread
// attempt is a rejected async call, so the tab never hangs.
"use strict";

const logEl = document.getElementById("log");
globalThis.opfsResults = [];

globalThis.opfsReport = function (line) {
  globalThis.opfsResults.push(line);
  const span = document.createElement("span");
  if (/\bOK\b|SURVIVED|BLOCKED \(expected\)/.test(line)) span.className = "ok";
  else if (/FAIL|UNEXPECTED|null/.test(line)) span.className = "bad";
  else if (/FRESH|WARN|note/.test(line)) span.className = "warn";
  else if (line.startsWith("[")) span.className = "sys";
  span.textContent = line + "\n";
  logEl.appendChild(span);
  console.log("[opfs] " + line);
  document.title = "OPFS:" + globalThis.opfsResults.length + ":" + line.slice(0, 60);
  if (/PROBE-DONE/.test(line)) globalThis.opfsDone = true;
};

async function maybeReset() {
  if (!new URLSearchParams(location.search).has("fresh")) return;
  try {
    const root = await navigator.storage.getDirectory();
    const names = [];
    for await (const name of root.keys()) names.push(name);
    for (const name of names) await root.removeEntry(name, { recursive: true });
    globalThis.opfsReport("[js] OPFS cleared (fresh=1): removed " + names.length + " entr(ies)");
  } catch (e) {
    globalThis.opfsReport("[js] OPFS reset error: " + e.name + ": " + e.message);
  }
}

// Test 3b — the browser MAIN thread must NOT be able to open a sync access handle.
async function mainThreadSyncTest() {
  try {
    const root = await navigator.storage.getDirectory();
    const fh = await root.getFileHandle("mainthread_probe.bin", { create: true });
    const h = await fh.createSyncAccessHandle();
    h.close();
    globalThis.opfsReport("MAINTHREAD-SYNC UNEXPECTED-OK: window created a sync access handle");
  } catch (e) {
    globalThis.opfsReport(
      "MAINTHREAD-SYNC BLOCKED (expected): " + e.name + ": " + String(e.message).slice(0, 110));
  }
}

// Test 3a (positive control, raw web platform) — a dedicated Worker CAN open a
// sync access handle and do synchronous read/write. This is the mechanism WasmFS's
// OPFS backend uses under the hood on our PROXY_TO_PTHREAD worker.
function workerControlTest() {
  return new Promise((resolve) => {
    const src = `self.onmessage = async () => {
      try {
        const root = await navigator.storage.getDirectory();
        const fh = await root.getFileHandle('worker_ctrl.bin', { create: true });
        const h = await fh.createSyncAccessHandle();
        const w = new Uint8Array([1,2,3,4,5,6,7,8]);
        h.write(w, { at: 0 }); h.flush();
        const r = new Uint8Array(8); h.read(r, { at: 0 }); h.close();
        const ok = w.every((v,i)=>v===r[i]);
        postMessage({ ok });
      } catch (e) { postMessage({ error: e.name + ': ' + e.message }); }
    };`;
    let url;
    try {
      url = URL.createObjectURL(new Blob([src], { type: "text/javascript" }));
      const w = new Worker(url);
      const done = (msg) => { try { w.terminate(); URL.revokeObjectURL(url); } catch (_) {} resolve(); globalThis.opfsReport(msg); };
      w.onmessage = (ev) => {
        if (ev.data && ev.data.ok) done("WORKER-SYNC OK: dedicated Worker created a sync access handle, sync write+read round-tripped");
        else done("WORKER-SYNC FAIL: " + (ev.data && ev.data.error ? ev.data.error : "no ok"));
      };
      w.onerror = (e) => done("WORKER-SYNC FAIL: worker error " + (e.message || e.type));
      w.postMessage("go");
    } catch (e) {
      if (url) try { URL.revokeObjectURL(url); } catch (_) {}
      globalThis.opfsReport("WORKER-SYNC FAIL: " + e.name + ": " + e.message);
      resolve();
    }
  });
}

globalThis.__startOpfsProbe = async function () {
  globalThis.opfsReport("[js] boot: crossOriginIsolated=" + globalThis.crossOriginIsolated +
    " opfs=" + (navigator.storage && !!navigator.storage.getDirectory));
  await maybeReset();
  await mainThreadSyncTest();
  await workerControlTest();
  globalThis.opfsReport("[js] instantiating wasm probe (WasmFS+OPFS, PROXY_TO_PTHREAD)...");
  createOpfsProbe({
    print: (l) => console.log(l),
    printErr: (l) => console.error(l),
  }).catch((e) => globalThis.opfsReport("BOOT FAIL: " + (e && e.message ? e.message : e)));
};

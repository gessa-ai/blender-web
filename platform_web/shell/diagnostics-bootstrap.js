// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later
// First-script diagnostics contract for release evidence. No layout/branding behavior.
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

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

import assert from "node:assert/strict";
import { classifyLivePreinitDiagnostic } from "./live_preinit_contract.mjs";

const good = {
  state: "running",
  module: true,
  loader: "running",
  secondTickSettled: true,
  startupSettleMs: 15000,
  first: { ticks: 10, presents: 2, sampledAtMs: 1000 },
  second: { ticks: 16, presents: 2, sampledAtMs: 2250 },
  inputStartedAtMs: 2300,
  trustedInputIssued: true,
  afterInput: { ticks: 19, presents: 3, sampledAtMs: 2500 },
  counters: {
    deviceReady: 1,
    presentationReady: 1,
    presentationFailed: 0,
    stage1Failed: 0,
    presentableImportFailed: 0,
    presentSubmissionRejected: 0,
    presentTransactionRejected: 0,
    deviceLost: 0,
    pageErrors: 0,
    adapterFallback: "true",
    presentationValidation: "fallback-diagnostic",
  },
};

assert.equal(classifyLivePreinitDiagnostic(good).accepted, true);

const mutations = [
  ["aborted", (v) => { v.state = "aborted"; }],
  ["missing module", (v) => { v.module = false; }],
  ["boot failed", (v) => { v.loader = "boot failed - see console"; }],
  ["missing tick export", (v) => { v.first.ticks = null; }],
  ["second tick did not settle", (v) => { v.secondTickSettled = false; }],
  ["startup settle late", (v) => { v.startupSettleMs = 60001; }],
  ["entry tick only", (v) => { v.first.ticks = 1; }],
  ["idle tick frozen", (v) => { v.second.ticks = v.first.ticks; }],
  ["idle sample too short", (v) => { v.second.sampledAtMs = 1200; }],
  ["idle sample too long", (v) => { v.second.sampledAtMs = 5000; }],
  ["trusted input absent", (v) => { v.trustedInputIssued = false; }],
  ["input tick frozen", (v) => { v.afterInput.ticks = v.second.ticks; }],
  ["input redraw absent", (v) => { v.afterInput.presents = v.second.presents; }],
  ["input round trip late", (v) => { v.afterInput.sampledAtMs = 9000; }],
  ["device lost", (v) => { v.counters.deviceLost = 1; }],
  ["duplicate device", (v) => { v.counters.deviceReady = 2; }],
  ["presentation absent", (v) => { v.counters.presentationReady = 0; }],
  ["stage one failure", (v) => { v.counters.stage1Failed = 1; }],
  ["import failure", (v) => { v.counters.presentableImportFailed = 1; }],
  ["present submission rejected", (v) => {
    v.counters.presentSubmissionRejected = 1;
  }],
  ["present transaction rejected", (v) => { v.counters.presentTransactionRejected = 1; }],
  ["page error", (v) => { v.counters.pageErrors = 1; }],
  ["fallback mislabeled strict", (v) => { v.counters.presentationValidation = "strict"; }],
  ["hardware mislabeled fallback", (v) => {
    v.counters.adapterFallback = "false";
    v.counters.presentationValidation = "fallback-diagnostic";
  }],
];

for (const [name, mutate] of mutations) {
  const candidate = structuredClone(good);
  mutate(candidate);
  assert.equal(classifyLivePreinitDiagnostic(candidate).accepted, false, name);
}

const strict = structuredClone(good);
strict.counters.adapterFallback = "false";
strict.counters.presentationValidation = "strict";
assert.equal(classifyLivePreinitDiagnostic(strict).accepted, false);

console.log(`CONTRACT ghost_preinit_live_classifier PASS positive=1 negative=${mutations.length + 1}`);

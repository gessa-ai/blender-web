// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-2.0-or-later

export const LIVE_IDLE_SAMPLE_MIN_MS = 750;
export const LIVE_IDLE_SAMPLE_MAX_MS = 3000;
export const LIVE_INPUT_ROUND_TRIP_MAX_MS = 6000;
export const LIVE_STARTUP_SETTLE_MAX_MS = 60000;

export function classifyLivePreinitDiagnostic(observation) {
  const failures = [];
  const first = observation.first || {};
  const second = observation.second || {};
  const afterInput = observation.afterInput || {};
  const counters = observation.counters || {};

  if (observation.state !== "running") failures.push(`state=${observation.state}`);
  if (!observation.module) failures.push("module=missing");
  if (observation.loader && observation.loader.includes("boot failed")) {
    failures.push("loader=boot-failed");
  }

  for (const [name, sample] of [["first", first], ["second", second], ["afterInput", afterInput]]) {
    if (!Number.isFinite(sample.ticks)) failures.push(`${name}.ticks=missing`);
    if (!Number.isFinite(sample.presents)) failures.push(`${name}.presents=missing`);
  }

  if (!observation.secondTickSettled) failures.push("secondTickSettled=0");
  if (!(observation.startupSettleMs >= 0 &&
        observation.startupSettleMs <= LIVE_STARTUP_SETTLE_MAX_MS)) {
    failures.push(`startupSettleMs=${observation.startupSettleMs}`);
  }
  if (!(first.ticks >= 2)) failures.push(`first.ticks=${first.ticks}`);

  const idleElapsedMs = second.sampledAtMs - first.sampledAtMs;
  if (!(idleElapsedMs >= LIVE_IDLE_SAMPLE_MIN_MS && idleElapsedMs <= LIVE_IDLE_SAMPLE_MAX_MS)) {
    failures.push(`idleSampleMs=${idleElapsedMs}`);
  }
  if (!(second.ticks > first.ticks)) {
    failures.push(`idleTickDelta=${second.ticks - first.ticks}`);
  }

  const inputElapsedMs = afterInput.sampledAtMs - observation.inputStartedAtMs;
  if (!(inputElapsedMs >= 0 && inputElapsedMs <= LIVE_INPUT_ROUND_TRIP_MAX_MS)) {
    failures.push(`inputRoundTripMs=${inputElapsedMs}`);
  }
  if (!observation.trustedInputIssued) failures.push("trustedInputIssued=0");
  if (!(afterInput.ticks > second.ticks)) {
    failures.push(`inputTickDelta=${afterInput.ticks - second.ticks}`);
  }
  if (!(afterInput.presents > second.presents)) {
    failures.push(`inputPresentDelta=${afterInput.presents - second.presents}`);
  }

  if (counters.deviceReady !== 1) failures.push(`deviceReady=${counters.deviceReady}`);
  if (counters.presentationReady !== 1) {
    failures.push(`presentationReady=${counters.presentationReady}`);
  }
  if (counters.presentationFailed !== 0) {
    failures.push(`presentationFailed=${counters.presentationFailed}`);
  }
  if (counters.stage1Failed !== 0) failures.push(`stage1Failed=${counters.stage1Failed}`);
  if (counters.presentableImportFailed !== 0) {
    failures.push(`presentableImportFailed=${counters.presentableImportFailed}`);
  }
  if (counters.deviceLost !== 0) failures.push(`deviceLost=${counters.deviceLost}`);
  if (counters.pageErrors !== 0) failures.push(`pageErrors=${counters.pageErrors}`);

  if (counters.adapterFallback !== "true") {
    failures.push(`adapterFallback=${counters.adapterFallback}`);
  }
  if (counters.presentationValidation !== "fallback-diagnostic") {
    failures.push(`presentationValidation=${counters.presentationValidation}`);
  }

  return {
    accepted: failures.length === 0,
    failures,
    startupSettleMs: observation.startupSettleMs,
    idleElapsedMs,
    idleTickDelta: second.ticks - first.ticks,
    inputElapsedMs,
    inputTickDelta: afterInput.ticks - second.ticks,
    inputPresentDelta: afterInput.presents - second.presents,
    adapterMode: "fallback-software",
  };
}

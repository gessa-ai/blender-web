// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
/** Fail-closed live identity binding for the split runtime browser proof. */

import { createHash } from 'node:crypto';
import { lstatSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');

function liveIdentity(path) {
  const stat = lstatSync(path);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error(`not an exact regular file: ${path}`);
  const bytes = readFileSync(path);
  return { path, bytes: stat.size, sha256: sha256(bytes) };
}

function requireRowIdentity(label, row, live, requireBytes = true) {
  if (!row || typeof row !== 'object') throw new Error(`${label} receipt row absent`);
  if ((requireBytes && row.bytes !== live.bytes) || row.sha256 !== live.sha256) {
    throw new Error(`${label} live identity mismatch`);
  }
}

export function validateSplitArtifactIdentity(split, bin) {
  const exactBin = resolve(bin);
  const expected = {
    primary: resolve(exactBin, 'blender_browser.wasm'),
    secondary: resolve(exactBin, 'blender_browser.deferred.wasm'),
    js: resolve(exactBin, 'blender_browser.js'),
  };
  for (const label of Object.keys(expected)) {
    const recorded = split?.[label]?.path;
    if (typeof recorded !== 'string' || resolve(recorded) !== expected[label]) {
      throw new Error(`${label} receipt path is not the exact served bin file`);
    }
  }

  const primary = liveIdentity(expected.primary);
  const secondary = liveIdentity(expected.secondary);
  const js = liveIdentity(expected.js);
  requireRowIdentity('primary', split.primary, primary);
  requireRowIdentity('secondary', split.secondary, secondary);
  requireRowIdentity('js', split.js, js, false);

  const proofPrimary = split?.controller_closure?.transitive_direct_call_proof?.primary;
  requireRowIdentity('controller closure primary', proofPrimary, primary);
  if (proofPrimary.bytes !== split.primary.bytes || proofPrimary.sha256 !== split.primary.sha256) {
    throw new Error('controller closure and split primary identity mismatch');
  }

  return {
    contract: 'exact-served-split-artifact-identity-v1',
    bin: exactBin,
    primary,
    secondary,
    js,
    controllerClosurePrimary: {
      sourcePath: proofPrimary.path,
      bytes: proofPrimary.bytes,
      sha256: proofPrimary.sha256,
    },
  };
}

export function validateMinimumWorkerCensus(status, minimumWorkers) {
  if (!Number.isSafeInteger(minimumWorkers) || minimumWorkers < 1) {
    throw new Error('invalid minimum worker census');
  }
  const workerIds = status?.workerIds;
  const lifecycle = status?.workerLifecycle;
  if (!Number.isSafeInteger(status?.workerCount) || status.workerCount < minimumWorkers) {
    throw new Error(`pre-prepare worker count ${status?.workerCount} is below minimum ${minimumWorkers}`);
  }
  if (!Array.isArray(workerIds) || workerIds.length !== status.workerCount ||
      workerIds.some((id) => !Number.isSafeInteger(id) || id < 1) ||
      new Set(workerIds).size !== workerIds.length) {
    throw new Error('pre-prepare worker ID census is not exact and unique');
  }
  const lifecycleIds = Array.isArray(lifecycle) ? lifecycle.map((row) => row?.workerId) : [];
  const lifecycleSet = new Set(lifecycleIds);
  if (lifecycleIds.length !== workerIds.length ||
      lifecycleIds.some((id) => !Number.isSafeInteger(id) || id < 1) ||
      lifecycleSet.size !== lifecycleIds.length ||
      !workerIds.every((id) => lifecycleSet.has(id))) {
    throw new Error('pre-prepare worker lifecycle does not match exact ID census');
  }
  return {
    contract: 'minimum-baseline-exact-current-worker-census-v1',
    minimumWorkers,
    workerCount: status.workerCount,
    workerIds: workerIds.slice(),
  };
}

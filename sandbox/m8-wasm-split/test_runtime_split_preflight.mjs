// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
/** Adversarial fixtures for exact live split artifact identity binding. */

import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  validateMinimumWorkerCensus,
  validateSplitArtifactIdentity,
} from './runtime_split_preflight.mjs';

const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const identity = (path) => {
  const bytes = readFileSync(path);
  return { path, bytes: bytes.length, sha256: sha256(bytes) };
};

function expectFail(label, split, bin, needle) {
  try {
    validateSplitArtifactIdentity(split, bin);
  } catch (error) {
    if (!String(error).includes(needle)) throw new Error(`${label}: ${error} lacks ${needle}`);
    return;
  }
  throw new Error(`${label}: unexpectedly passed`);
}

function expectCensusFail(label, census, minimumWorkers, needle) {
  try {
    validateMinimumWorkerCensus(census, minimumWorkers);
  } catch (error) {
    if (!String(error).includes(needle)) throw new Error(`${label}: ${error} lacks ${needle}`);
    return;
  }
  throw new Error(`${label}: unexpectedly passed`);
}

const root = mkdtempSync(join(tmpdir(), 'bw-runtime-preflight-'));
try {
  const bin = join(root, 'bin');
  mkdirSync(bin);
  const primaryPath = join(bin, 'blender_browser.wasm');
  const secondaryPath = join(bin, 'blender_browser.deferred.wasm');
  const jsPath = join(bin, 'blender_browser.js');
  writeFileSync(primaryPath, Buffer.from('primary-v1'));
  writeFileSync(secondaryPath, Buffer.from('secondary-v1'));
  writeFileSync(jsPath, Buffer.from('shipping-js-v1'));
  const split = {
    primary: identity(primaryPath),
    secondary: identity(secondaryPath),
    js: identity(jsPath),
    controller_closure: {
      transitive_direct_call_proof: { primary: identity(primaryPath) },
    },
  };
  const positive = validateSplitArtifactIdentity(structuredClone(split), bin);
  if (positive.contract !== 'exact-served-split-artifact-identity-v1' ||
      positive.primary.sha256 !== split.primary.sha256 ||
      positive.secondary.sha256 !== split.secondary.sha256 ||
      positive.js.sha256 !== split.js.sha256) {
    throw new Error(`positive identity mismatch: ${JSON.stringify(positive)}`);
  }

  writeFileSync(primaryPath, Buffer.from('primary-mutated'));
  expectFail('primary SHA', structuredClone(split), bin, 'primary live identity mismatch');
  writeFileSync(primaryPath, Buffer.from('primary-v1'));

  writeFileSync(jsPath, Buffer.from('shipping-js-mutated'));
  expectFail('JS SHA', structuredClone(split), bin, 'js live identity mismatch');
  writeFileSync(jsPath, Buffer.from('shipping-js-v1'));

  const wrongPath = structuredClone(split);
  wrongPath.secondary.path = join(root, 'elsewhere.wasm');
  expectFail('wrong path', wrongPath, bin, 'not the exact served bin file');

  const wrongProof = structuredClone(split);
  wrongProof.controller_closure.transitive_direct_call_proof.primary.sha256 = '0'.repeat(64);
  expectFail('proof primary mismatch', wrongProof, bin, 'controller closure primary live identity mismatch');

  const census = {
    workerCount: 14,
    workerIds: Array.from({ length: 14 }, (_value, index) => index + 1),
    workerLifecycle: Array.from({ length: 14 }, (_value, index) => ({ workerId: index + 1 })),
  };
  const acceptedCensus = validateMinimumWorkerCensus(census, 8);
  if (acceptedCensus.workerCount !== 14 || acceptedCensus.minimumWorkers !== 8) {
    throw new Error(`minimum worker census mismatch: ${JSON.stringify(acceptedCensus)}`);
  }
  expectCensusFail('below-minimum census', { ...census, workerCount: 7 }, 8,
    'pre-prepare worker count 7 is below minimum 8');
  const duplicateCensus = structuredClone(census);
  duplicateCensus.workerIds[13] = 1;
  expectCensusFail('duplicate worker ID census', duplicateCensus, 8, 'not exact and unique');
  const lifecycleMismatch = structuredClone(census);
  lifecycleMismatch.workerLifecycle[13].workerId = 99;
  expectCensusFail('lifecycle mismatch census', lifecycleMismatch, 8, 'lifecycle does not match');
  const lifecycleWrongType = structuredClone(census);
  lifecycleWrongType.workerLifecycle[0].workerId = '1';
  expectCensusFail('wrong-type lifecycle ID', lifecycleWrongType, 8, 'lifecycle does not match');
  const lifecycleNonpositive = structuredClone(census);
  lifecycleNonpositive.workerLifecycle[0].workerId = 0;
  expectCensusFail('nonpositive lifecycle ID', lifecycleNonpositive, 8, 'lifecycle does not match');

  console.log('runtime split preflight selfcheck: artifact-positive=1 artifact-negative=4 '
    + 'census-positive=1 census-negative=5 PASS');
} finally {
  rmSync(root, { recursive: true, force: true });
}

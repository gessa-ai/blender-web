// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Browser-free execution contract for the development/public shell seam. The
// full M8 runtime still proves the same attacks in a real browser and product.

import assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as vm from 'node:vm';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..', '..');
const BOOT = join(ROOT, 'platform_web/shell/boot-windowed.js');
const DEVELOPMENT_SEAM = 'const BW_ALLOW_QUERY_DEV_HOOKS = true;';
const PUBLIC_SEAM = 'const BW_ALLOW_QUERY_DEV_HOOKS = false;';
const CUTOFF = '// DOM handles (hidden diagnostics preserve the boot-windowed.js + rig contract)';
const ATTACK_QUERY = '?pyexpr=query-python&args=--background%20--debug-gpu' +
  '&gate=1x1&keepalive=0&ka_active=999999&ka_idle=999998';

function count(text, needle) {
  return text.split(needle).length - 1;
}

function replaceOnce(text, before, after) {
  assert.equal(count(text, before), 1, `expected one mutation target: ${before}`);
  return text.replace(before, after);
}

function harden(source) {
  assert.equal(count(source, DEVELOPMENT_SEAM), 1, 'development hardening seam must be unique');
  assert.equal(count(source, PUBLIC_SEAM), 0, 'development source already contains public seam');
  const result = source.replace(DEVELOPMENT_SEAM, PUBLIC_SEAM);
  assert.equal(count(result, PUBLIC_SEAM), 1, 'public hardening seam must be unique');
  assert.equal(count(result, DEVELOPMENT_SEAM), 0, 'public source retained development seam');
  return result;
}

function execute(source, search, overrides = {}) {
  const cutoff = source.indexOf(CUTOFF);
  assert.ok(cutoff > 0, 'boot-shell executable prefix cutoff is missing');
  const window = {...overrides};
  const context = vm.createContext({window, location: {search}, URLSearchParams});
  vm.runInContext(source.slice(0, cutoff) + `
    globalThis.__bwContractResult = JSON.stringify({
      allowed: window.__bwDevHooksAllowed,
      python: bootPythonExpr(),
      args: bootExtraArgs(),
      gate: GATE,
      keepalive: KEEPALIVE,
      exportedKeepalive: window.__bwKeepaliveConfig,
    });`, context, {filename: 'boot-windowed.contract.js'});
  return JSON.parse(context.__bwContractResult);
}

function assertPublic(result) {
  assert.equal(result.allowed, false);
  assert.equal(result.python, null);
  assert.deepEqual(result.args, []);
  assert.equal(result.gate, null);
  assert.deepEqual(result.keepalive, {enabled: 1, active: 0, idle: 0});
  assert.deepEqual(result.exportedKeepalive, {enabled: 1, active: 0, idle: 0});
}

const source = fs.readFileSync(BOOT, 'utf8');
assert.equal(count(source, 'const pyexpr = bootPythonExpr();'), 1,
  'boot no longer consumes the guarded Python hook exactly once');
assert.equal(count(source, 'const extraArgs = bootExtraArgs();'), 1,
  'boot no longer consumes the guarded argv hook exactly once');
assert.equal(count(source, 'const GATE = gateMode();'), 1,
  'boot no longer consumes the guarded gate hook exactly once');
assert.equal(count(source, 'const KEEPALIVE = keepaliveConfig();'), 1,
  'boot no longer consumes the guarded keepalive hook exactly once');

const developmentQuery = execute(source, ATTACK_QUERY);
assert.equal(developmentQuery.allowed, true);
assert.equal(developmentQuery.python, 'query-python');
assert.deepEqual(developmentQuery.args, ['--background', '--debug-gpu']);
assert.deepEqual(developmentQuery.gate, {w: 1, h: 1});
assert.deepEqual(developmentQuery.keepalive,
  {enabled: 0, active: 999999, idle: 999998});

const developmentGlobals = execute(source, '', {
  __BW_PYEXPR: 'global-python',
  __BW_ARGS: ['--global-arg'],
  __BW_GATE: '3x4',
  __BW_KEEPALIVE: '0',
});
assert.equal(developmentGlobals.python, 'global-python');
assert.deepEqual(developmentGlobals.args, ['--global-arg']);
assert.deepEqual(developmentGlobals.gate, {w: 3, h: 4});
assert.deepEqual(developmentGlobals.keepalive, {enabled: 0, active: 0, idle: 0});

const publicSource = harden(source);
const publicAttack = execute(publicSource, ATTACK_QUERY, {
  __BW_PYEXPR: 'global-python',
  __BW_ARGS: ['--global-arg'],
  __BW_GATE: '3x4',
  __BW_KEEPALIVE: '0',
});
assertPublic(publicAttack);

let negative = 0;
function reject(name, mutated) {
  try {
    assertPublic(execute(mutated, ATTACK_QUERY, {
      __BW_PYEXPR: 'global-python',
      __BW_ARGS: ['--global-arg'],
      __BW_GATE: '3x4',
      __BW_KEEPALIVE: '0',
    }));
  }
  catch (_) {
    negative += 1;
    return;
  }
  throw new Error(`public query hardening mutation survived: ${name}`);
}

reject('public_literal_reenabled', replaceOnce(publicSource, PUBLIC_SEAM, DEVELOPMENT_SEAM));
reject('public_marker_forged', replaceOnce(publicSource,
  'window.__bwDevHooksAllowed = BW_ALLOW_QUERY_DEV_HOOKS;',
  'window.__bwDevHooksAllowed = true;'));
reject('python_guard_removed', replaceOnce(publicSource,
  'function bootPythonExpr() {\n  if (!BW_ALLOW_QUERY_DEV_HOOKS) return null;',
  'function bootPythonExpr() {'));
reject('argv_guard_removed', replaceOnce(publicSource,
  'function bootExtraArgs() {\n  if (!BW_ALLOW_QUERY_DEV_HOOKS) return [];',
  'function bootExtraArgs() {'));
reject('gate_guard_removed', replaceOnce(publicSource,
  'function gateMode() {\n  if (!BW_ALLOW_QUERY_DEV_HOOKS) return null;',
  'function gateMode() {'));
reject('keepalive_guard_removed', replaceOnce(publicSource,
  '  const cfg = { enabled: 1, active: 0, idle: 0 };\n' +
  '  if (!BW_ALLOW_QUERY_DEV_HOOKS) return cfg;',
  '  const cfg = { enabled: 1, active: 0, idle: 0 };'));

assert.equal(negative, 6);
console.log('M8_PUBLIC_QUERY_HARDENING_CONTRACT_PASS positive=3 negative=6 ' +
  'python=off argv=off controls=off');

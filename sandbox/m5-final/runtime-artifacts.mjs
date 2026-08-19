// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

import { readFileSync } from 'fs';
import { basename, join, resolve } from 'path';
import { fileURLToPath } from 'url';

export const RUNTIME_CONTRACT_SOURCE = fileURLToPath(import.meta.url);
// Populated from the finalizer-owned split inventory by
// captureRuntimeArtifactSet(). Drivers call capture before serializing this
// exported contract, so a dynamically named deferred shard remains exact.
export const RUNTIME_BINARY_NAMES = [];
export const RUNTIME_BINARY_PATHS = [];
export const SPLIT_MANIFEST_NAME = 'blender_browser.split-build.json';

function requireContract(condition, message) {
  if (!condition) throw new Error(`runtime artifact contract: ${message}`);
}

function exactMembers(observed, expected, label) {
  requireContract(Array.isArray(observed), `${label} is not an array`);
  requireContract(new Set(observed).size === observed.length, `${label} contains duplicates`);
  requireContract(JSON.stringify([...observed].sort()) === JSON.stringify([...expected].sort()),
    `${label} drift: ${JSON.stringify(observed)}`);
}

function requireManifestArtifact(record, expectedName, binaryRecord, label) {
  requireContract(record && typeof record === 'object', `missing ${label}`);
  requireContract(basename(record.path || '') === expectedName, `${label} path drift`);
  requireContract(record.bytes === binaryRecord.bytes, `${label} byte-size drift`);
  requireContract(record.sha256 === binaryRecord.sha256, `${label} SHA-256 drift`);
}

export function captureRuntimeArtifactSet(binaryDirectory, fileReceipt) {
  const binaryDir = resolve(binaryDirectory);
  const manifestPath = join(binaryDir, SPLIT_MANIFEST_NAME);
  let manifest;
  try {
    manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  } catch (error) {
    throw new Error(`runtime artifact contract: invalid ${SPLIT_MANIFEST_NAME}: ${error.message}`);
  }
  requireContract(manifest.schema === 1, 'split manifest schema drift');
  requireContract(manifest.mode === 'apply' && manifest.verdict === 'PASS',
    'split manifest is not an applied PASS');
  requireContract(manifest.inventory_policy?.unlisted === 'reject',
    'split manifest no longer rejects unlisted Wasm');
  exactMembers(manifest.inventory_policy?.bundle_roles, ['primary', 'deferred'],
    'bundle roles');
  const deferredRows = manifest.wasm_inventory?.filter((item) => item.role === 'deferred');
  requireContract(deferredRows?.length === 1, 'expected exactly one deferred inventory row');
  const deferredName = deferredRows[0].filename;
  requireContract(/^blender_browser(?:\.[A-Za-z0-9_-]+)*\.wasm$/.test(deferredName) &&
    !['blender_browser.wasm', 'blender_browser.wasm.orig'].includes(deferredName),
  'unsafe deferred Wasm filename');
  const names = ['blender_browser.js', 'blender_browser.wasm', deferredName,
    'blender_browser.data'];
  RUNTIME_BINARY_NAMES.splice(0, RUNTIME_BINARY_NAMES.length, ...names);
  RUNTIME_BINARY_PATHS.splice(0, RUNTIME_BINARY_PATHS.length,
    ...names.map((name) => `build-wasm-windowed-opt/bin/${name}`));
  const binaryFiles = names.map((name) => fileReceipt(join(binaryDir, name)));
  const byName = new Map(binaryFiles.map((record) => [basename(record.path), record]));
  exactMembers([...byName.keys()], names, 'runtime binary set');

  requireContract(basename(manifest.js?.path || '') === 'blender_browser.js',
    'split manifest JS path drift');
  requireContract(manifest.js.sha256 === byName.get('blender_browser.js').sha256,
    'split manifest JS SHA-256 drift');
  requireManifestArtifact(manifest.primary, 'blender_browser.wasm',
    byName.get('blender_browser.wasm'), 'primary Wasm');
  requireManifestArtifact(manifest.secondary, deferredName,
    byName.get(deferredName), 'deferred Wasm');

  const inventory = manifest.wasm_inventory;
  requireContract(Array.isArray(inventory), 'wasm_inventory is not an array');
  exactMembers(inventory.map((item) => item.role),
    ['primary', 'deferred', 'original_build_only'], 'Wasm inventory roles');
  const shipped = inventory.filter((item) => item.shipped === true);
  exactMembers(shipped.map((item) => item.role), ['primary', 'deferred'], 'shipping roles');
  exactMembers(shipped.map((item) => item.filename),
    ['blender_browser.wasm', deferredName], 'shipping Wasm files');
  for (const item of shipped) {
    requireManifestArtifact(item, item.filename, byName.get(item.filename),
      `shipping inventory ${item.role}`);
  }
  const original = inventory.find((item) => item.role === 'original_build_only');
  requireContract(original?.filename === 'blender_browser.wasm.orig' && original.shipped === false,
    'original build-only Wasm became a shipping artifact');

  return {
    binaryFiles,
    splitManifest: fileReceipt(manifestPath),
  };
}

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

// Isolated launcher for the native-prebaked principled-default fixture. It
// leaves the canonical acceptance driver untouched, preparing a temporary copy
// whose only changes are the host blend path and its self-check hash.

import { spawnSync } from 'child_process';
import { createHash } from 'crypto';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';

const ROOT = '/Users/paws/blender-web';
const SOURCE = `${ROOT}/sandbox/gpu-r61/f12-eevee-acceptance/drive_eevee_f12.mjs`;
const FIXTURE = process.env.BW_EEVEE_FIXTURE_HOST ||
  (`${ROOT}/sandbox/gpu-r61/f12-eevee-acceptance/fixtures/` +
   'principled_bsdf_default_upstream_setup_native_baked.blend');
const ORIGINAL_BLEND_DECL =
  'const BLEND_HOST = `${ROOT}/upstream/tests/files/render/principled_bsdf/principled_bsdf_default.blend`;';
const ORIGINAL_BLEND_SHA = '39db218041e5d1f8338a666f78e3d06d93f6e7cbd1029390c8e1c646c7ddea5a';

const fixtureBytes = readFileSync(FIXTURE);
const fixtureSha = createHash('sha256').update(fixtureBytes).digest('hex');
let source = readFileSync(SOURCE, 'utf8');
if (source.split(ORIGINAL_BLEND_DECL).length !== 2) {
  throw new Error('canonical driver blend declaration changed');
}
if (source.split(ORIGINAL_BLEND_SHA).length !== 2) {
  throw new Error('canonical driver blend self-check changed');
}
source = source
  .replace(ORIGINAL_BLEND_DECL, `const BLEND_HOST = ${JSON.stringify(FIXTURE)};`)
  .replace(ORIGINAL_BLEND_SHA, fixtureSha);

const temporaryDir = mkdtempSync(join(tmpdir(), 'bw-eevee-prebaked-f12-'));
const temporaryDriver = join(temporaryDir, 'drive_eevee_prebaked_f12.mjs');
writeFileSync(temporaryDriver, source);
const result = spawnSync(process.execPath, [temporaryDriver, ...process.argv.slice(2)], {
  cwd: ROOT,
  env: process.env,
  stdio: 'inherit',
});
rmSync(temporaryDir, { recursive: true, force: true });
if (result.error) throw result.error;
process.exit(result.status ?? 1);

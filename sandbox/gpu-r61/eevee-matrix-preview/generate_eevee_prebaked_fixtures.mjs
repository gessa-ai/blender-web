// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

// Guarded serial launcher for the 29 EEVEE rows that require the upstream
// sphere/volume probe setup. raycast_visibility is verified as a scene-level
// probe-skip exclusion and never receives a baked fixture.

import { spawnSync } from 'child_process';
import { createHash, randomUUID } from 'crypto';
import {
  closeSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
  writeSync,
} from 'fs';
import { tmpdir } from 'os';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const ROOT = '/Users/paws/blender-web';
const HERE = `${ROOT}/sandbox/gpu-r61/eevee-matrix-preview`;
const RUNS_ROOT = `${HERE}/fixture-runs`;
const RUNNER_PATH = fileURLToPath(import.meta.url);
const WORKER = `${HERE}/prebake_eevee_fixture.py`;
const MANIFEST = `${ROOT}/sandbox/m6-prep/manifest.tsv`;
const INPUT_CONTRACT = `${HERE}/eevee-input-contract.tsv`;
const SETUP_SOURCE = `${ROOT}/upstream/tests/python/eevee_render_tests.py`;
const PIN_FILE = `${ROOT}/oracle/PIN`;
const OFFICIAL_BLENDER_DEFAULT =
  `${ROOT}/oracle/blender-5.2.0/Blender.app/Contents/MacOS/Blender`;
const PINNED_BUILD_HASH = 'fbe6228777e7';
const PINNED_SETUP_SHA256 =
  '18a5e10c897df2180f97021657162bc1544b1b8d29fa18c6b98f705f20435af2';
const PINNED_OFFICIAL_BLENDER_SHA256 =
  '60ba7a9b6743f7acf101274361fa76409e382ae07cd2007ce07dea30f6b129f2';
const SKIP_KEY = 'raycast/raycast_visibility';
const PINNED_SKIP_INPUT_SHA256 =
  'cc211e9593bba066457e0f1aa0384f365dee406521559f7d72b2017d97e71e75';
const EXPECTED_MANIFEST_ROWS = 30;
const EXPECTED_BAKE_ROWS = 29;
const GPU_LOCK_PATH = `${HERE}/.eevee-gpu.lock`;
const DEFAULT_ROW_TIMEOUT_MS = 1800000;
const CC0 =
  'SPDX-FileCopyrightText: 2026 blender-web contributors\n' +
  'SPDX-License-Identifier: CC0-1.0\n';

function sha256Bytes(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function sha256File(path) {
  return sha256Bytes(readFileSync(path));
}

function safeToken(value) {
  return value.replace(/[^A-Za-z0-9._-]+/g, '-');
}

function positiveInteger(raw, label, fallback) {
  const value = raw === undefined ? fallback : Number(raw);
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new Error(`${label} must be a positive integer; found ${JSON.stringify(raw)}`);
  }
  return value;
}

function atomicWrite(path, text) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.tmp`;
  writeFileSync(temporary, text);
  renameSync(temporary, path);
}

function writeCc0(path, text) {
  atomicWrite(path, text);
  atomicWrite(`${path}.license`, CC0);
}

function assertNewPath(path, label) {
  if (existsSync(path)) throw new Error(`refusing to overwrite existing ${label}: ${path}`);
}

function acquireExclusiveGpuLock(lockPath, owner) {
  try {
    mkdirSync(lockPath);
  }
  catch (error) {
    if (error?.code === 'EEXIST') {
      throw new Error(
        `refusing concurrent EEVEE GPU work; lock exists: ${lockPath}. ` +
        'Verify its recorded PID is dead before removing a stale lock.');
    }
    throw error;
  }
  const receipt = {
    schema: 'blender-web.eevee-exclusive-gpu-lock.v1',
    lockId: randomUUID(),
    pid: process.pid,
    acquiredAt: new Date().toISOString(),
    ...owner,
  };
  try {
    writeFileSync(
      `${lockPath}/owner.json`, `${JSON.stringify(receipt, null, 2)}\n`, { flag: 'wx' });
  }
  catch (error) {
    rmSync(lockPath, { recursive: true, force: true });
    throw error;
  }
  return { path: lockPath, receipt };
}

function releaseExclusiveGpuLock(lock) {
  if (!lock?.path) return;
  const ownerPath = `${lock.path}/owner.json`;
  const currentOwner = existsSync(ownerPath) ?
    JSON.parse(readFileSync(ownerPath, 'utf8')) : null;
  if (currentOwner?.lockId !== lock.receipt.lockId || currentOwner?.pid !== process.pid) {
    throw new Error(
      `refusing to release EEVEE GPU lock not owned by this process: ${lock.path}`);
  }
  rmSync(lock.path, { recursive: true, force: false });
}

function readInputContract() {
  const bytes = readFileSync(INPUT_CONTRACT);
  const entries = new Map();
  for (const [zeroIndex, line] of bytes.toString('utf8').split(/\r?\n/).entries()) {
    if (!line.trim() || line.startsWith('#')) continue;
    const fields = line.split('\t');
    if (fields.length !== 10) {
      throw new Error(`${INPUT_CONTRACT}:${zeroIndex + 1}: expected 10 fields`);
    }
    const [directory, test, inputSha256, sceneCount, contextMode, samples,
      viewTransform, skipProbes, preexisting, colorMode] = fields;
    const key = `${directory}/${test}`;
    if (entries.has(key)) throw new Error(`duplicate input-contract row ${key}`);
    if (!/^[0-9a-f]{64}$/.test(inputSha256) || sceneCount !== '1' ||
        contextMode !== 'OBJECT' || !Number.isSafeInteger(Number(samples)) || Number(samples) < 1 ||
        !viewTransform || !['RGB', 'RGBA'].includes(colorMode) ||
        !['true', 'false'].includes(skipProbes) || preexisting !== 'false')
    {
      throw new Error(`invalid pinned input contract for ${key}`);
    }
    entries.set(key, {
      line: zeroIndex + 1,
      inputSha256,
      sceneCount: 1,
      contextMode,
      expectedSamples: Number(samples),
      expectedViewTransform: viewTransform,
      expectedColorMode: colorMode,
      skipProbes: skipProbes === 'true',
      preexistingVolumeProbeBaked: false,
    });
  }
  if (entries.size !== EXPECTED_MANIFEST_ROWS) {
    throw new Error(`expected ${EXPECTED_MANIFEST_ROWS} input-contract rows, found ${entries.size}`);
  }
  return { path: INPUT_CONTRACT, sha256: sha256Bytes(bytes), entries };
}

function readRows() {
  const inputContract = readInputContract();
  const rows = [];
  const seen = new Set();
  const lines = readFileSync(MANIFEST, 'utf8').split(/\r?\n/);
  for (const [zeroIndex, line] of lines.entries()) {
    if (!line.trim() || line.startsWith('#')) continue;
    const fields = line.split('\t');
    if (fields.length !== 7) {
      throw new Error(`${MANIFEST}:${zeroIndex + 1}: expected 7 fields, found ${fields.length}`);
    }
    const [engine, directory, test, blend, golden, failThreshold, failPercent] = fields;
    if (engine !== 'eevee') continue;
    const key = `${directory}/${test}`;
    if (seen.has(key)) throw new Error(`duplicate EEVEE manifest row ${key}`);
    seen.add(key);
    const blendPath = resolve(ROOT, blend);
    if (!existsSync(blendPath)) throw new Error(`missing input for ${key}: ${blendPath}`);
    const contract = inputContract.entries.get(key);
    const blendSha256 = sha256File(blendPath);
    if (!contract || contract.inputSha256 !== blendSha256) {
      throw new Error(`input-contract hash mismatch for ${key}`);
    }
    rows.push({
      index: rows.length + 1,
      engine,
      directory,
      test,
      key,
      blend,
      blendPath,
      blendSha256,
      inputContract: contract,
      golden,
      failThreshold,
      failPercent,
      manifestLine: zeroIndex + 1,
      manifestRaw: line,
    });
  }
  if (rows.length !== EXPECTED_MANIFEST_ROWS) {
    throw new Error(`expected ${EXPECTED_MANIFEST_ROWS} EEVEE rows, found ${rows.length}`);
  }
  const excluded = rows.filter((row) => row.key === SKIP_KEY);
  const bakeRows = rows.filter((row) => row.key !== SKIP_KEY);
  if (excluded.length !== 1 || bakeRows.length !== EXPECTED_BAKE_ROWS) {
    throw new Error(
      `expected one ${SKIP_KEY} exclusion and ${EXPECTED_BAKE_ROWS} bake rows; ` +
      `found ${excluded.length}/${bakeRows.length}`);
  }
  if (excluded[0].blendSha256 !== PINNED_SKIP_INPUT_SHA256) {
    throw new Error(
      `${SKIP_KEY} input identity changed: ${excluded[0].blendSha256} ` +
      `!= ${PINNED_SKIP_INPUT_SHA256}`);
  }
  if (excluded[0].inputContract.skipProbes !== true ||
      bakeRows.some((row) => row.inputContract.skipProbes))
  {
    throw new Error('input-contract probe-skip selection mismatch');
  }
  return { rows, excluded: excluded[0], bakeRows, inputContract };
}

function pinnedSources() {
  const officialBlender = resolve(
    process.env.BW_EEVEE_PREBAKE_BLENDER || OFFICIAL_BLENDER_DEFAULT);
  if (!existsSync(officialBlender)) {
    throw new Error(`pinned official Blender is absent: ${officialBlender}`);
  }
  const pin = readFileSync(PIN_FILE, 'utf8').trim();
  if (pin.split(/\s+/)[0] !== PINNED_BUILD_HASH) {
    throw new Error(`oracle/PIN changed: ${pin}`);
  }
  const setupSha256 = sha256File(SETUP_SOURCE);
  const blenderSha256 = sha256File(officialBlender);
  if (setupSha256 !== PINNED_SETUP_SHA256) {
    throw new Error(`pinned EEVEE setup hash changed: ${setupSha256}`);
  }
  if (blenderSha256 !== PINNED_OFFICIAL_BLENDER_SHA256) {
    throw new Error(`pinned official Blender binary hash changed: ${blenderSha256}`);
  }
  return {
    pin: { path: PIN_FILE, text: pin, buildHash: PINNED_BUILD_HASH },
    setup: { path: SETUP_SOURCE, sha256: setupSha256 },
    blender: { path: officialBlender, sha256: blenderSha256 },
    worker: { path: WORKER, sha256: sha256File(WORKER) },
    runner: { path: RUNNER_PATH, sha256: sha256File(RUNNER_PATH) },
    manifest: { path: MANIFEST, sha256: sha256File(MANIFEST) },
    inputContract: { path: INPUT_CONTRACT, sha256: sha256File(INPUT_CONTRACT) },
  };
}

function buildPlan(bakeRows, runRoot) {
  return bakeRows.map((row, zeroIndex) => {
    const slug = safeToken(
      `${String(zeroIndex + 1).padStart(2, '0')}-${row.directory}-${row.test}`);
    const output = `${runRoot}/fixtures/${slug}-upstream-setup-native-baked.blend`;
    return {
      ...row,
      bakeIndex: zeroIndex + 1,
      slug,
      output,
      receipt: `${runRoot}/receipts/${slug}.receipt.json`,
      log: `${runRoot}/logs/${slug}.log`,
    };
  });
}

function workerEnvironment(sources, runRoot, row, mode, receipt, output = null) {
  const env = {
    ...process.env,
    BW_EEVEE_PREBAKE_MODE: mode,
    BW_EEVEE_PREBAKE_INPUT: row.blendPath,
    BW_EEVEE_PREBAKE_INPUT_SHA256: row.blendSha256,
    BW_EEVEE_PREBAKE_RECEIPT: receipt,
    BW_EEVEE_PREBAKE_RUN_ROOT: runRoot,
    BW_EEVEE_PREBAKE_ROW_KEY: row.key,
    BW_EEVEE_PREBAKE_BLENDER_PATH: sources.blender.path,
    BW_EEVEE_PREBAKE_BLENDER_SHA256: sources.blender.sha256,
    BW_EEVEE_PREBAKE_EXPECTED_SAMPLES: String(row.inputContract.expectedSamples),
    BW_EEVEE_PREBAKE_EXPECTED_VIEW_TRANSFORM: row.inputContract.expectedViewTransform,
    BW_EEVEE_PREBAKE_SKIP_PROBES: String(row.inputContract.skipProbes),
    BW_EEVEE_PREBAKE_INPUT_CONTRACT_SHA256: sources.inputContract.sha256,
  };
  if (output) env.BW_EEVEE_PREBAKE_OUTPUT = output;
  else delete env.BW_EEVEE_PREBAKE_OUTPUT;
  return env;
}

function workerArguments(sources, row) {
  return [
    '--background',
    '--factory-startup',
    '--enable-autoexec',
    '--debug-memory',
    '--console-crash-handler',
    '--debug-exit-on-error',
    '--gpu-backend',
    'metal',
    row.blendPath,
    '--python',
    WORKER,
  ];
}

function spawnWorker(sources, row, env, logPath, timeoutMs) {
  assertNewPath(logPath, 'row log');
  mkdirSync(dirname(logPath), { recursive: true });
  const logFd = openSync(logPath, 'wx');
  let child;
  try {
    writeSync(
      logFd,
      `FIXTURE_WORKER_BEGIN key=${row.key} input_sha256=${row.blendSha256} ` +
      `serialized_slot=1/1\n`);
    child = spawnSync(sources.blender.path, workerArguments(sources, row), {
      cwd: ROOT,
      env,
      stdio: ['ignore', logFd, logFd],
      timeout: timeoutMs,
    });
    writeSync(
      logFd,
      `FIXTURE_WORKER_END status=${child.status} signal=${child.signal || ''} ` +
      `error=${JSON.stringify(child.error?.message || null)}\n`);
  }
  finally {
    closeSync(logFd);
    writeFileSync(`${logPath}.license`, CC0);
  }
  return child;
}

function equivalentNumber(actual, expected) {
  return typeof actual === 'number' && Number.isFinite(actual) &&
    Math.abs(actual - expected) <= 1e-6;
}

function validateSphere(sphere) {
  return sphere?.object_type === 'LIGHT_PROBE' && sphere.probe_type === 'SPHERE' &&
    JSON.stringify(sphere.location) === JSON.stringify([0, 0.10000000149011612, 1]) &&
    JSON.stringify(sphere.scale) === JSON.stringify([5, 5, 2]) &&
    equivalentNumber(sphere.falloff, 0) && equivalentNumber(sphere.clip_start, 0.8) &&
    equivalentNumber(sphere.influence_distance, 1.2);
}

function validateVolume(volume) {
  return volume?.object_name === 'Volume_Probe_Baked' &&
    volume.data_name === 'Volume_Probe_Baked' &&
    volume.object_type === 'LIGHT_PROBE' && volume.probe_type === 'VOLUME' &&
    JSON.stringify(volume.location) === JSON.stringify([0, 0, 2]) &&
    JSON.stringify(volume.scale) === JSON.stringify([8, 4.5, 4.5]) &&
    JSON.stringify(volume.resolution) === JSON.stringify([32, 16, 8]) &&
    volume.bake_samples === 128 && volume.capture_world === true &&
    equivalentNumber(volume.surfel_density, 100) &&
    equivalentNumber(volume.dilation_threshold, 1);
}

function validateRenderSampling(sampling, row) {
  return sampling?.scene_count === 1 && sampling?.view_layer_samples === 0 &&
    sampling?.scene_taa_render_samples === row.inputContract.expectedSamples &&
    sampling?.effective === row.inputContract.expectedSamples &&
    sampling?.view_transform === row.inputContract.expectedViewTransform;
}

function validateBakeReceipt(receipt, row, sources) {
  const sphere = receipt?.new_probes?.find((probe) => probe.probe_type === 'SPHERE');
  const volume = receipt?.new_probes?.find((probe) => probe.probe_type === 'VOLUME');
  const identity = receipt?.recognition_identity;
  const outputHash = existsSync(row.output) ? sha256File(row.output) : null;
  const errors = [];
  if (receipt?.schema !== 'blender-web.eevee-native-prebake-receipt.v2') errors.push('schema');
  if (receipt?.row !== row.key) errors.push('row');
  if (receipt?.input?.path !== row.blendPath || receipt?.input?.sha256 !== row.blendSha256) {
    errors.push('input identity');
  }
  if (receipt?.setup?.sha256 !== sources.setup.sha256) errors.push('setup identity');
  if (receipt?.input_contract?.sha256 !== sources.inputContract.sha256) {
    errors.push('input-contract identity');
  }
  if (receipt?.worker?.sha256 !== sources.worker.sha256) errors.push('worker identity');
  if (receipt?.blender?.path !== sources.blender.path ||
      receipt?.blender?.sha256 !== sources.blender.sha256 ||
      !receipt?.blender?.build_hash?.startsWith(PINNED_BUILD_HASH))
  {
    errors.push('Blender identity');
  }
  if (receipt?.output?.path !== row.output || receipt?.output?.sha256 !== outputHash ||
      !Number.isInteger(receipt?.output?.bytes) || receipt.output.bytes <= 0)
  {
    errors.push('output identity');
  }
  if (receipt?.upstream_setup_returned !== true) errors.push('upstream setup return');
  if (!validateRenderSampling(receipt?.render_sampling, row)) errors.push('render samples');
  if (!Array.isArray(receipt?.new_probes) || receipt.new_probes.length !== 2 ||
      !validateSphere(sphere) || !validateVolume(volume))
  {
    errors.push('probe identity');
  }
  if (identity?.lookup !== "bpy.data.objects.get('Volume_Probe_Baked')" ||
      identity?.object_name !== 'Volume_Probe_Baked' ||
      identity?.data_name !== 'Volume_Probe_Baked' ||
      identity?.object_type !== 'LIGHT_PROBE' || identity?.probe_type !== 'VOLUME')
  {
    errors.push('recognition identity');
  }
  if (receipt?.scene_provenance?.BW_fixture_row !== row.key ||
      receipt?.scene_provenance?.BW_fixture_input_sha256 !== row.blendSha256 ||
      receipt?.scene_provenance?.BW_fixture_setup_sha256 !== sources.setup.sha256 ||
      receipt?.scene_provenance?.BW_fixture_input_contract_sha256 !==
        sources.inputContract.sha256 ||
      receipt?.scene_provenance?.BW_fixture_effective_render_samples !==
        row.inputContract.expectedSamples ||
      !receipt?.scene_flags?.every((item) => item.EEVEE_skip_probes_setup === false))
  {
    errors.push('scene provenance');
  }
  return { ok: errors.length === 0, errors, outputHash };
}

function validateExclusionReceipt(receipt, excluded, sources) {
  const errors = [];
  if (receipt?.schema !== 'blender-web.eevee-native-prebake-exclusion.v1') {
    errors.push('schema');
  }
  if (receipt?.row !== SKIP_KEY || receipt?.input?.path !== excluded.blendPath ||
      receipt?.input?.sha256 !== excluded.blendSha256)
  {
    errors.push('input identity');
  }
  if (receipt?.setup?.sha256 !== sources.setup.sha256 ||
      receipt?.input_contract?.sha256 !== sources.inputContract.sha256 ||
      receipt?.worker?.sha256 !== sources.worker.sha256 ||
      receipt?.blender?.sha256 !== sources.blender.sha256 ||
      !receipt?.blender?.build_hash?.startsWith(PINNED_BUILD_HASH))
  {
    errors.push('source identity');
  }
  if (receipt?.bake_executed !== false || receipt?.output_fixture !== null ||
      !validateRenderSampling(receipt?.render_sampling, excluded) ||
      !receipt?.scene_flags?.length ||
      !receipt.scene_flags.every((item) => item.EEVEE_skip_probes_setup === true))
  {
    errors.push('skip predicate');
  }
  return { ok: errors.length === 0, errors };
}

function fixtureMapTsv(completed) {
  const lines = [
    '# SPDX-FileCopyrightText: 2026 blender-web contributors',
    '# SPDX-License-Identifier: CC0-1.0',
    '# dir\ttest\tfixture_blend\texpected_sha256',
  ];
  for (const item of completed) {
    lines.push([
      item.directory,
      item.test,
      item.output,
      item.outputSha256,
    ].join('\t'));
  }
  return `${lines.join('\n')}\n`;
}

function statusReceipt(
  status, label, runRoot, sources, plan, excluded, exclusion, completed, failure, gpuLock)
{
  return {
    schema: 'blender-web.eevee-native-prebake-map-receipt.v1',
    status,
    generatedAt: new Date().toISOString(),
    run: {
      label,
      root: runRoot,
      browserLaunched: false,
      serialExecution: true,
      maximumNativeConcurrency: 1,
      gpuBackend: 'metal',
      exclusiveGpuLock: gpuLock?.receipt || null,
    },
    sources,
    selection: {
      manifestRows: EXPECTED_MANIFEST_ROWS,
      bakeRows: EXPECTED_BAKE_ROWS,
      excludedRows: 1,
      exclusion: {
        key: excluded.key,
        input: excluded.blendPath,
        inputSha256: excluded.blendSha256,
        predicate: 'EEVEE_skip_probes_setup=true',
        verification: exclusion,
      },
    },
    plan: plan.map((row) => ({
      index: row.bakeIndex,
      key: row.key,
      manifestLine: row.manifestLine,
      input: row.blendPath,
      inputSha256: row.blendSha256,
      inputContractLine: row.inputContract.line,
      expectedRenderSamples: row.inputContract.expectedSamples,
      output: row.output,
      receipt: row.receipt,
    })),
    progress: {
      completed: completed.length,
      pending: plan.length - completed.length,
      rows: completed,
    },
    fixtureMap: {
      path: `${runRoot}/fixture-map.tsv`,
      sha256: existsSync(`${runRoot}/fixture-map.tsv`) ?
        sha256File(`${runRoot}/fixture-map.tsv`) : null,
      rows: completed.length,
      compatibleConsumer:
        'BW_EEVEE_MATRIX_PREBAKED_MAP for run_eevee_matrix.mjs',
    },
    failure: failure || null,
  };
}

function selfcheck() {
  const { rows, excluded, bakeRows } = readRows();
  const sources = pinnedSources();
  const syntax = spawnSync(
    'python3',
    ['-c', 'import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text())', WORKER],
    { cwd: ROOT, encoding: 'utf8', timeout: 120000 });
  if (syntax.status !== 0) throw new Error(`worker Python syntax failed: ${syntax.stderr}`);
  const workerCheck = spawnSync('python3', [WORKER, '--selfcheck'], {
    cwd: ROOT, encoding: 'utf8', timeout: 120000,
  });
  if (workerCheck.status !== 0 || !workerCheck.stdout.includes('SELF_CHECK_PASS')) {
    throw new Error(`worker self-check failed: ${workerCheck.stderr || workerCheck.stdout}`);
  }
  const temporary = mkdtempSync(`${tmpdir()}/bw-eevee-fixture-refuse-`);
  let overwriteRefused = false;
  let concurrentGpuRefused = false;
  try {
    try {
      assertNewPath(temporary, 'self-check run');
    }
    catch (error) {
      overwriteRefused = /refusing to overwrite/.test(String(error));
    }
    const firstLock = acquireExclusiveGpuLock(
      `${temporary}/gpu-lock`, { role: 'selfcheck', runLabel: 'first' });
    try {
      acquireExclusiveGpuLock(
        `${temporary}/gpu-lock`, { role: 'selfcheck', runLabel: 'second' });
    }
    catch (error) {
      concurrentGpuRefused = /refusing concurrent EEVEE GPU work/.test(String(error));
    }
    releaseExclusiveGpuLock(firstLock);
    const fixturePath = `${temporary}/fixture.blend`;
    writeFileSync(fixturePath, 'synthetic fixture receipt self-check\n');
    const row = { ...bakeRows[0], output: fixturePath };
    const synthetic = {
      schema: 'blender-web.eevee-native-prebake-receipt.v2',
      row: row.key,
      input: { path: row.blendPath, sha256: row.blendSha256 },
      setup: { path: sources.setup.path, sha256: sources.setup.sha256 },
      input_contract: {
        path: sources.inputContract.path,
        sha256: sources.inputContract.sha256,
      },
      worker: { path: sources.worker.path, sha256: sources.worker.sha256 },
      blender: {
        path: sources.blender.path,
        sha256: sources.blender.sha256,
        version: '5.2.0 LTS',
        build_hash: PINNED_BUILD_HASH,
      },
      output: {
        path: fixturePath,
        sha256: sha256File(fixturePath),
        bytes: readFileSync(fixturePath).length,
      },
      render_sampling: {
        scene: 'Scene', scene_count: 1, view_layer: 'ViewLayer', view_layer_samples: 0,
        scene_taa_render_samples: row.inputContract.expectedSamples,
        effective: row.inputContract.expectedSamples,
        view_transform: row.inputContract.expectedViewTransform,
      },
      upstream_setup_returned: true,
      new_probes: [
        {
          object_name: 'Sphere', object_type: 'LIGHT_PROBE', data_name: 'Sphere',
          probe_type: 'SPHERE', location: [0, 0.10000000149011612, 1],
          scale: [5, 5, 2], falloff: 0, clip_start: 0.800000011920929,
          influence_distance: 1.2000000476837158,
        },
        {
          object_name: 'Volume_Probe_Baked', object_type: 'LIGHT_PROBE',
          data_name: 'Volume_Probe_Baked', probe_type: 'VOLUME', location: [0, 0, 2],
          scale: [8, 4.5, 4.5], resolution: [32, 16, 8], bake_samples: 128,
          capture_world: true, surfel_density: 100, dilation_threshold: 1,
        },
      ],
      recognition_identity: {
        lookup: "bpy.data.objects.get('Volume_Probe_Baked')",
        object_name: 'Volume_Probe_Baked', data_name: 'Volume_Probe_Baked',
        object_type: 'LIGHT_PROBE', probe_type: 'VOLUME',
      },
      scene_provenance: {
        BW_fixture_row: row.key,
        BW_fixture_input_sha256: row.blendSha256,
        BW_fixture_setup_sha256: sources.setup.sha256,
        BW_fixture_input_contract_sha256: sources.inputContract.sha256,
        BW_fixture_effective_render_samples: row.inputContract.expectedSamples,
      },
      scene_flags: [{ scene: 'Scene', EEVEE_skip_probes_setup: false }],
    };
    if (!validateBakeReceipt(synthetic, row, sources).ok ||
        validateBakeReceipt({
          ...synthetic,
          recognition_identity: {
            ...synthetic.recognition_identity,
            object_name: 'Wrong',
          },
        }, row, sources).ok)
    {
      throw new Error('bake receipt validator self-check failed');
    }
    const syntheticExclusion = {
      schema: 'blender-web.eevee-native-prebake-exclusion.v1',
      row: SKIP_KEY,
      input: { path: excluded.blendPath, sha256: excluded.blendSha256 },
      setup: { sha256: sources.setup.sha256 },
      input_contract: { sha256: sources.inputContract.sha256 },
      worker: { sha256: sources.worker.sha256 },
      blender: { sha256: sources.blender.sha256, build_hash: PINNED_BUILD_HASH },
      bake_executed: false,
      output_fixture: null,
      render_sampling: {
        scene: 'Scene', scene_count: 1, view_layer: 'ViewLayer', view_layer_samples: 0,
        scene_taa_render_samples: excluded.inputContract.expectedSamples,
        effective: excluded.inputContract.expectedSamples,
        view_transform: excluded.inputContract.expectedViewTransform,
      },
      scene_flags: [{ scene: 'Scene', EEVEE_skip_probes_setup: true }],
    };
    if (!validateExclusionReceipt(syntheticExclusion, excluded, sources).ok) {
      throw new Error('exclusion receipt validator self-check failed');
    }
  }
  finally {
    rmSync(temporary, { recursive: true, force: true });
  }
  if (!overwriteRefused || !concurrentGpuRefused) {
    throw new Error('overwrite/global-GPU-lock refusal self-check failed');
  }
  if (rows.length !== 30 || bakeRows.length !== 29 || excluded.key !== SKIP_KEY ||
      sources.setup.sha256 !== PINNED_SETUP_SHA256 ||
      sources.blender.sha256 !== PINNED_OFFICIAL_BLENDER_SHA256)
  {
    throw new Error('pinned plan self-check failed');
  }
  console.log(
    `SELF_CHECK_PASS harness=eevee-native-prebake-batch manifest_rows=${rows.length} ` +
    `bake_rows=${bakeRows.length} excluded=${excluded.key} overwrite_refusal=PASS ` +
    'serial_concurrency=1 global_gpu_lock=PASS blender_launches=0 browser_launches=0 bakes=0');
}

function main() {
  const label = (process.argv[2] || '').trim();
  if (!/^[A-Za-z0-9._-]+$/.test(label)) {
    throw new Error(`usage: node ${RUNNER_PATH} <unique-run-label>`);
  }
  const timeoutMs = positiveInteger(
    process.env.BW_EEVEE_PREBAKE_ROW_TIMEOUT_MS,
    'BW_EEVEE_PREBAKE_ROW_TIMEOUT_MS',
    DEFAULT_ROW_TIMEOUT_MS);
  const { excluded, bakeRows } = readRows();
  const sources = pinnedSources();
  const runRoot = `${RUNS_ROOT}/${label}`;
  assertNewPath(runRoot, 'fixture run');
  const plan = buildPlan(bakeRows, runRoot);
  for (const row of plan) {
    assertNewPath(row.output, 'fixture');
    assertNewPath(row.receipt, 'fixture receipt');
    assertNewPath(row.log, 'fixture log');
  }

  mkdirSync(RUNS_ROOT, { recursive: true });
  const gpuLock = acquireExclusiveGpuLock(GPU_LOCK_PATH, {
    role: 'native-prebake-batch',
    runLabel: label,
    runRoot,
    maximumGpuConcurrency: 1,
  });
  try {
  mkdirSync(runRoot);
  mkdirSync(`${runRoot}/fixtures`);
  mkdirSync(`${runRoot}/receipts`);
  mkdirSync(`${runRoot}/logs`);
  const mapPath = `${runRoot}/fixture-map.tsv`;
  const receiptPath = `${runRoot}/fixture-map.receipt.json`;
  const exclusionReceiptPath = `${runRoot}/receipts/raycast_visibility.skip.receipt.json`;
  const exclusionLogPath = `${runRoot}/logs/raycast_visibility.skip.log`;
  const completed = [];
  let exclusion = null;
  let status = 'RUNNING';
  let failure = null;
  writeCc0(mapPath, fixtureMapTsv(completed));
  writeCc0(
    receiptPath,
    `${JSON.stringify(statusReceipt(
      status, label, runRoot, sources, plan, excluded, exclusion, completed, failure, gpuLock), null, 2)}\n`);

  try {
    const exclusionChild = spawnWorker(
      sources,
      excluded,
      workerEnvironment(
        sources, runRoot, excluded, 'verify-skip', exclusionReceiptPath),
      exclusionLogPath,
      timeoutMs);
    if (exclusionChild.status !== 0) {
      throw new Error(
        `probe-skip verification failed status=${exclusionChild.status} ` +
        `signal=${exclusionChild.signal || ''} error=${exclusionChild.error?.message || ''}`);
    }
    exclusion = JSON.parse(readFileSync(exclusionReceiptPath, 'utf8'));
    const exclusionValidation = validateExclusionReceipt(exclusion, excluded, sources);
    if (!exclusionValidation.ok) {
      throw new Error(`probe-skip receipt invalid: ${exclusionValidation.errors.join(', ')}`);
    }
    writeFileSync(`${exclusionReceiptPath}.license`, CC0);

    for (const row of plan) {
      const child = spawnWorker(
        sources,
        row,
        workerEnvironment(sources, runRoot, row, 'bake', row.receipt, row.output),
        row.log,
        timeoutMs);
      if (child.status !== 0) {
        throw new Error(
          `fixture worker failed for ${row.key}: status=${child.status} ` +
          `signal=${child.signal || ''} error=${child.error?.message || ''}`);
      }
      const receipt = JSON.parse(readFileSync(row.receipt, 'utf8'));
      const validation = validateBakeReceipt(receipt, row, sources);
      if (!validation.ok) {
        throw new Error(`fixture receipt invalid for ${row.key}: ${validation.errors.join(', ')}`);
      }
      writeFileSync(`${row.receipt}.license`, CC0);
      completed.push({
        index: row.bakeIndex,
        directory: row.directory,
        test: row.test,
        key: row.key,
        input: row.blendPath,
        inputSha256: row.blendSha256,
        inputContractLine: row.inputContract.line,
        expectedRenderSamples: row.inputContract.expectedSamples,
        output: row.output,
        outputSha256: validation.outputHash,
        receipt: row.receipt,
        receiptSha256: sha256File(row.receipt),
        probeIdentity: receipt.recognition_identity,
      });
      writeCc0(mapPath, fixtureMapTsv(completed));
      const runningReceipt = statusReceipt(
        status, label, runRoot, sources, plan, excluded, exclusion, completed, failure, gpuLock);
      atomicWrite(receiptPath, `${JSON.stringify(runningReceipt, null, 2)}\n`);
      console.log(
        `FIXTURE_ROW_COMPLETE ${row.bakeIndex}/${plan.length} key=${row.key} ` +
        `sha256=${validation.outputHash}`);
    }
    status = 'PASS';
  }
  catch (error) {
    status = 'FAIL';
    failure = error.stack || error.message || String(error);
  }

  const finalReceipt = statusReceipt(
    status, label, runRoot, sources, plan, excluded, exclusion, completed, failure, gpuLock);
  finalReceipt.completedAt = new Date().toISOString();
  atomicWrite(receiptPath, `${JSON.stringify(finalReceipt, null, 2)}\n`);
  if (status !== 'PASS') {
    console.error(`FIXTURE_BATCH_FAIL receipt=${receiptPath} error=${failure}`);
    throw new Error(`fixture batch failed; receipt=${receiptPath}`);
  }
  console.log(
    `FIXTURE_BATCH_PASS rows=${completed.length} excluded=${excluded.key} ` +
    `map=${mapPath} receipt=${receiptPath}`);
  }
  finally {
    releaseExclusiveGpuLock(gpuLock);
  }
}

if (process.argv[2] === '--selfcheck') {
  selfcheck();
}
else {
  try {
    main();
  }
  catch (error) {
    console.error(error.stack || error.message || String(error));
    process.exit(1);
  }
}

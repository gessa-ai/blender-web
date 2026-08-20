// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

// Isolated 30-row EEVEE screen using the marker-independent physical-F12
// product driver. The canonical one-row driver is read-only: each row runs a
// temporary, hash-bound copy with row-specific inputs and comparator settings.

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
import { basename, delimiter, dirname, isAbsolute, join, resolve } from 'path';
import { fileURLToPath } from 'url';

const HARNESS_PATH = fileURLToPath(import.meta.url);
const HERE = dirname(HARNESS_PATH);
const ROOT = resolve(HERE, '../../..');
const RUNS_ROOT = `${HERE}/runs`;
const MANIFEST_PATH = `${ROOT}/sandbox/m6-prep/manifest.tsv`;
const INPUT_CONTRACT_PATH = `${HERE}/eevee-input-contract.tsv`;
const UPSTREAM_EEVEE_RUNNER = `${ROOT}/upstream/tests/python/eevee_render_tests.py`;
const THRESHOLD_VALIDATOR = `${ROOT}/sandbox/m6-prep/validate_eevee_thresholds.py`;
const FIXTURE_GENERATOR = `${HERE}/generate_eevee_prebaked_fixtures.mjs`;
const FIXTURE_WORKER = `${HERE}/prebake_eevee_fixture.py`;
const GPU_LOCK_PATH = `${HERE}/.eevee-gpu.lock`;
const CANONICAL_DRIVER =
  `${ROOT}/sandbox/gpu-r61/f12-eevee-acceptance/drive_eevee_f12.mjs`;
const EXPECTED_EEVEE_ROWS = 30;
const EXPECTED_PREBAKED_ROWS = 29;
const PROBE_SKIP_KEY = 'raycast/raycast_visibility';
const PIN_FILE = `${ROOT}/oracle/PIN`;
const PINNED_BUILD_HASH = 'fbe6228777e7';
const PINNED_OFFICIAL_BLENDER_SHA256 =
  '60ba7a9b6743f7acf101274361fa76409e382ae07cd2007ce07dea30f6b129f2';
const DEFAULT_PORT = 8151;
const DEFAULT_RENDER_MS = 300000;
const DEFAULT_PROCESS_MS = 900000;
const NODE_MODULE_ROOTS = [...new Set([
  process.env.BW_NODE_MODULES,
  process.env.NODE_PATH,
  `${ROOT}/.m4-node/node_modules`,
  `${ROOT}/node_modules`,
]
  .filter(Boolean)
  .flatMap((entry) => entry.split(delimiter))
  .filter(Boolean)
  .map((entry) => resolve(entry)))];
const BROWSER_ARGS = Object.freeze([
  '--enable-unsafe-webgpu',
  ...(process.platform === 'darwin' ? ['--use-angle=metal'] : []),
  '--disable-dev-tools',
]);
const CC0 =
  'SPDX-FileCopyrightText: 2026 blender-web contributors\n' +
  'SPDX-License-Identifier: CC0-1.0\n';
const STRIPPED_MATRIX_ENV = Object.freeze([
  'BW_F12_ASYNC_PROBE',
  'BW_READBACK_CAPTURE',
  'BW_EEVEE_INPUT_CAPTURE',
  'BW_EEVEE_PASS_CAPTURE',
  'BW_EEVEE_DEPTH_ALWAYS_DIAG',
  'BW_EEVEE_RENDER_SAMPLES_OVERRIDE',
  'BW_EEVEE_CANONICAL_PROBES',
  'BW_EEVEE_CANONICAL_PROBE_TIMEOUT_MS',
  'BW_EEVEE_EXPORT_BAKED_BLEND',
]);

function sha256Bytes(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function sha256File(path) {
  return sha256Bytes(readFileSync(path));
}

function requirePositiveInteger(raw, label, fallback) {
  const value = raw === undefined ? fallback : Number(raw);
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new Error(`${label} must be a positive integer; found ${JSON.stringify(raw)}`);
  }
  return value;
}

function absoluteInputPath(path) {
  return isAbsolute(path) ? path : resolve(ROOT, path);
}

function parseTsv(text, path) {
  const rows = [];
  for (const [zeroIndex, rawLine] of text.split(/\r?\n/).entries()) {
    if (!rawLine.trim() || rawLine.startsWith('#')) continue;
    rows.push({ lineNumber: zeroIndex + 1, fields: rawLine.split('\t'), rawLine, path });
  }
  return rows;
}

function parseBoolean(raw, label) {
  if (raw === 'true') return true;
  if (raw === 'false') return false;
  throw new Error(`${label} must be true or false; found ${JSON.stringify(raw)}`);
}

function readInputContract() {
  const bytes = readFileSync(INPUT_CONTRACT_PATH);
  const entries = new Map();
  for (const parsed of parseTsv(bytes.toString('utf8'), INPUT_CONTRACT_PATH)) {
    if (parsed.fields.length !== 10) {
      throw new Error(
        `${INPUT_CONTRACT_PATH}:${parsed.lineNumber}: expected 10 fields, ` +
        `found ${parsed.fields.length}`);
    }
    const [directory, test, inputSha256, sceneCountRaw, contextMode, samplesRaw,
      viewTransform, skipProbesRaw, preexistingRaw, colorMode] = parsed.fields;
    const key = `${directory}/${test}`;
    if (entries.has(key)) {
      throw new Error(`${INPUT_CONTRACT_PATH}:${parsed.lineNumber}: duplicate ${key}`);
    }
    if (!/^[0-9a-f]{64}$/.test(inputSha256)) {
      throw new Error(`${INPUT_CONTRACT_PATH}:${parsed.lineNumber}: invalid input hash for ${key}`);
    }
    const sceneCount = requirePositiveInteger(
      sceneCountRaw, `scene count contract for ${key}`, undefined);
    const effectiveSamples = requirePositiveInteger(
      samplesRaw, `sample contract for ${key}`, undefined);
    if (contextMode !== 'OBJECT') {
      throw new Error(`${INPUT_CONTRACT_PATH}:${parsed.lineNumber}: ${key} is not OBJECT mode`);
    }
    if (!viewTransform) {
      throw new Error(`${INPUT_CONTRACT_PATH}:${parsed.lineNumber}: ${key} has no view transform`);
    }
    if (!['RGB', 'RGBA'].includes(colorMode)) {
      throw new Error(
        `${INPUT_CONTRACT_PATH}:${parsed.lineNumber}: ${key} has invalid color mode ${colorMode}`);
    }
    entries.set(key, {
      line: parsed.lineNumber,
      inputSha256,
      sceneCount,
      contextMode,
      effectiveSamples,
      viewTransform,
      colorMode,
      skipProbes: parseBoolean(skipProbesRaw, `skip-probes contract for ${key}`),
      preexistingVolumeProbeBaked: parseBoolean(
        preexistingRaw, `preexisting-probe contract for ${key}`),
    });
  }
  if (entries.size !== EXPECTED_EEVEE_ROWS) {
    throw new Error(
      `expected ${EXPECTED_EEVEE_ROWS} input-contract rows, found ${entries.size}`);
  }
  const skipped = [...entries.entries()].filter(([, entry]) => entry.skipProbes);
  if (skipped.length !== 1 || skipped[0][0] !== PROBE_SKIP_KEY) {
    throw new Error(
      `input contract must identify only ${PROBE_SKIP_KEY} as probe-skipped; ` +
      `found ${skipped.map(([key]) => key).join(',')}`);
  }
  if ([...entries.values()].some((entry) => entry.preexistingVolumeProbeBaked)) {
    throw new Error('pinned manifest inputs unexpectedly contain Volume_Probe_Baked');
  }
  return { path: INPUT_CONTRACT_PATH, sha256: sha256Bytes(bytes), entries };
}

function readEeveeRows() {
  const rows = [];
  const keys = new Set();
  for (const parsed of parseTsv(readFileSync(MANIFEST_PATH, 'utf8'), MANIFEST_PATH)) {
    if (parsed.fields.length !== 7) {
      throw new Error(
        `${MANIFEST_PATH}:${parsed.lineNumber}: expected 7 fields, found ${parsed.fields.length}`);
    }
    const [engine, directory, test, blend, golden, failThreshold, failPercent] = parsed.fields;
    if (engine !== 'eevee') continue;
    const key = `${directory}/${test}`;
    if (keys.has(key)) throw new Error(`duplicate EEVEE row ${key}`);
    keys.add(key);
    const thresholdNumber = Number(failThreshold);
    const percentNumber = Number(failPercent);
    if (!Number.isFinite(thresholdNumber) || thresholdNumber <= 0 ||
        !Number.isFinite(percentNumber) || percentNumber < 0)
    {
      throw new Error(`${MANIFEST_PATH}:${parsed.lineNumber}: invalid comparator for ${key}`);
    }
    const blendPath = absoluteInputPath(blend);
    const goldenPath = absoluteInputPath(golden);
    if (!existsSync(blendPath)) throw new Error(`missing EEVEE blend for ${key}: ${blendPath}`);
    if (!existsSync(goldenPath)) throw new Error(`missing EEVEE golden for ${key}: ${goldenPath}`);
    rows.push({
      index: rows.length + 1,
      engine,
      directory,
      test,
      key,
      manifestLine: parsed.lineNumber,
      manifestRaw: parsed.rawLine,
      blend,
      blendPath,
      golden,
      goldenPath,
      failThreshold,
      failPercent,
    });
  }
  if (rows.length !== EXPECTED_EEVEE_ROWS) {
    throw new Error(`expected ${EXPECTED_EEVEE_ROWS} EEVEE rows, found ${rows.length}`);
  }
  return rows;
}

function selectExactRows(rows, rawSelection) {
  if (rawSelection === undefined) {
    return {
      rows,
      mode: 'full-manifest',
      requestedKeys: rows.map((row) => row.key),
    };
  }
  const requestedKeys = rawSelection.split(',').map((key) => key.trim());
  if (requestedKeys.length === 0 || requestedKeys.some((key) => !key)) {
    throw new Error(
      'BW_EEVEE_MATRIX_KEYS must be a comma-separated list of non-empty exact manifest keys');
  }
  const uniqueKeys = new Set(requestedKeys);
  if (uniqueKeys.size !== requestedKeys.length) {
    throw new Error('BW_EEVEE_MATRIX_KEYS contains a duplicate key');
  }
  const byKey = new Map(rows.map((row) => [row.key, row]));
  const unknownKeys = requestedKeys.filter((key) => !byKey.has(key));
  if (unknownKeys.length) {
    throw new Error(`BW_EEVEE_MATRIX_KEYS contains unknown keys: ${unknownKeys.join(',')}`);
  }
  return {
    rows: requestedKeys.map((key) => byKey.get(key)),
    mode: 'exact-key-subset',
    requestedKeys,
  };
}

function readOptionalMap(path, kind, expectedFields, { requireHash = false } = {}) {
  if (!path) return { path: null, sha256: null, entries: new Map() };
  const mapPath = absoluteInputPath(path);
  const bytes = readFileSync(mapPath);
  const entries = new Map();
  for (const parsed of parseTsv(bytes.toString('utf8'), mapPath)) {
    if (parsed.fields.length !== expectedFields) {
      throw new Error(
        `${mapPath}:${parsed.lineNumber}: ${kind} map expects ${expectedFields} fields`);
    }
    const [directory, test, value, expectedSha256] = parsed.fields;
    const key = `${directory}/${test}`;
    if (entries.has(key)) throw new Error(`${mapPath}:${parsed.lineNumber}: duplicate ${key}`);
    if (!directory || !test || !value) {
      throw new Error(`${mapPath}:${parsed.lineNumber}: ${kind} row has an empty required field`);
    }
    if (requireHash && !/^[0-9a-f]{64}$/.test(expectedSha256 || '')) {
      throw new Error(`${mapPath}:${parsed.lineNumber}: ${kind} hash is required for ${key}`);
    }
    entries.set(key, { value, expectedSha256: expectedSha256 || null, line: parsed.lineNumber });
  }
  return { path: mapPath, sha256: sha256Bytes(bytes), entries };
}

function validateFixtureMapProvenance(prebaked, rows, inputContract) {
  if (!prebaked.path) return null;
  const receiptPath = join(dirname(prebaked.path), 'fixture-map.receipt.json');
  if (!existsSync(receiptPath)) {
    throw new Error(`prebaked fixture map is missing adjacent receipt: ${receiptPath}`);
  }
  const receiptBytes = readFileSync(receiptPath);
  const receipt = JSON.parse(receiptBytes.toString('utf8'));
  const expectedFixtureKeys = new Set(
    rows.filter((row) => !inputContract.entries.get(row.key).skipProbes).map((row) => row.key));
  const actualFixtureKeys = new Set(prebaked.entries.keys());
  if (actualFixtureKeys.size !== EXPECTED_PREBAKED_ROWS ||
      [...expectedFixtureKeys].some((key) => !actualFixtureKeys.has(key)) ||
      [...actualFixtureKeys].some((key) => !expectedFixtureKeys.has(key)))
  {
    throw new Error(
      `prebaked fixture map must cover the exact ${EXPECTED_PREBAKED_ROWS} non-skip rows`);
  }
  const exclusion = receipt?.selection?.exclusion;
  const completed = receipt?.progress?.rows;
  const completedByKey = new Map(
    Array.isArray(completed) ? completed.map((item) => [item.key, item]) : []);
  const skipRow = rows.find((row) => row.key === PROBE_SKIP_KEY);
  const skipContract = inputContract.entries.get(PROBE_SKIP_KEY);
  const errors = [];
  if (receipt?.schema !== 'blender-web.eevee-native-prebake-map-receipt.v1') errors.push('schema');
  if (receipt?.status !== 'PASS') errors.push(`status=${receipt?.status}`);
  if (receipt?.run?.serialExecution !== true || receipt?.run?.maximumNativeConcurrency !== 1) {
    errors.push('native serialization');
  }
  if (receipt?.sources?.manifest?.path !== MANIFEST_PATH ||
      receipt?.sources?.manifest?.sha256 !== sha256File(MANIFEST_PATH))
  {
    errors.push('manifest identity');
  }
  if (receipt?.sources?.setup?.path !== UPSTREAM_EEVEE_RUNNER ||
      receipt?.sources?.setup?.sha256 !== sha256File(UPSTREAM_EEVEE_RUNNER))
  {
    errors.push('upstream setup identity');
  }
  if (receipt?.sources?.inputContract?.path !== inputContract.path ||
      receipt?.sources?.inputContract?.sha256 !== inputContract.sha256)
  {
    errors.push('input-contract identity');
  }
  if (receipt?.sources?.worker?.path !== FIXTURE_WORKER ||
      receipt?.sources?.worker?.sha256 !== sha256File(FIXTURE_WORKER) ||
      receipt?.sources?.runner?.path !== FIXTURE_GENERATOR ||
      receipt?.sources?.runner?.sha256 !== sha256File(FIXTURE_GENERATOR))
  {
    errors.push('fixture tool identity');
  }
  const receiptBlender = receipt?.sources?.blender;
  if (receipt?.sources?.pin?.path !== PIN_FILE ||
      receipt?.sources?.pin?.buildHash !== PINNED_BUILD_HASH ||
      readFileSync(PIN_FILE, 'utf8').trim().split(/\s+/)[0] !== PINNED_BUILD_HASH ||
      !receiptBlender?.path || !existsSync(receiptBlender.path) ||
      receiptBlender.sha256 !== PINNED_OFFICIAL_BLENDER_SHA256 ||
      sha256File(receiptBlender.path) !== PINNED_OFFICIAL_BLENDER_SHA256)
  {
    errors.push('official Blender identity');
  }
  if (receipt?.selection?.manifestRows !== EXPECTED_EEVEE_ROWS ||
      receipt?.selection?.bakeRows !== EXPECTED_PREBAKED_ROWS ||
      receipt?.selection?.excludedRows !== 1 || exclusion?.key !== PROBE_SKIP_KEY ||
      exclusion?.input !== skipRow?.blendPath ||
      exclusion?.inputSha256 !== skipContract?.inputSha256 ||
      exclusion?.predicate !== 'EEVEE_skip_probes_setup=true' ||
      exclusion?.verification?.schema !==
        'blender-web.eevee-native-prebake-exclusion.v1' ||
      exclusion?.verification?.row !== PROBE_SKIP_KEY ||
      exclusion?.verification?.input?.path !== skipRow?.blendPath ||
      exclusion?.verification?.input?.sha256 !== skipContract?.inputSha256 ||
      exclusion?.verification?.setup?.sha256 !== receipt?.sources?.setup?.sha256 ||
      exclusion?.verification?.input_contract?.sha256 !== inputContract.sha256 ||
      exclusion?.verification?.worker?.sha256 !== receipt?.sources?.worker?.sha256 ||
      exclusion?.verification?.blender?.sha256 !== PINNED_OFFICIAL_BLENDER_SHA256 ||
      !exclusion?.verification?.blender?.build_hash?.startsWith(PINNED_BUILD_HASH) ||
      exclusion?.verification?.bake_executed !== false ||
      exclusion?.verification?.output_fixture !== null ||
      exclusion?.verification?.render_sampling?.scene_count !== skipContract?.sceneCount ||
      exclusion?.verification?.render_sampling?.effective !== skipContract?.effectiveSamples ||
      exclusion?.verification?.scene_flags?.length !== skipContract?.sceneCount ||
      !exclusion?.verification?.scene_flags?.every(
        (item) => item.EEVEE_skip_probes_setup === true))
  {
    errors.push('selection/exclusion');
  }
  if (receipt?.progress?.completed !== EXPECTED_PREBAKED_ROWS ||
      receipt?.progress?.pending !== 0 || completedByKey.size !== EXPECTED_PREBAKED_ROWS)
  {
    errors.push('completion cardinality');
  }
  if (receipt?.fixtureMap?.path !== prebaked.path ||
      receipt?.fixtureMap?.sha256 !== prebaked.sha256 ||
      receipt?.fixtureMap?.rows !== EXPECTED_PREBAKED_ROWS)
  {
    errors.push('fixture-map identity');
  }
  for (const [key, entry] of prebaked.entries) {
    const item = completedByKey.get(key);
    const row = rows.find((candidate) => candidate.key === key);
    const contract = inputContract.entries.get(key);
    const outputPath = absoluteInputPath(entry.value);
    const outputValid = existsSync(outputPath) && sha256File(outputPath) === entry.expectedSha256;
    const receiptValid = typeof item?.receipt === 'string' && existsSync(item.receipt) &&
      /^[0-9a-f]{64}$/.test(item?.receiptSha256 || '') &&
      sha256File(item.receipt) === item.receiptSha256;
    let rowReceipt = null;
    if (receiptValid) {
      try {
        rowReceipt = JSON.parse(readFileSync(item.receipt, 'utf8'));
      }
      catch {
        rowReceipt = null;
      }
    }
    if (!item || item.output !== outputPath || item.outputSha256 !== entry.expectedSha256 ||
        item.input !== row?.blendPath || item.inputSha256 !== contract?.inputSha256 ||
        item.expectedRenderSamples !== contract?.effectiveSamples || !outputValid ||
        !/^[0-9a-f]{64}$/.test(item.receiptSha256 || '') ||
        !receiptValid ||
        rowReceipt?.schema !== 'blender-web.eevee-native-prebake-receipt.v2' ||
        rowReceipt?.row !== key || rowReceipt?.input?.path !== row?.blendPath ||
        rowReceipt?.input?.sha256 !== contract?.inputSha256 ||
        rowReceipt?.input_contract?.sha256 !== inputContract.sha256 ||
        rowReceipt?.setup?.sha256 !== receipt?.sources?.setup?.sha256 ||
        rowReceipt?.worker?.sha256 !== receipt?.sources?.worker?.sha256 ||
        rowReceipt?.blender?.sha256 !== PINNED_OFFICIAL_BLENDER_SHA256 ||
        !rowReceipt?.blender?.build_hash?.startsWith(PINNED_BUILD_HASH) ||
        rowReceipt?.output?.path !== outputPath ||
        rowReceipt?.output?.sha256 !== entry.expectedSha256 ||
        rowReceipt?.render_sampling?.scene_count !== contract?.sceneCount ||
        rowReceipt?.render_sampling?.effective !== contract?.effectiveSamples ||
        rowReceipt?.recognition_identity?.object_name !== 'Volume_Probe_Baked' ||
        rowReceipt?.recognition_identity?.data_name !== 'Volume_Probe_Baked' ||
        rowReceipt?.recognition_identity?.object_type !== 'LIGHT_PROBE' ||
        rowReceipt?.recognition_identity?.probe_type !== 'VOLUME')
    {
      errors.push(`completed fixture identity ${key}`);
    }
  }
  if (errors.length) {
    throw new Error(`prebaked fixture receipt invalid: ${errors.join(', ')}`);
  }
  return {
    path: receiptPath,
    sha256: sha256Bytes(receiptBytes),
    schema: receipt.schema,
    status: receipt.status,
    rows: receipt.fixtureMap.rows,
    exclusion: PROBE_SKIP_KEY,
  };
}

function resolveRowInputs(rows) {
  if (process.env.BW_EEVEE_MATRIX_SAMPLE_MAP !== undefined ||
      process.env.BW_EEVEE_MATRIX_DEFAULT_SAMPLES !== undefined)
  {
    throw new Error(
      'ad-hoc sample overrides are forbidden; update the pinned official-Blender input contract');
  }
  const canonicalProbes = process.env.BW_EEVEE_MATRIX_CANONICAL_PROBES === '1';
  if (canonicalProbes && process.env.BW_EEVEE_MATRIX_PREBAKED_MAP) {
    throw new Error(
      'canonical browser probes and native-prebaked fixtures are mutually exclusive setup routes');
  }
  const inputContract = readInputContract();
  const prebaked = readOptionalMap(
    process.env.BW_EEVEE_MATRIX_PREBAKED_MAP,
    'prebaked fixture',
    4,
    { requireHash: true });
  const rowKeys = new Set(rows.map((row) => row.key));
  for (const [key, contract] of inputContract.entries) {
    if (!rowKeys.has(key)) throw new Error(`input contract contains unknown row ${key}`);
    if (contract.sceneCount !== 1 || contract.contextMode !== 'OBJECT') {
      throw new Error(`unsupported pinned input shape for ${key}`);
    }
  }
  for (const [key] of prebaked.entries) {
    if (!rowKeys.has(key)) throw new Error(`prebaked fixture map contains unknown row ${key}`);
  }
  if (!canonicalProbes && !prebaked.path) {
    throw new Error(
      'exact upstream probe setup is uncovered: provide the complete guarded prebaked map or ' +
      'set BW_EEVEE_MATRIX_CANONICAL_PROBES=1');
  }
  const fixtureReceipt = validateFixtureMapProvenance(prebaked, rows, inputContract);
  const resolvedRows = rows.map((row) => {
    const contract = inputContract.entries.get(row.key);
    if (!contract || contract.inputSha256 !== sha256File(row.blendPath)) {
      throw new Error(`pinned input contract hash mismatch for ${row.key}`);
    }
    const fixtureEntry = prebaked.entries.get(row.key) || null;
    const actualBlendPath = fixtureEntry ? absoluteInputPath(fixtureEntry.value) : row.blendPath;
    if (!existsSync(actualBlendPath)) {
      throw new Error(`missing mapped prebaked fixture for ${row.key}: ${actualBlendPath}`);
    }
    const actualBlendSha256 = sha256File(actualBlendPath);
    if (fixtureEntry && fixtureEntry.expectedSha256 !== actualBlendSha256) {
      throw new Error(
        `prebaked fixture hash mismatch for ${row.key}: ` +
        `expected ${fixtureEntry.expectedSha256}, found ${actualBlendSha256}`);
    }
    const setupRoute = fixtureEntry ? 'guarded-native-prebaked' :
      contract.skipProbes ? 'upstream-scene-probe-skip' : 'browser-canonical-modal-bake';
    if (setupRoute === 'browser-canonical-modal-bake' && !canonicalProbes) {
      throw new Error(`probe-dependent row has no exact setup route: ${row.key}`);
    }
    return {
      ...row,
      expectedSamples: contract.effectiveSamples,
      expectedViewTransform: contract.viewTransform,
      expectedColorMode: contract.colorMode,
      sampleSource: `${inputContract.path}:${contract.line}`,
      inputContract: contract,
      setupRoute,
      canonicalProbesRequested: canonicalProbes,
      actualBlendPath,
      actualBlendSha256,
      manifestBlendSha256: sha256File(row.blendPath),
      goldenSha256: sha256File(row.goldenPath),
      blendSource: fixtureEntry ? 'native-prebaked-map' : 'manifest',
      prebakedMapLine: fixtureEntry?.line ?? null,
    };
  });
  return {
    rows: resolvedRows,
    mapping: {
      prebaked: {
        path: prebaked.path,
        sha256: prebaked.sha256,
        mappedRows: prebaked.entries.size,
        requiredWhenCanonicalProbeBakeDisabled: true,
        receipt: fixtureReceipt,
      },
      inputContract: {
        path: inputContract.path,
        sha256: inputContract.sha256,
        rows: inputContract.entries.size,
        sampleDistribution: Object.fromEntries(
          [...new Set([...inputContract.entries.values()].map((entry) => entry.effectiveSamples))]
            .sort((a, b) => a - b)
            .map((samples) => [
              String(samples),
              [...inputContract.entries.values()].filter(
                (entry) => entry.effectiveSamples === samples).length,
            ])),
      },
      exactSetupRoutes: Object.fromEntries(
        [...new Set(resolvedRows.map((row) => row.setupRoute))].map((route) => [
          route,
          resolvedRows.filter((row) => row.setupRoute === route).length,
        ])),
    },
  };
}

function replaceLiteralOnce(source, before, after, seam) {
  const first = source.indexOf(before);
  const second = first < 0 ? -1 : source.indexOf(before, first + before.length);
  if (first < 0 || second >= 0) {
    throw new Error(
      `canonical driver ${seam} seam count changed: ` +
      `${first < 0 ? 0 : second < 0 ? 1 : 'more-than-one'}`);
  }
  return source.slice(0, first) + after + source.slice(first + before.length);
}

function replaceLiteralCount(source, before, after, expectedCount, seam) {
  const count = source.split(before).length - 1;
  if (count !== expectedCount) {
    throw new Error(`canonical driver ${seam} seam count changed: ${count}`);
  }
  return source.split(before).join(after);
}

function replaceLineOnce(source, pattern, replacement, seam) {
  const matches = source.match(new RegExp(pattern.source, `${pattern.flags.replace('g', '')}g`)) || [];
  if (matches.length !== 1) {
    throw new Error(`canonical driver ${seam} seam count changed: ${matches.length}`);
  }
  return source.replace(pattern, replacement);
}

function safeToken(value) {
  return value.replace(/[^A-Za-z0-9._-]+/g, '-');
}

function validRunRoot(path) {
  return typeof path === 'string' && dirname(path) === RUNS_ROOT &&
    /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(basename(path));
}

function makeTemporaryDriver(canonicalSource, canonicalInputs, row, rowOutputDir, runLabel) {
  const outputLabel = safeToken(`${runLabel}-eevee-${row.directory}-${row.test}`);
  const opfsName = safeToken(`bw_f12_eevee_${row.directory}_${row.test}.blend`);
  let source = canonicalSource;
  const substitutions = {
    blendHost: row.actualBlendPath,
    blendSource: row.blendSource,
    blendSha256: row.actualBlendSha256,
    goldenHost: row.goldenPath,
    goldenSha256: row.goldenSha256,
    expectedSamples: row.expectedSamples,
    expectedViewTransform: row.expectedViewTransform,
    expectedColorMode: row.expectedColorMode,
    failThreshold: row.failThreshold,
    failPercent: row.failPercent,
    outputDir: rowOutputDir,
    outputLabel,
    opfsName,
    manifestSelector: `eevee/${row.directory}/${row.test}`,
    repositoryRoot: ROOT,
    nodeModuleRoots: NODE_MODULE_ROOTS,
    browserArgs: BROWSER_ARGS,
    servedShellFiles: 6,
  };
  source = replaceLineOnce(
    source,
    /^const ROOT = .*;$/m,
    `const ROOT = ${JSON.stringify(ROOT)};`,
    'ROOT');
  source = replaceLineOnce(
    source,
    /^const OUTDIR = .*;$/m,
    `const OUTDIR = ${JSON.stringify(rowOutputDir)};`,
    'OUTDIR');
  source = replaceLineOnce(
    source,
    /^const BLEND_HOST = .*;$/m,
    `const BLEND_HOST = ${JSON.stringify(row.actualBlendPath)};`,
    'BLEND_HOST');
  source = replaceLineOnce(
    source,
    /^const GOLDEN_HOST = .*;$/m,
    `const GOLDEN_HOST = ${JSON.stringify(row.goldenPath)};`,
    'GOLDEN_HOST');
  source = replaceLineOnce(
    source,
    /^const OPFS_NAME = .*;$/m,
    `const OPFS_NAME = ${JSON.stringify(opfsName)};`,
    'OPFS_NAME');
  source = replaceLineOnce(
    source,
    /^const FAIL_THRESHOLD = .*;$/m,
    `const FAIL_THRESHOLD = ${JSON.stringify(row.failThreshold)};`,
    'FAIL_THRESHOLD');
  source = replaceLineOnce(
    source,
    /^const FAIL_PERCENT = .*;$/m,
    `const FAIL_PERCENT = ${JSON.stringify(row.failPercent)};`,
    'FAIL_PERCENT');
  source = replaceLineOnce(
    source,
    /^const EXPECTED_RENDER_SAMPLES = RENDER_SAMPLES_OVERRIDE \?\? \d+;$/m,
    `const EXPECTED_RENDER_SAMPLES = RENDER_SAMPLES_OVERRIDE ?? ${row.expectedSamples};`,
    'EXPECTED_RENDER_SAMPLES');
  source = replaceLineOnce(
    source,
    /^const EXPECTED_VIEW_TRANSFORM = .*;$/m,
    `const EXPECTED_VIEW_TRANSFORM = ${JSON.stringify(row.expectedViewTransform)};`,
    'EXPECTED_VIEW_TRANSFORM');
  source = replaceLineOnce(
    source,
    /^const EXPECTED_COLOR_MODE = .*;$/m,
    `const EXPECTED_COLOR_MODE = ${JSON.stringify(row.expectedColorMode)};`,
    'EXPECTED_COLOR_MODE');
  source = replaceLineOnce(
    source,
    /^const OIIOTOOL = .*;$/m,
    "const OIIOTOOL = process.env.OIIOTOOL || 'oiiotool';",
    'OIIOTOOL');
  source = replaceLiteralOnce(
    source,
    "  windowed: `${ROOT}/platform_web/shell/windowed.html`,\n  boot: `${ROOT}/platform_web/shell/boot-windowed.js`,",
    "  windowed: `${ROOT}/platform_web/shell/windowed.html`,\n  diagnostics: `${ROOT}/platform_web/shell/diagnostics-bootstrap.js`,\n  boot: `${ROOT}/platform_web/shell/boot-windowed.js`,",
    'diagnostics shell identity');
  source = replaceLiteralOnce(
    source,
    "    const paths = {index: '/index.html', windowed: '/windowed.html', boot: '/boot-windowed.js',\n      fileBridge: '/file-bridge.js', preinit: '/wgpu-preinit-worker.js'};",
    "    const paths = {index: '/index.html', windowed: '/windowed.html',\n      diagnostics: '/diagnostics-bootstrap.js', boot: '/boot-windowed.js',\n      fileBridge: '/file-bridge.js', preinit: '/wgpu-preinit-worker.js'};",
    'served diagnostics shell identity');
  source = replaceLiteralOnce(
    source,
    "Object.keys(localShellReceipts()).sort().join(',') === 'boot,fileBridge,index,preinit,windowed'",
    "Object.keys(localShellReceipts()).sort().join(',') === 'boot,diagnostics,fileBridge,index,preinit,windowed'",
    'shell self-check identity');
  const playwrightLoader = [
    `const __bwModuleRoots = ${JSON.stringify(NODE_MODULE_ROOTS)};`,
    'let chromium = null;',
    'let __bwPlaywrightRoot = null;',
    'for (const moduleRoot of __bwModuleRoots) {',
    '  try {',
    "    chromium = createRequire(moduleRoot + '/package.json')('playwright').chromium;",
    '    __bwPlaywrightRoot = moduleRoot;',
    '    break;',
    '  } catch {}',
    '}',
    "if (chromium === null) throw new Error('playwright is unavailable; checked module roots: ' + __bwModuleRoots.join(', '));",
    `const __bwBrowserArgs = ${JSON.stringify(BROWSER_ARGS)};`,
  ].join('\n');
  source = replaceLiteralOnce(
    source,
    "const require = createRequire('/Users/paws/plushly/game-platform/node_modules/');\nconst { chromium } = require('playwright');",
    playwrightLoader,
    'Playwright module root');
  source = replaceLiteralCount(
    source,
    "['--enable-unsafe-webgpu', '--use-angle=metal', '--disable-dev-tools']",
    '__bwBrowserArgs',
    2,
    'browser platform arguments');
  source = replaceLiteralOnce(
    source,
    "    engine: 'playwright-chromium',\n    headed: true,",
    "    engine: 'playwright-chromium',\n    playwrightRoot: __bwPlaywrightRoot,\n    headed: true,",
    'Playwright receipt root');
  source = replaceLiteralOnce(
    source,
    "  'eevee-principled-default-f12';",
    `  ${JSON.stringify(outputLabel)};`,
    'default output label');
  source = replaceLiteralOnce(
    source,
    "line.startsWith('eevee\\tprincipled_bsdf\\tprincipled_bsdf_default\\t')",
    `line.startsWith(${JSON.stringify(`eevee\t${row.directory}\t${row.test}\t`)})`,
    'manifest-row selector');
  source = replaceLiteralOnce(
    source,
    canonicalInputs.blendSha256,
    row.actualBlendSha256,
    'blend self-check hash');
  source = replaceLiteralOnce(
    source,
    canonicalInputs.goldenSha256,
    row.goldenSha256,
    'golden self-check hash');
  return {
    source,
    sourceSha256: sha256Bytes(source),
    outputLabel,
    opfsName,
    substitutions,
  };
}

function canonicalInputHashes(canonicalSource) {
  const blendPath =
    `${ROOT}/upstream/tests/files/render/principled_bsdf/principled_bsdf_default.blend`;
  const goldenPath =
    `${ROOT}/sandbox/m6-prep/goldens/eevee/principled_bsdf/principled_bsdf_default.png`;
  const blendSha256 = sha256File(blendPath);
  const goldenSha256 = sha256File(goldenPath);
  if (!canonicalSource.includes(blendSha256) || !canonicalSource.includes(goldenSha256)) {
    throw new Error('canonical driver input hash self-check seams do not match current input files');
  }
  return { blendPath, blendSha256, goldenPath, goldenSha256 };
}

function temporaryPlan(rows, runRoot, runLabel) {
  const canonicalBytes = readFileSync(CANONICAL_DRIVER);
  const canonicalSource = canonicalBytes.toString('utf8');
  const canonicalInputs = canonicalInputHashes(canonicalSource);
  const temporaryRoot = mkdtempSync(join(tmpdir(), 'bw-eevee-matrix-'));
  const plan = rows.map((row) => {
    const rowSlug = safeToken(`${String(row.index).padStart(2, '0')}-${row.directory}-${row.test}`);
    const rowOutputDir = `${runRoot}/rows/${rowSlug}`;
    const generated = makeTemporaryDriver(
      canonicalSource, canonicalInputs, row, rowOutputDir, runLabel);
    const driverPath = `${temporaryRoot}/${rowSlug}.mjs`;
    writeFileSync(driverPath, generated.source);
    return { ...row, ...generated, rowSlug, rowOutputDir, driverPath };
  });
  return {
    plan,
    temporaryRoot,
    canonical: {
      path: CANONICAL_DRIVER,
      sha256: sha256Bytes(canonicalBytes),
      inputs: canonicalInputs,
    },
  };
}

function validateThresholdSources() {
  const child = spawnSync('python3', [THRESHOLD_VALIDATOR], {
    cwd: ROOT,
    encoding: 'utf8',
    timeout: 120000,
  });
  if (child.status !== 0 || !child.stdout.includes('PASS: 30 EEVEE manifest rows')) {
    throw new Error(
      `pinned EEVEE threshold validation failed: ${child.stderr || child.stdout}`);
  }
  return {
    validator: { path: THRESHOLD_VALIDATOR, sha256: sha256File(THRESHOLD_VALIDATOR) },
    upstreamRunner: { path: UPSTREAM_EEVEE_RUNNER, sha256: sha256File(UPSTREAM_EEVEE_RUNNER) },
    output: child.stdout.trim(),
  };
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

function selfcheck() {
  const expectedBrowserArgs = process.platform === 'darwin' ?
    ['--enable-unsafe-webgpu', '--use-angle=metal', '--disable-dev-tools'] :
    ['--enable-unsafe-webgpu', '--disable-dev-tools'];
  if (!existsSync(`${ROOT}/GOAL.md`) || HERE !== dirname(HARNESS_PATH) ||
      NODE_MODULE_ROOTS.length < 2 || !NODE_MODULE_ROOTS.every(isAbsolute) ||
      JSON.stringify(BROWSER_ARGS) !== JSON.stringify(expectedBrowserArgs) ||
      !validRunRoot(`${RUNS_ROOT}/selfcheck`) || validRunRoot(RUNS_ROOT) ||
      validRunRoot(`${RUNS_ROOT}/nested/child`) ||
      validRunRoot(`${HERE}/runs-escape/child`))
  {
    throw new Error('repository-root/run-directory portability self-check failed');
  }
  const baseRows = readEeveeRows();
  const oldPrebaked = process.env.BW_EEVEE_MATRIX_PREBAKED_MAP;
  const oldSamples = process.env.BW_EEVEE_MATRIX_SAMPLE_MAP;
  const oldDefaultSamples = process.env.BW_EEVEE_MATRIX_DEFAULT_SAMPLES;
  const oldCanonicalProbes = process.env.BW_EEVEE_MATRIX_CANONICAL_PROBES;
  delete process.env.BW_EEVEE_MATRIX_PREBAKED_MAP;
  delete process.env.BW_EEVEE_MATRIX_SAMPLE_MAP;
  delete process.env.BW_EEVEE_MATRIX_DEFAULT_SAMPLES;
  process.env.BW_EEVEE_MATRIX_CANONICAL_PROBES = '1';
  let generated;
  let lockSelfcheckRoot;
  try {
    const thresholds = validateThresholdSources();
    const resolved = resolveRowInputs(baseRows);
    const sampleCounts = Object.fromEntries(
      [64, 128, 800].map((samples) => [
        String(samples),
        resolved.rows.filter((row) => row.expectedSamples === samples).length,
      ]));
    const viewTransformCounts = Object.fromEntries(
      [...new Set(resolved.rows.map((row) => row.expectedViewTransform))]
        .sort()
        .map((viewTransform) => [
          viewTransform,
          resolved.rows.filter((row) => row.expectedViewTransform === viewTransform).length,
        ]));
    if (JSON.stringify(sampleCounts) !== JSON.stringify({ 64: 27, 128: 1, 800: 2 }) ||
        JSON.stringify(viewTransformCounts) !==
          JSON.stringify({ 'ACES 2.0': 1, AgX: 4, Standard: 25 }) ||
        resolved.rows.find((row) => row.key === 'raycast/raycast_bump')?.expectedSamples !== 128 ||
        resolved.rows.find((row) => row.key === 'transparency/transparency_blended')
          ?.expectedSamples !== 800 ||
        resolved.mapping.exactSetupRoutes['browser-canonical-modal-bake'] !== 29 ||
        resolved.mapping.exactSetupRoutes['upstream-scene-probe-skip'] !== 1)
    {
      throw new Error('pinned input samples/setup routes are not stable');
    }
    delete process.env.BW_EEVEE_MATRIX_CANONICAL_PROBES;
    let uncoveredRefused = false;
    try {
      resolveRowInputs(baseRows);
    }
    catch (error) {
      uncoveredRefused = /exact upstream probe setup is uncovered/.test(String(error));
    }
    process.env.BW_EEVEE_MATRIX_CANONICAL_PROBES = '1';
    process.env.BW_EEVEE_MATRIX_DEFAULT_SAMPLES = '7';
    let sampleOverrideRefused = false;
    try {
      resolveRowInputs(baseRows);
    }
    catch (error) {
      sampleOverrideRefused = /ad-hoc sample overrides are forbidden/.test(String(error));
    }
    delete process.env.BW_EEVEE_MATRIX_DEFAULT_SAMPLES;
    process.env.BW_EEVEE_MATRIX_PREBAKED_MAP = '/unused/mutually-exclusive-map.tsv';
    let conflictingRoutesRefused = false;
    try {
      resolveRowInputs(baseRows);
    }
    catch (error) {
      conflictingRoutesRefused = /mutually exclusive setup routes/.test(String(error));
    }
    delete process.env.BW_EEVEE_MATRIX_PREBAKED_MAP;
    if (!uncoveredRefused || !sampleOverrideRefused || !conflictingRoutesRefused) {
      throw new Error('setup-route/sample-override refusal self-check failed');
    }
    lockSelfcheckRoot = mkdtempSync(join(tmpdir(), 'bw-eevee-gpu-lock-selfcheck-'));
    const firstLock = acquireExclusiveGpuLock(
      `${lockSelfcheckRoot}/lock`, { role: 'selfcheck', runLabel: 'first' });
    let concurrentLockRefused = false;
    try {
      acquireExclusiveGpuLock(
        `${lockSelfcheckRoot}/lock`, { role: 'selfcheck', runLabel: 'second' });
    }
    catch (error) {
      concurrentLockRefused = /refusing concurrent EEVEE GPU work/.test(String(error));
    }
    releaseExclusiveGpuLock(firstLock);
    if (!concurrentLockRefused) throw new Error('global GPU lock refusal self-check failed');
    generated = temporaryPlan(resolved.rows, `${tmpdir()}/bw-eevee-matrix-selfcheck-out`, 'selfcheck');
    const driverEnvironment = productEnvironment();
    for (const row of generated.plan) {
      const syntax = spawnSync(process.execPath, ['--check', row.driverPath], {
        cwd: ROOT, encoding: 'utf8', timeout: 120000,
      });
      if (syntax.status !== 0) {
        throw new Error(`generated syntax failed for ${row.key}: ${syntax.stderr || syntax.stdout}`);
      }
      const driverCheck = spawnSync(process.execPath, [row.driverPath, '--selfcheck'], {
        cwd: ROOT, env: driverEnvironment, encoding: 'utf8', timeout: 120000,
        maxBuffer: 8 * 1024 * 1024,
      });
      if (driverCheck.status !== 0 || !driverCheck.stdout.includes('SELF_CHECK_PASS')) {
        throw new Error(
          `generated driver self-check failed for ${row.key}: ` +
          `${driverCheck.stderr || driverCheck.stdout}`);
      }
      if (!row.source.includes(
        `const EXPECTED_RENDER_SAMPLES = RENDER_SAMPLES_OVERRIDE ?? ${row.expectedSamples};`))
      {
        throw new Error(`sample expectation substitution missing for ${row.key}`);
      }
      if (!row.source.includes(
        `const EXPECTED_VIEW_TRANSFORM = ${JSON.stringify(row.expectedViewTransform)};`))
      {
        throw new Error(`view-transform expectation substitution missing for ${row.key}`);
      }
      if (!row.source.includes(
        `const EXPECTED_COLOR_MODE = ${JSON.stringify(row.expectedColorMode)};`))
      {
        throw new Error(`color-mode expectation substitution missing for ${row.key}`);
      }
      if (row.substitutions.failThreshold !== row.failThreshold ||
          row.substitutions.failPercent !== row.failPercent)
      {
        throw new Error(`comparator substitution mismatch for ${row.key}`);
      }
      const portabilityChecks = [
        row.source.includes(`const ROOT = ${JSON.stringify(ROOT)};`),
        !row.source.includes("const ROOT = '/Users/paws/blender-web';"),
        row.source.includes('const __bwModuleRoots = '),
        row.source.includes("createRequire(moduleRoot + '/package.json')('playwright').chromium"),
        !row.source.includes("const { chromium } = require('playwright');"),
        row.source.includes(`const __bwBrowserArgs = ${JSON.stringify(BROWSER_ARGS)};`),
        row.source.includes('diagnostics-bootstrap.js'),
        row.source.includes("const OIIOTOOL = process.env.OIIOTOOL || 'oiiotool';"),
        row.substitutions.repositoryRoot === ROOT,
        JSON.stringify(row.substitutions.nodeModuleRoots) === JSON.stringify(NODE_MODULE_ROOTS),
        JSON.stringify(row.substitutions.browserArgs) === JSON.stringify(BROWSER_ARGS),
        row.substitutions.servedShellFiles === 6,
      ];
      if (!portabilityChecks.every(Boolean)) {
        throw new Error(`host-portability substitution mismatch for ${row.key}`);
      }
    }
    const categoryCounts = Object.fromEntries(
      [...new Set(baseRows.map((row) => row.directory))].map((directory) => [
        directory,
        baseRows.filter((row) => row.directory === directory).length,
      ]));
    console.log(
      `SELF_CHECK_PASS harness=eevee-matrix rows=${generated.plan.length} ` +
      `generated_driver_syntax=${generated.plan.length} ` +
      `generated_driver_selfchecks=${generated.plan.length} browser_launches=0 ` +
      `gpu_concurrency=1 setup_coverage=PASS samples=${JSON.stringify(sampleCounts)} ` +
      `view_transforms=${JSON.stringify(viewTransformCounts)} ` +
      `root=${ROOT} shell_files=6 browser_args=${JSON.stringify(BROWSER_ARGS)} ` +
      `thresholds_sha256=${thresholds.upstreamRunner.sha256} ` +
      `categories=${JSON.stringify(categoryCounts)}`);
  }
  finally {
    if (generated?.temporaryRoot) rmSync(generated.temporaryRoot, { recursive: true, force: true });
    if (lockSelfcheckRoot) rmSync(lockSelfcheckRoot, { recursive: true, force: true });
    if (oldPrebaked === undefined) delete process.env.BW_EEVEE_MATRIX_PREBAKED_MAP;
    else process.env.BW_EEVEE_MATRIX_PREBAKED_MAP = oldPrebaked;
    if (oldSamples === undefined) delete process.env.BW_EEVEE_MATRIX_SAMPLE_MAP;
    else process.env.BW_EEVEE_MATRIX_SAMPLE_MAP = oldSamples;
    if (oldDefaultSamples === undefined) delete process.env.BW_EEVEE_MATRIX_DEFAULT_SAMPLES;
    else process.env.BW_EEVEE_MATRIX_DEFAULT_SAMPLES = oldDefaultSamples;
    if (oldCanonicalProbes === undefined) delete process.env.BW_EEVEE_MATRIX_CANONICAL_PROBES;
    else process.env.BW_EEVEE_MATRIX_CANONICAL_PROBES = oldCanonicalProbes;
  }
}

function atomicWrite(path, text) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.tmp`;
  writeFileSync(temporary, text);
  renameSync(temporary, path);
}

function writeCc0Artifact(path, text) {
  atomicWrite(path, text);
  atomicWrite(`${path}.license`, CC0);
}

function cleanTsv(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(/[\t\r\n]+/g, ' ');
}

function resultsTsv(results) {
  const header = [
    'index', 'engine', 'dir', 'test', 'blend_source', 'setup_route', 'samples', 'color_mode',
    'fail_threshold', 'fail_percent', 'label', 'exit_status', 'signal', 'verdict', 'binding_ok',
    'binding_errors', 'comparator_pass',
    'max_error', 'percent_over', 'gpu_errors', 'page_errors', 'page_crash',
    'run_error', 'manifest_sha256', 'manifest_path', 'log_path',
  ];
  const lines = [
    '# SPDX-FileCopyrightText: 2026 blender-web contributors',
    '# SPDX-License-Identifier: CC0-1.0',
    `# ${header.join('\t')}`,
  ];
  for (const result of results) {
    const row = result.row;
    lines.push([
      row.index,
      row.engine,
      row.directory,
      row.test,
      row.blendSource,
      row.setupRoute,
      row.expectedSamples,
      row.expectedColorMode,
      row.failThreshold,
      row.failPercent,
      row.outputLabel,
      result.process.status,
      result.process.signal,
      result.verdict,
      result.receiptBinding.ok,
      result.receiptBinding.errors.join('; '),
      result.comparator.pass,
      result.comparator.maxError,
      result.comparator.percentOver,
      result.failures.gpuErrors,
      result.failures.pageErrors,
      result.failures.pageCrash,
      result.failures.runError,
      result.manifest.sha256,
      result.manifest.path,
      result.log.path,
    ].map(cleanTsv).join('\t'));
  }
  return `${lines.join('\n')}\n`;
}

function parseManifest(path) {
  if (!existsSync(path)) return { receipt: null, error: 'manifest not produced' };
  try {
    return { receipt: JSON.parse(readFileSync(path, 'utf8')), error: null };
  }
  catch (error) {
    return { receipt: null, error: `manifest parse failed: ${error.message}` };
  }
}

function summarize(results, total) {
  const verdicts = {};
  for (const result of results) {
    verdicts[result.verdict] = (verdicts[result.verdict] || 0) + 1;
  }
  return {
    total,
    completed: results.length,
    pending: total - results.length,
    pass: results.filter((result) => result.verdict === 'PASS').length,
    fail: results.filter((result) => result.verdict !== 'PASS').length,
    verdicts,
    rowsWithGpuErrors: results.filter((result) => result.failures.gpuErrors > 0).length,
  };
}

function consolidatedJson(results, total, status, provenancePath) {
  return {
    schema: 'blender-web.eevee-matrix-results.v1',
    generatedAt: new Date().toISOString(),
    status,
    summary: summarize(results, total),
    provenancePath,
    results,
  };
}

function validateRowManifestBinding(row, receipt) {
  const errors = [];
  if (!receipt) return { ok: false, errors: ['manifest absent or unparseable'] };
  if (receipt.schema !== 'blender-web.f12-eevee-acceptance.v4') errors.push('schema');
  if (!['PASS', 'FAIL'].includes(receipt.verdict)) errors.push(`verdict=${receipt.verdict}`);
  if (receipt.driver?.sha256 !== row.sourceSha256) errors.push('generated driver identity');
  if (receipt.inputs?.blend?.hostPath !== row.actualBlendPath ||
      receipt.inputs?.blend?.sha256 !== row.actualBlendSha256)
  {
    errors.push('blend identity');
  }
  if (receipt.inputs?.golden?.path !== row.goldenPath ||
      receipt.inputs?.golden?.sha256 !== row.goldenSha256)
  {
    errors.push('golden identity');
  }
  const canonicalProbeSource = receipt.inputs?.canonicalProbeSource;
  if (row.canonicalProbesRequested ?
    (canonicalProbeSource?.path !== UPSTREAM_EEVEE_RUNNER ||
      canonicalProbeSource?.sha256 !== sha256File(UPSTREAM_EEVEE_RUNNER)) :
    canonicalProbeSource !== null)
  {
    errors.push('canonical upstream probe source identity');
  }
  if (receipt.invocation?.method !== 'page.keyboard.press(F12)' ||
      receipt.invocation?.count !== 1 || receipt.invocation?.physicalTrustedF12 !== true ||
      receipt.invocation?.bpyRenderOperatorUsed !== false ||
      receipt.invocation?.pythonExprRenderOperatorAbsent !== true ||
      receipt.invocation?.renderPreReceipt?.status !== 'RENDER_PRE' ||
      receipt.invocation?.renderPreReceipt?.count !== 1 ||
      receipt.invocation?.renderPreReceipt?.engine !== 'BLENDER_EEVEE')
  {
    errors.push('physical-F12 invocation');
  }
  if (receipt.asyncContract?.mode !== 'product-marker-independent' ||
      receipt.asyncContract?.environment !== null ||
      receipt.asyncContract?.result?.markerIndependent !== true)
  {
    errors.push('marker-independent product mode');
  }
  if (receipt.render?.engine !== 'BLENDER_EEVEE' ||
      receipt.render?.expectedEffectiveSamples !== row.expectedSamples ||
      receipt.render?.configReceipt?.render_sampling?.effective !== row.expectedSamples ||
      receipt.render?.expectedViewTransform !== row.expectedViewTransform ||
      receipt.render?.configReceipt?.view_transform !== row.expectedViewTransform ||
      receipt.render?.completionReceipt?.view_transform !== row.expectedViewTransform ||
      receipt.render?.expectedColorMode !== row.expectedColorMode ||
      receipt.render?.configReceipt?.color_mode !== row.expectedColorMode ||
      receipt.render?.completionReceipt?.color_mode !== row.expectedColorMode)
  {
    errors.push('effective render samples');
  }
  if (receipt.comparator?.threshold !== row.failThreshold ||
      receipt.comparator?.failPercent !== row.failPercent ||
      receipt.comparator?.acceptanceGate !== true)
  {
    errors.push('comparator contract');
  }
  if (receipt.probePreparation?.requested !== row.canonicalProbesRequested) {
    errors.push('canonical-probe route');
  }
  if (row.canonicalProbesRequested) {
    const expectedProbeState = row.inputContract.skipProbes ?
      'SKIPPED_BY_SCENE' : 'BAKE_COMPLETE';
    if (receipt.probePreparation?.receipt?.state !== expectedProbeState ||
        receipt.probePreparation?.validation?.ok !== true ||
        receipt.probePreparation?.noF12BeforeTerminal !== true ||
        receipt.assertions?.canonicalProbePreparation !== true ||
        receipt.assertions?.noF12BeforeCanonicalProbeTerminal !== true ||
        receipt.invocation?.bpySetupOperatorsPresent !== true ||
        receipt.invocation?.bpySetupOperatorsExecuted !== !row.inputContract.skipProbes ||
        receipt.invocation?.bpyExecUsed !== !row.inputContract.skipProbes)
    {
      errors.push('canonical probe terminal/F12 order');
    }
  }
  else if (receipt.probePreparation?.receipt !== null ||
      receipt.assertions?.canonicalProbePreparation !== null ||
      receipt.assertions?.canonicalPassiveEeveeSetup !== true ||
      receipt.assertions?.noF12BeforeCanonicalProbeTerminal !== null ||
      receipt.invocation?.bpySetupOperatorsPresent !== false ||
      receipt.invocation?.bpySetupOperatorsExecuted !== false)
  {
    errors.push('guarded prebaked passive route');
  }
  const binaryReceipts = receipt.inputs?.shippingBinary || {};
  const expectedBinaryKeys = ['deferred', 'javascript', 'preload', 'wasm'];
  if (JSON.stringify(Object.keys(binaryReceipts).sort()) !== JSON.stringify(expectedBinaryKeys) ||
      !expectedBinaryKeys.every(
    (key) => /^[0-9a-f]{64}$/.test(binaryReceipts[key]?.sha256 || '') &&
      Number.isSafeInteger(binaryReceipts[key]?.bytes) && binaryReceipts[key].bytes > 0))
  {
    errors.push('shipping artifact identity');
  }
  const shellPaths = {
    index: `${ROOT}/platform_web/shell/index.html`,
    windowed: `${ROOT}/platform_web/shell/windowed.html`,
    diagnostics: `${ROOT}/platform_web/shell/diagnostics-bootstrap.js`,
    boot: `${ROOT}/platform_web/shell/boot-windowed.js`,
    fileBridge: `${ROOT}/platform_web/shell/file-bridge.js`,
    preinit: `${ROOT}/platform_web/shell/wgpu-preinit-worker.js`,
  };
  const servedShell = receipt.inputs?.servedShell || {};
  const expectedShell = receipt.inputs?.expectedServedShell || {};
  const shellKeys = ['boot', 'diagnostics', 'fileBridge', 'index', 'preinit', 'windowed'];
  if (JSON.stringify(Object.keys(servedShell).sort()) !== JSON.stringify(shellKeys) ||
      JSON.stringify(Object.keys(expectedShell).sort()) !== JSON.stringify(shellKeys) ||
      !shellKeys.every((key) => {
        const local = readFileSync(shellPaths[key]);
        const digest = sha256Bytes(local);
        return expectedShell[key]?.path === shellPaths[key] &&
          expectedShell[key]?.bytes === local.length && expectedShell[key]?.sha256 === digest &&
          servedShell[key]?.bytes === local.length && servedShell[key]?.sha256 === digest;
      }))
  {
    errors.push('served shell identity');
  }
  if (receipt.browser?.engine !== 'playwright-chromium' ||
      receipt.browser?.headed !== true ||
      !row.substitutions.nodeModuleRoots.includes(receipt.browser?.playwrightRoot) ||
      JSON.stringify(receipt.browser?.args) !== JSON.stringify(row.substitutions.browserArgs))
  {
    errors.push('browser identity');
  }
  if (receipt.verdict === 'PASS') {
    const requiredAssertions = [
      'opfsStartupFile',
      'physicalTrustedF12ExactlyOnce',
      'blenderRenderPreStartedExactlyOnce',
      'noBpyRenderOperator',
      'setupOperatorsPresentOnlyWhenCanonical',
      'computeWorkgroupStorageAtLeast32768',
      'colorAttachmentBytesPerSampleAtLeast36',
      'exactRenderSamplesAndViewTransform',
      'canonicalUpstreamEeveeSetup',
      'markerIndependentProductMode',
      'strippedDiagnosticEnvironmentAbsent',
      'wmTickAdvancedAfterRender',
      'renderHandlerCompletedExactlyOnce',
      'finitePng',
      'nonBlack',
      'comparatorPass',
      'noGpuError',
      'noPageError',
      'noPageCrash',
      'noHeartbeatError',
      'noRunError',
    ];
    if (requiredAssertions.some((key) => receipt.assertions?.[key] !== true)) {
      errors.push('PASS assertion set');
    }
  }
  return { ok: errors.length === 0, errors };
}

function rowResult(row, child, manifestPath, logPath) {
  const parsed = parseManifest(manifestPath);
  const receipt = parsed.receipt;
  const manifestSha256 = receipt ? sha256File(manifestPath) : null;
  const timedOut = child.error?.code === 'ETIMEDOUT';
  const manifestVerdict = receipt?.verdict || null;
  const receiptBinding = validateRowManifestBinding(row, receipt);
  const verdict = !receiptBinding.ok ? 'RIG_FAIL' :
    manifestVerdict === 'PASS' && child.status !== 0 ? 'RIG_FAIL' :
      manifestVerdict || (timedOut ? 'RIG_TIMEOUT' : parsed.error ? 'RIG_FAIL' : 'FAIL');
  return {
    row: {
      index: row.index,
      engine: row.engine,
      directory: row.directory,
      test: row.test,
      key: row.key,
      manifestLine: row.manifestLine,
      manifestBlendPath: row.blendPath,
      manifestBlendSha256: row.manifestBlendSha256,
      actualBlendPath: row.actualBlendPath,
      actualBlendSha256: row.actualBlendSha256,
      blendSource: row.blendSource,
      setupRoute: row.setupRoute,
      inputContract: row.inputContract,
      goldenPath: row.goldenPath,
      goldenSha256: row.goldenSha256,
      expectedSamples: row.expectedSamples,
      expectedViewTransform: row.expectedViewTransform,
      expectedColorMode: row.expectedColorMode,
      sampleSource: row.sampleSource,
      failThreshold: row.failThreshold,
      failPercent: row.failPercent,
      outputLabel: row.outputLabel,
      generatedDriverSha256: row.sourceSha256,
      substitutions: row.substitutions,
    },
    process: {
      status: child.status,
      signal: child.signal,
      error: child.error?.message || null,
      timedOut,
    },
    verdict,
    receiptBinding,
    comparator: {
      pass: receipt?.comparator?.result?.pass ?? null,
      maxError: receipt?.comparator?.result?.maxError ?? null,
      percentOver: receipt?.comparator?.result?.percentOver ?? null,
    },
    failures: {
      gpuErrors: receipt?.failures?.gpuErrors?.length ?? 0,
      pageErrors: receipt?.failures?.pageErrors?.length ?? 0,
      pageCrash: receipt?.failures?.pageCrashed ?? false,
      runError: receipt?.failures?.runError || parsed.error,
    },
    manifest: { path: receipt ? manifestPath : null, sha256: manifestSha256 },
    log: { path: logPath, sha256: sha256File(logPath) },
  };
}

function productEnvironment() {
  const env = { ...process.env };
  for (const key of STRIPPED_MATRIX_ENV) delete env[key];
  env.BW_EEVEE_PRODUCT_SMOKE = '1';
  if (process.env.BW_EEVEE_MATRIX_CANONICAL_PROBES === '1') {
    env.BW_EEVEE_CANONICAL_PROBES = '1';
  }
  if (process.env.BW_EEVEE_MATRIX_PROBE_TIMEOUT_MS) {
    env.BW_EEVEE_CANONICAL_PROBE_TIMEOUT_MS =
      process.env.BW_EEVEE_MATRIX_PROBE_TIMEOUT_MS;
  }
  return env;
}

function writeConsolidated(runRoot, results, total, status, provenancePath) {
  writeCc0Artifact(`${runRoot}/results.tsv`, resultsTsv(results));
  writeCc0Artifact(
    `${runRoot}/results.json`,
    `${JSON.stringify(consolidatedJson(results, total, status, provenancePath), null, 2)}\n`);
}

function main() {
  const runLabel = (process.argv[2] || '').trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(runLabel)) {
    throw new Error(
      `usage: node ${HARNESS_PATH} <unique-run-label>\n` +
      'run labels may contain only A-Z, a-z, 0-9, dot, underscore, and dash');
  }
  const port = requirePositiveInteger(
    process.env.BW_EEVEE_MATRIX_PORT, 'BW_EEVEE_MATRIX_PORT', DEFAULT_PORT);
  if (port > 65535) throw new Error(`BW_EEVEE_MATRIX_PORT out of range: ${port}`);
  const renderMs = requirePositiveInteger(
    process.env.BW_EEVEE_MATRIX_RENDER_MS,
    'BW_EEVEE_MATRIX_RENDER_MS',
    DEFAULT_RENDER_MS);
  if (renderMs < 2000) throw new Error('BW_EEVEE_MATRIX_RENDER_MS must be at least 2000');
  const processMs = requirePositiveInteger(
    process.env.BW_EEVEE_MATRIX_PROCESS_MS,
    'BW_EEVEE_MATRIX_PROCESS_MS',
    DEFAULT_PROCESS_MS);
  const thresholdSources = validateThresholdSources();
  const baseRows = readEeveeRows();
  const resolved = resolveRowInputs(baseRows);
  const selection = selectExactRows(resolved.rows, process.env.BW_EEVEE_MATRIX_KEYS);
  const runRoot = resolve(RUNS_ROOT, runLabel);
  if (!validRunRoot(runRoot)) {
    throw new Error(`refusing unsafe EEVEE run root: ${runRoot}`);
  }
  if (existsSync(runRoot)) throw new Error(`refusing to overwrite existing run: ${runRoot}`);

  let generated = null;
  let runCreated = false;
  let provenance = null;
  let gpuLock = null;
  const results = [];
  try {
    generated = temporaryPlan(selection.rows, runRoot, runLabel);
    for (const row of generated.plan) {
      const syntax = spawnSync(process.execPath, ['--check', row.driverPath], {
        cwd: ROOT, encoding: 'utf8', timeout: 120000,
      });
      if (syntax.status !== 0) {
        throw new Error(`generated syntax failed for ${row.key}: ${syntax.stderr || syntax.stdout}`);
      }
    }

    mkdirSync(RUNS_ROOT, { recursive: true });
    gpuLock = acquireExclusiveGpuLock(GPU_LOCK_PATH, {
      role: 'browser-matrix',
      runLabel,
      runRoot,
      maximumGpuConcurrency: 1,
    });
    mkdirSync(runRoot);
    mkdirSync(`${runRoot}/rows`);
    runCreated = true;
    const provenancePath = `${runRoot}/provenance.json`;
    provenance = {
      schema: 'blender-web.eevee-matrix-provenance.v1',
      status: 'RUNNING',
      generatedAt: new Date().toISOString(),
      completedAt: null,
      harness: { path: HARNESS_PATH, sha256: sha256File(HARNESS_PATH) },
      manifest: { path: MANIFEST_PATH, sha256: sha256File(MANIFEST_PATH) },
      inputContract: resolved.mapping.inputContract,
      thresholdSources,
      canonicalDriver: generated.canonical,
      run: {
        label: runLabel,
        root: runRoot,
        productMode: true,
        markerIndependent: true,
        physicalF12: true,
        browserRowsSerialized: true,
        maximumGpuConcurrency: 1,
        exclusiveGpuLock: gpuLock.receipt,
        port,
        renderTimeoutMs: renderMs,
        processTimeoutMs: processMs,
        canonicalProbes: process.env.BW_EEVEE_MATRIX_CANONICAL_PROBES === '1',
      },
      selection: {
        mode: selection.mode,
        manifestRowCount: baseRows.length,
        selectedRowCount: selection.rows.length,
        requestedKeys: selection.requestedKeys,
      },
      mappings: resolved.mapping,
      rowCount: generated.plan.length,
      temporaryDrivers: {
        persisted: false,
        cleanup: 'removed after the matrix process exits',
        rows: generated.plan.map((row) => ({
          index: row.index,
          key: row.key,
          sha256: row.sourceSha256,
          substitutions: row.substitutions,
        })),
      },
      progress: summarize(results, generated.plan.length),
    };
    writeCc0Artifact(provenancePath, `${JSON.stringify(provenance, null, 2)}\n`);
    writeConsolidated(runRoot, results, generated.plan.length, 'RUNNING', provenancePath);

    const env = productEnvironment();
    for (const row of generated.plan) {
      mkdirSync(row.rowOutputDir, { recursive: false });
      const logPath = `${row.rowOutputDir}/${row.outputLabel}-matrix.log`;
      const logFd = openSync(logPath, 'wx');
      let child;
      try {
        writeSync(logFd,
          `MATRIX_ROW ${row.index}/${generated.plan.length} key=${row.key} ` +
          `driver_sha256=${row.sourceSha256}\n`);
        const driverCheck = spawnSync(process.execPath, [row.driverPath, '--selfcheck'], {
          cwd: ROOT, env, encoding: 'utf8', timeout: 120000, maxBuffer: 8 * 1024 * 1024,
        });
        writeSync(logFd, driverCheck.stdout || '');
        writeSync(logFd, driverCheck.stderr || '');
        if (driverCheck.status !== 0 || !driverCheck.stdout.includes('SELF_CHECK_PASS')) {
          writeSync(logFd, `MATRIX_RIG_FAIL generated driver self-check status=${driverCheck.status}\n`);
          child = {
            status: driverCheck.status,
            signal: driverCheck.signal,
            error: driverCheck.error || new Error('generated driver self-check failed'),
          };
        }
        else {
          writeSync(logFd, 'MATRIX_BROWSER_BEGIN serialized_slot=1/1\n');
          child = spawnSync(
            process.execPath,
            [row.driverPath, String(port), String(renderMs), row.outputLabel],
            { cwd: ROOT, env, stdio: ['ignore', logFd, logFd], timeout: processMs },
          );
          writeSync(logFd,
            `MATRIX_BROWSER_END status=${child.status} signal=${child.signal || ''} ` +
            `error=${JSON.stringify(child.error?.message || null)}\n`);
        }
      }
      finally {
        closeSync(logFd);
        writeFileSync(`${logPath}.license`, CC0);
      }
      const manifestPath = `${row.rowOutputDir}/${row.outputLabel}-manifest.json`;
      const result = rowResult(row, child, manifestPath, logPath);
      results.push(result);
      provenance.progress = summarize(results, generated.plan.length);
      atomicWrite(provenancePath, `${JSON.stringify(provenance, null, 2)}\n`);
      writeConsolidated(runRoot, results, generated.plan.length, 'RUNNING', provenancePath);
      console.log(
        `MATRIX_ROW_RESULT ${row.index}/${generated.plan.length} ` +
        `key=${row.key} verdict=${result.verdict} gpu_errors=${result.failures.gpuErrors}`);
    }

    const summary = summarize(results, generated.plan.length);
    provenance.status = summary.pass === generated.plan.length ? 'PASS' : 'FAIL';
    provenance.completedAt = new Date().toISOString();
    provenance.progress = summary;
    atomicWrite(provenancePath, `${JSON.stringify(provenance, null, 2)}\n`);
    writeConsolidated(runRoot, results, generated.plan.length, provenance.status, provenancePath);
    console.log(
      `MATRIX_COMPLETE status=${provenance.status} rows=${summary.completed}/${summary.total} ` +
      `pass=${summary.pass} fail=${summary.fail} results=${runRoot}/results.tsv`);
    if (provenance.status !== 'PASS') process.exitCode = 1;
  }
  catch (error) {
    if (runCreated && provenance) {
      provenance.status = 'RIG_FAIL';
      provenance.completedAt = new Date().toISOString();
      provenance.failure = error.stack || error.message || String(error);
      provenance.progress = summarize(results, generated?.plan.length || EXPECTED_EEVEE_ROWS);
      atomicWrite(`${runRoot}/provenance.json`, `${JSON.stringify(provenance, null, 2)}\n`);
      writeConsolidated(
        runRoot,
        results,
        generated?.plan.length || EXPECTED_EEVEE_ROWS,
        'RIG_FAIL',
        `${runRoot}/provenance.json`);
    }
    throw error;
  }
  finally {
    if (generated?.temporaryRoot) rmSync(generated.temporaryRoot, { recursive: true, force: true });
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

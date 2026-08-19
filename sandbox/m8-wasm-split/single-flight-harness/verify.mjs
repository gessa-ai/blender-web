// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

import { spawn, spawnSync } from 'child_process';
import { createHash } from 'crypto';
import { createRequire } from 'module';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'fs';
import { dirname, join, resolve } from 'path';
import { fileURLToPath } from 'url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, '..', '..', '..');
const MODULES = '/Users/paws/plushly/game-platform/node_modules';
const require = createRequire(join(process.env.NODE_PATH || MODULES, 'package.json'));
const { chromium } = require('playwright');
const wasmAs = join(REPO, 'tools/emsdk/upstream/bin/wasm-as');
const serverScript = join(REPO, 'sandbox/m8-wasm-split/serve_split.py');

function parseArgs(argv) {
  const result = { run: null, port: 8171, outRoot: join(HERE, 'evidence') };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--run') result.run = argv[++i];
    else if (argv[i] === '--port') result.port = Number(argv[++i]);
    else if (argv[i] === '--out-root') result.outRoot = resolve(argv[++i]);
    else throw new Error(`unknown argument ${argv[i]}`);
  }
  if (!result.run || !/^[a-z0-9][a-z0-9._-]*$/i.test(result.run)) throw new Error('safe --run is required');
  return result;
}

const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const sleep = (milliseconds) => new Promise((resolveSleep) => setTimeout(resolveSleep, milliseconds));

async function waitForServer(process, timeoutMs = 10000) {
  let stdout = ''; let stderr = '';
  process.stdout.on('data', (chunk) => { stdout += String(chunk); });
  process.stderr.on('data', (chunk) => { stderr += String(chunk); });
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const line = stdout.split('\n').find((candidate) => candidate.includes('"ready": true'));
    if (line) return JSON.parse(line);
    if (process.exitCode !== null) throw new Error(`server exited ${process.exitCode}: ${stderr}`);
    await sleep(25);
  }
  throw new Error(`server readiness timeout: ${stderr}`);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const outDir = join(options.outRoot, options.run);
  if (existsSync(outDir)) throw new Error(`refusing overwrite ${outDir}`);
  mkdirSync(outDir, { recursive: true });
  const wasmPath = join(HERE, 'secondary.wasm');
  const assembly = spawnSync(wasmAs, [join(HERE, 'secondary.wat'), '-o', wasmPath], { encoding: 'utf8' });
  if (assembly.status !== 0) throw new Error(`wasm-as failed: ${assembly.stdout}${assembly.stderr}`);
  const wasm = readFileSync(wasmPath); const expectedSha256 = sha256(wasm);
  const serverLog = join(outDir, 'server.jsonl');
  const browserProfile = join(outDir, 'chromium-profile');
  const server = spawn('python3', [serverScript, String(options.port), HERE, serverLog], {
    stdio: ['ignore', 'pipe', 'pipe'], detached: false,
  });
  const started = Date.now(); let context = null;
  try {
    const serverReady = await waitForServer(server);
    context = await chromium.launchPersistentContext(browserProfile, {
      headless: false, viewport: { width: 800, height: 600 }, deviceScaleFactor: 1,
    });
    const browserVersion = context.browser()?.version() || null;
    const page = context.pages()[0] || await context.newPage();
    const pageErrors = []; page.on('pageerror', (error) => pageErrors.push(String(error)));
    await page.goto(`http://127.0.0.1:${options.port}/index.html?bytes=${wasm.length}&sha256=${expectedSha256}`,
      { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForFunction(() => window.bwHarnessResult !== undefined, null, { timeout: 30000 });
    const runtime = await page.evaluate(() => window.bwHarnessResult);
    await context.close(); context = null;
    await sleep(100);
    const transfers = readFileSync(serverLog, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse);
    const wasmTransfers = transfers.filter((row) => row.path === '/secondary.wasm');
    const pass = runtime.verdict === 'PASS' && pageErrors.length === 0 &&
      runtime.stats.fetchCount === 1 && runtime.stats.compileCount === 1 && runtime.stats.pageInstanceCount === 1 &&
      runtime.poolAckCount === 43 && runtime.duplicateInstanceCount === 1 && runtime.lateWorkerAckCount === 1 &&
      wasmTransfers.length === 1 && wasmTransfers[0].complete === true &&
      wasmTransfers[0].bytes_sent === wasm.length && wasmTransfers[0].sha256 === expectedSha256;
    const receipt = {
      schema: 1, verdict: pass ? 'PASS' : 'FAIL', marker: 'BW_SPLIT_SINGLE_FLIGHT_SYNTHETIC_V1',
      elapsedMs: Date.now() - started, browserVersion, pageErrors, runtime, wasmTransfers,
      artifact: { path: 'sandbox/m8-wasm-split/single-flight-harness/secondary.wasm', bytes: wasm.length, sha256: expectedSha256 },
      sources: Object.fromEntries(['index.html', 'worker.js', 'verify.mjs', 'secondary.wat'].map((name) => {
        const bytes = readFileSync(join(HERE, name)); return [name, { bytes: bytes.length, sha256: sha256(bytes) }];
      })),
      server: serverReady,
    };
    writeFileSync(join(outDir, 'receipt.json'), `${JSON.stringify(receipt, null, 2)}\n`, { flag: 'wx' });
    console.log(JSON.stringify(receipt, null, 2));
    if (!pass) process.exitCode = 1;
  }
  finally {
    if (context) await context.close().catch(() => {});
    if (existsSync(browserProfile)) rmSync(browserProfile, { recursive: true });
    if (server.exitCode === null) { server.kill('SIGTERM'); await sleep(100); }
  }
}

await main();

// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Deterministic, fail-closed JavaScript minification for public bundle controls.
// The executable Terser bundle is already pinned inside the Emscripten toolchain;
// this wrapper binds its exact bytes and options instead of consulting PATH/npm.

"use strict";

import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {lstat, mkdir, readFile, rename, rm, writeFile} from "node:fs/promises";
import {createRequire} from "node:module";
import {dirname, resolve} from "node:path";
import process from "node:process";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

const SELF = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(SELF, "..", "..");
const NODE_MODULES = resolve(ROOT, "tools/emsdk/upstream/emscripten/node_modules");
const TERSER_ROOT = resolve(NODE_MODULES, "terser");
const TERSER_PACKAGE = resolve(TERSER_ROOT, "package.json");
const TERSER_BUNDLE = resolve(TERSER_ROOT, "dist/bundle.min.js");
const EMSCRIPTEN_LOCK = resolve(ROOT, "tools/emsdk/upstream/emscripten/package-lock.json");

const PINNED_NODE_VERSION = "v22.16.0";
const PINNED_TERSER_VERSION = "5.39.0";
const PINNED_TERSER_LICENSE = "BSD-2-Clause";
const PINNED_TERSER_INTEGRITY =
  "sha512-LBAhFyLho16harJoWMg/nZsQYgTrg5jXOn2nCYjRUcZZEdE3qa2zb8QEDRUGVZBW4rlazf2fxkg8tztybTaqWw==";
const PINNED_TERSER_BUNDLE_SHA256 =
  "ac4c20a115313612e52b93153165861ec710d2ec0329f27b968110d53df9c116";
const COMPRESS_PASSES = 2;

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function validateIdentity(identity) {
  if (identity.nodeVersion !== PINNED_NODE_VERSION) {
    throw new Error(
      `public minifier requires Node ${PINNED_NODE_VERSION}, got ${identity.nodeVersion}`);
  }
  if (identity.terserVersion !== PINNED_TERSER_VERSION) {
    throw new Error(
      `public minifier requires Terser ${PINNED_TERSER_VERSION}, got ${identity.terserVersion}`);
  }
  if (identity.terserLicense !== PINNED_TERSER_LICENSE) {
    throw new Error(
      `public minifier Terser license drift: ${identity.terserLicense}`);
  }
  if (identity.terserIntegrity !== PINNED_TERSER_INTEGRITY) {
    throw new Error("public minifier Terser package-lock integrity drift");
  }
  if (identity.terserBundleSha256 !== PINNED_TERSER_BUNDLE_SHA256) {
    throw new Error("public minifier executable bundle integrity drift");
  }
}

async function loadPinnedMinifier() {
  const packageJson = JSON.parse(await readFile(TERSER_PACKAGE, "utf8"));
  const packageLock = JSON.parse(await readFile(EMSCRIPTEN_LOCK, "utf8"));
  const lockRow = packageLock.packages?.["node_modules/terser"];
  const bundleBytes = await readFile(TERSER_BUNDLE);
  validateIdentity({
    nodeVersion: process.version,
    terserVersion: packageJson.version,
    terserLicense: packageJson.license,
    terserIntegrity: lockRow?.integrity,
    terserBundleSha256: sha256(bundleBytes),
  });
  const requireFromToolchain = createRequire(resolve(NODE_MODULES, "bw-minifier-anchor.cjs"));
  const terser = requireFromToolchain("terser");
  if (typeof terser.minify !== "function") {
    throw new Error("pinned Terser minify API is unavailable");
  }
  return terser.minify;
}

async function minifySource(source, minify) {
  const result = await minify(source, {
    compress: {passes: COMPRESS_PASSES},
    mangle: true,
    format: {comments: /SPDX-/},
    sourceMap: false,
  });
  if (typeof result.code !== "string" || result.code.length === 0) {
    throw new Error("pinned Terser produced no JavaScript");
  }
  return `${result.code}\n`;
}

async function assertRegularInput(path) {
  const info = await lstat(path);
  if (!info.isFile() || info.isSymbolicLink()) {
    throw new Error(`public minifier input is not a regular file: ${path}`);
  }
}

async function writeAtomic(path, body) {
  await mkdir(dirname(path), {recursive: true});
  try {
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink()) {
      throw new Error(`public minifier output is not a regular file: ${path}`);
    }
  }
  catch (error) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
  }
  const temporary = `${path}.bw-minify-${process.pid}`;
  try {
    await writeFile(temporary, body, {flag: "wx", mode: 0o644});
    await rename(temporary, path);
  }
  finally {
    await rm(temporary, {force: true});
  }
}

async function selfcheck() {
  const minify = await loadPinnedMinifier();
  const sample = `// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
(function () {
  const deliberatelyUnusedValue = 99;
  const deliberatelyLongLocalName = 6;
  globalThis.__bwMinifierProbe = {
    publicProperty: deliberatelyLongLocalName * 7,
    publicString: "stable"
  };
})();\n`;
  const first = await minifySource(sample, minify);
  const second = await minifySource(sample, minify);
  assert.equal(first, second);
  assert.ok(Buffer.byteLength(first) < Buffer.byteLength(sample));
  assert.equal((first.match(/SPDX-/g) || []).length, 2);
  const context = {};
  vm.runInNewContext(first, context, {timeout: 1000});
  assert.deepEqual(
    JSON.parse(JSON.stringify(context.__bwMinifierProbe)),
    {publicProperty: 42, publicString: "stable"});
  await assert.rejects(() => minifySource("function {", minify));

  const good = {
    nodeVersion: PINNED_NODE_VERSION,
    terserVersion: PINNED_TERSER_VERSION,
    terserLicense: PINNED_TERSER_LICENSE,
    terserIntegrity: PINNED_TERSER_INTEGRITY,
    terserBundleSha256: PINNED_TERSER_BUNDLE_SHA256,
  };
  for (const [field, value] of Object.entries({
    nodeVersion: "v25.0.0",
    terserVersion: "5.40.0",
    terserLicense: "UNKNOWN",
    terserIntegrity: "sha512-wrong",
    terserBundleSha256: "0".repeat(64),
  })) {
    assert.throws(() => validateIdentity({...good, [field]: value}));
  }
  console.log(
    "BW_PUBLIC_SHELL_MINIFIER_SELFCHECK_PASS " +
    `node=${PINNED_NODE_VERSION} terser=${PINNED_TERSER_VERSION} ` +
    `bundle=${PINNED_TERSER_BUNDLE_SHA256} positive=5 negative=6`);
}

function usage() {
  console.error(
    "usage: public_shell_minify.mjs --input SOURCE.js --output OUTPUT.js | --selfcheck");
}

async function main() {
  if (process.argv.length === 3 && process.argv[2] === "--selfcheck") {
    await selfcheck();
    return;
  }
  if (process.argv.length !== 6 || process.argv[2] !== "--input" ||
      process.argv[4] !== "--output") {
    usage();
    process.exitCode = 2;
    return;
  }
  const input = resolve(process.argv[3]);
  const output = resolve(process.argv[5]);
  await assertRegularInput(input);
  const source = await readFile(input, "utf8");
  const minify = await loadPinnedMinifier();
  const result = await minifySource(source, minify);
  await writeAtomic(output, result);
}

main().catch((error) => {
  console.error(`public_shell_minify: FATAL: ${error?.stack || error}`);
  process.exitCode = 1;
});

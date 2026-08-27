// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Canonical binding between the released split-build inventory, the exact local
// deploy tree, and the bytes served by serve_measure.py.  No wasm filename is
// guessed here: the finalizer-owned inventory is the sole allowlist.

import {createHash} from "crypto";
import {basename, resolve} from "path";
import {lstatSync, readFileSync, readdirSync, realpathSync} from "fs";
import {isDeepStrictEqual} from "util";

export const SPLIT_MANIFEST = "blender_browser.split-build.json";
export const BUNDLE_SPLIT_MANIFEST = "bin/split-build.json";
export const BOOT_CRITICAL_URLS = Object.freeze([
  "/index.html",
  "/diagnostics-bootstrap.js",
  "/file-bridge.js",
  "/boot-windowed.js",
  "/stage1-loader.js",
  "/service-worker-register.js",
  "/service-worker.js",
  "/fonts/bw-interface-sans.woff2",
  "/bin/blender_browser.js",
  "/bin/blender_browser.data",
]);

export const STATIC_BUNDLE_NAMES = [
  "index.html", "diagnostics-bootstrap.js", "boot-windowed.js", "file-bridge.js", "wgpu-preinit-worker.js",
  "stage1-loader.js", "service-worker-register.js", "service-worker.js", "_headers",
  "fonts/bw-interface-sans.woff2",
  "scenes/stress-mixed.blend", "scenes/stress-mixed.blend.license",
  "legal/LICENSE.txt", "legal/AUTHORS.txt", "legal/NOTICE.txt",
  "legal/THIRD-PARTY.md", "legal/PROVENANCE.md",
  "legal/LICENSES/Apache-2.0.txt", "legal/LICENSES/BSD-3-Clause.txt",
  "legal/LICENSES/Bitstream-Vera.txt",
  "legal/LICENSES/CC0-1.0.txt", "legal/LICENSES/GPL-2.0-or-later.txt",
  "legal/LICENSES/GPL-3.0-or-later.txt",
  "legal/LICENSES/OFL-1.1.txt",
  "legal/LICENSES/LicenseRef-OpenSubdiv-TOST-1.0.txt",
  "legal/THIRD_PARTY_NOTICES/OpenSubdiv-3.7.0-NOTICE.txt",
  "legal/OpenUSD-26.03/LICENSE.txt", "legal/OpenUSD-26.03/NOTICE.txt",
  "bin/blender_browser.js", "bin/blender_browser.data",
  "bin/stage1.data", "bin/stage1-manifest.json", BUNDLE_SPLIT_MANIFEST,
  "bin/blender_browser.js.br", "bin/blender_browser.data.br", "bin/stage1.data.br",
  "index.html.br", "diagnostics-bootstrap.js.br", "file-bridge.js.br",
  "boot-windowed.js.br", "stage1-loader.js.br", "service-worker-register.js.br",
  "service-worker.js.br", "fonts/bw-interface-sans.woff2.br",
];

function invariant(condition, message) {
  if (!condition) throw new Error(`invalid split-build inventory: ${message}`);
}

function sameSet(actual, expected) {
  return actual.length === expected.length && actual.every((value) => expected.includes(value));
}

function listExactTree(base, relative = "") {
  const directory = relative ? `${base}/${relative}` : base;
  const names = [];
  for (const entry of readdirSync(directory, {withFileTypes: true})) {
    const name = relative ? `${relative}/${entry.name}` : entry.name;
    invariant(!entry.isSymbolicLink(), `deploy bundle contains a symlink: ${name}`);
    if (entry.isDirectory()) names.push(...listExactTree(base, name));
    else if (entry.isFile()) names.push(name);
    else invariant(false, `deploy bundle contains an unsupported entry: ${name}`);
  }
  return names.sort();
}

export function fileIdentity(path) {
  const data = readFileSync(path);
  return {bytes: data.length, sha256: createHash("sha256").update(data).digest("hex")};
}

function validateInventoryRow(row, buildBase, policy) {
  invariant(row && typeof row === "object" && !Array.isArray(row), "inventory row is not an object");
  invariant(typeof row.filename === "string" &&
    /^blender_browser(?:\.[A-Za-z0-9_-]+)*\.wasm(?:\.orig)?$/.test(row.filename),
  `unsafe or unsupported wasm filename ${JSON.stringify(row.filename)}`);
  invariant(basename(row.filename) === row.filename, `wasm filename escapes build directory: ${row.filename}`);
  invariant(typeof row.role === "string" &&
    [...policy.bundle_roles, ...policy.build_only_roles].includes(row.role),
  `unknown role for ${row.filename}: ${row.role}`);
  const shouldShip = policy.bundle_roles.includes(row.role);
  invariant(row.shipped === shouldShip, `shipped flag disagrees with role for ${row.filename}`);
  invariant(typeof row.critical === "boolean", `critical is not boolean for ${row.filename}`);
  invariant(typeof row.request_phase === "string" && row.request_phase.length > 0,
    `request_phase is absent for ${row.filename}`);
  if (row.role === "primary") {
    invariant(row.critical === true && row.request_phase === "stage0",
      "primary wasm must be critical stage0");
  } else if (row.role === "deferred") {
    invariant(row.critical === false && row.request_phase === "after_semantic_first_interaction",
      `${row.filename} is not classified after semantic first interaction`);
  } else {
    invariant(row.critical === false && row.request_phase === "never",
      `build-only wasm ${row.filename} must never be requested`);
  }
  const expectedPath = resolve(buildBase, row.filename);
  invariant(resolve(row.path || "") === expectedPath, `noncanonical path for ${row.filename}`);
  invariant(realpathSync(expectedPath) === expectedPath && !lstatSync(expectedPath).isSymbolicLink() &&
    lstatSync(expectedPath).isFile(), `missing/noncanonical wasm file ${row.filename}`);
  const actual = fileIdentity(expectedPath);
  invariant(row.bytes === actual.bytes && row.sha256 === actual.sha256,
    `identity mismatch for ${row.filename}`);
  return {...row};
}

export function loadArtifactContract(root = "/Users/paws/blender-web") {
  const buildBase = `${root}/build-wasm-windowed-opt/bin`;
  const bundleBase = `${root}/sandbox/m8-staged-deploy/bundle-staged`;
  const manifestPath = `${buildBase}/${SPLIT_MANIFEST}`;
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  invariant(manifest.schema === 1, "schema must be 1");
  invariant(manifest.mode === "apply" && manifest.verdict === "PASS",
    "only a successful APPLY inventory may ship");
  invariant(manifest.contract === "shared-main-memory-profile-v1", "unexpected split contract");
  const policy = manifest.inventory_policy;
  invariant(policy && typeof policy === "object", "inventory_policy is absent");
  invariant(policy.unlisted === "reject", "unlisted wasm policy must reject");
  invariant(policy.glob === "blender_browser*.wasm*", "unexpected inventory glob");
  invariant(policy.profile_export_absent === true, "profile export remains in shipping bytes");
  invariant(isDeepStrictEqual(policy.bundle_roles, ["primary", "deferred"]),
    "bundle_roles must be primary+deferred");
  invariant(isDeepStrictEqual(policy.build_only_roles, ["original_build_only"]),
  "build_only_roles must contain only original_build_only");
  invariant(Array.isArray(manifest.wasm_inventory) && manifest.wasm_inventory.length >= 3,
    "wasm_inventory is missing/incomplete");
  const inventory = manifest.wasm_inventory.map((row) => validateInventoryRow(row, buildBase, policy));
  const names = inventory.map((row) => row.filename);
  invariant(new Set(names).size === names.length, "duplicate wasm inventory filenames");
  invariant(inventory.filter((row) => row.role === "primary").length === 1,
    "inventory must contain exactly one primary");
  invariant(inventory.filter((row) => row.role === "deferred").length >= 1,
    "inventory must contain at least one deferred shard");
  invariant(inventory.filter((row) => row.role === "original_build_only").length === 1,
    "inventory must contain exactly one build-only original");
  const actualWasm = readdirSync(buildBase, {withFileTypes: true})
    .filter((entry) => entry.isFile() && /^blender_browser.*\.wasm.*$/.test(entry.name))
    .map((entry) => entry.name).sort();
  invariant(sameSet(actualWasm, [...names].sort()),
    `unlisted wasm files: actual=${JSON.stringify(actualWasm)} inventory=${JSON.stringify([...names].sort())}`);
  const jsIdentity = fileIdentity(`${buildBase}/blender_browser.js`);
  invariant(manifest.js?.sha256 === jsIdentity.sha256, "shipping glue does not match split manifest");
  const shippedWasm = inventory.filter((row) => row.shipped).sort((a, b) => a.filename.localeCompare(b.filename));
  const sourceNames = ["blender_browser.js", "blender_browser.data", SPLIT_MANIFEST,
    ...shippedWasm.map((row) => row.filename)];
  const bundleNames = [...STATIC_BUNDLE_NAMES,
    ...shippedWasm.flatMap((row) => [`bin/${row.filename}`, `bin/${row.filename}.br`])];
  invariant(new Set(sourceNames).size === sourceNames.length, "duplicate source artifact names");
  invariant(new Set(bundleNames).size === bundleNames.length, "duplicate bundle artifact names");
  const actualBundleNames = listExactTree(bundleBase);
  invariant(sameSet(actualBundleNames, [...bundleNames].sort()),
    `deploy tree mismatch: actual=${JSON.stringify(actualBundleNames)} expected=${JSON.stringify([...bundleNames].sort())}`);
  const publicSplitManifest = {
    schema: 1,
    contract: manifest.contract,
    source_manifest_sha256: fileIdentity(manifestPath).sha256,
    js_sha256: jsIdentity.sha256,
    inventory_policy: {
      unlisted: "reject",
      bundle_roles: ["primary", "deferred"],
    },
    wasm_inventory: shippedWasm.map((row) => ({
      filename: row.filename, role: row.role, bytes: row.bytes, sha256: row.sha256,
      critical: row.critical, request_phase: row.request_phase,
    })),
  };
  const bundledPublicManifest = JSON.parse(
    readFileSync(`${bundleBase}/${BUNDLE_SPLIT_MANIFEST}`, "utf8"));
  invariant(isDeepStrictEqual(bundledPublicManifest, publicSplitManifest),
    "public split manifest is stale, incomplete, or leaks non-public fields");
  return {
    manifest, inventory, shippedWasm, sourceNames, bundleNames, buildBase, bundleBase,
    publicSplitManifest,
    shippedWasmUrls: shippedWasm.map((row) => `/bin/${row.filename}`),
    criticalWasmUrls: shippedWasm.filter((row) => row.critical).map((row) => `/bin/${row.filename}`),
  };
}

export function collectArtifacts(base, names) {
  return Object.fromEntries(names.map((name) => [name, fileIdentity(`${base}/${name}`)]));
}

export function canonicalBundleDigest(artifacts) {
  if (!artifacts || typeof artifacts !== "object" || Array.isArray(artifacts)) {
    throw new Error("bundle artifacts must be an object");
  }
  const names = Object.keys(artifacts).sort();
  if (names.length === 0) throw new Error("bundle artifact set is empty");
  const digest = createHash("sha256");
  for (const name of names) {
    const row = artifacts[name];
    if (!row || !Number.isSafeInteger(row.bytes) || row.bytes < 0 ||
        !/^[0-9a-f]{64}$/.test(row.sha256 || "")) {
      throw new Error(`invalid bundle identity for ${name}`);
    }
    digest.update(`${name}\0${row.bytes}\0${row.sha256}\n`, "utf8");
  }
  return digest.digest("hex");
}

export async function requireServedBundle(response, expectedDigest) {
  if (!response) throw new Error("initial navigation returned no HTTP response");
  const headers = await response.allHeaders();
  const served = headers["x-bw-bundle-sha256"] || "";
  if (served !== expectedDigest) {
    throw new Error(`served bundle mismatch: expected ${expectedDigest}, got ${served || "<missing>"}`);
  }
  return served;
}

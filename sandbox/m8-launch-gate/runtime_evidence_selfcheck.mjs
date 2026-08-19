// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later

"use strict";

import assert from "node:assert/strict";
import {
  chmodSync, mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync,
} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {
  bindRuntimeVersion, browserMatrixInvocationPass, browserMatrixRowPass,
  collectBrowserRuntimeIdentity, requireEmptyEarlyDiagnostics,
  revalidateBrowserRuntimeIdentity,
  validateEarlyDiagnostics, validatePriorBrowserMatrix,
} from "./runtime_evidence.mjs";

const root = mkdtempSync(join(realpathSync(tmpdir()), "m8-runtime-evidence-"));
const app = `${root}/Chrome.app`;
const executable = `${app}/Contents/MacOS/Chrome`;
mkdirSync(`${app}/Contents/MacOS`, {recursive: true});
writeFileSync(`${app}/Contents/Info.plist`, "fixture");
writeFileSync(executable, "fixture browser bytes");
chmodSync(executable, 0o755);

const expected = {identifier: "com.google.Chrome", team: "EQHXZ8M8AV"};
function runnerWith(overrides = {}) {
  return (command, args) => {
    const key = `${command} ${args.slice(0, 2).join(" ")}`;
    if (overrides[key]) return overrides[key];
    if (command === "codesign" && args[0] === "--verify") return {status: 0, stdout: "", stderr: ""};
    if (command === "codesign") return {status: 0, stdout: "", stderr:
      "Identifier=com.google.Chrome\nTeamIdentifier=EQHXZ8M8AV\nCDHash=0123456789abcdef0123456789abcdef01234567\n"};
    if (command === "spctl") return {status: 0, stdout: "", stderr:
      `${app}: accepted\nsource=Notarized Developer ID\norigin=Developer ID Application: Google LLC\n`};
    if (command === "plutil") return {status: 0, stdout: "151.0.1.2\n", stderr: ""};
    return {status: 1, stdout: "", stderr: "unexpected command"};
  };
}

const identity = collectBrowserRuntimeIdentity(executable, expected, runnerWith());
assert.equal(identity.executable.bytes, 21);
assert.match(identity.executable.sha256, /^[0-9a-f]{64}$/);
assert.equal(identity.codesign.deep_strict, true);
assert.equal(identity.notarization.accepted, true);
assert.equal(bindRuntimeVersion(identity, "151.0.1.2").version_matches_app, true);
const boundIdentity = bindRuntimeVersion(identity, "151.0.1.2");
assert.deepEqual(revalidateBrowserRuntimeIdentity(boundIdentity, expected, runnerWith()), boundIdentity);
assert.deepEqual(validateEarlyDiagnostics({schema: 1, preload: true, snapshot: []}),
  {schema: 1, preload: true, snapshot: []});

const matrixRow = {
  channel: "edge",
  executable,
  actual_version: "151.0.1.2",
  runtime_identity: boundIdentity,
  early_diagnostics: {
    online: {schema: 1, preload: true, snapshot: []},
    offline_reload: {schema: 1, preload: true, snapshot: []},
  },
  served_bundle_sha256: "a".repeat(64),
  current_at_test: true,
  first_pixels: true,
  interaction_smoke: true,
  offline_reload: true,
  query_hooks_disabled: true,
  external_request_count: 0,
  gpu_errors: 0,
  errors: [],
};
const matrixSourceArtifacts = [{path: "source", bytes: 1, sha256: "b".repeat(64)}];
const matrixBundleArtifacts = [{path: "bundle", bytes: 1, sha256: "c".repeat(64)}];
const matrixPrior = {
  schema: 1,
  source_artifacts: matrixSourceArtifacts,
  bundle_artifacts: matrixBundleArtifacts,
  served_bundle_sha256: matrixRow.served_bundle_sha256,
  engines: {edge: matrixRow},
  verdict: "INCOMPLETE",
  updated_at: "2026-08-15T00:00:00.000Z",
};
assert.equal(browserMatrixRowPass(matrixRow), true);
assert.equal(validatePriorBrowserMatrix(
  matrixPrior, "chrome", matrixSourceArtifacts, matrixBundleArtifacts,
  matrixRow.served_bundle_sha256, Object.keys(matrixRow), (seen, channel) => {
    assert.deepEqual(seen, boundIdentity);
    assert.equal(channel, "edge");
  }), matrixRow);
assert.equal(browserMatrixInvocationPass(false, false, true), true);
assert.equal(browserMatrixInvocationPass(false, true, false), false);
assert.equal(browserMatrixInvocationPass(true, true, false), true);
assert.equal(browserMatrixInvocationPass(true, false, true), false);

const negatives = [];
function reject(name, fn) {
  assert.throws(fn, /M8 runtime evidence:/);
  negatives.push(name);
}
const alias = `${app}/Contents/MacOS/Alias`;
symlinkSync(executable, alias);
reject("executable_symlink", () => collectBrowserRuntimeIdentity(alias, expected, runnerWith()));
chmodSync(executable, 0o644);
reject("executable_not_executable", () =>
  collectBrowserRuntimeIdentity(executable, expected, runnerWith()));
chmodSync(executable, 0o755);
reject("codesign_deep_strict_failure", () => collectBrowserRuntimeIdentity(executable, expected,
  runnerWith({"codesign --verify --deep": {status: 1, stdout: "", stderr: "rejected"}})));
reject("wrong_team", () => collectBrowserRuntimeIdentity(executable, expected, (command, args) => {
  const result = runnerWith()(command, args);
  if (command === "codesign" && args[0] === "-d") result.stderr = result.stderr.replace("EQHXZ8M8AV", "BADTEAM000");
  return result;
}));
reject("missing_cdhash", () => collectBrowserRuntimeIdentity(executable, expected, (command, args) => {
  const result = runnerWith()(command, args);
  if (command === "codesign" && args[0] === "-d") result.stderr = result.stderr.replace(/^CDHash=.*$/m, "");
  return result;
}));
reject("notarization_rejected", () => collectBrowserRuntimeIdentity(executable, expected, (command, args) => {
  if (command === "spctl") return {status: 1, stdout: "", stderr: `${app}: rejected\nsource=no usable signature\n`};
  return runnerWith()(command, args);
}));
reject("notarization_origin_missing", () => collectBrowserRuntimeIdentity(executable, expected,
  (command, args) => {
    const result = runnerWith()(command, args);
    if (command === "spctl") result.stderr = result.stderr.replace(/^origin=.*$/m, "");
    return result;
  }));
reject("runtime_version_alias", () => bindRuntimeVersion(identity, "151.0.1.02"));
const intermediate = `${root}/intermediate`;
symlinkSync(`${app}/Contents`, intermediate, "dir");
reject("intermediate_symlink", () => collectBrowserRuntimeIdentity(
  `${intermediate}/MacOS/Chrome`, expected, runnerWith()));
const driftedIdentity = structuredClone(boundIdentity);
driftedIdentity.executable.sha256 = "f".repeat(64);
reject("terminal_identity_drift", () =>
  revalidateBrowserRuntimeIdentity(driftedIdentity, expected, runnerWith()));
reject("diagnostic_snapshot_nonempty", () =>
  validateEarlyDiagnostics({schema: 1, preload: true, snapshot: [{type: "error"}]}));
reject("diagnostic_preload_false", () =>
  validateEarlyDiagnostics({schema: 1, preload: false, snapshot: []}));
reject("matrix_prior_invalid", () => validatePriorBrowserMatrix(
  {}, "chrome", matrixSourceArtifacts, matrixBundleArtifacts,
  matrixRow.served_bundle_sha256, Object.keys(matrixRow), () => {}));
const sameChannelPrior = structuredClone(matrixPrior);
sameChannelPrior.engines = {chrome: {...matrixRow, channel: "chrome"}};
reject("matrix_prior_same_channel", () => validatePriorBrowserMatrix(
  sameChannelPrior, "chrome", matrixSourceArtifacts, matrixBundleArtifacts,
  matrixRow.served_bundle_sha256, Object.keys(matrixRow), () => {}));
const twoRowPrior = structuredClone(matrixPrior);
twoRowPrior.engines.chrome = {...matrixRow, channel: "chrome"};
reject("matrix_prior_two_rows", () => validatePriorBrowserMatrix(
  twoRowPrior, "chrome", matrixSourceArtifacts, matrixBundleArtifacts,
  matrixRow.served_bundle_sha256, Object.keys(matrixRow), () => {}));
const failedRowPrior = structuredClone(matrixPrior);
failedRowPrior.engines.edge.first_pixels = false;
reject("matrix_prior_failed_row", () => validatePriorBrowserMatrix(
  failedRowPrior, "chrome", matrixSourceArtifacts, matrixBundleArtifacts,
  matrixRow.served_bundle_sha256, Object.keys(matrixRow), () => {}));
const passVerdictPrior = structuredClone(matrixPrior);
passVerdictPrior.verdict = "PASS";
reject("matrix_prior_pass_verdict", () => validatePriorBrowserMatrix(
  passVerdictPrior, "chrome", matrixSourceArtifacts, matrixBundleArtifacts,
  matrixRow.served_bundle_sha256, Object.keys(matrixRow), () => {}));

const fakePage = {evaluate: async () => ({schema: 1, preload: true, snapshot: []})};
assert.deepEqual(await requireEmptyEarlyDiagnostics(fakePage, "fixture"),
  {schema: 1, preload: true, snapshot: []});

const producers = {
  browser_matrix: readFileSync(new URL("./browser_matrix.mjs", import.meta.url), "utf8"),
  product: readFileSync(new URL("./verify_product_bar.mjs", import.meta.url), "utf8"),
  performance: readFileSync(new URL("./measure_current.mjs", import.meta.url), "utf8"),
  soak: readFileSync(new URL("./soak_current.mjs", import.meta.url), "utf8"),
  staged: readFileSync(new URL("../m8-staged-deploy/verify_staged.mjs", import.meta.url), "utf8"),
};
for (const [name, source] of Object.entries(producers)) {
  assert.match(source, /collectBrowserRuntimeIdentity\(/, `${name} omits executable identity`);
  assert.match(source, /bindRuntimeVersion\(/, `${name} omits app/runtime version binding`);
  assert.match(source, /revalidateBrowserRuntimeIdentity\(/,
    `${name} omits terminal executable identity revalidation`);
  assert.match(source, /runtime_identity/, `${name} omits identity from its receipt`);
  assert.match(source, /requireEmptyEarlyDiagnostics\(/, `${name} omits terminal diagnostics`);
  assert.match(source, /early_diagnostics/, `${name} omits diagnostics from its receipt`);
}
assert.match(producers.browser_matrix,
  /process\.exit\(browserMatrixInvocationPass\(priorExists, matrixPass, pass\) \? 0 : 1\)/,
  "browser matrix does not exit on the completed matrix verdict after a prior row");
assert.equal((producers.browser_matrix.match(/requireEmptyEarlyDiagnostics\(/g) || []).length, 2);
assert.equal((producers.product.match(/requireEmptyEarlyDiagnostics\(/g) || []).length, 4);
assert.equal((producers.performance.match(/requireEmptyEarlyDiagnostics\(/g) || []).length, 1);
assert.equal((producers.soak.match(/requireEmptyEarlyDiagnostics\(/g) || []).length, 1);
assert.equal((producers.staged.match(/recordEarlyDiagnostics\('/g) || []).length, 3);

rmSync(root, {recursive: true, force: true});
console.log(`M8_RUNTIME_EVIDENCE_SELFCHECK_PASS ` +
  `positive=identity+diagnostics+matrix-prior+matrix-exit negative=${negatives.length} ` +
  `producers=${Object.keys(producers).join(",")} checks=${negatives.join(",")}`);

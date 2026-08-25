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
  browserIdentityContract, classifyRuntimeAdapter, collectBrowserRuntimeIdentity, legacySigning,
  requireEmptyEarlyDiagnostics, requireHardwareRuntimeAdapter,
  revalidateBrowserRuntimeIdentity,
  validateEarlyDiagnostics, validatePriorBrowserMatrix, validateRuntimeAdapter,
} from "./runtime_evidence.mjs";

const root = mkdtempSync(join(realpathSync(tmpdir()), "m8-runtime-evidence-"));
const app = `${root}/Google Chrome.app`;
const executable = `${app}/Contents/MacOS/Google Chrome`;
mkdirSync(`${app}/Contents/MacOS`, {recursive: true});
writeFileSync(`${app}/Contents/Info.plist`, "fixture");
writeFileSync(executable, "fixture browser bytes");
chmodSync(executable, 0o755);

const expected = browserIdentityContract("chrome", "darwin");
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

const identity = collectBrowserRuntimeIdentity(executable, expected, runnerWith(), "darwin");
assert.equal(identity.executable.bytes, 21);
assert.match(identity.executable.sha256, /^[0-9a-f]{64}$/);
assert.equal(identity.codesign.deep_strict, true);
assert.equal(identity.notarization.accepted, true);
assert.equal(bindRuntimeVersion(identity, "151.0.1.2").version_matches_app, true);
const boundIdentity = bindRuntimeVersion(identity, "151.0.1.2");
assert.deepEqual(
  revalidateBrowserRuntimeIdentity(boundIdentity, expected, runnerWith(), "darwin"), boundIdentity);
assert.deepEqual(legacySigning(boundIdentity), {
  identifier: "com.google.Chrome", team: "EQHXZ8M8AV", valid: true,
});
assert.deepEqual(validateEarlyDiagnostics({schema: 1, preload: true, snapshot: []}),
  {schema: 1, preload: true, snapshot: []});

const adapterFixture = classifyRuntimeAdapter({
  present: true,
  isFallbackAdapter: false,
  info: {vendor: "NVIDIA", architecture: "Ada", device: "GeForce RTX 4090", description: ""},
}, process.platform);
assert.deepEqual(validateRuntimeAdapter(adapterFixture), adapterFixture);
function adapterProbeFixture(adapter) {
  const observed = {url: null, closed: false};
  return {observed, context: {newPage: async () => ({
    goto: async (url) => { observed.url = url; },
    evaluate: async (action) => {
      const descriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
      Object.defineProperty(globalThis, "navigator", {
        configurable: true,
        value: {gpu: {requestAdapter: async () => adapter}},
      });
      try {
        return await action();
      }
      finally {
        if (descriptor) Object.defineProperty(globalThis, "navigator", descriptor);
        else delete globalThis.navigator;
      }
    },
    close: async () => { observed.closed = true; },
  })}};
}

for (const adapter of [
  {info: {vendor: "NVIDIA", architecture: "Ada", device: "GeForce RTX 4090", description: "",
    isFallbackAdapter: false}},
  {isFallbackAdapter: false,
    info: {vendor: "NVIDIA", architecture: "Ada", device: "GeForce RTX 4090", description: ""}},
  {isFallbackAdapter: true,
    info: {vendor: "NVIDIA", architecture: "Ada", device: "GeForce RTX 4090", description: "",
      isFallbackAdapter: false}},
]) {
  const fixture = adapterProbeFixture(adapter);
  assert.deepEqual(await requireHardwareRuntimeAdapter(fixture.context), adapterFixture);
  assert.match(fixture.observed.url, /^file:.*\/GOAL\.md$/);
  assert.equal(fixture.observed.closed, true);
}
for (const adapter of [
  {isFallbackAdapter: false,
    info: {vendor: "NVIDIA", architecture: "Ada", device: "GeForce RTX 4090", description: "",
      isFallbackAdapter: true}},
  {info: {vendor: "Google", architecture: "SwiftShader", device: "", description: "",
    isFallbackAdapter: false}},
]) {
  const fixture = adapterProbeFixture(adapter);
  await assert.rejects(() => requireHardwareRuntimeAdapter(fixture.context),
    /M8 runtime evidence: runtime adapter is not exact accepted hardware/);
  assert.equal(fixture.observed.closed, true);
}

const matrixRow = {
  channel: "edge",
  executable,
  actual_version: "151.0.1.2",
  runtime_identity: boundIdentity,
  runtime_adapter: adapterFixture,
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
reject("executable_symlink", () =>
  collectBrowserRuntimeIdentity(alias, expected, runnerWith(), "darwin"));
chmodSync(executable, 0o644);
reject("executable_not_executable", () =>
  collectBrowserRuntimeIdentity(executable, expected, runnerWith(), "darwin"));
chmodSync(executable, 0o755);
reject("codesign_deep_strict_failure", () => collectBrowserRuntimeIdentity(executable, expected,
  runnerWith({"codesign --verify --deep": {status: 1, stdout: "", stderr: "rejected"}}), "darwin"));
reject("wrong_team", () => collectBrowserRuntimeIdentity(executable, expected, (command, args) => {
  const result = runnerWith()(command, args);
  if (command === "codesign" && args[0] === "-d") result.stderr = result.stderr.replace("EQHXZ8M8AV", "BADTEAM000");
  return result;
}, "darwin"));
reject("missing_cdhash", () => collectBrowserRuntimeIdentity(executable, expected, (command, args) => {
  const result = runnerWith()(command, args);
  if (command === "codesign" && args[0] === "-d") result.stderr = result.stderr.replace(/^CDHash=.*$/m, "");
  return result;
}, "darwin"));
reject("notarization_rejected", () => collectBrowserRuntimeIdentity(executable, expected, (command, args) => {
  if (command === "spctl") return {status: 1, stdout: "", stderr: `${app}: rejected\nsource=no usable signature\n`};
  return runnerWith()(command, args);
}, "darwin"));
reject("notarization_origin_missing", () => collectBrowserRuntimeIdentity(executable, expected,
  (command, args) => {
    const result = runnerWith()(command, args);
    if (command === "spctl") result.stderr = result.stderr.replace(/^origin=.*$/m, "");
    return result;
  }, "darwin"));
reject("runtime_version_alias", () => bindRuntimeVersion(identity, "151.0.1.02"));
const intermediate = `${root}/intermediate`;
symlinkSync(`${app}/Contents`, intermediate, "dir");
reject("intermediate_symlink", () => collectBrowserRuntimeIdentity(
  `${intermediate}/MacOS/Google Chrome`, expected, runnerWith(), "darwin"));
const driftedIdentity = structuredClone(boundIdentity);
driftedIdentity.executable.sha256 = "f".repeat(64);
reject("terminal_identity_drift", () =>
  revalidateBrowserRuntimeIdentity(driftedIdentity, expected, runnerWith(), "darwin"));
reject("diagnostic_snapshot_nonempty", () =>
  validateEarlyDiagnostics({schema: 1, preload: true, snapshot: [{type: "error"}]}));
reject("diagnostic_preload_false", () =>
  validateEarlyDiagnostics({schema: 1, preload: false, snapshot: []}));
for (const [name, mutate] of [
  ["adapter_missing_reason", (value) => { delete value.reason; }],
  ["adapter_fallback", (value) => { value.isFallbackAdapter = true; }],
  ["adapter_fallback_absent", (value) => { value.isFallbackAdapter = null; }],
  ["adapter_rejected", (value) => { value.status = "REJECTED"; }],
  ["adapter_wrong_platform", (value) => { value.platform = "win32"; }],
  ["adapter_masked", (value) => {
    value.info.architecture = ""; value.info.device = ""; value.info.description = "";
  }],
  ["adapter_llvmpipe", (value) => { value.info.architecture = "llvmpipe"; }],
  ["adapter_cpu", (value) => { value.info.description = "CPU Vulkan adapter"; }],
  ["adapter_claimed_match", (value) => { value.softwareMatches = ["fixture"]; }],
  ["adapter_extra_field", (value) => { value.extra = true; }],
]) reject(name, () => {
  const candidate = structuredClone(adapterFixture);
  mutate(candidate);
  validateRuntimeAdapter(candidate);
});
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

const linuxRoot = `${root}/linux`;
const linuxExecutable = `${linuxRoot}/opt/google/chrome/chrome`;
const linuxSource = `${linuxRoot}/etc/apt/sources.list.d/blender-web-google-chrome.list`;
const linuxKeyring = `${linuxRoot}/etc/apt/keyrings/blender-web-google-linux.gpg`;
mkdirSync(`${linuxRoot}/opt/google/chrome`, {recursive: true});
mkdirSync(`${linuxRoot}/etc/apt/sources.list.d`, {recursive: true});
mkdirSync(`${linuxRoot}/etc/apt/keyrings`, {recursive: true});
writeFileSync(linuxExecutable, "fixture Linux ELF bytes");
chmodSync(linuxExecutable, 0o755);
writeFileSync(linuxKeyring, "fixture vendor keyring");
const linuxExpected = {
  ...browserIdentityContract("chrome", "linux"),
  executablePath: linuxExecutable,
  sourceFile: linuxSource,
  keyringPath: linuxKeyring,
};
const linuxSourceLine = `deb [arch=amd64 signed-by=${linuxKeyring}] ` +
  `https://dl.google.com/linux/chrome/deb/ stable main\n`;
writeFileSync(linuxSource, linuxSourceLine);
const packageVersion = "151.0.7922.173-1";
const packageSha256 = "d".repeat(64);
const keyFingerprint = linuxExpected.requiredFingerprint;
const gpgFixture = [
  "pub:-:4096:1:7721F63BD38B4796:0:0::::::scESC::::::23::0:",
  ["fpr", "", "", "", "", "", "", "", "", keyFingerprint, ""].join(":"),
].join("\n");
const readelfFixture = [
  "ELF Header:",
  "  Class:                             ELF64",
  "  Data:                              2's complement, little endian",
  "  Type:                              DYN (Position-Independent Executable file)",
  "  Machine:                           Advanced Micro Devices X86-64",
].join("\n");
function linuxRunner(overrides = {}) {
  return (command, args) => {
    const key = `${command} ${args[0] || ""}`;
    if (Object.hasOwn(overrides, key)) return overrides[key];
    if (command === "gpg") return {status: 0, stdout: gpgFixture, stderr: ""};
    if (command === "readelf") return {status: 0, stdout: readelfFixture, stderr: ""};
    if (command === "dpkg-query" && args[0] === "-S") {
      return {status: 0, stdout: `google-chrome-stable: ${linuxExecutable}\n`, stderr: ""};
    }
    if (command === "dpkg-query" && args[0] === "-W") {
      return {status: 0, stdout: `ii \tgoogle-chrome-stable\t${packageVersion}\tamd64\n`, stderr: ""};
    }
    if (command === "apt-cache" && args[0] === "policy") {
      return {status: 0, stdout: `google-chrome-stable:\n  Installed: ${packageVersion}\n` +
        `  Candidate: ${packageVersion}\n        500 https://dl.google.com/linux/chrome/deb ` +
        `stable/main amd64 Packages\n`, stderr: ""};
    }
    if (command === "apt-cache" && args[0] === "show") {
      return {status: 0, stdout: `Package: google-chrome-stable\nVersion: ${packageVersion}\n` +
        `Architecture: amd64\nFilename: pool/main/g/google-chrome-stable.deb\n` +
        `SHA256: ${packageSha256}\n`, stderr: ""};
    }
    if (command === "dpkg" && args[0] === "--verify") {
      return {status: 0, stdout: "", stderr: ""};
    }
    return {status: 1, stdout: "", stderr: "unexpected Linux identity command"};
  };
}

const linuxIdentity = collectBrowserRuntimeIdentity(
  linuxExecutable, linuxExpected, linuxRunner(), "linux");
assert.equal(linuxIdentity.schema, 2);
assert.equal(linuxIdentity.platform, "linux");
assert.equal(linuxIdentity.product.version, "151.0.7922.173");
assert.equal(linuxIdentity.package.candidate.sha256, packageSha256);
assert.deepEqual(linuxIdentity.package.keyring.primary_fingerprints, [keyFingerprint]);
const boundLinuxIdentity = bindRuntimeVersion(linuxIdentity, "151.0.7922.173");
assert.equal(boundLinuxIdentity.version_matches_product, true);
assert.deepEqual(revalidateBrowserRuntimeIdentity(
  boundLinuxIdentity, linuxExpected, linuxRunner(), "linux"), boundLinuxIdentity);
assert.deepEqual(legacySigning(boundLinuxIdentity), {
  identifier: "google-chrome-stable", team: keyFingerprint, valid: true,
});

reject("linux_wrong_elf_machine", () => collectBrowserRuntimeIdentity(
  linuxExecutable, linuxExpected, linuxRunner({"readelf -hW": {
    status: 0, stdout: readelfFixture.replace("Advanced Micro Devices X86-64", "AArch64"), stderr: "",
  }}), "linux"));
reject("linux_wrong_package_owner", () => collectBrowserRuntimeIdentity(
  linuxExecutable, linuxExpected, linuxRunner({"dpkg-query -S": {
    status: 0, stdout: `chromium: ${linuxExecutable}\n`, stderr: "",
  }}), "linux"));
reject("linux_stale_candidate", () => collectBrowserRuntimeIdentity(
  linuxExecutable, linuxExpected, linuxRunner({"apt-cache policy": {
    status: 0, stdout: `  Installed: ${packageVersion}\n  Candidate: 150.0.0.0-1\n` +
      `  500 https://dl.google.com/linux/chrome/deb stable/main amd64 Packages\n`, stderr: "",
  }}), "linux"));
reject("linux_unaccepted_signer", () => collectBrowserRuntimeIdentity(
  linuxExecutable, linuxExpected, linuxRunner({"gpg --batch": {
    status: 0, stdout: gpgFixture.replace(keyFingerprint, "A".repeat(40)), stderr: "",
  }}), "linux"));
reject("linux_modified_package", () => collectBrowserRuntimeIdentity(
  linuxExecutable, linuxExpected, linuxRunner({"dpkg --verify": {
    status: 0, stdout: `??5?????? ${linuxExecutable}\n`, stderr: "",
  }}), "linux"));
writeFileSync(linuxSource, linuxSourceLine.replace("signed-by=", "trusted=yes signed-by="));
reject("linux_source_contract_drift", () => collectBrowserRuntimeIdentity(
  linuxExecutable, linuxExpected, linuxRunner(), "linux"));
writeFileSync(linuxSource, linuxSourceLine);
reject("linux_contract_host_mismatch", () => collectBrowserRuntimeIdentity(
  linuxExecutable, linuxExpected, linuxRunner(), "darwin"));
const driftedLinuxIdentity = structuredClone(boundLinuxIdentity);
driftedLinuxIdentity.package.candidate.sha256 = "e".repeat(64);
reject("linux_terminal_identity_drift", () => revalidateBrowserRuntimeIdentity(
  driftedLinuxIdentity, linuxExpected, linuxRunner(), "linux"));

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
const adapterProducers = {
  ...producers,
  usd: readFileSync(new URL("../m7-usd-prep/verify_browser_usd.mjs", import.meta.url), "utf8"),
  files: readFileSync(new URL("../m7-product-gate/verify_files.mjs", import.meta.url), "utf8"),
};
const allocationMarkers = {
  browser_matrix: "mkdirSync(join(HERE, \"artifacts\")",
  product: "mkdirSync(ART",
  performance: "mkdirSync(ART",
  soak: "mkdirSync(PROFILE",
  staged: "fs.mkdirSync(OUTDIR",
  usd: "reserveReceiptDirectory(outRoot, outDir);",
  files: "writeFileSync(options.out",
};
for (const [name, source] of Object.entries(adapterProducers)) {
  const probeIndex = source.indexOf("requireHardwareRuntimeAdapter(");
  const allocationIndex = source.indexOf(allocationMarkers[name]);
  assert.ok(probeIndex >= 0, `${name} omits the shared hardware-adapter probe`);
  assert.match(source, /runtime_adapter/, `${name} omits the adapter from its receipt`);
  assert.ok(allocationIndex > probeIndex,
    `${name} allocates receipt evidence before the hardware-adapter gate`);
}
assert.match(producers.browser_matrix,
  /process\.exit\(browserMatrixInvocationPass\(priorExists, matrixPass, pass\) \? 0 : 1\)/,
  "browser matrix does not exit on the completed matrix verdict after a prior row");
assert.equal((producers.browser_matrix.match(/requireEmptyEarlyDiagnostics\(/g) || []).length, 2);
assert.equal((producers.product.match(/requireEmptyEarlyDiagnostics\(/g) || []).length, 4);
assert.doesNotMatch(producers.product, /\/Users\/paws/,
  "product producer retains the retired macOS checkout/module root");
assert.equal((producers.product.match(/browserIdentityContract\("chrome", HOST_PLATFORM\)/g) || []).length, 1,
  "product producer does not use exactly one host-specific Chrome identity contract");
assert.match(producers.product, /const NODE_VERSION = "v22\.16\.0";/,
  "product producer does not pin the receipt Node runtime");
assert.match(producers.product, /playwrightVersion !== PLAYWRIGHT_VERSION \|\| loaded\.pngjsVersion !== PNGJS_VERSION/,
  "product producer does not enforce exact browser dependency versions");
assert.equal((producers.performance.match(/requireEmptyEarlyDiagnostics\(/g) || []).length, 1);
assert.doesNotMatch(producers.performance, /\/Users\/paws/,
  "performance producer retains the retired macOS checkout/module root");
assert.equal((producers.performance.match(/browserIdentityContract\("chrome", HOST_PLATFORM\)/g) || []).length, 1,
  "performance producer does not use exactly one host-specific Chrome identity contract");
assert.match(producers.performance, /const NODE_VERSION = "v22\.16\.0";/,
  "performance producer does not pin the receipt Node runtime");
assert.match(producers.performance,
  /playwrightVersion !== PLAYWRIGHT_VERSION \|\| loaded\.pngjsVersion !== PNGJS_VERSION/,
  "performance producer does not enforce exact browser dependency versions");
assert.equal((producers.soak.match(/requireEmptyEarlyDiagnostics\(/g) || []).length, 1);
assert.doesNotMatch(producers.soak, /\/Users\/paws/,
  "soak producer retains the retired macOS checkout/module root");
assert.equal((producers.soak.match(/browserIdentityContract\("chrome", HOST_PLATFORM\)/g) || []).length, 1,
  "soak producer does not use exactly one host-specific Chrome identity contract");
assert.match(producers.soak, /officialChromeVersion\(HOST_PLATFORM\)/,
  "soak producer does not select the host-specific Chrome stable feed");
assert.match(producers.soak, /const NODE_VERSION = "v22\.16\.0";/,
  "soak producer does not pin the receipt Node runtime");
assert.match(producers.soak,
  /playwrightVersion !== PLAYWRIGHT_VERSION \|\| loaded\.pngjsVersion !== PNGJS_VERSION/,
  "soak producer does not enforce exact browser dependency versions");
assert.equal((producers.soak.match(/requireHardwareRuntimeAdapter\(/g) || []).length, 2,
  "soak producer does not gate before profile allocation and recheck its persistent context");
assert.match(producers.soak, /JSON\.stringify\(runtimeAdapter\) !== JSON\.stringify\(preflightAdapter\)/,
  "soak producer does not bind its persistent context to the pre-allocation adapter");
assert.equal((producers.staged.match(/recordEarlyDiagnostics\('/g) || []).length, 3);
assert.doesNotMatch(producers.staged, /\/Users\/paws/,
  "staged producer retains the retired macOS checkout/module root");
assert.equal((producers.staged.match(/browserIdentityContract\(['"]chrome['"], HOST_PLATFORM\)/g) || []).length, 1,
  "staged producer does not use exactly one host-specific Chrome identity contract");
assert.match(producers.staged, /const NODE_VERSION = ['"]v22\.16\.0['"];/,
  "staged producer does not pin the receipt Node runtime");
assert.match(producers.staged,
  /playwrightVersion !== PLAYWRIGHT_VERSION \|\| loaded\.pngjsVersion !== PNGJS_VERSION/,
  "staged producer does not enforce exact browser dependency versions");

rmSync(root, {recursive: true, force: true});
console.log(`M8_RUNTIME_EVIDENCE_SELFCHECK_PASS ` +
  `positive=identity+diagnostics+matrix-prior+matrix-exit negative=${negatives.length} ` +
  `adapter_producers=${Object.keys(adapterProducers).join(",")} checks=${negatives.join(",")}`);

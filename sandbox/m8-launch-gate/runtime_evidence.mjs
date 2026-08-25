// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Shared fail-closed runtime identity, hardware-adapter, and first-script
// diagnostics evidence for M5-M8 browser producers. Darwin binds the canonical
// notarized app. Linux binds the canonical vendor-owned ELF through dpkg plus
// signed APT metadata.

"use strict";

import {spawnSync} from "node:child_process";
import {createHash} from "node:crypto";
import {
  closeSync, lstatSync, openSync, readFileSync, readSync, realpathSync,
} from "node:fs";
import {isAbsolute, normalize} from "node:path";

const HEX_SHA256 = /^[0-9a-f]{64}$/;
const HEX_CDHASH = /^[0-9a-f]{40,64}$/;
const HEX_FINGERPRINT = /^[0-9A-F]{40}$/;
const RUNTIME_ADAPTER_CONTRACT = "hardware-webgpu-adapter-v1";
const RUNTIME_ADAPTER_FIELDS = Object.freeze([
  "contract", "status", "present", "platform", "powerPreference",
  "isFallbackAdapter", "info", "softwareMatches", "reason",
]);
const RUNTIME_ADAPTER_INFO_FIELDS = Object.freeze([
  "vendor", "architecture", "device", "description",
]);
const SOFTWARE_ADAPTER_TOKENS = Object.freeze([
  "swiftshader", "llvmpipe", "lavapipe", "softpipe", "software rasterizer",
  "microsoft basic render", "warp",
]);
const ADAPTER_PROBE_URL = new URL("../../GOAL.md", import.meta.url).href;

const DARWIN_CONTRACTS = Object.freeze({
  chrome: Object.freeze({
    platform: "darwin", channel: "chrome",
    identifier: "com.google.Chrome", team: "EQHXZ8M8AV", appName: "Google Chrome.app",
    executableName: "Google Chrome",
  }),
  edge: Object.freeze({
    platform: "darwin", channel: "edge",
    identifier: "com.microsoft.edgemac", team: "UBF8T346G9", appName: "Microsoft Edge.app",
    executableName: "Microsoft Edge",
  }),
});

const LINUX_CONTRACTS = Object.freeze({
  chrome: Object.freeze({
    platform: "linux", channel: "chrome",
    executablePath: "/opt/google/chrome/chrome",
    packageName: "google-chrome-stable",
    sourceFile: "/etc/apt/sources.list.d/blender-web-google-chrome.list",
    keyringPath: "/etc/apt/keyrings/blender-web-google-linux.gpg",
    repositoryUri: "https://dl.google.com/linux/chrome/deb/",
    suite: "stable", component: "main",
    requiredFingerprint: "EB4C1BFD4F042F6DDDCCEC917721F63BD38B4796",
    allowedPrimaryFingerprints: Object.freeze(["EB4C1BFD4F042F6DDDCCEC917721F63BD38B4796"]),
  }),
  edge: Object.freeze({
    platform: "linux", channel: "edge",
    executablePath: "/opt/microsoft/msedge/msedge",
    packageName: "microsoft-edge-stable",
    sourceFile: "/etc/apt/sources.list.d/blender-web-microsoft-edge.list",
    keyringPath: "/etc/apt/keyrings/blender-web-microsoft-edge.gpg",
    repositoryUri: "https://packages.microsoft.com/repos/edge",
    suite: "stable", component: "main",
    requiredFingerprint: "BC528686B50D79E339D3721CEB3E94ADBE1229CF",
    allowedPrimaryFingerprints: Object.freeze(["BC528686B50D79E339D3721CEB3E94ADBE1229CF"]),
  }),
});

function fail(message) {
  throw new Error(`M8 runtime evidence: ${message}`);
}

export function classifyRuntimeAdapter(raw, platform = process.platform) {
  const info = Object.fromEntries(RUNTIME_ADAPTER_INFO_FIELDS.map((key) =>
    [key, typeof raw?.info?.[key] === "string" ? raw.info[key] : ""]));
  const identity = Object.values(info).join(" ").trim().toLowerCase();
  const detailIdentity = [info.architecture, info.device, info.description].join(" ").trim();
  const softwareMatches = SOFTWARE_ADAPTER_TOKENS.filter((token) => identity.includes(token));
  if (/(^|[^a-z0-9])cpu([^a-z0-9]|$)/.test(identity)) softwareMatches.push("cpu");
  const present = raw?.present === true;
  const isFallbackAdapter = typeof raw?.isFallbackAdapter === "boolean" ?
    raw.isFallbackAdapter : null;
  let reason = "accepted-hardware";
  if (!present) reason = "adapter-absent";
  else if (isFallbackAdapter === true) reason = "fallback-adapter";
  else if (isFallbackAdapter !== false) reason = "fallback-status-absent";
  else if (!identity || !detailIdentity) reason = "adapter-info-absent";
  else if (softwareMatches.length) reason = "software-adapter";
  return {
    contract: RUNTIME_ADAPTER_CONTRACT,
    status: reason === "accepted-hardware" ? "ACCEPTED" : "REJECTED",
    present,
    platform,
    powerPreference: "high-performance",
    isFallbackAdapter,
    info,
    softwareMatches,
    reason,
  };
}

export function validateRuntimeAdapter(value, platform = process.platform) {
  const keys = value && typeof value === "object" && !Array.isArray(value) ?
    Object.keys(value).sort() : [];
  const info = value?.info;
  const infoKeys = info && typeof info === "object" && !Array.isArray(info) ?
    Object.keys(info).sort() : [];
  const identity = RUNTIME_ADAPTER_INFO_FIELDS.map((key) => info?.[key] || "")
    .join(" ").trim().toLowerCase();
  const detailIdentity = [info?.architecture, info?.device, info?.description]
    .filter((item) => typeof item === "string").join(" ").trim();
  const softwareMatches = SOFTWARE_ADAPTER_TOKENS.filter((token) => identity.includes(token));
  if (/(^|[^a-z0-9])cpu([^a-z0-9]|$)/.test(identity)) softwareMatches.push("cpu");
  if (JSON.stringify(keys) !== JSON.stringify([...RUNTIME_ADAPTER_FIELDS].sort()) ||
      JSON.stringify(infoKeys) !== JSON.stringify([...RUNTIME_ADAPTER_INFO_FIELDS].sort()) ||
      RUNTIME_ADAPTER_INFO_FIELDS.some((key) => typeof info?.[key] !== "string") ||
      value?.contract !== RUNTIME_ADAPTER_CONTRACT || value?.status !== "ACCEPTED" ||
      value?.present !== true || !new Set(["darwin", "linux"]).has(platform) ||
      value?.platform !== platform ||
      value?.powerPreference !== "high-performance" || value?.isFallbackAdapter !== false ||
      !identity || !detailIdentity || softwareMatches.length !== 0 ||
      !Array.isArray(value?.softwareMatches) || value.softwareMatches.length !== 0 ||
      value?.reason !== "accepted-hardware") {
    fail(`runtime adapter is not exact accepted hardware: ${JSON.stringify(value)}`);
  }
  return value;
}

export async function requireHardwareRuntimeAdapter(context, platform = process.platform) {
  if (!context || typeof context.newPage !== "function") {
    fail("browser context is absent before runtime adapter probe");
  }
  const page = await context.newPage();
  try {
    await page.goto(ADAPTER_PROBE_URL, {waitUntil: "load", timeout: 30_000});
    const raw = await page.evaluate(async () => {
      const adapter = await navigator.gpu?.requestAdapter({powerPreference: "high-performance"});
      if (!adapter) return {present: false, isFallbackAdapter: null, info: null};
      const info = adapter.info || {};
      return {
        present: true,
        isFallbackAdapter: typeof info.isFallbackAdapter === "boolean" ?
          info.isFallbackAdapter : (adapter.isFallbackAdapter ?? null),
        info: Object.fromEntries(["vendor", "architecture", "device", "description"]
          .map((key) => [key, typeof info[key] === "string" ? info[key] : ""])),
      };
    });
    return validateRuntimeAdapter(classifyRuntimeAdapter(raw, platform), platform);
  }
  finally {
    await page.close().catch(() => {});
  }
}

function checkedCommand(runner, command, args) {
  const result = runner(command, args, {
    encoding: "utf8", timeout: 60_000, maxBuffer: 1024 * 1024,
    env: {...process.env, LC_ALL: "C", LANG: "C"},
  });
  if (!result || result.error || result.signal || result.status !== 0) {
    const detail = String(result?.stderr || result?.stdout || result?.error || "").trim();
    fail(`${command} ${args.join(" ")} failed${detail ? `: ${detail}` : ""}`);
  }
  return {stdout: String(result.stdout || "").trim(), stderr: String(result.stderr || "").trim()};
}

function commandText(runner, command, args) {
  const result = checkedCommand(runner, command, args);
  return `${result.stderr}\n${result.stdout}`.trim();
}

export function browserIdentityContract(channel, platform = process.platform) {
  const table = platform === "darwin" ? DARWIN_CONTRACTS :
    platform === "linux" ? LINUX_CONTRACTS : null;
  const contract = table?.[channel];
  if (!contract) fail(`unsupported branded browser platform/channel ${platform}/${channel}`);
  return contract;
}

export function sha256File(path) {
  const hash = createHash("sha256");
  const descriptor = openSync(path, "r");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  try {
    for (;;) {
      const count = readSync(descriptor, buffer, 0, buffer.length, null);
      if (count === 0) break;
      hash.update(buffer.subarray(0, count));
    }
  }
  finally {
    closeSync(descriptor);
  }
  return hash.digest("hex");
}

function exactPath(path, kind, executable = false) {
  if (typeof path !== "string" || !isAbsolute(path) || normalize(path) !== path) {
    fail(`${kind} path must be absolute and normalized`);
  }
  let component = "/";
  for (const part of path.split("/").filter(Boolean)) {
    component = component === "/" ? `/${part}` : `${component}/${part}`;
    let info;
    try {
      info = lstatSync(component);
    }
    catch (error) {
      fail(`${kind} path is unavailable: ${component}: ${error?.code || error}`);
    }
    if (info.isSymbolicLink()) fail(`${kind} path contains symlink component: ${component}`);
  }
  const leaf = lstatSync(path);
  if (leaf.isSymbolicLink() || !leaf.isFile()) fail(`${kind} is not a regular non-symlink file`);
  if (realpathSync(path) !== path) fail(`${kind} requested path is not its exact real path`);
  if (leaf.size <= 0) fail(`${kind} must be nonempty`);
  if (executable && (leaf.mode & 0o111) === 0) fail(`${kind} is not executable`);
  return leaf;
}

function executableRecord(path) {
  const info = exactPath(path, "browser executable", true);
  const sha256 = sha256File(path);
  if (!HEX_SHA256.test(sha256)) fail("browser executable SHA-256 is noncanonical");
  return {requested_path: path, path, bytes: info.size, sha256};
}

function fileRecord(path, kind) {
  const info = exactPath(path, kind, false);
  const sha256 = sha256File(path);
  if (!HEX_SHA256.test(sha256)) fail(`${kind} SHA-256 is noncanonical`);
  return {path, bytes: info.size, sha256};
}

function field(text, name) {
  const matches = [...text.matchAll(new RegExp(`^${name}=(.+)$`, "gm"))];
  return matches.length === 1 ? matches[0][1].trim() : null;
}

function collectDarwinIdentity(executable, expected, runner) {
  const executableInfo = executableRecord(executable);
  const appMatch = /^(.*\.app)\/Contents\/MacOS\/([^/]+)$/.exec(executable);
  if (!appMatch || appMatch[1].split("/").at(-1) !== expected.appName ||
      appMatch[2] !== expected.executableName) {
    fail("browser executable is not the canonical branded Mac app executable");
  }
  const appPath = appMatch[1];
  const appInfo = lstatSync(appPath);
  if (appInfo.isSymbolicLink() || !appInfo.isDirectory()) {
    fail("browser app is not a real non-symlink directory");
  }
  const plist = `${appPath}/Contents/Info.plist`;
  const plistInfo = lstatSync(plist);
  if (plistInfo.isSymbolicLink() || !plistInfo.isFile()) fail("browser app Info.plist is absent or indirect");

  commandText(runner, "codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  const detail = commandText(runner, "codesign", ["-d", "--verbose=4", appPath]);
  const identifier = field(detail, "Identifier");
  const teamIdentifier = field(detail, "TeamIdentifier");
  const cdhash = field(detail, "CDHash")?.toLowerCase() || null;
  if (!identifier || !teamIdentifier || !cdhash || !HEX_CDHASH.test(cdhash)) {
    fail("codesign detail lacks canonical identifier/team/CDHash");
  }
  if (identifier !== expected.identifier || teamIdentifier !== expected.team) {
    fail(`unexpected browser signature identity ${identifier}/${teamIdentifier}`);
  }

  const assessment = commandText(
    runner, "spctl", ["--assess", "--type", "execute", "--verbose=4", appPath]);
  const source = field(assessment, "source");
  const origin = field(assessment, "origin");
  if (!/(?:^|\n).*: accepted(?:\n|$)/m.test(assessment) || source !== "Notarized Developer ID") {
    fail("Gatekeeper did not accept the app as Notarized Developer ID");
  }
  if (!origin) fail("Gatekeeper assessment has no notarized application origin");
  const appVersion = commandText(
    runner, "plutil", ["-extract", "CFBundleShortVersionString", "raw", "-o", "-", plist]);
  if (!/^[0-9]+(?:\.[0-9]+){1,4}$/.test(appVersion)) fail("app bundle version is noncanonical");

  return {
    schema: 1,
    executable: executableInfo,
    app: {path: appPath, version: appVersion},
    codesign: {deep_strict: true, identifier, team_identifier: teamIdentifier, cdhash},
    notarization: {assessed: true, accepted: true, source, origin},
  };
}

function parsePrimaryFingerprints(text) {
  const fingerprints = [];
  let waitingForPrimary = false;
  for (const line of text.split("\n")) {
    const fields = line.split(":");
    if (fields[0] === "pub") waitingForPrimary = true;
    else if (fields[0] === "fpr" && waitingForPrimary) {
      const fingerprint = String(fields[9] || "").toUpperCase();
      if (!HEX_FINGERPRINT.test(fingerprint)) fail("APT keyring has a noncanonical primary fingerprint");
      fingerprints.push(fingerprint);
      waitingForPrimary = false;
    }
  }
  if (waitingForPrimary || fingerprints.length === 0 || new Set(fingerprints).size !== fingerprints.length) {
    fail("APT keyring primary fingerprint inventory is absent or ambiguous");
  }
  return fingerprints.sort();
}

function parseReadelf(text) {
  const value = (name) => new RegExp(`^\\s*${name}:\\s*(.+)$`, "m").exec(text)?.[1]?.trim() || null;
  const result = {
    class: value("Class"), data: value("Data"), type: value("Type")?.split(/\s+/)[0] || null,
    machine: value("Machine"),
  };
  if (result.class !== "ELF64" || result.data !== "2's complement, little endian" ||
      result.type !== "DYN" || result.machine !== "Advanced Micro Devices X86-64") {
    fail(`browser executable is not the canonical amd64 PIE ELF: ${JSON.stringify(result)}`);
  }
  return result;
}

function parseDeb822(text) {
  const wanted = new Set(["Package", "Version", "Architecture", "Filename", "SHA256"]);
  const values = {};
  for (const line of text.split("\n")) {
    const match = /^([A-Za-z0-9][A-Za-z0-9-]*):\s*(.*)$/.exec(line);
    if (!match || !wanted.has(match[1])) continue;
    if (Object.hasOwn(values, match[1])) fail(`APT package metadata duplicates ${match[1]}`);
    values[match[1]] = match[2].trim();
  }
  if ([...wanted].some((name) => !values[name])) fail("APT package metadata is incomplete");
  return values;
}

function upstreamDebianVersion(version) {
  const withoutEpoch = version.replace(/^\d+:/, "");
  const revision = withoutEpoch.lastIndexOf("-");
  const upstream = revision > 0 ? withoutEpoch.slice(0, revision) : withoutEpoch;
  if (!/^[0-9]+(?:\.[0-9]+){1,4}$/.test(upstream)) fail(`package version is noncanonical: ${version}`);
  return upstream;
}

function expectedSourceLine(contract) {
  return `deb [arch=amd64 signed-by=${contract.keyringPath}] ` +
    `${contract.repositoryUri} ${contract.suite} ${contract.component}`;
}

function collectLinuxIdentity(executable, contract, runner) {
  if (executable !== contract.executablePath) {
    fail(`Linux browser executable must be canonical ${contract.executablePath}`);
  }
  const executableInfo = executableRecord(executable);
  const sourceInfo = fileRecord(contract.sourceFile, "APT source");
  const keyringInfo = fileRecord(contract.keyringPath, "APT keyring");
  const activeSourceLines = readFileSync(contract.sourceFile, "utf8").split(/\r?\n/)
    .map((line) => line.trim()).filter((line) => line && !line.startsWith("#"));
  if (activeSourceLines.length !== 1 || activeSourceLines[0] !== expectedSourceLine(contract)) {
    fail("APT source is not the exact arch/signed-by/vendor stable repository contract");
  }

  const gpg = checkedCommand(runner, "gpg", [
    "--batch", "--no-options", "--show-keys", "--with-colons", "--fingerprint",
    contract.keyringPath,
  ]).stdout;
  const primaryFingerprints = parsePrimaryFingerprints(gpg);
  const allowed = [...contract.allowedPrimaryFingerprints].sort();
  if (!primaryFingerprints.includes(contract.requiredFingerprint) ||
      primaryFingerprints.some((value) => !allowed.includes(value))) {
    fail("APT keyring does not contain only the accepted vendor primary signing key");
  }

  const elf = parseReadelf(checkedCommand(runner, "readelf", ["-hW", executable]).stdout);
  const ownerLines = checkedCommand(runner, "dpkg-query", ["-S", executable]).stdout.split("\n");
  const escapedExecutable = executable.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const ownerPattern = new RegExp(`^${contract.packageName}(?::amd64)?: ${escapedExecutable}$`);
  if (ownerLines.length !== 1 || !ownerPattern.test(ownerLines[0])) {
    fail("browser executable is not uniquely owned by the canonical vendor package");
  }

  const installed = checkedCommand(runner, "dpkg-query", [
    "-W", "-f=${db:Status-Abbrev}\\t${binary:Package}\\t${Version}\\t${Architecture}\\n",
    contract.packageName,
  ]).stdout.split("\t");
  if (installed.length !== 4 || installed[0] !== "ii " ||
      !new Set([contract.packageName, `${contract.packageName}:amd64`]).has(installed[1]) ||
      !installed[2] || installed[3] !== "amd64") {
    fail("canonical browser package is not exactly installed for amd64");
  }
  const packageVersion = installed[2];
  const productVersion = upstreamDebianVersion(packageVersion);

  const policy = checkedCommand(runner, "apt-cache", ["policy", contract.packageName]).stdout;
  const installedPolicy = /^\s*Installed:\s*(\S+)\s*$/m.exec(policy)?.[1] || null;
  const candidatePolicy = /^\s*Candidate:\s*(\S+)\s*$/m.exec(policy)?.[1] || null;
  const repositoryMarker = `${contract.repositoryUri.replace(/\/$/, "")} ` +
    `${contract.suite}/${contract.component} amd64 Packages`;
  if (installedPolicy !== packageVersion || candidatePolicy !== packageVersion ||
      !policy.includes(repositoryMarker)) {
    fail("installed browser is not the exact vendor-repository APT candidate");
  }

  const metadata = parseDeb822(checkedCommand(runner, "apt-cache", [
    "show", "--no-all-versions", `${contract.packageName}=${packageVersion}`,
  ]).stdout);
  if (metadata.Package !== contract.packageName || metadata.Version !== packageVersion ||
      metadata.Architecture !== "amd64" || !HEX_SHA256.test(metadata.SHA256.toLowerCase()) ||
      !/^[A-Za-z0-9][A-Za-z0-9+._\/-]*\.deb$/.test(metadata.Filename) ||
      metadata.Filename.includes("..")) {
    fail("APT candidate package metadata does not exactly identify the vendor amd64 archive");
  }
  const verified = checkedCommand(runner, "dpkg", ["--verify", contract.packageName]);
  if (verified.stdout || verified.stderr) fail("dpkg reports modified browser package files");

  return {
    schema: 2,
    platform: "linux",
    executable: executableInfo,
    product: {channel: contract.channel, version: productVersion, package_version: packageVersion},
    elf,
    package: {
      manager: "dpkg+apt", name: contract.packageName, status: "ii", version: packageVersion,
      architecture: "amd64", owner_verified: true, files_verified: true,
      source: {...sourceInfo, uri: contract.repositoryUri, suite: contract.suite,
        component: contract.component, signed_by: contract.keyringPath},
      keyring: {...keyringInfo, required_fingerprint: contract.requiredFingerprint,
        primary_fingerprints: primaryFingerprints},
      candidate: {version: metadata.Version, filename: metadata.Filename,
        sha256: metadata.SHA256.toLowerCase()},
    },
  };
}

export function collectBrowserRuntimeIdentity(executable, expected, runner = spawnSync,
  platform = process.platform) {
  const contract = expected?.platform ? expected : {
    ...expected, platform: "darwin", appName: /microsoft/i.test(expected?.identifier || "") ?
      "Microsoft Edge.app" : "Google Chrome.app",
    executableName: /microsoft/i.test(expected?.identifier || "") ? "Microsoft Edge" : "Google Chrome",
  };
  if (contract.platform !== platform) {
    fail(`browser identity contract ${contract.platform} does not match host ${platform}`);
  }
  if (platform === "darwin") return collectDarwinIdentity(executable, contract, runner);
  if (platform === "linux") return collectLinuxIdentity(executable, contract, runner);
  fail(`unsupported browser identity host ${platform}`);
}

export function bindRuntimeVersion(identity, runtimeVersion) {
  const expectedVersion = identity?.schema === 1 ? identity.app?.version :
    identity?.schema === 2 && identity.platform === "linux" ? identity.product?.version : null;
  if (!identity || typeof runtimeVersion !== "string" || runtimeVersion !== expectedVersion) {
    fail(`browser runtime/product version mismatch ${runtimeVersion}/${expectedVersion}`);
  }
  return identity.schema === 1 ?
    {...identity, runtime_version: runtimeVersion, version_matches_app: true} :
    {...identity, runtime_version: runtimeVersion, version_matches_product: true};
}

export function revalidateBrowserRuntimeIdentity(identity, expected, runner = spawnSync,
  platform = process.platform) {
  if (!identity || typeof identity.runtime_version !== "string") {
    fail("terminal runtime identity has no bound runtime version");
  }
  const terminal = bindRuntimeVersion(
    collectBrowserRuntimeIdentity(identity.executable?.requested_path, expected, runner, platform),
    identity.runtime_version);
  if (JSON.stringify(terminal) !== JSON.stringify(identity)) {
    fail("browser executable/package identity drifted during runtime evidence capture");
  }
  return terminal;
}

export function legacySigning(identity) {
  if (identity?.schema === 1) {
    return {
      identifier: identity.codesign.identifier,
      team: identity.codesign.team_identifier,
      valid: identity.codesign.deep_strict === true && identity.notarization.accepted === true,
    };
  }
  if (identity?.schema === 2 && identity.platform === "linux") {
    return {
      identifier: identity.package.name,
      team: identity.package.keyring.required_fingerprint,
      valid: identity.package.owner_verified === true && identity.package.files_verified === true &&
        identity.package.candidate.version === identity.package.version &&
        identity.package.keyring.primary_fingerprints.includes(
          identity.package.keyring.required_fingerprint),
    };
  }
  fail("unsupported runtime identity schema for legacy signing projection");
}

export function validateEarlyDiagnostics(value, label = "scenario") {
  const keys = value && typeof value === "object" && !Array.isArray(value) ? Object.keys(value).sort() : [];
  if (JSON.stringify(keys) !== JSON.stringify(["preload", "schema", "snapshot"]) ||
      value.schema !== 1 || value.preload !== true || !Array.isArray(value.snapshot) ||
      value.snapshot.length !== 0) {
    fail(`${label} early diagnostics are not exact schema-1/preloaded/empty`);
  }
  return {schema: 1, preload: true, snapshot: []};
}

export function browserMatrixRowPass(row) {
  return Boolean(row && typeof row === "object" && !Array.isArray(row) &&
    (() => {
      try { validateRuntimeAdapter(row.runtime_adapter); return true; }
      catch (_) { return false; }
    })() &&
    row.current_at_test === true && row.first_pixels === true &&
    row.interaction_smoke === true && row.offline_reload === true &&
    row.query_hooks_disabled === true && row.external_request_count === 0 &&
    row.gpu_errors === 0 && Array.isArray(row.errors) && row.errors.length === 0);
}

export function browserMatrixInvocationPass(priorExists, matrixPass, currentRowPass) {
  return priorExists ? matrixPass === true : currentRowPass === true;
}

export function validatePriorBrowserMatrix(prior, currentChannel, sourceArtifacts,
  bundleArtifacts, servedBundleSha256, rowKeys, revalidateIdentity) {
  const expectedTop = ["bundle_artifacts", "engines", "schema", "served_bundle_sha256",
    "source_artifacts", "updated_at", "verdict"];
  if (!prior || typeof prior !== "object" || Array.isArray(prior) ||
      JSON.stringify(Object.keys(prior).sort()) !== JSON.stringify(expectedTop) ||
      prior.schema !== 1 || prior.verdict !== "INCOMPLETE" ||
      typeof prior.updated_at !== "string" || !prior.updated_at ||
      JSON.stringify(prior.source_artifacts) !== JSON.stringify(sourceArtifacts) ||
      JSON.stringify(prior.bundle_artifacts) !== JSON.stringify(bundleArtifacts) ||
      prior.served_bundle_sha256 !== servedBundleSha256) {
    fail("existing browser-matrix receipt is not an exact current first-channel receipt");
  }
  const channels = prior.engines && typeof prior.engines === "object" &&
    !Array.isArray(prior.engines) ? Object.keys(prior.engines) : [];
  const opposite = currentChannel === "chrome" ? "edge" :
    currentChannel === "edge" ? "chrome" : null;
  if (!opposite || channels.length !== 1 || channels[0] !== opposite) {
    fail("existing browser-matrix receipt must contain exactly the opposite first channel");
  }
  const engine = prior.engines[opposite];
  if (!engine || typeof engine !== "object" || Array.isArray(engine) ||
      JSON.stringify(Object.keys(engine).sort()) !== JSON.stringify([...rowKeys].sort()) ||
      engine.channel !== opposite || engine.served_bundle_sha256 !== servedBundleSha256 ||
      engine.executable !== engine.runtime_identity?.executable?.path ||
      engine.actual_version !== engine.runtime_identity?.runtime_version ||
      !browserMatrixRowPass(engine)) {
    fail("existing browser-matrix first-channel row is not exact and passing");
  }
  validateEarlyDiagnostics(engine.early_diagnostics?.online, `${opposite}:prior-online`);
  validateEarlyDiagnostics(engine.early_diagnostics?.offline_reload,
    `${opposite}:prior-offline-reload`);
  validateRuntimeAdapter(engine.runtime_adapter);
  if (typeof revalidateIdentity !== "function") fail("matrix identity revalidator is absent");
  revalidateIdentity(engine.runtime_identity, opposite);
  return engine;
}

export async function requireEmptyEarlyDiagnostics(page, label = "scenario") {
  const value = await page.evaluate(() => ({
    schema: window.__bwEarlyDiagnostics?.schema ?? null,
    preload: window.__bwEarlyDiagnostics?.installedBeforeProductScripts === true,
    snapshot: window.__bwEarlyDiagnostics?.snapshot?.() ?? null,
  }));
  return validateEarlyDiagnostics(value, label);
}

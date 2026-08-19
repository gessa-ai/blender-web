// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Shared fail-closed runtime identity and first-script diagnostics evidence for
// M8 browser producers.  This module deliberately performs the live macOS
// signature/notarization commands; a browser-reported product name is not an
// executable identity.

"use strict";

import {spawnSync} from "node:child_process";
import {createHash} from "node:crypto";
import {
  closeSync, lstatSync, openSync, readSync, realpathSync, statSync,
} from "node:fs";
import {isAbsolute, normalize} from "node:path";

const HEX_SHA256 = /^[0-9a-f]{64}$/;
const HEX_CDHASH = /^[0-9a-f]{40,64}$/;

function fail(message) {
  throw new Error(`M8 runtime evidence: ${message}`);
}

function command(runner, command, args) {
  const result = runner(command, args, {encoding: "utf8", timeout: 60_000, maxBuffer: 1024 * 1024});
  if (!result || result.error || result.signal || result.status !== 0) {
    const detail = String(result?.stderr || result?.stdout || result?.error || "").trim();
    fail(`${command} ${args.join(" ")} failed${detail ? `: ${detail}` : ""}`);
  }
  return `${String(result.stderr || "")}\n${String(result.stdout || "")}`.trim();
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

function executableStat(path) {
  const stat = statSync(path);
  if (stat.size <= 0 || (stat.mode & 0o111) === 0) {
    fail("browser executable must be nonempty and executable");
  }
  return stat;
}

function field(text, name) {
  return new RegExp(`^${name}=(.+)$`, "m").exec(text)?.[1]?.trim() || null;
}

export function collectBrowserRuntimeIdentity(executable, expected, runner = spawnSync) {
  // Keep the lstat/realpath checks separate from stat so a leaf symlink cannot
  // inherit the target's otherwise-valid file facts.
  if (typeof executable !== "string" || !isAbsolute(executable) || normalize(executable) !== executable) {
    fail("browser executable path must be an absolute normalized path");
  }
  let component = "/";
  for (const part of executable.split("/").filter(Boolean)) {
    component = component === "/" ? `/${part}` : `${component}/${part}`;
    const info = lstatSync(component);
    if (info.isSymbolicLink()) fail(`browser executable path contains symlink component: ${component}`);
  }
  const leaf = lstatSync(executable);
  if (leaf.isSymbolicLink() || !leaf.isFile()) fail("browser executable is not a regular non-symlink file");
  const actual = realpathSync(executable);
  if (actual !== executable) fail("browser executable requested path is not its exact real path");
  const executableInfo = executableStat(actual);
  const appMatch = /^(.*\.app)\/Contents\/MacOS\/[^/]+$/.exec(actual);
  if (!appMatch) fail("browser executable is not the canonical Mac app executable");
  const appPath = appMatch[1];
  const appInfo = lstatSync(appPath);
  if (appInfo.isSymbolicLink() || !appInfo.isDirectory()) {
    fail("browser app is not a real non-symlink directory");
  }
  const plist = `${appPath}/Contents/Info.plist`;
  const plistInfo = lstatSync(plist);
  if (plistInfo.isSymbolicLink() || !plistInfo.isFile()) fail("browser app Info.plist is absent or indirect");

  command(runner, "codesign", ["--verify", "--deep", "--strict", "--verbose=2", appPath]);
  const detail = command(runner, "codesign", ["-d", "--verbose=4", appPath]);
  const identifier = field(detail, "Identifier");
  const teamIdentifier = field(detail, "TeamIdentifier");
  const cdhash = field(detail, "CDHash")?.toLowerCase() || null;
  if (!identifier || !teamIdentifier || !cdhash || !HEX_CDHASH.test(cdhash)) {
    fail("codesign detail lacks canonical identifier/team/CDHash");
  }
  if (!expected || identifier !== expected.identifier || teamIdentifier !== expected.team) {
    fail(`unexpected browser signature identity ${identifier}/${teamIdentifier}`);
  }

  const assessment = command(
    runner, "spctl", ["--assess", "--type", "execute", "--verbose=4", appPath]);
  const source = field(assessment, "source");
  const origin = field(assessment, "origin");
  if (!/(?:^|\n).*: accepted(?:\n|$)/m.test(assessment) || source !== "Notarized Developer ID") {
    fail("Gatekeeper did not accept the app as Notarized Developer ID");
  }
  if (!origin) fail("Gatekeeper assessment has no notarized application origin");
  const appVersion = command(
    runner, "plutil", ["-extract", "CFBundleShortVersionString", "raw", "-o", "-", plist]);
  if (!/^[0-9]+(?:\.[0-9]+){1,4}$/.test(appVersion)) fail("app bundle version is noncanonical");

  const sha256 = sha256File(actual);
  if (!HEX_SHA256.test(sha256)) fail("browser executable SHA-256 is noncanonical");
  return {
    schema: 1,
    executable: {requested_path: executable, path: actual, bytes: executableInfo.size, sha256},
    app: {path: appPath, version: appVersion},
    codesign: {
      deep_strict: true,
      identifier,
      team_identifier: teamIdentifier,
      cdhash,
    },
    notarization: {assessed: true, accepted: true, source, origin},
  };
}

export function bindRuntimeVersion(identity, runtimeVersion) {
  if (!identity || identity.schema !== 1 || typeof runtimeVersion !== "string" ||
      runtimeVersion !== identity.app?.version) {
    fail(`browser runtime/app version mismatch ${runtimeVersion}/${identity?.app?.version}`);
  }
  return {...identity, runtime_version: runtimeVersion, version_matches_app: true};
}

export function revalidateBrowserRuntimeIdentity(identity, expected, runner = spawnSync) {
  if (!identity || typeof identity.runtime_version !== "string") {
    fail("terminal runtime identity has no bound runtime version");
  }
  const terminal = bindRuntimeVersion(
    collectBrowserRuntimeIdentity(identity.executable?.requested_path, expected, runner),
    identity.runtime_version);
  if (JSON.stringify(terminal) !== JSON.stringify(identity)) {
    fail("browser executable/signature identity drifted during runtime evidence capture");
  }
  return terminal;
}

export function legacySigning(identity) {
  return {
    identifier: identity.codesign.identifier,
    team: identity.codesign.team_identifier,
    valid: identity.codesign.deep_strict === true && identity.notarization.accepted === true,
  };
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

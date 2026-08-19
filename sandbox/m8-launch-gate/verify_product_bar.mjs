// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Current-bundle product acceptance for LAUNCH.md's 30-second bar. Every timed
// scenario starts at navigation, so deferred loading cannot be hidden before the
// skeptic/own-file clocks. The pinned cold-load budget is additionally owned by
// measure_current.mjs and remains fail-closed in verify_m8.py.

import {createRequire} from "module";
import {mkdirSync, readFileSync, writeFileSync} from "fs";
import {
  canonicalBundleDigest, collectArtifacts, loadArtifactContract, requireServedBundle,
} from "./bundle_identity.mjs";
import {
  bindRuntimeVersion, collectBrowserRuntimeIdentity, legacySigning,
  requireEmptyEarlyDiagnostics, revalidateBrowserRuntimeIdentity,
} from "./runtime_evidence.mjs";

const require = createRequire("/Users/paws/plushly/game-platform/node_modules/");
const {chromium} = require("playwright");
const {PNG} = require("pngjs");

const ROOT = "/Users/paws/blender-web";
const ART = `${ROOT}/sandbox/m8-launch-gate/artifacts`;
const OUT = `${ART}/current-product-receipt.json`;
const PORT = Number.parseInt(process.argv[2] || "8168", 10);
const BASE = `http://localhost:${PORT}`;
const EXECUTABLE = process.argv[3] ||
  `${ROOT}/sandbox/m8-launch-gate/.browsers/Google Chrome.app/Contents/MacOS/Google Chrome`;
const OWN_BLEND = `${ROOT}/sandbox/corpus-prep/corpus/stress_mixed.blend`;
mkdirSync(ART, {recursive: true});
const artifactContract = loadArtifactContract(ROOT);
const sourceArtifacts = collectArtifacts(artifactContract.buildBase, artifactContract.sourceNames);
const bundleArtifacts = collectArtifacts(artifactContract.bundleBase, artifactContract.bundleNames);
const expectedBundleDigest = canonicalBundleDigest(bundleArtifacts);

const collectedRuntimeIdentity = collectBrowserRuntimeIdentity(EXECUTABLE,
  {identifier: "com.google.Chrome", team: "EQHXZ8M8AV"});
const signing = legacySigning(collectedRuntimeIdentity);

const receipt = {
  schema: 1,
  checked_at: new Date().toISOString(),
  source_artifacts: sourceArtifacts,
  bundle_artifacts: bundleArtifacts,
  served_bundle_sha256: null,
  browser: {},
  first_interaction_local: false,
  orbit_tab_extrude: false,
  own_blend_wow_under_30s: false,
  fidelity_tells_under_10s: false,
  share_scene_allowlisted: false,
  skeptic_path_complete: false,
  skeptic_path_seconds: null,
  own_blend_wow_seconds: null,
  interactive_viewport_ms: null,
  interactive_viewport_under_8s: false,
  details: {},
  early_diagnostics: {},
  failures: [],
};
const fail = (message) => { receipt.failures.push(message); console.error("[m8-product] FAIL " + message); };

function signature(buffer) {
  const png = PNG.sync.read(buffer);
  const values = [];
  for (let y = 0; y < png.height; y += 8) {
    for (let x = 0; x < png.width; x += 8) {
      const i = (y * png.width + x) * 4;
      values.push((png.data[i] + png.data[i + 1] + png.data[i + 2]) / 3);
    }
  }
  return values;
}
function meanAbsDiff(a, b) {
  if (!a || !b || a.length !== b.length) return null;
  let total = 0;
  for (let i = 0; i < a.length; i++) total += Math.abs(a[i] - b[i]);
  return total / a.length;
}
function pixelProof(buffer) {
  const png = PNG.sync.read(buffer);
  let samples = 0, nonblack = 0;
  const colors = new Set();
  for (let y = 0; y < png.height; y += 8) {
    for (let x = 0; x < png.width; x += 8) {
      const i = (y * png.width + x) * 4;
      const r = png.data[i], g = png.data[i + 1], b = png.data[i + 2];
      samples++;
      if (r + g + b > 30) nonblack++;
      colors.add(`${r >> 3},${g >> 3},${b >> 3}`);
    }
  }
  return {width: png.width, height: png.height, nonblack_ratio: nonblack / samples,
    quantized_colors: colors.size,
    pass: png.width >= 1000 && png.height >= 600 && nonblack / samples > 0.1 && colors.size > 128};
}

async function waitProduct(page) {
  await page.waitForFunction(() => {
    const state = document.querySelector("#state");
    return state?.textContent.includes("main loop (WM_main)") && window.__bwModule && window.BWFileBridge;
  }, null, {timeout: 240_000});
  const ready = await page.evaluate(() => window.BWFileBridge.ready());
  if (!ready) throw new Error("file bridge daemon did not arm");
  await page.waitForFunction(() => {
    const stage = window.__bwStage1;
    return stage && stage.phase === "done" && !stage.error &&
      stage.filesDone === stage.filesTotal && stage.bytesDone === stage.bytesTotal;
  }, null, {timeout: 600_000});
  await page.waitForFunction(() => window.__bwServiceWorker?.phase === "done", null, {timeout: 600_000});
  let proof = null;
  for (let attempt = 0; attempt < 120; attempt++) {
    proof = pixelProof(await page.locator("#canvas").screenshot());
    if (proof.pass) return proof;
    await page.waitForTimeout(500);
  }
  throw new Error("strict product pixels absent: " + JSON.stringify(proof));
}

const launch = {headless: false};
if (EXECUTABLE) launch.executablePath = EXECUTABLE;
const browser = await chromium.launch(launch);
const browserVersion = browser.version();
const runtimeIdentity = bindRuntimeVersion(collectedRuntimeIdentity, browserVersion);
receipt.browser = {engine: "chrome", executable: EXECUTABLE, version: browserVersion,
  signing, runtime_identity: runtimeIdentity};
const context = await browser.newContext({
  viewport: {width: 1280, height: 720}, deviceScaleFactor: 1, acceptDownloads: true,
});
const allRequests = [];
const external = [];
const errors = [];

function observe(page) {
  page.on("request", (request) => {
    allRequests.push(request.url());
    try { if (new URL(request.url()).origin !== new URL(BASE).origin) external.push(request.url()); }
    catch (_) { external.push(request.url()); }
  });
  page.on("console", (message) => {
    const text = message.text();
    if (/ValidationError|GPU-ERROR|uncaptured WebGPU error/i.test(text)) errors.push(text.slice(0, 500));
  });
  page.on("pageerror", (error) => errors.push("pageerror: " + error.message));
  page.on("crash", () => errors.push("PAGE CRASH"));
}

try {
  const page = await context.newPage();
  observe(page);
  const navigationStart = performance.now();
  const navigationResponse = await page.goto(`${BASE}/index.html`,
    {waitUntil: "domcontentloaded", timeout: 60_000});
  receipt.served_bundle_sha256 = await requireServedBundle(navigationResponse, expectedBundleDigest);
  const initialPixels = await waitProduct(page);
  receipt.interactive_viewport_ms = Math.round((performance.now() - navigationStart) * 10) / 10;
  receipt.interactive_viewport_under_8s = receipt.interactive_viewport_ms <= 8000;
  const initial = await page.evaluate(() => window.BWFileBridge.inspectScene());
  const canvas = page.locator("#canvas");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas has no bounding box");
  const cx = box.x + box.width * 0.42;
  const cy = box.y + box.height * 0.48;
  await page.mouse.move(cx, cy);
  await canvas.focus();

  // The exact skeptic path runs with Chromium's network disabled after the full
  // staged load/cache.  Any successful edit/render/save/export is therefore local.
  const requestsAtReady = allRequests.length;
  await context.setOffline(true);
  const pathStart = navigationStart;
  const beforeSplashDismiss = signature(await canvas.screenshot());
  await page.keyboard.press("Escape");
  await page.waitForTimeout(250);
  const workspaceBuffer = await canvas.screenshot();
  const splashDifference = meanAbsDiff(beforeSplashDismiss, signature(workspaceBuffer));
  const workspacePixels = pixelProof(workspaceBuffer);
  const beforeOrbit = signature(await canvas.screenshot());
  await page.mouse.down({button: "middle"});
  await page.mouse.move(cx + 90, cy + 45, {steps: 6});
  await page.mouse.up({button: "middle"});
  await page.waitForTimeout(350);
  const afterOrbit = signature(await canvas.screenshot());
  const orbitDifference = meanAbsDiff(beforeOrbit, afterOrbit);

  // Model + modifier through trusted Blender keymap events.
  await page.keyboard.press("Tab");
  await page.keyboard.press("3");
  await page.keyboard.press("e");
  await page.keyboard.type("1");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Control+2");

  // Exercise two unmistakable standard-layout keymap tells while the ten-second
  // fidelity clock is still running.  Pixel deltas prove the N/T panels really
  // toggled; the authoritative M4 comparator separately owns exact theme/font/
  // splash parity, so this runner does not infer fidelity from a pretty image.
  const beforeN = signature(await canvas.screenshot());
  await page.keyboard.press("n");
  await page.waitForTimeout(120);
  const nPanelDifference = meanAbsDiff(beforeN, signature(await canvas.screenshot()));
  await page.keyboard.press("n");
  const beforeT = signature(await canvas.screenshot());
  await page.keyboard.press("t");
  await page.waitForTimeout(120);
  const tPanelDifference = meanAbsDiff(beforeT, signature(await canvas.screenshot()));
  await page.keyboard.press("t");
  const fidelitySeconds = Math.round((performance.now() - pathStart) / 10) / 100;

  // Material + animation + OBJ export through Blender's own visible Python
  // Console (Shift+F4 is launch-tier UI), not through a URL/dev execution hook.
  await page.keyboard.press("Shift+F4");
  await page.waitForTimeout(200);
  const consoleCommand = [
    "import bpy",
    "o=bpy.context.active_object",
    "m=bpy.data.materials.get('M8_Skeptic') or bpy.data.materials.new('M8_Skeptic')",
    "o.data.materials.append(m) if len(o.data.materials)==0 else None",
    "o.keyframe_insert(data_path='location',frame=1)",
    "o.location.z+=0.5",
    "o.keyframe_insert(data_path='location',frame=24)",
    "bpy.context.scene.frame_set(12)",
    "bpy.ops.wm.obj_export(filepath='/tmp/bw_io/m8-skeptic.obj',export_selected_objects=False)",
  ].join("; ");
  await page.keyboard.type(consoleCommand, {delay: 0});
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => {
    try { return window.__bwModule.FS.stat("/tmp/bw_io/m8-skeptic.obj").size > 100; }
    catch (_) { return false; }
  }, null, {timeout: 15_000});
  const exportBytes = await page.evaluate(() =>
    window.__bwModule.FS.stat("/tmp/bw_io/m8-skeptic.obj").size);
  await page.keyboard.press("Shift+F5");

  // Material Preview is the skeptic path's bounded render preview.
  const beforePreview = signature(await canvas.screenshot());
  await page.keyboard.press("z");
  await page.keyboard.press("m");
  await page.waitForTimeout(1200);
  const afterPreviewBuffer = await canvas.screenshot();
  const previewDifference = meanAbsDiff(beforePreview, signature(afterPreviewBuffer));
  const previewPixels = pixelProof(afterPreviewBuffer);

  const save = await page.evaluate(async () => {
    const result = await window.BWFileBridge.requestSaveBytes("m8-skeptic.blend");
    return {bytes: result.bytes.length, magic: Array.from(result.bytes.slice(0, 4)), ack: result.ack};
  });
  const authored = await page.evaluate(() => window.BWFileBridge.inspectScene());
  receipt.skeptic_path_seconds = Math.round((performance.now() - pathStart) / 10) / 100;
  const noNetworkDuringPath = allRequests.length === requestsAtReady;
  receipt.first_interaction_local = receipt.interactive_viewport_under_8s &&
    noNetworkDuringPath && orbitDifference > 0.5;
  receipt.orbit_tab_extrude = orbitDifference > 0.5 && authored.ok && authored.mode === "OBJECT" &&
    authored.meshVertices > 8;
  const saveOk = save.bytes > 1000 && save.magic.join(",") === "40,181,47,253" && save.ack?.ok;
  const skepticChecks = {
    initial_default_scene: initial.ok && ["Camera", "Cube", "Light"].every((name) => initial.objects.includes(name)),
    orbit_visible: orbitDifference > 0.5,
    extruded_mesh: authored.meshVertices > 8,
    modifier: authored.modifiers.includes("SUBSURF"),
    material: authored.materials.includes("M8_Skeptic"),
    animated: authored.hasAction === true,
    render_preview: previewDifference > 0.5 && previewPixels.pass,
    save: saveOk,
    export_obj: exportBytes > 100,
    offline: noNetworkDuringPath,
    under_30s: receipt.skeptic_path_seconds <= 30,
  };
  receipt.skeptic_path_complete = Object.values(skepticChecks).every(Boolean);
  receipt.details.skeptic = {checks: skepticChecks, initial, authored, orbitDifference,
    previewDifference, previewPixels, saveBytes: save.bytes, exportBytes, initialPixels,
    splashDifference, workspacePixels, nPanelDifference, tPanelDifference, fidelitySeconds};
  receipt.early_diagnostics.skeptic = await requireEmptyEarlyDiagnostics(page, "product:skeptic");

  await context.setOffline(false);
  await page.close();

  // Viewer-owned .blend killshot is its own navigation-clock scenario.  It must
  // not inherit the time already spent completing the separate skeptic authoring
  // path, and its <=30 s clock includes its complete navigation/product load.
  const ownPage = await context.newPage();
  observe(ownPage);
  const ownStart = performance.now();
  const ownNavigationResponse = await ownPage.goto(`${BASE}/index.html`,
    {waitUntil: "domcontentloaded", timeout: 60_000});
  const ownServedBundle = await requireServedBundle(ownNavigationResponse, expectedBundleDigest);
  await waitProduct(ownPage);
  const ownCanvas = ownPage.locator("#canvas");
  const ownBox = await ownCanvas.boundingBox();
  if (!ownBox) throw new Error("own-file canvas has no bounding box");
  const ownCx = ownBox.x + ownBox.width * 0.42;
  const ownCy = ownBox.y + ownBox.height * 0.48;
  await ownCanvas.focus();
  const ownRequestsAtReady = allRequests.length;
  await context.setOffline(true);
  const cdp = await context.newCDPSession(ownPage);
  await ownPage.evaluate(() => window.addEventListener("drop", (event) => {
    window.__m8Drop = {trusted: event.isTrusted, name: event.dataTransfer?.files?.[0]?.name || ""};
  }, {capture: true, once: true}));
  const dragData = {items: [{mimeType: "application/x-blender", data: ""}],
    files: [OWN_BLEND], dragOperationsMask: 1};
  await cdp.send("Input.dispatchDragEvent", {type: "dragEnter", x: ownCx, y: ownCy, data: dragData});
  await cdp.send("Input.dispatchDragEvent", {type: "dragOver", x: ownCx, y: ownCy, data: dragData});
  await cdp.send("Input.dispatchDragEvent", {type: "drop", x: ownCx, y: ownCy, data: dragData});
  await ownPage.waitForFunction(async () => {
    try { return (await window.BWFileBridge.listStore()).items.includes("stress_mixed.blend"); }
    catch (_) { return false; }
  }, null, {timeout: 30_000});
  const ownState = await ownPage.evaluate(() => window.BWFileBridge.inspectScene());
  const ownPixels = pixelProof(await ownCanvas.screenshot());
  const beforeOwnOrbit = signature(await ownCanvas.screenshot());
  await ownPage.mouse.move(ownCx - 40, ownCy - 20);
  await ownPage.mouse.down({button: "middle"});
  await ownPage.mouse.move(ownCx + 40, ownCy + 20, {steps: 5});
  await ownPage.mouse.up({button: "middle"});
  await ownPage.waitForTimeout(250);
  const ownOrbitDifference = meanAbsDiff(beforeOwnOrbit, signature(await ownCanvas.screenshot()));
  const drop = await ownPage.evaluate(() => window.__m8Drop);
  receipt.own_blend_wow_seconds = Math.round((performance.now() - ownStart) / 10) / 100;
  receipt.own_blend_wow_under_30s = drop?.trusted === true && drop.name === "stress_mixed.blend" &&
    ownState.ok && ownState.objectCount === 22 && ownPixels.pass && ownOrbitDifference > 0.5 &&
    allRequests.length === ownRequestsAtReady && receipt.own_blend_wow_seconds <= 30;
  receipt.details.own_blend = {drop, state: ownState, pixels: ownPixels,
    orbitDifference: ownOrbitDifference, served_bundle_sha256: ownServedBundle,
    no_network_after_ready: allRequests.length === ownRequestsAtReady};
  receipt.early_diagnostics.own_blend = await requireEmptyEarlyDiagnostics(
    ownPage, "product:own-blend");
  await context.setOffline(false);
  await ownPage.close();

  // Malicious/unknown query values must not become a request or path.
  const rejectPage = await context.newPage();
  observe(rejectPage);
  const rejectExternalStart = external.length;
  await rejectPage.goto(`${BASE}/index.html?scene=${encodeURIComponent("https://example.invalid/evil.blend")}`,
    {waitUntil: "domcontentloaded", timeout: 60_000});
  await rejectPage.waitForFunction(() => window.BWFileBridge && window.__bwModule, null, {timeout: 240_000});
  const rejected = await rejectPage.evaluate(() => window.BWFileBridge.shareReady());
  const rejectionSafe = rejected?.status === "rejected" && rejected.reason === "not-allowlisted" &&
    external.length === rejectExternalStart;
  receipt.early_diagnostics.rejected_share = await requireEmptyEarlyDiagnostics(
    rejectPage, "product:rejected-share");
  await rejectPage.close();

  // The one accepted URL must open only the bundled byte/sha-bound CC0 fixture.
  const sharePage = await context.newPage();
  observe(sharePage);
  await sharePage.goto(`${BASE}/index.html?scene=stress-mixed`,
    {waitUntil: "domcontentloaded", timeout: 60_000});
  await sharePage.waitForFunction(() => window.BWFileBridge && window.__bwModule, null, {timeout: 240_000});
  const shared = await sharePage.evaluate(() => window.BWFileBridge.shareReady());
  const sharedState = await sharePage.evaluate(() => window.BWFileBridge.inspectScene());
  const sharePixels = pixelProof(await sharePage.locator("#canvas").screenshot());
  const validShare = shared?.status === "opened" && shared.bytes === 581494 &&
    shared.sha256 === "c2a7974ceec3da3ed11a102d924f3318ea82ffa29fd393a8ff5103b6181b4e2e" &&
    shared.ack?.ok && shared.ack?.name === "stress-mixed.blend" &&
    sharedState.objectCount === 22 && sharePixels.pass;
  receipt.share_scene_allowlisted = rejectionSafe && validShare;
  receipt.details.share_scene = {rejected, rejectionSafe, shared, state: sharedState, pixels: sharePixels};
  receipt.early_diagnostics.allowed_share = await requireEmptyEarlyDiagnostics(
    sharePage, "product:allowed-share");
  await sharePage.close();

  // Exact theme/font/splash fidelity is owned by the authoritative M4 result.
  // This product runner adds the <=10 s reachability evidence: real default
  // scene, MMB orbit, Tab/edit/extrude, and visible standard N/T panel keymaps.
  let m4 = null;
  try { m4 = JSON.parse(readFileSync(`${ROOT}/ledger/results/m4.json`, "utf8")); } catch (_) {}
  const defaultScene = initial.ok && ["Camera", "Cube", "Light"].every((name) => initial.objects.includes(name));
  receipt.fidelity_tells_under_10s = m4?.pass === true && defaultScene && orbitDifference > 0.5 &&
    splashDifference > 0.5 && workspacePixels.pass && authored.meshVertices > 8 &&
    nPanelDifference > 0.5 && tPanelDifference > 0.5 && fidelitySeconds <= 10;
  receipt.details.fidelity = {source: "ledger/results/m4.json", authoritative_pass: m4?.pass === true,
    defaultScene, splashDifference, workspacePixels, orbitDifference,
    extrudedVertices: authored.meshVertices, nPanelDifference, tPanelDifference,
    seconds: fidelitySeconds, under_10s: fidelitySeconds <= 10};
}
catch (error) {
  fail(String(error && error.stack || error));
}
finally {
  await context.setOffline(false).catch(() => {});
  await context.close().catch(() => {});
  await browser.close().catch(() => {});
  try {
    revalidateBrowserRuntimeIdentity(runtimeIdentity,
      {identifier: "com.google.Chrome", team: "EQHXZ8M8AV"});
  }
  catch (error) { fail(String(error && error.message || error)); }
  if (external.length) fail("external requests escaped bundle: " + external.join(", "));
  if (errors.length) fail("GPU/page errors: " + errors[0]);
  receipt.details.runtime = {external_request_count: external.length, external_requests: external,
    gpu_or_page_error_count: errors.length, errors};
  const booleans = ["interactive_viewport_under_8s", "first_interaction_local",
    "orbit_tab_extrude", "own_blend_wow_under_30s",
    "fidelity_tells_under_10s", "share_scene_allowlisted", "skeptic_path_complete"];
  receipt.verdict = booleans.every((key) => receipt[key] === true) && receipt.failures.length === 0 ? "PASS" : "FAIL";
  writeFileSync(OUT, JSON.stringify(receipt, null, 2) + "\n");
  console.log(`[m8-product] ${receipt.verdict} skeptic=${receipt.skeptic_path_seconds}s own=${receipt.own_blend_wow_seconds}s -> ${OUT}`);
  process.exit(receipt.verdict === "PASS" ? 0 : 1);
}

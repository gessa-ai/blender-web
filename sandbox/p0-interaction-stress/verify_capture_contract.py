#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind the P0-I/J interaction producer to its hardware and visual contracts."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "sandbox/p0-interaction-stress/capture_diagnostic.mjs"
ANALYZER = ROOT / "sandbox/p0-interaction-stress/analyze_diagnostic.py"


def require_once(source: str, marker: str, label: str) -> None:
    if source.count(marker) != 1:
        raise ValueError(f"{label} must occur exactly once: {marker}")


def require_order(source: str, markers: tuple[str, ...], label: str) -> None:
    offsets = []
    for marker in markers:
        require_once(source, marker, label)
        offsets.append(source.index(marker))
    if offsets != sorted(offsets):
        raise ValueError(f"{label} order differs")


def validate(capture: str, analyzer: str) -> None:
    for marker in (
        'const HARDWARE_EVIDENCE_CLASS = "apple-hardware-interaction-v1";',
        'const FALLBACK_EVIDENCE_CLASS = "diagnostic-software-fallback";',
        'const ADAPTER_CONTRACT = "hardware-webgpu-adapter-v1";',
        'if (process.platform !== "darwin")',
        'requireDirectDescendantPath(root, options.outRoot, "--out-root");',
        'requireDirectDescendantPath(root, options.binDir, "--bin-dir");',
        '"--use-angle=metal"',
        '"--use-webgpu-adapter=swiftshader"',
        'if (!options.hardware) {\n    await page.addInitScript(() => {',
        'typeof info.isFallbackAdapter === "boolean"',
        'typeof adapter.isFallbackAdapter === "boolean"',
        'else if (isFallbackAdapter !== false) reason = "fallback-status-absent";',
        'else if (softwareMatches.length) reason = "software-adapter";',
        '"post-stress-known-pose", "03b-reference-pose-6s", "61c-frame-selected-6s"',
        '"post-orbit-known-pose", "03b-reference-pose-6s", "65b-post-orbit-known-pose-6s"',
        'await page.keyboard.press("g");',
        'await page.keyboard.press("x");',
        'await page.keyboard.type("2");',
        'await page.keyboard.press("Control+z");',
        'const TEXT_REGION_CHANGED_FRACTION_LIMIT = 0.002;',
        'const PIXEL_RECOVERY_TIMEOUT_MS = 12000;',
        'const ISOLATED_VIEW_KEYS = Object.freeze(["Numpad1", "Numpad3", "Numpad7", "Numpad0", "Numpad4"]);',
        'outlinerText: {',
        'workspaceTabs: {',
        'await page.keyboard.press("Alt+a");',
        'selectionMode = "fallback-select-all";',
        'Cancel that diagnostic-only pick explicitly',
        'await page.keyboard.press("Escape");\n    await page.waitForTimeout(250);\n    await page.keyboard.press("a");',
        '"fallback post-orbit Select All liveness", 10000);',
        'fallbackLivenessInput: selectionMode === "fallback-select-all" ? "A" : null,',
        'await orderedLeftClick(target.x, target.y, "fallback Outliner Cube");',
        'method: "outliner-click",',
        'fallbackSelectionRestore,',
        'const waitForCanvasChange = async (beforeSha256, label) => {',
        'candidate.view_perspective === "CAMERA",',
        'pixelSettleMs: preClickOrbitPixelSettleMs,',
        'expectedGhostY: Math.round(canvasBox.height - (target.y - canvasBox.y) - 1),',
        'const receiptTimeout = options.hardware ? 5000 : 15000;',
        'await orderedLeftClick(x, 13, `workspace ${workspace}`, receiptTimeout);',
        'const isolationCanary = {',
        'viewKeys: ISOLATED_VIEW_KEYS,',
        '/assembled group-0 resources do not match surviving WGSL bindings/i',
    ):
        require_once(capture, marker, "capture invariant")
    if capture.count("_bw_redraw_retry_count") != 3:
        raise ValueError("capture redraw-retry counter census differs")

    # Two canaries intentionally call the same helper; every named call remains unique.
    if capture.count("samePoseCanaries.push(makeSamePoseCanary(") != 2:
        raise ValueError("same-pose canary census differs")

    require_order(
        capture,
        (
            "const productIdentity = options.hardware ?",
            "const browser = await chromium.launch({",
        ),
        "local product preflight",
    )
    hardware_probe = capture.index("adapter = await probeAdapter(probePage);")
    hardware_tail = capture[hardware_probe:]
    require_order(
        hardware_tail,
        (
            "adapter = await probeAdapter(probePage);",
            'if (adapter.status !== "ACCEPTED")',
            "productIdentity.servedGeneration = await fetchServedGeneration(",
            "if (existsSync(outDir))",
            "mkdirSync(outDir, { recursive: true });",
            "evidenceAllocated = true;",
        ),
        "hardware evidence allocation",
    )
    current_spec = capture.index('typeof info.isFallbackAdapter === "boolean"')
    legacy = capture.index('typeof adapter.isFallbackAdapter === "boolean"')
    if current_spec >= legacy:
        raise ValueError("GPUAdapterInfo fallback status is not preferred over the legacy field")

    for marker in (
        'HARDWARE_EVIDENCE_CLASS = "apple-hardware-interaction-v1"',
        'FALLBACK_EVIDENCE_CLASS = "diagnostic-software-fallback"',
        'ADAPTER_CONTRACT = "hardware-webgpu-adapter-v1"',
        'SAME_POSE_CHANGED_FRACTION_LIMIT = 0.01',
        'TEXT_REGION_CHANGED_FRACTION_LIMIT = 0.002',
        'ISOLATED_VIEW_KEYS = ["Numpad1", "Numpad3", "Numpad7", "Numpad0", "Numpad4"]',
        '"post-stress-known-pose": "61c-frame-selected-6s"',
        '"post-orbit-known-pose": "65b-post-orbit-known-pose-6s"',
        '{"viewHeader", "leftToolbar", "outlinerText", "workspaceTabs"}',
        'isolated.get("viewKeys") == ISOLATED_VIEW_KEYS',
        '[3, 0, 1] if evidence_class == HARDWARE_EVIDENCE_CLASS else [3, 0, 3]',
        'click.get("selectionMode") in {"viewport", "fallback-select-all"}',
        'click.get("fallbackLivenessInput") == "A"',
        'selection_restore.get("method") == "outliner-click"',
        'selection_restore.get("selectedCount") == 1',
        'step.get("redrawRetries")',
        'orbit.get("redrawRetries")',
        '0 <= orbit["pixelSettleMs"] <= 12000',
        'product.get("redrawRetries")',
        'operator.get("operation") == "G X 2 Enter; Control+Z"',
        'require(not hard_warnings',
        'adapter.get("isFallbackAdapter") is False',
        'served.get("originalWasmSha256") == expected',
    ):
        require_once(analyzer, marker, "analyzer invariant")


def self_check(capture: str, analyzer: str) -> None:
    validate(capture, analyzer)
    capture_markers = (
        'const HARDWARE_EVIDENCE_CLASS = "apple-hardware-interaction-v1";',
        'if (process.platform !== "darwin")',
        'requireDirectDescendantPath(root, options.outRoot, "--out-root");',
        '"--use-angle=metal"',
        'typeof info.isFallbackAdapter === "boolean"',
        'if (adapter.status !== "ACCEPTED")',
        "productIdentity.servedGeneration = await fetchServedGeneration(",
        '"post-stress-known-pose", "03b-reference-pose-6s", "61c-frame-selected-6s"',
        '"post-orbit-known-pose", "03b-reference-pose-6s", "65b-post-orbit-known-pose-6s"',
        'await page.keyboard.press("Control+z");',
        'const TEXT_REGION_CHANGED_FRACTION_LIMIT = 0.002;',
        'const PIXEL_RECOVERY_TIMEOUT_MS = 12000;',
        'const ISOLATED_VIEW_KEYS = Object.freeze(["Numpad1", "Numpad3", "Numpad7", "Numpad0", "Numpad4"]);',
        'await page.keyboard.press("Alt+a");',
        'selectionMode = "fallback-select-all";',
        'Cancel that diagnostic-only pick explicitly',
        'await page.keyboard.press("Escape");\n    await page.waitForTimeout(250);\n    await page.keyboard.press("a");',
        'fallbackLivenessInput: selectionMode === "fallback-select-all" ? "A" : null,',
        'await orderedLeftClick(target.x, target.y, "fallback Outliner Cube");',
        'method: "outliner-click",',
        'fallbackSelectionRestore,',
        'const waitForCanvasChange = async (beforeSha256, label) => {',
        'pixelSettleMs: preClickOrbitPixelSettleMs,',
        'const receiptTimeout = options.hardware ? 5000 : 15000;',
        'const isolationCanary = {',
        'outlinerText: {',
        '/assembled group-0 resources do not match surviving WGSL bindings/i',
    )
    analyzer_markers = (
        'adapter.get("isFallbackAdapter") is False',
        'served.get("originalWasmSha256") == expected',
        '{"viewHeader", "leftToolbar", "outlinerText", "workspaceTabs"}',
        'isolated.get("viewKeys") == ISOLATED_VIEW_KEYS',
        '[3, 0, 1] if evidence_class == HARDWARE_EVIDENCE_CLASS else [3, 0, 3]',
        'click.get("fallbackLivenessInput") == "A"',
        'selection_restore.get("method") == "outliner-click"',
        'orbit.get("redrawRetries")',
        '0 <= orbit["pixelSettleMs"] <= 12000',
        'product.get("redrawRetries")',
        'operator.get("operation") == "G X 2 Enter; Control+Z"',
        'require(not hard_warnings',
    )
    rejected = 0
    for marker in capture_markers:
        replacement = ("X" if marker[0] != "X" else "Y") + marker[1:]
        candidate = capture.replace(marker, replacement, 1)
        try:
            validate(candidate, analyzer)
        except ValueError:
            rejected += 1
        else:
            raise ValueError(f"capture mutation was accepted: {marker}")
    for marker in analyzer_markers:
        replacement = ("X" if marker[0] != "X" else "Y") + marker[1:]
        candidate = analyzer.replace(marker, replacement, 1)
        try:
            validate(capture, candidate)
        except ValueError:
            rejected += 1
        else:
            raise ValueError(f"analyzer mutation was accepted: {marker}")
    expected = len(capture_markers) + len(analyzer_markers)
    if rejected != expected:
        raise ValueError(f"mutation self-check rejected {rejected}/{expected}")
    print(f"P0IJ_HARDWARE_CAPTURE_SOURCE_SELFCHECK_PASS mutations={rejected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    capture = CAPTURE.read_text(encoding="utf-8")
    analyzer = ANALYZER.read_text(encoding="utf-8")
    if args.self_check:
        self_check(capture, analyzer)
    else:
        validate(capture, analyzer)
        print("P0IJ_HARDWARE_CAPTURE_SOURCE_PASS producer=1 consumer=1")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0IJ_HARDWARE_CAPTURE_SOURCE_FAIL {error}")
        raise SystemExit(1)

#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Score a Workbench production Render Result or a retained diagnostic capture.

Production rows compare Blender's finite RGBA8 ``save_render`` PNG directly to
the golden; Blender has already applied the scene's pinned OCIO display/view.
For retained diagnostic-only runs, preserve the r35 classification and its
explicit pinned-OCIO conversion of non-Standard full-float readbacks.
"""

import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
LEGACY_SCORER = ROOT / "sandbox/gpu-r35/score.py"
DECODER = ROOT / "sandbox/gpu-r35/decode_readback.py"
OCIO_CONFIG = ROOT / "upstream/release/datafiles/colormanagement/config.ocio"
PRODUCT_SCHEMA = "bw-workbench-product-v1"
PRODUCT_FILE = "render_result.png"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = load_module("r35_score", LEGACY_SCORER)
decoder = load_module("r35_decode", DECODER)


def run(command, env=None):
    process = subprocess.run(command, capture_output=True, text=True, env=env)
    return process.returncode, process.stdout + process.stderr


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_physical_f12(invocation):
    receipt = invocation.get("keyReceipt") if isinstance(invocation, dict) else None
    return (
        invocation.get("method") == "page.keyboard.press(F12)"
        and invocation.get("count") == 1
        and invocation.get("physicalTrustedF12") is True
        and isinstance(receipt, list) and len(receipt) == 1
        and receipt[0].get("key") == "F12" and receipt[0].get("code") == "F12"
        and receipt[0].get("isTrusted") is True and receipt[0].get("repeat") is False
        and receipt[0].get("targetId") == "canvas" and receipt[0].get("activeId") == "canvas"
    )


def color_receipt(manifest):
    prefix = "M6_BRIDGE_COLOR "
    matches = [mark.split(prefix, 1)[1] for mark in manifest.get("marks", []) if prefix in mark]
    if len(matches) != 1:
        raise ValueError("expected exactly one M6_BRIDGE_COLOR receipt")
    return json.loads(matches[0])


def write_pfm(path, header):
    pixels = decoder.decode_floats(header)
    width, height = header["w"], header["h"]
    rows = [pixels[y * width:(y + 1) * width] for y in range(height)]
    # The WebGPU readback is vertically inverted. PFM stores rows bottom-up, so
    # writing WebGPU rows in their existing order produces the desired top-down
    # image when OpenImageIO reads the PFM.
    with open(path, "wb") as handle:
        handle.write(("PF\n%d %d\n-1.0\n" % (width, height)).encode("ascii"))
        for row in rows:
            values = [component for pixel in row for component in pixel[:3]]
            handle.write(struct.pack("<%df" % len(values), *values))


def parse_metrics(output):
    mean = maximum = percent = None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("Mean error"):
            mean = stripped.split("=")[-1].strip()
        elif "Max error" in stripped:
            try:
                maximum = stripped.split("Max error", 1)[1].split("=", 1)[1].strip().split()[0]
            except (IndexError, ValueError):
                pass
        elif "over" in stripped and "%" in stripped:
            percent = stripped
    return mean, maximum, percent


def validate_product_manifest(manifest, capdir=None):
    """Independently enforce the production Render Result contract."""
    errors = []
    resolution = manifest.get("res")
    if (not isinstance(resolution, list) or len(resolution) != 2
            or not all(isinstance(value, int) and value > 0 for value in resolution)):
        errors.append("manifest resolution invalid")
        width, height = 0, 0
    else:
        width, height = resolution
    receipt = manifest.get("productReceipt")
    armed = manifest.get("productArmedReceipt")
    captures = manifest.get("productCaptures") or []
    gate = manifest.get("productGate") or {}

    if not str(manifest.get("sentinel") or "").startswith("OK"):
        errors.append("render sentinel is not OK")
    if manifest.get("pageCrashed"):
        errors.append("page crashed")
    if manifest.get("pageUnresponsive"):
        errors.append("page unresponsive")
    if manifest.get("gpuErrorCount", 0) != 0:
        errors.append("GPU errors=%s" % manifest.get("gpuErrorCount"))
    if manifest.get("pageErrorCount", 0) != 0:
        errors.append("page errors=%s" % manifest.get("pageErrorCount"))
    if manifest.get("productCaptureError"):
        errors.append("product capture error")
    if gate.get("pass") is not True or gate.get("errors"):
        errors.append("driver product gate did not pass")
    if len(captures) != 1:
        errors.append("product capture count=%d" % len(captures))
    if not valid_physical_f12(manifest.get("invocation")):
        errors.append("physical trusted F12 receipt invalid")

    if not isinstance(armed, dict):
        errors.append("product ARMED receipt missing")
    else:
        armed_checks = {
            "schema": armed.get("schema") == PRODUCT_SCHEMA,
            "status": armed.get("status") == "ARMED",
            "engine": armed.get("engine") == "BLENDER_WORKBENCH",
            "dimensions": [armed.get("width"), armed.get("height")] == [width, height],
            "resolution_percentage": armed.get("resolution_percentage") == 100,
        }
        errors.extend(
            "ARMED receipt %s invalid" % name
            for name, valid in armed_checks.items()
            if not valid
        )

    if not isinstance(receipt, dict):
        errors.append("product receipt missing")
    else:
        checks = {
            "schema": receipt.get("schema") == PRODUCT_SCHEMA,
            "status": receipt.get("status") == "OK",
            "engine": receipt.get("engine") == "BLENDER_WORKBENCH",
            "dimensions": [receipt.get("width"), receipt.get("height")] == [width, height],
            "rgba8": receipt.get("channels") == 4 and receipt.get("bit_depth") == 8
            and receipt.get("color_type") == "RGBA",
            "finite": receipt.get("finite_values") == width * height * 4
            and receipt.get("nonfinite_values") == 0,
            "handlers": receipt.get("pre_count") == 1 and receipt.get("complete_count") == 1
            and receipt.get("cancel_count") == 0,
            "png": isinstance(receipt.get("png"), str)
            and receipt.get("png", "").startswith("/tmp/")
            and receipt.get("png", "").endswith("-render-result.png"),
            "png_size": isinstance(receipt.get("png_size"), int) and receipt.get("png_size") > 0,
        }
        errors.extend("receipt %s invalid" % name for name, valid in checks.items() if not valid)

    if len(captures) == 1:
        capture = captures[0]
        checks = {
            "file": capture.get("file") == PRODUCT_FILE,
            "guest_path": isinstance(receipt, dict)
            and capture.get("guestPath") == receipt.get("png"),
            "dimensions": [capture.get("width"), capture.get("height")] == [width, height]
            and [capture.get("ihdrWidth"), capture.get("ihdrHeight")] == [width, height],
            "rgba8": capture.get("bitDepth") == 8 and capture.get("colorType") == 6,
            "finite": capture.get("finitePixels") is True,
            "nonblack": capture.get("nonBlackPixels", 0) > 0
            and capture.get("nonBlackFraction", 0) > 0 and capture.get("rgbMax", 0) > 0,
            "byte_length": isinstance(receipt, dict)
            and capture.get("byteLength") == receipt.get("png_size"),
            "sha256": isinstance(capture.get("sha256"), str)
            and len(capture.get("sha256")) == 64,
        }
        errors.extend("capture %s invalid" % name for name, valid in checks.items() if not valid)
        if capdir is not None:
            product_path = os.path.join(capdir, PRODUCT_FILE)
            if not os.path.isfile(product_path):
                errors.append("host product PNG missing")
            elif os.path.getsize(product_path) != capture.get("byteLength"):
                errors.append("host product PNG size mismatch")
            else:
                with open(product_path, "rb") as handle:
                    actual_hash = hashlib.sha256(handle.read()).hexdigest()
                if actual_hash != capture.get("sha256"):
                    errors.append("host product PNG SHA-256 mismatch")
    return errors


def score_product(capdir, golden, threshold, fail_percent, json_out, manifest):
    errors = validate_product_manifest(manifest, capdir)
    result = {
        "capdir": capdir,
        "golden": golden,
        "sources": {
            "scorer": {
                "path": os.path.abspath(__file__),
                "sha256": sha256_file(os.path.abspath(__file__)),
                "bytes": os.path.getsize(os.path.abspath(__file__)),
            },
        },
        "sentinel": manifest.get("sentinel"),
        "ncaps": len(manifest.get("caps", [])),
        "product_capture_count": len(manifest.get("productCaptures") or []),
        "gpuErrorCount": manifest.get("gpuErrorCount", 0),
        "pageErrorCount": manifest.get("pageErrorCount", 0),
        "gpu_sig": legacy.error_signature(manifest.get("gpuErrorSample", [])),
    }
    if errors:
        result.update({
            "verdict": "RIG-FAIL",
            "cluster": "product-capture-gate",
            "note": "; ".join(errors),
        })
        json.dump(result, open(json_out, "w"), indent=2)
        print(json.dumps(result))
        return

    receipt = color_receipt(manifest)
    if receipt.get("look") != "None" or float(receipt.get("gamma", 1.0)) != 1.0:
        raise ValueError("non-default Workbench look/gamma needs an explicit OCIO scoring rule")

    product_path = os.path.join(capdir, PRODUCT_FILE)
    golden_rgb = os.path.join(capdir, "golden_rgb.png")
    product_rgb = os.path.join(capdir, "render_result_rgb.png")
    for source, output in ((golden, golden_rgb), (product_path, product_rgb)):
        convert_rc, convert_output = run(["oiiotool", source, "--ch", "R,G,B", "-o", output])
        if convert_rc != 0:
            raise RuntimeError(convert_output)
    diff_rc, diff_output = run([
        "oiiotool",
        golden_rgb,
        product_rgb,
        "--fail",
        threshold,
        "--failpercent",
        fail_percent,
        "--diff",
    ])
    comparator_argv = [
        "oiiotool",
        golden_rgb,
        product_rgb,
        "--fail",
        threshold,
        "--failpercent",
        fail_percent,
        "--diff",
    ]
    mean, maximum, percent = parse_metrics(diff_output)
    result.update({
        "render_result": {
            "product": True,
            "file": PRODUCT_FILE,
            "w": manifest["res"][0],
            "h": manifest["res"][1],
        },
        "oiiotool_rc": diff_rc,
        "comparator": {
            "argv": comparator_argv,
            "threshold": threshold,
            "fail_percent": fail_percent,
            "golden": {"path": golden, "sha256": sha256_file(golden)},
            "product": {"path": product_path, "sha256": sha256_file(product_path)},
            "golden_rgb": {"path": golden_rgb, "sha256": sha256_file(golden_rgb)},
            "product_rgb": {"path": product_rgb, "sha256": sha256_file(product_rgb)},
        },
        "mean_error": mean,
        "max_error": maximum,
        "pct_over": percent,
        "verdict": "PASS" if diff_rc == 0 else "FAIL",
        "cluster": "pixel-pass" if diff_rc == 0 else "pixel-delta",
        "display_transform": receipt,
        "display_transform_output": PRODUCT_FILE,
        "display_transform_source": "Blender save_render using the pinned OCIO configuration",
    })
    json.dump(result, open(json_out, "w"), indent=2)
    print(json.dumps(result))


def self_check():
    armed = {
        "schema": PRODUCT_SCHEMA,
        "status": "ARMED",
        "engine": "BLENDER_WORKBENCH",
        "width": 128,
        "height": 128,
        "resolution_percentage": 100,
    }
    receipt = {
        "schema": PRODUCT_SCHEMA,
        "status": "OK",
        "engine": "BLENDER_WORKBENCH",
        "png": "/tmp/selfcheck-render-result.png",
        "png_size": 1024,
        "width": 128,
        "height": 128,
        "channels": 4,
        "bit_depth": 8,
        "color_type": "RGBA",
        "finite_values": 128 * 128 * 4,
        "nonfinite_values": 0,
        "pre_count": 1,
        "complete_count": 1,
        "cancel_count": 0,
    }
    capture = {
        "file": PRODUCT_FILE,
        "guestPath": receipt["png"],
        "width": 128,
        "height": 128,
        "ihdrWidth": 128,
        "ihdrHeight": 128,
        "bitDepth": 8,
        "colorType": 6,
        "byteLength": 1024,
        "sha256": "0" * 64,
        "nonBlackPixels": 10,
        "nonBlackFraction": 10 / (128 * 128),
        "rgbMax": 255,
        "finitePixels": True,
    }
    positive = {
        "schema": "blender-web.workbench-product.v2",
        "res": [128, 128],
        "sentinel": "OK BLENDER_WORKBENCH",
        "pageCrashed": False,
        "pageUnresponsive": False,
        "gpuErrorCount": 0,
        "pageErrorCount": 0,
        "productCaptureError": None,
        "productArmedReceipt": armed,
        "invocation": {
            "method": "page.keyboard.press(F12)",
            "count": 1,
            "physicalTrustedF12": True,
            "keyReceipt": [{
                "key": "F12", "code": "F12", "isTrusted": True, "repeat": False,
                "targetId": "canvas", "activeId": "canvas",
            }],
        },
        "productReceipt": receipt,
        "productCaptures": [capture],
        "productGate": {"pass": True, "errors": []},
    }
    negative = copy.deepcopy(positive)
    negative["gpuErrorCount"] = 1
    negative["invocation"]["keyReceipt"][0]["isTrusted"] = False
    negative["productCaptures"][0]["nonBlackPixels"] = 0
    negative["productCaptures"][0]["nonBlackFraction"] = 0
    negative["productCaptures"][0]["rgbMax"] = 0
    positive_errors = validate_product_manifest(positive)
    negative_errors = validate_product_manifest(negative)
    result = {
        "positive": not positive_errors,
        "negative": bool(negative_errors)
        and any("GPU errors" in error for error in negative_errors)
        and any("nonblack" in error for error in negative_errors)
        and any("physical trusted F12" in error for error in negative_errors),
        "negative_errors": negative_errors,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if all((result["positive"], result["negative"])) else 1


def main():
    args = sys.argv[1:]
    if args == ["--self-check"]:
        raise SystemExit(self_check())
    if len(args) != 6 or args[4] != "--json":
        raise SystemExit("usage: score_workbench.py CAP GOLDEN THRESHOLD FAIL_PERCENT --json OUT")
    capdir, golden, threshold, fail_percent, _, json_out = args

    manifest = json.load(open(os.path.join(capdir, "manifest.json")))
    if any(key in manifest for key in ("productReceipt", "productCaptures", "productGate")):
        score_product(capdir, golden, threshold, fail_percent, json_out, manifest)
        return

    legacy_command = [
        sys.executable,
        LEGACY_SCORER,
        capdir,
        golden,
        threshold,
        fail_percent,
        "--colorspace",
        "linear",
        "--json",
        json_out,
    ]
    legacy_rc, legacy_output = run(legacy_command)
    if legacy_rc != 0 or not os.path.exists(json_out):
        sys.stdout.write(legacy_output)
        raise SystemExit(legacy_rc or 1)

    score = json.load(open(json_out))
    receipt = color_receipt(manifest)
    standard = (
        receipt == {"display": "sRGB", "view": "Standard", "look": "None", "exposure": 0.0, "gamma": 1.0}
    )
    if standard or score.get("render_result") is None:
        print(json.dumps(score))
        return
    if receipt.get("look") != "None" or float(receipt.get("gamma", 1.0)) != 1.0:
        raise ValueError("non-default Workbench look/gamma needs an explicit OCIO scoring rule")

    render_result = score["render_result"]
    capture = next(cap for cap in manifest["caps"] if cap.get("seq") == render_result["seq"])
    header = decoder.parse(os.path.join(capdir, capture["file"]))
    output_png = os.path.join(capdir, "render_result_ocio.png")

    with tempfile.TemporaryDirectory(prefix="bw-workbench-ocio-") as tempdir:
        pfm = os.path.join(tempdir, "linear.pfm")
        write_pfm(pfm, header)
        command = ["oiiotool", pfm, "--iscolorspace", "Linear Rec.709"]
        exposure = float(receipt.get("exposure", 0.0))
        if exposure != 0.0:
            command.extend(["--mulc", str(math.pow(2.0, exposure))])
        command.extend([
            "--ociodisplay",
            receipt["display"],
            receipt["view"],
            "-d",
            "uint8",
            "-o",
            output_png,
        ])
        ocio_env = dict(os.environ)
        ocio_env["OCIO"] = os.fspath(OCIO_CONFIG)
        transform_rc, transform_output = run(command, env=ocio_env)
        if transform_rc != 0:
            raise RuntimeError(transform_output)

    golden_rgb = os.path.join(capdir, "golden_rgb.png")
    run(["oiiotool", golden, "--ch", "R,G,B", "-o", golden_rgb])
    diff_rc, diff_output = run([
        "oiiotool",
        golden_rgb,
        output_png,
        "--fail",
        threshold,
        "--failpercent",
        fail_percent,
        "--diff",
    ])
    mean, maximum, percent = parse_metrics(diff_output)
    score.update({
        "oiiotool_rc": diff_rc,
        "mean_error": mean,
        "max_error": maximum,
        "pct_over": percent,
        "verdict": "PASS" if diff_rc == 0 else "FAIL",
        "cluster": "pixel-pass" if diff_rc == 0 else "pixel-delta",
        "display_transform": receipt,
        "display_transform_output": os.path.basename(output_png),
    })
    json.dump(score, open(json_out, "w"), indent=2)
    print(json.dumps(score))


if __name__ == "__main__":
    main()

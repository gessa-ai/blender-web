# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Execute the embedded saved-render oracle with a stale Render Result size."""

from __future__ import annotations

import ast
import binascii
import hashlib
import os
from pathlib import Path
import re
import subprocess
import struct
import tempfile
import zlib


DRIVER = Path(__file__).with_name("verify_blender_split_runtime.mjs")
REPO = DRIVER.resolve().parents[2]
NODE_VERSION = "v22.16.0"


def resolve_node_binary() -> Path:
    candidates = [
        os.environ.get("BW_NODE_BINARY"),
        REPO / "tools/emsdk/node/22.16.0_64bit/bin/node",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).resolve()
        if path.is_file():
            version = subprocess.run(
                [str(path), "--version"], check=False, capture_output=True, text=True
            )
            if version.returncode == 0 and version.stdout.strip() == NODE_VERSION:
                return path
    raise AssertionError(f"exact Node {NODE_VERSION} executable unavailable")


def resolve_node_modules() -> Path:
    candidates: list[str | Path] = []
    for variable in ("BW_NODE_MODULES", "NODE_PATH"):
        if value := os.environ.get(variable):
            candidates.extend(item for item in value.split(os.pathsep) if item)
    candidates.extend((REPO / ".m4-node/node_modules", REPO / "node_modules"))
    for candidate in candidates:
        path = Path(candidate).resolve()
        if (path / "pngjs/package.json").is_file():
            return path
    raise AssertionError("pngjs module root unavailable; set BW_NODE_MODULES")


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(
        ">I", binascii.crc32(kind + payload) & 0xFFFFFFFF
    )


def rgba_png(width: int, height: int, *, color_type: int = 6) -> bytes:
    channels = 4 if color_type == 6 else 3
    pixel = bytes([48, 96, 192, 255][:channels])
    scanline = b"\0" + pixel * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(scanline * height))
        + png_chunk(b"IEND", b"")
    )


def embedded_exporter(source: str):
    match = re.search(r"const PY_MONITOR = String\.raw`([\s\S]*?)`\.trim\(\);", source)
    assert match, "embedded Python monitor missing"
    tree = ast.parse(match.group(1))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "_bwsr_export_png"
    )
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {"hashlib": hashlib}
    exec(compile(ast.fix_missing_locations(module), "<runtime-exporter>", "exec"), namespace)
    return namespace["_bwsr_export_png"]


class FakeImage:
    def __init__(self, payload: bytes):
        self.size = [0, 0]
        self.channels = 0
        self.payload = payload

    def save_render(self, *, filepath: str, scene: object) -> None:
        assert scene is SENTINEL_SCENE
        Path(filepath).write_bytes(self.payload)


SENTINEL_SCENE = object()


def extract_js_function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated JS function {name}")


def execute_node_oracle(source: str) -> None:
    function = extract_js_function(source, "renderPngProof")
    script = f"""
const {{ PNG }} = require('pngjs');
{function}
function encoded(width, height, nonblack) {{
  const png = new PNG({{ width, height }});
  for (let offset = 0; offset < png.data.length; offset += 4) {{
    png.data[offset] = nonblack ? 48 : 0;
    png.data[offset + 1] = nonblack ? 96 : 0;
    png.data[offset + 2] = nonblack ? 192 : 0;
    png.data[offset + 3] = 255;
  }}
  return PNG.sync.write(png);
}}
if (!renderPngProof(encoded(32, 32, true)).pass) throw new Error('positive rejected');
if (renderPngProof(encoded(32, 32, false)).pass) throw new Error('black accepted');
if (renderPngProof(encoded(31, 32, true)).pass) throw new Error('wrong dimensions accepted');
console.log('BW_RUNTIME_RENDER_NODE_ORACLE PASS positive=1 negatives=2');
"""
    node_binary = resolve_node_binary()
    node_modules = resolve_node_modules()
    result = subprocess.run(
        [str(node_binary), "-e", script],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "NODE_PATH": str(node_modules)},
    )
    assert result.returncode == 0, result.stderr
    assert "BW_RUNTIME_RENDER_NODE_ORACLE PASS positive=1 negatives=2" in result.stdout


def main() -> None:
    source = DRIVER.read_text(encoding="utf-8")
    exporter = embedded_exporter(source)
    with tempfile.TemporaryDirectory(prefix="bw-runtime-render-") as temp:
        output = Path(temp) / "render.png"
        payload = rgba_png(32, 32)
        receipt = exporter(FakeImage(payload), str(output), SENTINEL_SCENE)
        assert receipt["width"] == 32 and receipt["height"] == 32
        assert receipt["bytes"] == len(payload)
        assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
        assert receipt["bit_depth"] == 8 and receipt["color_type"] == 6
        assert receipt["render_result_size"] == [0, 0]
        assert receipt["render_result_channels"] == 0

        negatives = 0
        for bad in (b"not png", rgba_png(31, 32), rgba_png(32, 32, color_type=2)):
            try:
                exporter(FakeImage(bad), str(output), SENTINEL_SCENE)
            except RuntimeError:
                negatives += 1
            else:
                raise AssertionError("malformed render export was accepted")

    assert "image.pixels" not in source and "_bwsr_pixels" not in source
    assert "saved-render-png-authoritative-readback-v1" in source
    assert "nonblackPixels > 0 && rgbMax > 0" in source
    for exact_cycles_setting in (
        "scene.cycles.device='CPU'; scene.cycles.samples=1",
        "scene.cycles.use_adaptive_sampling=False",
        "scene.cycles.sampling_pattern='AUTOMATIC'",
        "scene.cycles.use_denoising=False",
        "scene.cycles.seed=0",
        "scene.render.threads_mode='FIXED'; scene.render.threads=1",
        '"threads_mode":"FIXED","requested_threads":1,"effective_threads":8',
    ):
        assert exact_cycles_setting in source
    execute_node_oracle(source)
    print(
        "BW_RUNTIME_RENDER_EXPORT_TEST PASS stale-size=1 saved-png=1 "
        f"nonblack-node-gate=1 canonical-cycles-post-apply-override8=1 negatives={negatives}+2"
    )


if __name__ == "__main__":
    main()

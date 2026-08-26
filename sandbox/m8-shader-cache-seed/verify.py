#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fail-closed source/pack contract for the first-boot WGSL cache seed."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "platform_web/shader_cache/first_boot.bwsp"
MANIFEST = ROOT / "platform_web/shader_cache/first_boot.seed.json"
GENERATOR = ROOT / "scripts/build-shader-cache-seed.py"
SOURCE_ENTRIES = ROOT / "sandbox/m8-shader-cache-seed/artifacts/seed"
CACHE_CC = ROOT / "upstream/source/blender/gpu/webgpu/wgpu_shader_cache.cc"
PLATFORM = ROOT / "patches/platform_wasm.cmake"
PATCH = ROOT / "patches/0285-gpu-webgpu-first-boot-shader-cache-seed.patch"
SERIES = ROOT / "patches/series"
PREVIEW = ROOT / "patches/PREVIEW_SNAPSHOT.patch"
PREVIEW_SHA = ROOT / "patches/PREVIEW_SNAPSHOT.sha256"

PACK_HEADER = struct.Struct("<4sII")
PACK_RECORD = struct.Struct("<QQI")
CACHE_HEADER = struct.Struct("<4sIQQQIIIQ")
MAX_PACK_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 2048
MAX_STAGE_BYTES = 16 * 1024 * 1024


class ContractError(RuntimeError):
    pass


def fnv_payload(vertex: bytes, fragment: bytes, compute: bytes) -> int:
    a = 0xCBF29CE484222325
    b = 0x84222325CBF29CE4
    mask = (1 << 64) - 1

    def feed(data: bytes) -> None:
        nonlocal a, b
        for value in data:
            a = ((a ^ value) * 0x100000001B3) & mask
            b = ((b ^ value) * 0x100000001B3) & mask

    for stage in (vertex, fragment, compute):
        feed(struct.pack("<Q", len(stage)))
        feed(stage)
    return a ^ (((b << 1) & mask) | (b >> 63))


def parse_cache_entry(data: bytes, expected_key: tuple[int, int]) -> None:
    if len(data) < CACHE_HEADER.size:
        raise ContractError("cache entry is shorter than its header")
    magic, version, _salt, hi, lo, vlen, flen, clen, checksum = CACHE_HEADER.unpack_from(data)
    if magic != b"BWSC" or version != 3:
        raise ContractError("cache entry magic/version mismatch")
    if (hi, lo) != expected_key:
        raise ContractError("cache record key does not match its envelope")
    if max(vlen, flen, clen) > MAX_STAGE_BYTES:
        raise ContractError("cache stage exceeds the 16 MiB bound")
    expected_size = CACHE_HEADER.size + vlen + flen + clen
    if len(data) != expected_size:
        raise ContractError("cache envelope has truncated or trailing bytes")
    cursor = CACHE_HEADER.size
    vertex = data[cursor : cursor + vlen]
    cursor += vlen
    fragment = data[cursor : cursor + flen]
    cursor += flen
    compute = data[cursor : cursor + clen]
    if fnv_payload(vertex, fragment, compute) != checksum:
        raise ContractError("cache payload checksum mismatch")


def parse_pack(data: bytes) -> list[tuple[int, int, bytes]]:
    if len(data) > MAX_PACK_BYTES:
        raise ContractError("seed pack exceeds the runtime bound")
    if len(data) < PACK_HEADER.size:
        raise ContractError("seed pack is shorter than its header")
    magic, version, count = PACK_HEADER.unpack_from(data)
    if magic != b"BWSP" or version != 1:
        raise ContractError("seed pack magic/version mismatch")
    if count == 0 or count > MAX_ENTRIES:
        raise ContractError("seed pack entry count is outside its bound")
    cursor = PACK_HEADER.size
    previous: tuple[int, int] | None = None
    result = []
    for _ in range(count):
        if cursor + PACK_RECORD.size > len(data):
            raise ContractError("seed pack record header is truncated")
        hi, lo, length = PACK_RECORD.unpack_from(data, cursor)
        cursor += PACK_RECORD.size
        key = (hi, lo)
        if previous is not None and key <= previous:
            raise ContractError("seed pack keys are duplicate or unsorted")
        previous = key
        if length < CACHE_HEADER.size or cursor + length > len(data):
            raise ContractError("seed pack record payload is out of bounds")
        payload = data[cursor : cursor + length]
        cursor += length
        parse_cache_entry(payload, key)
        result.append((hi, lo, payload))
    if cursor != len(data):
        raise ContractError("seed pack has trailing bytes")
    return result


def expect_failure(label: str, data: bytes) -> None:
    try:
        parse_pack(data)
    except ContractError:
        return
    raise ContractError(f"mutation was accepted: {label}")


def require_once(text: str, needle: str, label: str) -> None:
    if text.count(needle) != 1:
        raise ContractError(f"{label}: expected one exact anchor, found {text.count(needle)}")


def main() -> int:
    required = [PACK, MANIFEST, GENERATOR, CACHE_CC, PLATFORM, PATCH, SERIES, PREVIEW, PREVIEW_SHA]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise ContractError("missing first-boot seed inputs: " + ", ".join(missing))

    pack_data = PACK.read_bytes()
    entries = parse_pack(pack_data)
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("schema") != "blender-web-wgsl-first-boot-seed-v1":
        raise ContractError("seed manifest schema mismatch")
    expected = {
        "entryCount": len(entries),
        "entryBytes": sum(len(entry[2]) for entry in entries),
        "packBytes": len(pack_data),
        "packSha256": hashlib.sha256(pack_data).hexdigest(),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ContractError(f"seed manifest {key} mismatch")
    source_sha = manifest.get("sourceWasmOrigSha256")
    if not isinstance(source_sha, str) or len(source_sha) != 64:
        raise ContractError("seed manifest lacks a concrete source Wasm identity")
    if manifest.get("diagnosticNonreceipt") is not True:
        raise ContractError("software extraction must remain explicitly nonreceipt")
    if len(entries) != 100:
        raise ContractError(f"first-frame seed identity drifted: {len(entries)} != 100")

    cache_source = CACHE_CC.read_text()
    platform_source = PLATFORM.read_text()
    numbered_patch = PATCH.read_text()
    series = SERIES.read_text()
    preview = PREVIEW.read_text()
    require_once(cache_source,
                 'constexpr const char *kSeedPath = "/bw/shader-cache/first_boot.bwsp";',
                 "runtime seed path")
    require_once(cache_source, "return seed_cache_lookup(", "persistent-to-seed fallback")
    require_once(cache_source, "BW_SHADER_CACHE_SEED loaded", "bounded seed diagnostic")
    require_once(platform_source,
                 '" --preload-file ${_shader_cache_seed}@/bw/shader-cache/first_boot.bwsp")',
                 "preload mapping")
    require_once(platform_source,
                 'set_property(TARGET ${_new} APPEND PROPERTY LINK_DEPENDS\n'
                 '    "${_shader_cache_seed}")',
                 "incremental link dependency")
    for label, source in (("numbered patch", numbered_patch), ("canonical patch", preview)):
        require_once(source, 'kSeedPath = "/bw/shader-cache/first_boot.bwsp"', label)
        require_once(source, "return seed_cache_lookup(", label)
    if not series.rstrip().endswith("0285-gpu-webgpu-first-boot-shader-cache-seed.patch"):
        raise ContractError("0285 is not the final applied series entry")
    expected_preview_hash, expected_preview_name = PREVIEW_SHA.read_text().split()
    if expected_preview_name != "PREVIEW_SNAPSHOT.patch" or \
            hashlib.sha256(PREVIEW.read_bytes()).hexdigest() != expected_preview_hash:
        raise ContractError("canonical preview checksum is stale")
    reverse = subprocess.run(
        ["git", "-C", str(ROOT / "upstream"), "apply", "--check", "--reverse", str(PATCH)],
        capture_output=True,
        text=True,
        check=False,
    )
    if reverse.returncode != 0:
        raise ContractError("0285 does not reverse from the live source: " + reverse.stderr.strip())

    if SOURCE_ENTRIES.is_dir():
        with tempfile.TemporaryDirectory(prefix="bw-shader-seed-contract-") as tmp:
            rebuilt = Path(tmp) / "first_boot.bwsp"
            rebuilt_manifest = Path(tmp) / "first_boot.seed.json"
            subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--input-dir",
                    str(SOURCE_ENTRIES),
                    "--output",
                    str(rebuilt),
                    "--manifest",
                    str(rebuilt_manifest),
                    "--source-wasm-orig-sha256",
                    source_sha,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            if rebuilt.read_bytes() != pack_data:
                raise ContractError("seed generator does not reproduce the committed pack")
            rebuilt_meta = json.loads(rebuilt_manifest.read_text())
            if rebuilt_meta != manifest:
                raise ContractError("seed generator does not reproduce the committed manifest")

    mutated = bytearray(pack_data)
    mutated[0] ^= 1
    expect_failure("pack magic", bytes(mutated))
    mutated = bytearray(pack_data)
    mutated[8:12] = struct.pack("<I", MAX_ENTRIES + 1)
    expect_failure("entry count", bytes(mutated))
    expect_failure("truncation", pack_data[:-1])
    expect_failure("trailing byte", pack_data + b"x")
    mutated = bytearray(pack_data)
    first_payload = PACK_HEADER.size + PACK_RECORD.size
    mutated[first_payload] ^= 1
    expect_failure("entry envelope", bytes(mutated))
    mutated = bytearray(pack_data)
    mutated[first_payload + CACHE_HEADER.size] ^= 1
    expect_failure("entry checksum", bytes(mutated))

    print(
        "BW_SHADER_CACHE_SEED_CONTRACT_PASS "
        f"entries={len(entries)} entry_bytes={expected['entryBytes']} "
        f"pack_bytes={len(pack_data)} mutations=6 sha256={expected['packSha256']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"BW_SHADER_CACHE_SEED_CONTRACT_FAIL {error}", file=sys.stderr)
        raise SystemExit(1)

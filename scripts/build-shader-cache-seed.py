#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Build the deterministic first-boot WGSL cache seed consumed by WebAssembly."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import tempfile
from pathlib import Path


PACK_HEADER = struct.Struct("<4sII")
PACK_RECORD = struct.Struct("<QQI")
CACHE_HEADER = struct.Struct("<4sIQQQIIIQ")
ENTRY_NAME = re.compile(r"^([0-9a-f]{16})([0-9a-f]{16})\.wgslc$")
MAX_STAGE_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 2048
MAX_PACK_BYTES = 32 * 1024 * 1024


def payload_hash(vertex: bytes, fragment: bytes, compute: bytes) -> int:
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


def validate_entry(path: Path, key: tuple[int, int]) -> tuple[bytes, int, int]:
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"shader-cache seed: entry is not a regular file: {path}")
    data = path.read_bytes()
    if len(data) < CACHE_HEADER.size:
        raise SystemExit(f"shader-cache seed: short cache header: {path.name}")
    magic, version, salt, hi, lo, vlen, flen, clen, checksum = CACHE_HEADER.unpack_from(data)
    if magic != b"BWSC" or version != 3:
        raise SystemExit(f"shader-cache seed: cache format mismatch: {path.name}")
    if (hi, lo) != key:
        raise SystemExit(f"shader-cache seed: filename/envelope key mismatch: {path.name}")
    if max(vlen, flen, clen) > MAX_STAGE_BYTES:
        raise SystemExit(f"shader-cache seed: stage exceeds 16 MiB: {path.name}")
    if len(data) != CACHE_HEADER.size + vlen + flen + clen:
        raise SystemExit(f"shader-cache seed: truncated/trailing envelope: {path.name}")
    cursor = CACHE_HEADER.size
    vertex = data[cursor : cursor + vlen]
    cursor += vlen
    fragment = data[cursor : cursor + flen]
    cursor += flen
    compute = data[cursor : cursor + clen]
    if payload_hash(vertex, fragment, compute) != checksum:
        raise SystemExit(f"shader-cache seed: payload checksum mismatch: {path.name}")
    return data, version, salt


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-wasm-orig-sha256", required=True)
    args = parser.parse_args()

    source_sha = args.source_wasm_orig_sha256.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
        raise SystemExit("shader-cache seed: source Wasm SHA-256 must be 64 lowercase hex digits")
    if not args.input_dir.is_dir() or args.input_dir.is_symlink():
        raise SystemExit(f"shader-cache seed: input is not a regular directory: {args.input_dir}")

    paths = sorted(args.input_dir.iterdir(), key=lambda path: path.name)
    unexpected = [path.name for path in paths if not ENTRY_NAME.fullmatch(path.name)]
    if unexpected:
        raise SystemExit("shader-cache seed: unexpected input entries: " + ", ".join(unexpected))
    if not paths or len(paths) > MAX_ENTRIES:
        raise SystemExit(f"shader-cache seed: entry count outside 1..{MAX_ENTRIES}: {len(paths)}")

    records: list[tuple[int, int, str, bytes]] = []
    cache_version = None
    cache_salt = None
    input_hash = hashlib.sha256()
    for path in paths:
        match = ENTRY_NAME.fullmatch(path.name)
        assert match is not None
        key = (int(match.group(1), 16), int(match.group(2), 16))
        data, version, salt = validate_entry(path, key)
        if cache_version is None:
            cache_version, cache_salt = version, salt
        elif version != cache_version or salt != cache_salt:
            raise SystemExit("shader-cache seed: mixed cache format/salt generations")
        input_hash.update(path.name.encode("ascii"))
        input_hash.update(b"\0")
        input_hash.update(data)
        records.append((key[0], key[1], path.name, data))

    records.sort(key=lambda record: (record[0], record[1]))
    if any(records[index][:2] >= records[index + 1][:2] for index in range(len(records) - 1)):
        raise SystemExit("shader-cache seed: duplicate cache key")

    pack = bytearray(PACK_HEADER.pack(b"BWSP", 1, len(records)))
    for hi, lo, _name, data in records:
        pack.extend(PACK_RECORD.pack(hi, lo, len(data)))
        pack.extend(data)
    if len(pack) > MAX_PACK_BYTES:
        raise SystemExit(f"shader-cache seed: pack exceeds {MAX_PACK_BYTES} bytes")

    pack_bytes = bytes(pack)
    metadata = {
        "schema": "blender-web-wgsl-first-boot-seed-v1",
        "formatVersion": 1,
        "cacheFormatVersion": cache_version,
        "cacheSaltHash": f"{cache_salt:016x}",
        "sourceWasmOrigSha256": source_sha,
        "diagnosticNonreceipt": True,
        "entryCount": len(records),
        "entryBytes": sum(len(record[3]) for record in records),
        "inputEntriesSha256": input_hash.hexdigest(),
        "packBytes": len(pack_bytes),
        "packSha256": hashlib.sha256(pack_bytes).hexdigest(),
    }
    manifest_bytes = (json.dumps(metadata, indent=2) + "\n").encode()
    atomic_write(args.output.resolve(), pack_bytes)
    atomic_write(args.manifest.resolve(), manifest_bytes)
    print(
        "BW_SHADER_CACHE_SEED_BUILT "
        f"entries={metadata['entryCount']} entry_bytes={metadata['entryBytes']} "
        f"pack_bytes={metadata['packBytes']} sha256={metadata['packSha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact static-host transport contract shared by M8's local server and gate."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
BROTLI_CODEC = ROOT / "sandbox/m8-staged-deploy/brotli_q11.mjs"
PINNED_NODE = Path(os.environ.get(
    "EMSDK_NODE", ROOT / "tools/emsdk/node/22.16.0_64bit/bin/node"))


BASE_HEADERS = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
        "worker-src 'self' blob:; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'none'"
    ),
}

EXACT_HEADER_BLOCKS = {
    "/*": BASE_HEADERS,
    "/bin/*.wasm": {
        "Content-Type": "application/wasm",
        "Cache-Control": "no-cache, must-revalidate",
    },
    "/bin/*.data": {
        "Content-Type": "application/octet-stream",
        "Cache-Control": "no-cache, must-revalidate",
    },
    "/bin/*.js": {
        "Content-Type": "text/javascript; charset=utf-8",
        "Cache-Control": "no-cache, must-revalidate",
    },
    "/bin/*.json": {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-cache, must-revalidate",
    },
    "/service-worker.js": {
        "Content-Type": "text/javascript; charset=utf-8",
        "Cache-Control": "no-cache",
    },
    "/service-worker-register.js": {
        "Content-Type": "text/javascript; charset=utf-8",
        "Cache-Control": "no-cache, must-revalidate",
    },
    "/scenes/*.blend": {
        "Content-Type": "application/octet-stream",
        "Cache-Control": "public, max-age=31536000, immutable",
    },
}


class TransportContractError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, object]:
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def parse_headers(text: str) -> dict[str, dict[str, str]]:
    """Parse the deliberately small Cloudflare ``_headers`` grammar exactly."""
    blocks: dict[str, dict[str, str]] = {}
    current: str | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            if not raw.startswith("/") or ":" in raw:
                raise TransportContractError(f"_headers line {number}: invalid block selector")
            current = raw.strip()
            if current in blocks:
                raise TransportContractError(f"_headers line {number}: duplicate block {current}")
            blocks[current] = {}
            continue
        if current is None or not raw.startswith("  ") or raw.startswith("   "):
            raise TransportContractError(f"_headers line {number}: header is outside/exceeds two-space indent")
        name, separator, value = raw.strip().partition(":")
        if not separator or not name or not value.strip():
            raise TransportContractError(f"_headers line {number}: malformed header")
        if name in blocks[current]:
            raise TransportContractError(f"_headers line {number}: duplicate {name} in {current}")
        blocks[current][name] = value.strip()
    return blocks


def validate_headers(path: Path) -> None:
    try:
        blocks = parse_headers(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as error:
        raise TransportContractError(f"cannot read _headers: {error}") from error
    if blocks != EXACT_HEADER_BLOCKS:
        missing = sorted(set(EXACT_HEADER_BLOCKS) - set(blocks))
        extra = sorted(set(blocks) - set(EXACT_HEADER_BLOCKS))
        changed = sorted(
            key for key in set(blocks) & set(EXACT_HEADER_BLOCKS)
            if blocks[key] != EXACT_HEADER_BLOCKS[key]
        )
        raise TransportContractError(
            f"_headers policy mismatch: missing={missing!r} extra={extra!r} changed={changed!r}"
        )


def request_file(docroot: Path, request_target: str) -> Path:
    """Resolve an HTTP target below docroot or reject ambiguous/escaping forms."""
    try:
        parsed = urlsplit(request_target)
        decoded = unquote(parsed.path, errors="strict")
    except (UnicodeError, ValueError) as error:
        raise TransportContractError(f"invalid request target: {error}") from error
    if not decoded.startswith("/") or "\\" in decoded or "\x00" in decoded:
        raise TransportContractError("request path is not an absolute canonical URL path")
    raw_parts = decoded[1:].split("/")
    if decoded != "/" and any(part in {"", ".", ".."} for part in raw_parts):
        raise TransportContractError("request path contains an empty/dot segment")
    parts = PurePosixPath(decoded).parts[1:]
    root = docroot.resolve(strict=True)
    candidate = root.joinpath(*parts).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise TransportContractError("request path escapes docroot") from error
    return candidate


def exact_tree(docroot: Path) -> list[str]:
    root = docroot.resolve(strict=True)
    names: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise TransportContractError(f"deploy tree contains a symlink: {relative}")
        if path.is_file():
            names.append(relative)
        elif not path.is_dir():
            raise TransportContractError(f"deploy tree contains unsupported entry: {relative}")
    return sorted(names)


def validate_docroot(
    docroot: Path,
    expected_names: list[str] | tuple[str, ...],
    expected_public_manifest: dict[str, object],
    source_identities: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Validate any candidate docroot, never silently substituting the canonical one."""
    root = docroot.resolve(strict=True)
    expected = sorted(expected_names)
    actual = exact_tree(root)
    if actual != expected:
        raise TransportContractError(
            f"deploy tree mismatch: missing={sorted(set(expected) - set(actual))!r} "
            f"extra={sorted(set(actual) - set(expected))!r}"
        )
    try:
        public = json.loads((root / "bin/split-build.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TransportContractError(f"cannot read public split manifest: {error}") from error
    if public != expected_public_manifest:
        raise TransportContractError("public split manifest is stale, incomplete, or noncanonical")
    validate_headers(root / "_headers")
    for relative, wanted in source_identities.items():
        path = root / relative
        if identity(path) != wanted:
            raise TransportContractError(f"shipped source identity mismatch: {relative}")
    for relative in expected:
        if not relative.endswith(".br"):
            continue
        compressed = root / relative
        raw = root / relative[:-3]
        if not raw.is_file():
            raise TransportContractError(f"Brotli sibling has no raw asset: {relative}")
        try:
            process = subprocess.Popen(
                [str(PINNED_NODE), str(BROTLI_CODEC), "decode-stdout", str(compressed)],
                stdout=subprocess.PIPE)
        except OSError as error:
            raise TransportContractError(
                f"cannot execute deterministic Brotli decoder: {error}") from error
        assert process.stdout is not None
        digest = hashlib.sha256()
        for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
            digest.update(chunk)
        if process.wait() != 0 or digest.hexdigest() != sha256(raw):
            raise TransportContractError(f"Brotli sibling differs from raw asset: {relative}")
    return {name: identity(root / name) for name in expected}


def _selfcheck() -> None:
    codec = subprocess.run(
        [str(PINNED_NODE), str(BROTLI_CODEC), "--selfcheck"],
        cwd=ROOT, capture_output=True, text=True)
    assert codec.returncode == 0 and \
        "BW_BROTLI_Q11_SELFCHECK_PASS node=v22.16.0 quality=11 lgwin=24" in codec.stdout
    rendered = "\n".join(
        line for selector, headers in EXACT_HEADER_BLOCKS.items()
        for line in ([selector] + [f"  {name}: {value}" for name, value in headers.items()] + [""])
    )
    assert parse_headers(rendered) == EXACT_HEADER_BLOCKS
    for mutation in (
        rendered.replace("application/json; charset=utf-8", "application/json", 1),
        rendered.replace(
            "/service-worker-register.js\n  Content-Type: text/javascript; charset=utf-8\n"
            "  Cache-Control: no-cache, must-revalidate",
            "/service-worker-register.js\n  Content-Type: text/javascript; charset=utf-8\n"
            "  Cache-Control: public, max-age=3600",
            1,
        ),
        rendered + "\n/bin/*.json\n  Cache-Control: public\n",
        rendered.replace("  Cache-Control: no-cache, must-revalidate", "   Cache-Control: no-cache", 1),
    ):
        try:
            blocks = parse_headers(mutation)
            if blocks == EXACT_HEADER_BLOCKS:
                raise AssertionError("mutated header policy was accepted")
        except TransportContractError:
            pass
    with tempfile.TemporaryDirectory(prefix="bw-transport-selfcheck-") as temp:
        root = Path(temp)
        (root / "bin").mkdir()
        assert request_file(root, "/bin/x.wasm?sha256=abc") == (root / "bin/x.wasm").resolve()
        for attack in ("/../secret", "/%2e%2e/secret", "/bin\\..\\secret", "/bin/%00x"):
            try:
                request_file(root, attack)
            except TransportContractError:
                continue
            raise AssertionError(f"escaping request accepted: {attack}")
        (root / "_headers").write_text(rendered, encoding="utf-8")
        manifest = {"schema": 1, "marker": "selfcheck"}
        (root / "bin/split-build.json").write_text(
            json.dumps(manifest) + "\n", encoding="utf-8")
        (root / "bin/x").write_bytes(b"exact")
        names = ["_headers", "bin/split-build.json", "bin/x"]
        source = {"bin/x": identity(root / "bin/x")}
        assert sorted(validate_docroot(root, names, manifest, source)) == sorted(names)
        for mutation in ("extra", "manifest", "symlink"):
            if mutation == "extra":
                changed = root / "extra"
                changed.write_bytes(b"bad")
            elif mutation == "manifest":
                changed = root / "bin/split-build.json"
                changed.write_text('{"schema":2}\n', encoding="utf-8")
            else:
                changed = root / "escape"
                changed.symlink_to(root / "bin/x")
            try:
                validate_docroot(root, names, manifest, source)
            except TransportContractError:
                pass
            else:
                raise AssertionError(f"docroot mutation accepted: {mutation}")
            changed.unlink()
            if mutation == "manifest":
                changed.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    print("M8_TRANSPORT_SELFCHECK_PASS positive=3 negative=11")


if __name__ == "__main__":
    _selfcheck()

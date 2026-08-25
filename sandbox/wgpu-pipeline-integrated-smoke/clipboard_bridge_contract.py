#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Bind GHOST's synchronous text clipboard API to the browser-main bridge."""

from __future__ import annotations

import argparse
from pathlib import Path


REGISTER_MARKER = "void GHOST_SystemWeb::registerCanvasCallbacks()"
GET_MARKER = "char *GHOST_SystemWeb::getClipboard(bool selection) const"
PUT_MARKER = "void GHOST_SystemWeb::putClipboard(const char *buffer, bool selection) const"
CAPABILITIES_MARKER = "GHOST_TCapabilityFlag GHOST_SystemWeb::getCapabilities() const"


def method(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"missing method: {marker}")
    opening = source.find("{", start)
    if opening < 0:
        raise ValueError(f"missing method body: {marker}")
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise ValueError(f"unterminated method: {marker}")


def mutate_method(source: str, marker: str, old: str, new: str) -> str:
    original = method(source, marker)
    changed = original.replace(old, new, 1)
    if changed == original:
        raise ValueError(f"mutation input is absent from {marker}: {old!r}")
    return source.replace(original, changed, 1)


def require_once(body: str, token: str, label: str) -> None:
    if body.count(token) != 1:
        raise ValueError(f"{label} requires exactly one {token!r}")


def validate(source: str, header: str) -> None:
    register = method(source, REGISTER_MARKER)
    getter = method(source, GET_MARKER)
    setter = method(source, PUT_MARKER)
    capabilities = method(source, CAPABILITIES_MARKER)

    require_once(header, "char *getClipboard(bool selection) const override;", "header")
    require_once(header, "void putClipboard(const char *buffer, bool selection) const override;", "header")

    required_register = (
        "typeof globalThis.__bwTextClipboardBridge !== \"object\"",
        "var clipboardText = null;",
        "var writeRequest = 0;",
        "var publish = function (text, source)",
        "navigator.permissions.query({name: \"clipboard-read\"})",
        "permission.state !== \"granted\"",
        "if (sequence === startedAt)",
        "navigator.clipboard.readText()",
        "navigator.clipboard.writeText(clipboardText)",
        "var request = ++writeRequest;",
        "readForBlender: function ()",
        "writeFromBlender: function (text)",
        "Object.defineProperty(globalThis, \"__bwTextClipboardBridge\"",
        "document.addEventListener(\"paste\", function (event)",
        "event.clipboardData.getData(\"text/plain\")",
        "publish(event.clipboardData.getData(\"text/plain\"), \"paste-event\")",
        "document.addEventListener(\"pointerdown\", refreshIfGranted, true);",
        "utf8Bytes:",
        "writeStatus:",
        "readStatus:",
    )
    for token in required_register:
        require_once(register, token, "main-thread bridge")
    if register.count("if (request === writeRequest)") != 2:
        raise ValueError("clipboard write completion is not bound to its latest request")
    if register.count(".catch(function ()") < 2:
        raise ValueError("clipboard read/write promises are not rejection-safe")
    if "text: clipboardText" in register:
        raise ValueError("clipboard diagnostics expose copied text")

    required_get = (
        "MAIN_THREAD_EM_ASM_PTR({",
        "if ($0 || typeof globalThis.__bwTextClipboardBridge !== \"object\")",
        "globalThis.__bwTextClipboardBridge.readForBlender()",
        "if (text === null)",
        "lengthBytesUTF8(text) + 1",
        "var result = _malloc(size);",
        "stringToUTF8(text, result, size);",
        "selection ? 1 : 0",
    )
    for token in required_get:
        require_once(getter, token, "synchronous getter")
    if "return nullptr;" in getter:
        raise ValueError("ordinary text clipboard still returns the old unconditional null")

    required_set = (
        "if (selection || buffer == nullptr)",
        "MAIN_THREAD_EM_ASM({",
        "globalThis.__bwTextClipboardBridge.writeFromBlender(UTF8ToString($0));",
        "}, buffer);",
    )
    for token in required_set:
        require_once(setter, token, "synchronous setter")
    if "MAIN_THREAD_ASYNC_EM_ASM" in setter:
        raise ValueError("setter retains a borrowed Wasm pointer across an asynchronous proxy")

    require_once(capabilities, "GHOST_kCapabilityClipboardPrimary", "capability mask")
    require_once(capabilities, "GHOST_kCapabilityClipboardImage", "capability mask")


def selfcheck(source: str, header: str) -> None:
    validate(source, header)
    mutations = (
        mutate_method(source, REGISTER_MARKER, 'document.addEventListener("paste"',
                      'document.addEventListener("copy"'),
        mutate_method(source, REGISTER_MARKER, 'getData("text/plain")',
                      'getData("text/html")'),
        mutate_method(source, REGISTER_MARKER,
                      'document.addEventListener("pointerdown", refreshIfGranted, true);',
                      'document.addEventListener("pointerup", refreshIfGranted, true);'),
        mutate_method(source, REGISTER_MARKER, 'permission.state !== "granted"',
                      'permission.state === "granted"'),
        mutate_method(source, REGISTER_MARKER, "if (sequence === startedAt)", "if (true)"),
        mutate_method(source, REGISTER_MARKER, "navigator.clipboard.readText()",
                      "Promise.resolve(null)"),
        mutate_method(source, REGISTER_MARKER, "navigator.clipboard.writeText(clipboardText)",
                      "Promise.resolve()"),
        mutate_method(source, REGISTER_MARKER, "if (request === writeRequest)", "if (true)"),
        mutate_method(source, REGISTER_MARKER, '"paste-event"', '"clipboard-read"'),
        mutate_method(source, GET_MARKER, "if ($0 ||", "if (false ||"),
        mutate_method(source, GET_MARKER, "lengthBytesUTF8(text) + 1",
                      "lengthBytesUTF8(text)"),
        mutate_method(source, GET_MARKER, "var result = _malloc(size);", "var result = 0;"),
        mutate_method(source, GET_MARKER, "stringToUTF8(text, result, size);", ""),
        mutate_method(source, PUT_MARKER, "if (selection || buffer == nullptr)",
                      "if (buffer == nullptr)"),
        mutate_method(source, PUT_MARKER, "UTF8ToString($0)", '"stale"'),
        mutate_method(source, CAPABILITIES_MARKER, "GHOST_kCapabilityClipboardPrimary |", ""),
        header.replace("getClipboard(bool selection)", "getClipboard(bool missing)", 1),
    )
    for index, mutation in enumerate(mutations, start=1):
        mutated_source, mutated_header = (source, mutation) if index == len(mutations) else (mutation, header)
        try:
            validate(mutated_source, mutated_header)
        except ValueError:
            continue
        raise ValueError(f"mutation {index} was accepted")


def validate_runtime(runtime: str) -> None:
    required = {
        "__bwTextClipboardBridge": 6,
        "paste-event": 1,
        "clipboard-read": 2,
        "writeFromBlender": 2,
        "readForBlender": 2,
        "text/plain": 1,
    }
    for token, expected in required.items():
        if runtime.count(token) != expected:
            raise ValueError(
                f"baked runtime requires {expected} exact {token!r} occurrence(s)"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("system_source", type=Path)
    parser.add_argument("system_header", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    source = args.system_source.read_text(encoding="utf-8")
    header = args.system_header.read_text(encoding="utf-8")
    if args.selfcheck:
        selfcheck(source, header)
    else:
        validate(source, header)
    if args.runtime is not None:
        validate_runtime(args.runtime.read_text(encoding="utf-8"))
    print(
        "CLIPBOARD_BRIDGE_CONTRACT PASS paste=trusted put=owned get=malloc "
        f"primary=off privacy=metadata-only mutations=17 runtime={'baked' if args.runtime else 'source'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

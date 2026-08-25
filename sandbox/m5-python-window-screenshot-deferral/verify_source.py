#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

"""Fail-closed source contract for the browser Window.screenshot policy."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PYTHON_WM = Path("source/blender/python/intern/bpy_rna_wm.cc")
SCREENDUMP = Path("source/blender/editors/screen/screendump.cc")
PATHS = (PYTHON_WM, SCREENDUMP)
SIGNATURE = "static PyObject *bpy_rna_window_screenshot(PyObject *self, PyObject *args, PyObject *kwds)"
BACKGROUND_ERROR = "Window.screenshot() is not available in background mode"
BROWSER_ERROR_PARTS = (
    '"Window.screenshot() is unavailable in the browser because WebGPU readback is "',
    '"asynchronous; use bpy.ops.screen.screenshot() for file capture"',
)


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def require_once(text: str, needle: str, label: str) -> None:
    count = text.count(needle)
    require(count == 1, f"{label}: expected one occurrence, found {count}")


def function_body(text: str, signature: str) -> str:
    require_once(text, signature, signature)
    start = text.index(signature)
    brace = text.find("{", start + len(signature))
    require(brace >= 0, f"missing function body: {signature}")
    depth = 0
    state = "code"
    quote = ""
    index = brace
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if state == "line_comment":
            if char == "\n":
                state = "code"
        elif state == "block_comment":
            if char == "*" and next_char == "/":
                state = "code"
                index += 1
        elif state == "string":
            if char == "\\":
                index += 1
            elif char == quote:
                state = "code"
        else:
            if char == "/" and next_char == "/":
                state = "line_comment"
                index += 1
            elif char == "/" and next_char == "*":
                state = "block_comment"
                index += 1
            elif char in ('"', "'"):
                state = "string"
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        index += 1
    raise VerificationError(f"unterminated function body: {signature}")


def read_sources(root: Path) -> dict[Path, str]:
    sources: dict[Path, str] = {}
    for relative in PATHS:
        source = root / relative
        require(source.is_file(), f"missing source: {relative}")
        sources[relative] = source.read_text(encoding="utf-8")
    return sources


def source_digest(sources: dict[Path, str]) -> str:
    digest = hashlib.sha256()
    for relative in PATHS:
        digest.update(str(relative).encode())
        digest.update(b"\0")
        digest.update(sources[relative].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def validate(sources: dict[Path, str]) -> dict[str, object]:
    python_wm = sources[PYTHON_WM]
    screendump = sources[SCREENDUMP]
    body = function_body(python_wm, SIGNATURE)

    require_once(body, "#ifdef __EMSCRIPTEN__", "browser policy guard")
    require_once(body, "#else", "browser/native branch")
    require_once(body, "#endif", "browser policy terminator")
    prefix, guarded = body.split("#ifdef __EMSCRIPTEN__", 1)
    browser, native_guarded = guarded.split("#else", 1)
    native, suffix = native_guarded.split("#endif", 1)

    require(BACKGROUND_ERROR in prefix, "background behavior does not precede browser policy")
    require("if (G.background)" in prefix, "background gate missing")
    require("_PyArg_ParseTupleAndKeywordsFast(" in prefix, "stock keyword parsing missing")
    require("return nullptr;" in browser, "browser policy does not raise")
    require(browser.count("return nullptr;") == 1, "browser branch return census differs")
    for part in BROWSER_ERROR_PARTS:
        require_once(browser, part, "browser error")
    require("PyErr_SetString(" in browser, "browser RuntimeError setter missing")
    require("PyExc_RuntimeError" in browser, "browser error type differs")
    require("WM_window_pixels_read" not in browser, "browser branch retains synchronous read")
    require("PyC_MemoryView_FromBufferOwned" not in browser, "browser branch fabricates memoryview")

    require_once(native, "WM_window_pixels_read(C, win, dumprect_size)", "native capture")
    for needle in (
        "PyC_ParseOptionalRectI",
        "MEM_new_array_uninitialized<uint8_t>",
        "dumprect[i] = 0xff;",
        "PyC_MemoryView_FromBufferOwned(&info)",
    ):
        require(needle in body, f"stock screenshot contract missing {needle!r}")
    require("unavailable in the browser" not in native, "native branch carries browser error")
    require(suffix.strip() == "}", "browser policy does not end with screenshot function")

    for needle in (
        '".. method:: screenshot(*, region=None, use_alpha=False)\\n"',
        '"   :rtype: memoryview\\n"',
        '"screenshot",',
        "reinterpret_cast<PyCFunction>(bpy_rna_window_screenshot)",
        "METH_VARARGS | METH_KEYWORDS",
    ):
        require(needle in python_wm, f"public method surface drifted: {needle!r}")

    for needle in (
        "scd->readback = WM_window_pixels_read_async(C, win);",
        "WM_window_pixels_read_async_status(scd->readback)",
        "WM_window_pixels_read_async_consume(scd->readback, dumprect_size)",
        "WM_window_pixels_read_async_cancel(scd->readback);",
        "constexpr int max_tick_count = 240;",
        "return OPERATOR_RUNNING_MODAL;",
        'ot->idname = "SCREEN_OT_screenshot";',
    ):
        require(needle in screendump, f"async file-capture workaround missing {needle!r}")
    require(
        "WM_window_pixels_read(C, win" not in screendump,
        "file-capture workaround regressed to synchronous read",
    )

    return {
        "schema": 1,
        "verdict": "PASS",
        "contracts": {
            "public_surface_preserved": True,
            "argument_parsing_preserved": True,
            "background_error_preserved": True,
            "native_memoryview_preserved": True,
            "browser_fail_closed": True,
            "browser_sync_call_excluded": True,
            "async_file_capture_workaround": True,
            "live_hardware_receipt": False,
        },
        "deferred_callers": ["python_window_screenshot_memoryview"],
        "remaining_window_capture_callers": [],
        "remaining_sync_families": [],
        "source_sha256": source_digest(sources),
    }


def run_selfcheck(sources: dict[Path, str]) -> None:
    validate(sources)
    mutations = (
        (PYTHON_WM, "#ifdef __EMSCRIPTEN__", "#if 0", "browser guard"),
        (PYTHON_WM, BROWSER_ERROR_PARTS[0], '"Window screenshot failed"', "actionable error"),
        (PYTHON_WM, BROWSER_ERROR_PARTS[1], '"asynchronous"', "operator workaround"),
        (PYTHON_WM, "PyExc_RuntimeError,\n      \"Window.screenshot()", "PyExc_TypeError,\n      \"Window.screenshot()", "error type"),
        (PYTHON_WM, "#else\n  bContext *C", "#endif\n  bContext *C", "native branch"),
        (PYTHON_WM, "WM_window_pixels_read(C, win, dumprect_size)", "WM_window_pixels_read_async(C, win)", "native capture"),
        (PYTHON_WM, "PyC_MemoryView_FromBufferOwned(&info)", "Py_NewRef(Py_None)", "native memoryview"),
        (PYTHON_WM, BACKGROUND_ERROR, "Window screenshot background failure", "background behavior"),
        (PYTHON_WM, "METH_VARARGS | METH_KEYWORDS", "METH_NOARGS", "public flags"),
        (SCREENDUMP, "WM_window_pixels_read_async(C, win);", "WM_window_pixels_read(C, win, nullptr);", "async workaround"),
        (SCREENDUMP, "constexpr int max_tick_count = 240;", "constexpr int max_tick_count = 0;", "bounded workaround"),
        (SCREENDUMP, 'ot->idname = "SCREEN_OT_screenshot";', 'ot->idname = "SCREEN_OT_missing";', "operator surface"),
    )
    for relative, old, new, label in mutations:
        require_once(sources[relative], old, f"selfcheck {label}")
        mutated = dict(sources)
        mutated[relative] = sources[relative].replace(old, new, 1)
        try:
            validate(mutated)
        except VerificationError:
            continue
        raise VerificationError(f"selfcheck mutation accepted: {label}")
    print(
        "M5_PYTHON_WINDOW_SCREENSHOT_SOURCE_SELFCHECK_PASS "
        f"mutations={len(mutations)} allocation=zero"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    require(args.selfcheck != (args.output is not None), "choose exactly one of --selfcheck/--output")
    sources = read_sources(args.source_root)
    if args.selfcheck:
        run_selfcheck(sources)
        return 0
    receipt = validate(sources)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "M5_PYTHON_WINDOW_SCREENSHOT_SOURCE_PASS "
        f"sha256={receipt['source_sha256']} deferred=1 remaining=0 live_receipt=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, VerificationError) as error:
        print(f"M5_PYTHON_WINDOW_SCREENSHOT_SOURCE_FAIL {error}")
        raise SystemExit(1)

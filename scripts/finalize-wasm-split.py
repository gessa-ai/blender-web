#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed Binaryen profile capture/apply finalizer for blender_browser.

CAPTURE replaces emcc's stock per-instance-global SPLIT_MODULE instrumented wasm
with `wasm-split --instrument --in-memory`. The browser link reserves the first
1 MiB by setting GLOBAL_BASE, so the shared pthread memory aggregates hits from
the proxied WM worker and every pooled/fresh worker.

APPLY accepts only a profile bound to the exact same `.wasm.orig`, creates the
primary and secondary modules, patches the deterministic pthread URL guard into
the generated Emscripten glue, and records the placeholder/symbol maps. It never
leaves emcc's instrumented module as a shipping success path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile


MARKER = "BW_PTHREAD_SPLIT_WASM_BINARY_V1"
SINGLE_FLIGHT_RUNTIME_MARKER = "BW_SPLIT_SINGLE_FLIGHT_RUNTIME_V1"
SINGLE_FLIGHT_LOADER_MARKER = "BW_SPLIT_SINGLE_FLIGHT_LOADER_V1"
SINGLE_FLIGHT_CORE_DISPATCH_MARKER = "BW_SPLIT_WORKER_CORE_DISPATCH_V1"
SINGLE_FLIGHT_INITIAL_DISPATCH_MARKER = "BW_SPLIT_WORKER_INITIAL_INSTALL_FIFO_V1"
CAPTURE_PROBE_CORE_DISPATCH_MARKER = "BW_SPLIT_CAPTURE_PROBE_CORE_DISPATCH_V1"
CAPTURE_THREAD_ENTRY_DIAG_MARKER = "BW_SPLIT_CAPTURE_THREAD_ENTRY_DIAG_V1"
CAPTURE_THREAD_ENTRY_STAGE_MARKER = "BW_SPLIT_CAPTURE_THREAD_ENTRY_STAGE_V1"
CAPTURE_MAIN_DIAGNOSTIC_DISPATCH_MARKER = "BW_SPLIT_CAPTURE_MAIN_DIAGNOSTIC_DISPATCH_V1"
SHARED_MEMORY_VIEW_REFRESH_MARKER = "BW_SPLIT_SHARED_MEMORY_VIEW_REFRESH_V1"
SHARED_MEMORY_GROWABLE_VIEW_GUARD_MARKER = "BW_SPLIT_SHARED_MEMORY_GROWABLE_VIEW_GUARD_V1"
PTHREAD_MEMORY_RANGE_SYNC_MARKER = "BW_SPLIT_PTHREAD_MEMORY_RANGE_SYNC_V1"
PTHREAD_STACK_RANGE_SYNC_MARKER = "BW_SPLIT_PTHREAD_STACK_RANGE_SYNC_V1"
PTHREAD_MAILBOX_RANGE_SYNC_MARKER = "BW_SPLIT_PTHREAD_MAILBOX_RANGE_SYNC_V1"
ADAPTER_CONTRACT = "hardware-webgpu-adapter-v1"
CAPTURE_NODE_VERSION = "v22.16.0"
CAPTURE_PLAYWRIGHT_VERSION = "1.61.1"
CAPTURE_PNGJS_VERSION = "7.0.0"
CAPTURE_CHROMIUM_VERSION = "149.0.7827.55"
SOFTWARE_ADAPTER_TOKENS = (
    "swiftshader",
    "llvmpipe",
    "lavapipe",
    "softpipe",
    "software rasterizer",
    "microsoft basic render",
    "warp",
)
ADAPTER_FIELDS = {
    "contract",
    "status",
    "present",
    "platform",
    "powerPreference",
    "isFallbackAdapter",
    "info",
    "softwareMatches",
    "reason",
}
ADAPTER_INFO_FIELDS = {"vendor", "architecture", "device", "description"}
SPLIT_CONTROLLER_EXPORTS = [
    "BW_web_split_request_park",
    "BW_web_split_request_prepared",
    "BW_web_split_request_apply",
    "BW_web_split_request_page_ready",
    "BW_web_split_request_resume",
    "BW_web_split_phase",
    "BW_web_split_request_generation",
    "BW_web_split_park_request_generation",
    "BW_web_split_parked_generation",
    "BW_web_split_prepared_request_generation",
    "BW_web_split_prepared_generation",
    "BW_web_split_apply_request_generation",
    "BW_web_split_applied_generation",
    "BW_web_split_page_ready_request_generation",
    "BW_web_split_page_ready_generation",
    "BW_web_split_resume_request_generation",
    "BW_web_split_resumed_generation",
    "BW_web_split_error_generation",
    "BW_web_split_offending_generation",
    "BW_web_split_error_code",
    "BW_web_split_target_threads",
    "BW_web_split_active_threads",
    "BW_web_split_native_ready",
    "BW_web_split_openexr_threads",
    "BW_web_split_oiio_threads",
    "BW_web_split_apply_openexr_set",
    "BW_web_split_apply_openexr_threads",
    "BW_web_split_apply_oiio_set",
    "BW_web_split_apply_oiio_threads",
    "BW_web_split_rollback_openexr_set",
    "BW_web_split_rollback_openexr_threads",
    "BW_web_split_rollback_oiio_set",
    "BW_web_split_rollback_oiio_threads",
    "BW_web_split_reload_required",
    "BW_web_split_prepared_workers",
    "BW_web_split_prepared_acknowledgements",
    "BW_web_split_prepared_instances",
    "BW_web_split_prepared_local_instances",
    "BW_web_split_prepared_pending",
    "BW_web_split_prepared_protocol_errors",
    "BW_web_split_prepared_stabilization_epoch",
    "BW_web_split_page_ready_workers",
    "BW_web_split_page_ready_acknowledgements",
    "BW_web_split_page_ready_instances",
    "BW_web_split_page_ready_local_instances",
    "BW_web_split_page_ready_pending",
    "BW_web_split_page_ready_protocol_errors",
    "BW_web_split_page_ready_late_workers",
    "BW_web_split_page_ready_stabilization_epoch",
]
SINGLE_FLIGHT_SOURCE = Path(__file__).resolve().parents[1] / "platform_web/split/single-flight.js"
PROFILE_EXPORT_SOURCE = Path(__file__).resolve().parents[1] / "platform_web/split/profile-export.js"
SECONDARY_FILENAME_SENTINEL = "__BW_SPLIT_SECONDARY_FILENAME_SENTINEL__"
SECONDARY_BYTES_SENTINEL = "__BW_SPLIT_SECONDARY_BYTES_SENTINEL__"
SECONDARY_SHA256_SENTINEL = "__BW_SPLIT_SECONDARY_SHA256_SENTINEL__"
DEFAULT_RESERVE = 1_048_576
PROFILE_BYTES_PER_FUNCTION = 4
PROFILE_MARKER = "BW_SPLIT_PROFILE_EXPORT_V1"
BINARYEN_FEATURES = [
    "--enable-sign-ext",
    "--enable-mutable-globals",
    "--enable-nontrapping-float-to-int",
    "--enable-bulk-memory",
    "--enable-bulk-memory-opt",
    "--enable-threads",
    "--enable-multivalue",
    "--enable-reference-types",
    "--enable-call-indirect-overlong",
    "--enable-extended-const",
]


class WasmError(RuntimeError):
    pass


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def byte(self) -> int:
        if self.pos >= len(self.data):
            raise WasmError("unexpected end of wasm")
        value = self.data[self.pos]
        self.pos += 1
        return value

    def take(self, count: int) -> bytes:
        end = self.pos + count
        if count < 0 or end > len(self.data):
            raise WasmError("truncated wasm field")
        value = self.data[self.pos:end]
        self.pos = end
        return value

    def uleb(self) -> int:
        value = 0
        shift = 0
        while True:
            byte = self.byte()
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value
            shift += 7
            if shift > 70:
                raise WasmError("oversized unsigned LEB")

    def sleb(self, bits: int = 32) -> int:
        value = 0
        shift = 0
        while True:
            byte = self.byte()
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                if shift < bits and byte & 0x40:
                    value |= -(1 << shift)
                return value
            if shift > bits + 7:
                raise WasmError("oversized signed LEB")

    def name(self) -> str:
        return self.take(self.uleb()).decode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_limits(reader: Reader) -> tuple[int, int | None, bool]:
    flags = reader.uleb()
    minimum = reader.uleb()
    maximum = reader.uleb() if flags & 1 else None
    return minimum, maximum, bool(flags & 2)


def skip_table_type(reader: Reader) -> None:
    reader.byte()
    parse_limits(reader)


def wasm_facts(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    reader = Reader(raw)
    if reader.take(8) != b"\0asm\x01\0\0\0":
        raise WasmError(f"not a WebAssembly 1 binary: {path}")

    imported_functions = 0
    defined_functions = 0
    memory_imports: list[dict[str, object]] = []
    exports: list[str] = []
    import_modules: list[str] = []
    active_data_offsets: list[int] = []
    passive_data_segments = 0

    while reader.pos < len(raw):
        section_id = reader.byte()
        payload = Reader(reader.take(reader.uleb()))
        if section_id == 2:
            for _ in range(payload.uleb()):
                module = payload.name()
                payload.name()
                kind = payload.byte()
                import_modules.append(module)
                if kind == 0:
                    imported_functions += 1
                    payload.uleb()
                elif kind == 1:
                    skip_table_type(payload)
                elif kind == 2:
                    minimum, maximum, shared = parse_limits(payload)
                    memory_imports.append(
                        {"module": module, "minimum": minimum, "maximum": maximum, "shared": shared}
                    )
                elif kind == 3:
                    payload.byte()
                    payload.byte()
                elif kind == 4:
                    payload.byte()
                    payload.uleb()
                else:
                    raise WasmError(f"unsupported import kind {kind}")
        elif section_id == 3:
            defined_functions = payload.uleb()
            for _ in range(defined_functions):
                payload.uleb()
        elif section_id == 7:
            for _ in range(payload.uleb()):
                exports.append(payload.name())
                payload.byte()
                payload.uleb()
        elif section_id == 11:
            for _ in range(payload.uleb()):
                flags = payload.uleb()
                if flags == 1:
                    passive_data_segments += 1
                elif flags in (0, 2):
                    if flags == 2:
                        memory_index = payload.uleb()
                        if memory_index != 0:
                            raise WasmError(f"active data targets memory {memory_index}, expected 0")
                    opcode = payload.byte()
                    if opcode != 0x41:
                        raise WasmError(
                            f"active data offset opcode 0x{opcode:02x} is not constant i32"
                        )
                    offset = payload.sleb(32)
                    if payload.byte() != 0x0B:
                        raise WasmError("active data offset expression has trailing instructions")
                    active_data_offsets.append(offset)
                else:
                    raise WasmError(f"unsupported data segment flags {flags}")
                payload.take(payload.uleb())
        if payload.pos != len(payload.data):
            # Sections we intentionally do not decode are allowed. Decoded
            # sections, however, must be consumed exactly.
            if section_id in (2, 3, 7, 11):
                raise WasmError(f"section {section_id} has unparsed bytes")

    return {
        "imported_functions": imported_functions,
        "defined_functions": defined_functions,
        "total_functions": imported_functions + defined_functions,
        "memory_imports": memory_imports,
        "exports": exports,
        "import_modules": sorted(set(import_modules)),
        "active_data_segment_count": len(active_data_offsets),
        "passive_data_segment_count": passive_data_segments,
        "minimum_active_data_offset": min(active_data_offsets) if active_data_offsets else None,
    }


def wasm_function_layout(path: Path) -> dict[str, object]:
    """Return exact binary function imports/exports and defined-function count."""
    reader = Reader(path.read_bytes())
    if reader.take(8) != b"\0asm\x01\0\0\0":
        raise WasmError(f"not a WebAssembly 1 binary: {path}")
    function_imports: list[dict[str, object]] = []
    defined_functions = 0
    function_exports: dict[str, int] = {}
    while reader.pos < len(reader.data):
        section_id = reader.byte()
        payload = Reader(reader.take(reader.uleb()))
        if section_id == 2:
            for _ in range(payload.uleb()):
                module = payload.name()
                field = payload.name()
                kind = payload.byte()
                if kind == 0:
                    function_imports.append(
                        {"index": len(function_imports), "module": module, "field": field}
                    )
                    payload.uleb()
                elif kind == 1:
                    skip_table_type(payload)
                elif kind == 2:
                    parse_limits(payload)
                elif kind == 3:
                    payload.byte(); payload.byte()
                elif kind == 4:
                    payload.byte(); payload.uleb()
                else:
                    raise WasmError(f"unsupported import kind {kind}")
        elif section_id == 3:
            defined_functions = payload.uleb()
            for _ in range(defined_functions):
                payload.uleb()
        elif section_id == 7:
            for _ in range(payload.uleb()):
                name = payload.name()
                kind = payload.byte()
                index = payload.uleb()
                if kind == 0:
                    function_exports[name] = index
    return {
        "function_imports": function_imports,
        "imported_function_count": len(function_imports),
        "defined_function_count": defined_functions,
        "function_exports": function_exports,
    }


def controller_keep_functions(layout: dict[str, object]) -> dict[str, object]:
    """Resolve protected exports to Binaryen's defined-function ordinals.

    wasm-split synthesizes indirect-call export trampolines for an exported
    function that the profile leaves cold.  Those trampolines cannot satisfy
    the pre-shard closure proof because the primary table also contains
    deferred placeholders.  Keep every protected export's original body in
    primary by exact binary index, then let the ordinary transitive closure
    proof reject any cold dependency or indirect escape that remains.
    """
    imported_count = int(layout["imported_function_count"])
    defined_count = int(layout["defined_function_count"])
    exports = layout["function_exports"]
    if not isinstance(exports, dict):
        raise WasmError("function export layout is not a mapping")
    missing = sorted(set(SPLIT_CONTROLLER_EXPORTS) - set(exports))
    if missing:
        raise WasmError(f"controller exports absent from original: {missing}")
    mapping: dict[str, str] = {}
    for name in SPLIT_CONTROLLER_EXPORTS:
        absolute = int(exports[name])
        defined = absolute - imported_count
        if defined < 0 or defined >= defined_count:
            raise WasmError(f"controller export {name} is not an original defined function")
        mapping[name] = str(defined)
    functions = list(dict.fromkeys(mapping.values()))
    if not functions:
        raise WasmError("controller keep-function set is empty")
    return {
        "contract": "exact-controller-export-defined-function-keep-set-v1",
        "imported_function_count": imported_count,
        "defined_function_count": defined_count,
        "exports": mapping,
        "functions": functions,
        "function_count": len(functions),
    }


def verify_reserved_shared_memory(facts: dict[str, object], reserve: int) -> None:
    total_functions = int(facts["total_functions"])
    required_profile_bytes = total_functions * PROFILE_BYTES_PER_FUNCTION + 64
    if total_functions <= 0 or required_profile_bytes > reserve:
        raise WasmError(
            f"conservative profile span {required_profile_bytes} bytes for {total_functions} "
            f"functions does not fit reserved {reserve} bytes"
        )
    memory_imports = facts["memory_imports"]
    if not isinstance(memory_imports, list) or not any(
        isinstance(row, dict) and row.get("shared") is True for row in memory_imports
    ):
        raise WasmError("module does not import shared pthread memory")
    minimum_offset = facts["minimum_active_data_offset"]
    # Pthread Emscripten modules normally carry only passive data segments and
    # initialize them from __wasm_init_memory at GLOBAL_BASE. Active segments,
    # when present, must all clear the reserve; an empty set is valid.
    if minimum_offset is not None and int(minimum_offset) < reserve:
        raise WasmError(
            f"active data begins at {minimum_offset}, inside profile reserve [0,{reserve})"
        )


def patch_pthread_guard(js_path: Path) -> None:
    source = js_path.read_text(encoding="utf-8")
    if MARKER in source:
        return
    readable = "      let secondaryFile;\n"
    minified = '{let secondaryFile;if(moduleName=="placeholder")'
    if source.count(readable) == 1 and source.count(minified) == 0:
        replacement = (
            readable
            + "      // " + MARKER + ": pthread instances have not initialized wasmBinaryFile.\n"
            + "      if (typeof wasmBinaryFile == 'undefined' || !wasmBinaryFile) "
            + "wasmBinaryFile = findWasmBinary();\n"
        )
        source = source.replace(readable, replacement, 1)
    elif source.count(minified) == 1 and source.count(readable) == 0:
        replacement = (
            "{let secondaryFile;/*"
            + MARKER
            + '*/if(typeof wasmBinaryFile=="undefined"||!wasmBinaryFile)'
            + 'wasmBinaryFile=findWasmBinary();if(moduleName=="placeholder")'
        )
        source = source.replace(minified, replacement, 1)
    else:
        raise WasmError(
            "Emscripten split proxy anchors do not have one unambiguous readable/minified match: "
            f"readable={source.count(readable)} minified={source.count(minified)}"
        )
    js_path.write_text(source, encoding="utf-8")


def replace_once(source: str, old: str, new: str, description: str) -> str:
    count = source.count(old)
    if count != 1:
        raise WasmError(f"{description} expected one anchor, found {count}")
    return source.replace(old, new, 1)


def patch_shared_memory_view_refresh(js_path: Path) -> dict[str, object]:
    """Refresh fixed typed-array views after in-place shared-memory growth.

    Chromium can grow a WebAssembly shared-memory buffer in place. In that
    case Emscripten's identity-only check misses that fixed-length HEAP views
    still have the old bounds. Preserve the identity check and also compare the
    current buffer byte length with the view byte length.
    """
    source = js_path.read_text(encoding="utf-8")
    refresh_anchor = (
        "function growMemViews(){if(wasmMemory.buffer!=HEAP8.buffer){"
        "updateMemoryViews()}}"
    )
    refresh_replacement = (
        "function growMemViews(){/*" + SHARED_MEMORY_VIEW_REFRESH_MARKER + "*/"
        "var b=wasmMemory.buffer;if(b!=HEAP8.buffer||b.byteLength!=HEAP8.byteLength){"
        "updateMemoryViews()}}"
    )
    guard_anchor = "if(HEAP8?.buffer?.growable)return;"
    guard_replacement = (
        "if(HEAP8?.buffer?.growable&&HEAP8.byteLength==getMemoryBuffer().byteLength){/*"
        + SHARED_MEMORY_GROWABLE_VIEW_GUARD_MARKER
        + "*/return}"
    )
    if (SHARED_MEMORY_VIEW_REFRESH_MARKER in source or
            SHARED_MEMORY_GROWABLE_VIEW_GUARD_MARKER in source):
        raise WasmError("shared-memory view refresh is already patched")
    refresh_before = source.count(refresh_anchor)
    guard_before = source.count(guard_anchor)
    source = replace_once(
        source, refresh_anchor, refresh_replacement, "shared-memory view refresh"
    )
    source = replace_once(
        source, guard_anchor, guard_replacement, "shared-memory growable-view guard"
    )
    if (source.count(SHARED_MEMORY_VIEW_REFRESH_MARKER) != 1 or
            source.count(SHARED_MEMORY_GROWABLE_VIEW_GUARD_MARKER) != 1 or
            source.count(refresh_replacement) != 1 or source.count(guard_replacement) != 1):
        raise WasmError("shared-memory view refresh patch is not unique")
    js_path.write_text(source, encoding="utf-8")
    return {
        "contract": "shared-memory-fixed-view-refresh-v2",
        "refresh_marker": SHARED_MEMORY_VIEW_REFRESH_MARKER,
        "guard_marker": SHARED_MEMORY_GROWABLE_VIEW_GUARD_MARKER,
        "refresh_anchor_count_before": refresh_before,
        "refresh_anchor_count_after": source.count(refresh_anchor),
        "refresh_marker_count_after": source.count(SHARED_MEMORY_VIEW_REFRESH_MARKER),
        "refresh_replacement_count_after": source.count(refresh_replacement),
        "guard_anchor_count_before": guard_before,
        "guard_anchor_count_after": source.count(guard_anchor),
        "guard_marker_count_after": source.count(SHARED_MEMORY_GROWABLE_VIEW_GUARD_MARKER),
        "guard_replacement_count_after": source.count(guard_replacement),
        "identity_predicate_count_after": source.count("b!=HEAP8.buffer"),
        "byte_length_predicate_count_after": source.count(
            "b.byteLength!=HEAP8.byteLength"
        ),
        "growable_length_guard_count_after": source.count(
            "HEAP8?.buffer?.growable&&HEAP8.byteLength==getMemoryBuffer().byteLength"
        ),
    }


def patch_pthread_memory_range_sync(js_path: Path) -> dict[str, object]:
    """Synchronize a pthread realm before dereferencing newly allocated metadata.

    A shared-memory grow performed by another realm can be visible to the
    allocator before this worker's ``wasmMemory.buffer`` getter exposes the
    larger wrapper.  Identity and byte-length comparisons therefore cannot
    make an indexed access safe by themselves.  ``wasmMemory.grow(0)`` is used
    as the non-allocating synchronization operation, followed by a bounded
    view refresh and an exact range check.
    """
    source = js_path.read_text(encoding="utf-8")
    grow_anchor = (
        "function growMemViews(){/*" + SHARED_MEMORY_VIEW_REFRESH_MARKER + "*/"
        "var b=wasmMemory.buffer;if(b!=HEAP8.buffer||b.byteLength!=HEAP8.byteLength){"
        "updateMemoryViews()}}"
    )
    helper = (
        "function bwSyncPthreadMemoryRange(ptr,end){/*"
        + PTHREAD_MEMORY_RANGE_SYNC_MARKER
        + "*/if(!Number.isSafeInteger(ptr)||ptr<0||(ptr&3)!=0||"
        "!Number.isSafeInteger(end)||end<0||end>2147483648)"
        "throw new RangeError(\"pthread memory range invalid\");"
        "growMemViews();for(var attempt=0;end>HEAPU8.byteLength&&attempt<3;attempt++){"
        "wasmMemory.grow(0);updateMemoryViews();growMemViews()}"
        "if(end>HEAPU8.byteLength)throw new RangeError("
        "\"pthread memory range uncovered\");return HEAP32}"
    )
    stack_anchor = (
        "function establishStackSpace(pthread_ptr){var stackHigh=(growMemViews(),HEAPU32)"
        "[pthread_ptr+48>>2];var stackSize=(growMemViews(),HEAPU32)[pthread_ptr+52>>2];"
        "var stackLow=stackHigh-stackSize;_emscripten_stack_set_limits(stackHigh,stackLow);"
        "stackRestore(stackHigh)}"
    )
    stack_replacement = (
        "function establishStackSpace(pthread_ptr){/*"
        + PTHREAD_STACK_RANGE_SYNC_MARKER
        + "*/bwSyncPthreadMemoryRange(pthread_ptr,pthread_ptr+116);"
        "var stackHigh=HEAPU32[pthread_ptr+48>>2];"
        "var stackSize=HEAPU32[pthread_ptr+52>>2];var stackLow=stackHigh-stackSize;"
        "if(!Number.isSafeInteger(stackHigh)||!Number.isSafeInteger(stackSize)||"
        "stackSize<=0||stackHigh<stackSize||stackLow<0)throw new RangeError("
        "\"pthread stack metadata invalid\");"
        "bwSyncPthreadMemoryRange(pthread_ptr,stackHigh);"
        "_emscripten_stack_set_limits(stackHigh,stackLow);stackRestore(stackHigh)}"
    )
    mailbox_anchor = (
        "var __emscripten_thread_mailbox_await=pthread_ptr=>{if(!waitAsyncPolyfilled){"
        "var wait=Atomics.waitAsync((growMemViews(),HEAP32),pthread_ptr>>2,pthread_ptr);"
        "wait.value.then(checkMailbox);var waitingAsync=pthread_ptr+112;"
        "Atomics.store((growMemViews(),HEAP32),waitingAsync>>2,1)}};var checkMailbox="
    )
    mailbox_replacement = (
        "var __emscripten_thread_mailbox_await=pthread_ptr=>{if(!waitAsyncPolyfilled){/*"
        + PTHREAD_MAILBOX_RANGE_SYNC_MARKER
        + "*/var heap32=bwSyncPthreadMemoryRange(pthread_ptr,pthread_ptr+116);"
        "var wait=Atomics.waitAsync(heap32,pthread_ptr>>2,pthread_ptr);"
        "wait.value.then(checkMailbox);var waitingAsync=pthread_ptr+112;"
        "Atomics.store(heap32,waitingAsync>>2,1)}};var checkMailbox="
    )
    for marker in (
        PTHREAD_MEMORY_RANGE_SYNC_MARKER,
        PTHREAD_STACK_RANGE_SYNC_MARKER,
        PTHREAD_MAILBOX_RANGE_SYNC_MARKER,
    ):
        if marker in source:
            raise WasmError("pthread memory range synchronization is already patched")
    helper_tail = "if(ENVIRONMENT_IS_NODE&&ENVIRONMENT_IS_PTHREAD)"
    helper_anchor = grow_anchor + helper_tail
    grow_before = source.count(helper_anchor)
    stack_before = source.count(stack_anchor)
    mailbox_before = source.count(mailbox_anchor)
    source = replace_once(
        source,
        helper_anchor,
        grow_anchor + helper + helper_tail,
        "pthread range-sync helper",
    )
    source = replace_once(source, stack_anchor, stack_replacement, "pthread stack range sync")
    source = replace_once(
        source, mailbox_anchor, mailbox_replacement, "pthread mailbox range sync"
    )
    if any(source.count(marker) != 1 for marker in (
        PTHREAD_MEMORY_RANGE_SYNC_MARKER,
        PTHREAD_STACK_RANGE_SYNC_MARKER,
        PTHREAD_MAILBOX_RANGE_SYNC_MARKER,
    )):
        raise WasmError("pthread memory range synchronization patch is not unique")
    js_path.write_text(source, encoding="utf-8")
    return {
        "contract": "pthread-cross-realm-memory-range-sync-v1",
        "helper_marker": PTHREAD_MEMORY_RANGE_SYNC_MARKER,
        "stack_marker": PTHREAD_STACK_RANGE_SYNC_MARKER,
        "mailbox_marker": PTHREAD_MAILBOX_RANGE_SYNC_MARKER,
        "helper_anchor_count_before": grow_before,
        "helper_anchor_count_after": source.count(helper_anchor),
        "helper_marker_count_after": source.count(PTHREAD_MEMORY_RANGE_SYNC_MARKER),
        "stack_anchor_count_before": stack_before,
        "stack_anchor_count_after": source.count(stack_anchor),
        "stack_marker_count_after": source.count(PTHREAD_STACK_RANGE_SYNC_MARKER),
        "mailbox_anchor_count_before": mailbox_before,
        "mailbox_anchor_count_after": source.count(mailbox_anchor),
        "mailbox_marker_count_after": source.count(PTHREAD_MAILBOX_RANGE_SYNC_MARKER),
        "grow_zero_count_after": source.count("wasmMemory.grow(0)"),
        "bounded_attempt_count": 3,
        "metadata_end_offset": 116,
        "stack_high_offset": 48,
        "stack_size_offset": 52,
    }


def patch_capture_probe_dispatch(js_path: Path) -> dict[str, object]:
    """Patch the Emscripten worker closure before cmd:2 thread entry.

    Post-js reassignment of handleMessage cannot affect startWorker's closed-over
    original function. CAPTURE therefore installs the probe ACK in that exact
    core dispatcher; this branch is excluded from APPLY shipping glue.
    """
    source = js_path.read_text(encoding="utf-8")
    anchor = "wasmModule=msgData.wasmModule;createWasm();run();startWorker()}else if(cmd==2){"
    anchor_count_before = source.count(anchor)
    replacement = (
        'wasmModule=msgData.wasmModule;createWasm();run();startWorker()'
        '}else if(cmd=="bwCaptureProbe"){/*'
        + CAPTURE_PROBE_CORE_DISPATCH_MARKER
        + '*/globalThis.__bwCaptureWorkerId=msgData.workerId;'
        'postMessage({cmd:"bwCaptureProbeAck",token:msgData.token,'
        'workerId:msgData.workerId})}else if(cmd==2){'
    )
    if CAPTURE_PROBE_CORE_DISPATCH_MARKER in source or 'cmd=="bwCaptureProbe"' in source:
        raise WasmError("CAPTURE pthread probe dispatch is already patched")
    source = replace_once(source, anchor, replacement, "CAPTURE pthread probe dispatch")
    if source.count(CAPTURE_PROBE_CORE_DISPATCH_MARKER) != 1:
        raise WasmError("CAPTURE pthread probe dispatch marker is not unique")
    js_path.write_text(source, encoding="utf-8")
    core_count = source.count(replacement)
    # The exact core branch contains the same minified ACK object spelling as
    # the post-js worker handler. Mask the independently-validated core branch
    # before counting the post-js seam so the receipt cannot conflate them.
    postjs_source = source.replace(replacement, "", 1) if core_count == 1 else source
    return {
        "contract": "capture-worker-core-probe-ack-v1",
        "marker": CAPTURE_PROBE_CORE_DISPATCH_MARKER,
        "anchor": anchor,
        "anchor_count_before": anchor_count_before,
        "anchor_count_after": source.count(anchor),
        "marker_count_after": source.count(CAPTURE_PROBE_CORE_DISPATCH_MARKER),
        "probe_branch_count_after": source.count('cmd=="bwCaptureProbe"'),
        "core_branch_count_after": core_count,
        "postjs_probe_handler_count_after": source.count(
            'if (message?.cmd === "bwCaptureProbe")') + source.count(
            'if(message?.cmd==="bwCaptureProbe")'),
        "postjs_outgoing_ack_count_after": postjs_source.count(
            'cmd: "bwCaptureProbeAck"') + postjs_source.count('cmd:"bwCaptureProbeAck"'),
        "main_ack_listener_count_after": source.count(
            'if (message?.cmd === "bwCaptureProbeAck")') + source.count(
            'if(message?.cmd==="bwCaptureProbeAck")'),
        "source": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256(Path(__file__).resolve()),
        },
    }


def patch_capture_atomic_diagnostics(js_path: Path) -> dict[str, object]:
    """Tag the two JS mailbox Atomics used when a pthread becomes live.

    This is CAPTURE-only diagnostic glue. It preserves the original operations
    and rethrows, but reports the exact pointer/index/view/memory facts first so
    an APPLY-transition failure cannot collapse to Chromium's generic
    ``Invalid atomic access index`` message.
    """
    source = js_path.read_text(encoding="utf-8")
    marker = "BW_SPLIT_CAPTURE_ATOMIC_DIAG_V1"
    anchor = (
        "var __emscripten_thread_mailbox_await=pthread_ptr=>{if(!waitAsyncPolyfilled){/*"
        + PTHREAD_MAILBOX_RANGE_SYNC_MARKER
        + "*/var heap32=bwSyncPthreadMemoryRange(pthread_ptr,pthread_ptr+116);"
        "var wait=Atomics.waitAsync(heap32,pthread_ptr>>2,pthread_ptr);"
        "wait.value.then(checkMailbox);var waitingAsync=pthread_ptr+112;"
        "Atomics.store(heap32,waitingAsync>>2,1)}};var checkMailbox="
    )
    replacement = (
        "var __emscripten_thread_mailbox_await=pthread_ptr=>{if(!waitAsyncPolyfilled){/*"
        + PTHREAD_MAILBOX_RANGE_SYNC_MARKER
        + "*/"
        "var bwCaptureAtomicMarker=\"" + marker + "\";"
        "var bwCaptureSelf=null;try{bwCaptureSelf=typeof _pthread_self==\"function\"?"
        "_pthread_self():null}catch(_){}"
        "var bwCaptureAtomicFail=(op,index,error)=>{var detail={marker:bwCaptureAtomicMarker,"
        "op:op,pthreadPtr:pthread_ptr,index:index,waitIndex:pthread_ptr>>2,"
        "storeIndex:(pthread_ptr+112)>>2,aligned:(pthread_ptr&3)==0,"
        "safeInteger:Number.isSafeInteger(pthread_ptr),waitInRange:(pthread_ptr>>2)>=0&&"
        "(pthread_ptr>>2)<HEAP32.length,storeInRange:((pthread_ptr+112)>>2)>=0&&"
        "((pthread_ptr+112)>>2)<HEAP32.length,heap32Length:HEAP32.length,"
        "heap8Bytes:typeof HEAP8==\"undefined\"?null:HEAP8.byteLength,"
        "heapU8Bytes:typeof HEAPU8==\"undefined\"?null:HEAPU8.byteLength,"
        "heap16Bytes:typeof HEAP16==\"undefined\"?null:HEAP16.byteLength,"
        "heapU16Bytes:typeof HEAPU16==\"undefined\"?null:HEAPU16.byteLength,"
        "heap32Bytes:typeof HEAP32==\"undefined\"?null:HEAP32.byteLength,"
        "heapU32Bytes:typeof HEAPU32==\"undefined\"?null:HEAPU32.byteLength,"
        "heapF32Bytes:typeof HEAPF32==\"undefined\"?null:HEAPF32.byteLength,"
        "heapF64Bytes:typeof HEAPF64==\"undefined\"?null:HEAPF64.byteLength,"
        "heap64Bytes:typeof HEAP64==\"undefined\"?null:HEAP64.byteLength,"
        "heapU64Bytes:typeof HEAPU64==\"undefined\"?null:HEAPU64.byteLength,"
        "heap8BufferBytes:HEAP8.buffer.byteLength,"
        "heap8BufferGrowable:HEAP8.buffer.growable??null,heap8BufferMaxBytes:"
        "HEAP8.buffer.maxByteLength??null,heap8BufferIsMemory:"
        "HEAP8.buffer===wasmMemory.buffer,heap8BufferShared:"
        "HEAP8.buffer instanceof SharedArrayBuffer,memoryBufferShared:"
        "wasmMemory.buffer instanceof SharedArrayBuffer,"
        "memoryBytes:wasmMemory.buffer.byteLength,memoryGrowable:"
        "typeof wasmMemory.grow==\"function\",bufferGrowable:"
        "wasmMemory.buffer.growable??null,memoryMaxBytes:"
        "wasmMemory.buffer.maxByteLength??null,selfPtr:bwCaptureSelf,messageParams:"
        "globalThis.__bwCaptureThreadParams??null,stages:"
        "(globalThis.__bwCaptureThreadEntryStages||[]).slice(),workerId:"
        "globalThis.__bwCaptureWorkerId??null,realm:ENVIRONMENT_IS_PTHREAD?\"pthread\":\"page\","
        "message:String(error&&error.message||error),stack:String(error&&error.stack||error)};"
        "try{postMessage({cmd:\"bwCaptureAtomicError\",detail:detail})}catch(_){}"
        "throw new RangeError(bwCaptureAtomicMarker+\" \"+JSON.stringify(detail),{cause:error})};"
        "var waitIndex=pthread_ptr>>2;var heap32;try{heap32="
        "bwSyncPthreadMemoryRange(pthread_ptr,pthread_ptr+116)}catch(error){"
        "bwCaptureAtomicFail(\"rangeSync\",waitIndex,error)}var wait;try{wait=Atomics.waitAsync("
        "heap32,waitIndex,pthread_ptr)}catch(error){"
        "bwCaptureAtomicFail(\"waitAsync\",waitIndex,error)}wait.value.then(checkMailbox);"
        "var waitingAsync=pthread_ptr+112;var storeIndex=waitingAsync>>2;try{"
        "Atomics.store(heap32,storeIndex,1)}catch(error){"
        "bwCaptureAtomicFail(\"store\",storeIndex,error)}}};var checkMailbox="
    )
    if marker in source:
        raise WasmError("CAPTURE atomic diagnostics are already patched")
    before = source.count(anchor)
    source = replace_once(source, anchor, replacement, "CAPTURE atomic diagnostics")
    js_path.write_text(source, encoding="utf-8")
    return {
        "contract": "capture-mailbox-atomic-diagnostics-v1",
        "marker": marker,
        "anchor_count_before": before,
        "anchor_count_after": source.count(anchor),
        "marker_count_after": source.count(marker),
        "wait_tag_count_after": source.count('bwCaptureAtomicFail(\"waitAsync\"'),
        "store_tag_count_after": source.count('bwCaptureAtomicFail(\"store\"'),
        "range_sync_tag_count_after": source.count('bwCaptureAtomicFail(\"rangeSync\"'),
        "listener_count_after": source.count(
            'if (message?.cmd === "bwCaptureAtomicError")') + source.count(
            'if(message?.cmd==="bwCaptureAtomicError")'),
    }


def patch_capture_thread_entry_diagnostics(js_path: Path) -> dict[str, object]:
    """Report the exact pthread stack/routine facts before rethrowing an entry trap.

    The CAPTURE scheduler transition deliberately creates dependency workers only
    after PREPARED.  A generic ``memory access out of bounds`` from
    ``invokeEntryPoint`` otherwise loses the pthread stack allocation and start
    routine that distinguish an invalid stack from a failing worker body.
    """
    source = js_path.read_text(encoding="utf-8")
    marker = CAPTURE_THREAD_ENTRY_DIAG_MARKER
    entry_anchor = (
        "var invokeEntryPoint=(ptr,arg)=>{runtimeKeepaliveCounter=0;noExitRuntime=0;"
        "var result=getWasmTableEntry(ptr)(arg);function finish(result){"
    )
    entry_replacement = (
        "var invokeEntryPoint=(ptr,arg)=>{runtimeKeepaliveCounter=0;noExitRuntime=0;"
        "var bwEntryPthread=null;try{bwEntryPthread=typeof _pthread_self==\"function\"?"
        "_pthread_self():null}catch(_){}growMemViews();"
        "var bwEntrySelfSafe=Number.isSafeInteger(bwEntryPthread)&&bwEntryPthread>=0;"
        "var bwEntrySelfMetadataInRange=bwEntrySelfSafe&&(bwEntryPthread&3)==0&&"
        "bwEntryPthread+56<=HEAPU8.byteLength;"
        "var bwEntryStackHigh=bwEntrySelfMetadataInRange?HEAPU32[bwEntryPthread+48>>2]:null;"
        "var bwEntryStackSize=bwEntrySelfMetadataInRange?HEAPU32[bwEntryPthread+52>>2]:null;"
        "var bwEntryStackCurrent=stackSave();var bwEntryTable=null;var bwEntryTableName=null;"
        "var result;try{bwEntryTable=getWasmTableEntry(ptr);bwEntryTableName=typeof "
        "bwEntryTable.name==\"string" "\"&&bwEntryTable.name?bwEntryTable.name:null;"
        "result=bwEntryTable(arg)}"
        "catch(error){var messageParams=globalThis.__bwCaptureThreadParams||null;"
        "var detail={marker:\"" + marker + "\",startRoutine:ptr,arg:arg,"
        "pthreadPtr:bwEntryPthread,stackCurrent:bwEntryStackCurrent,stackHigh:bwEntryStackHigh,"
        "stackSize:bwEntryStackSize,stackLow:bwEntryStackHigh===null||bwEntryStackSize===null?"
        "null:bwEntryStackHigh-bwEntryStackSize,selfMetadataInRange:bwEntrySelfMetadataInRange,"
        "messageParams:messageParams,messagePthreadMatchesSelf:messageParams!==null&&"
        "messageParams.pthreadPtr===bwEntryPthread,messageRoutineMatchesInvoke:messageParams!==null&&"
        "messageParams.startRoutine===ptr,messageArgMatchesInvoke:messageParams!==null&&"
        "messageParams.arg===arg,stackCurrentMatchesMessageHigh:messageParams!==null&&"
        "messageParams.stackHigh!==null&&bwEntryStackCurrent===messageParams.stackHigh,"
        "stackCurrentMatchesSelfHigh:bwEntryStackHigh!==null&&bwEntryStackCurrent===bwEntryStackHigh,"
        "tableEntryName:bwEntryTableName,stackCurrentInMemory:bwEntryStackCurrent>=16&&"
        "bwEntryStackCurrent<=wasmMemory.buffer.byteLength,stackHighInMemory:"
        "bwEntryStackHigh!==null&&bwEntryStackHigh>=16&&bwEntryStackHigh<="
        "wasmMemory.buffer.byteLength,messageStackHighInMemory:messageParams!==null&&"
        "messageParams.stackHigh!==null&&messageParams.stackHigh>=16&&messageParams.stackHigh<="
        "wasmMemory.buffer.byteLength,heap8Bytes:HEAP8.byteLength,heap32Length:HEAP32.length,"
        "memoryBytes:wasmMemory.buffer.byteLength,workerId:globalThis.__bwCaptureWorkerId??null,"
        "realm:ENVIRONMENT_IS_PTHREAD?\"pthread\":\"page\",message:String(error&&error.message||error),"
        "stages:(globalThis.__bwCaptureThreadEntryStages||[]).slice(),"
        "stack:String(error&&error.stack||error)};try{postMessage({cmd:"
        "\"bwCaptureThreadEntryError\",detail:detail})}catch(_){}throw error}function finish(result){"
    )
    stage_marker = CAPTURE_THREAD_ENTRY_STAGE_MARKER
    stage_anchor = (
        "}else if(cmd==2){establishStackSpace(msgData.pthread_ptr);"
        "__emscripten_thread_init(msgData.pthread_ptr,0,0,1,0,0);"
        "PThread.receiveOffscreenCanvases(msgData);PThread.threadInitTLS();"
        "__emscripten_thread_mailbox_await(msgData.pthread_ptr);if(!initializedJS){"
        "initializedJS=true}try{invokeEntryPoint(msgData.start_routine,msgData.arg)}"
    )
    stage_replacement = (
        '}else if(cmd==2){/*' + stage_marker + '*/globalThis.__bwCaptureThreadEntryStages=[];'
        'var bwMsgPtr=Number(msgData.pthread_ptr);'
        'bwSyncPthreadMemoryRange(bwMsgPtr,bwMsgPtr+116);'
        'var bwMsgPtrSafe=Number.isSafeInteger(bwMsgPtr)&&bwMsgPtr>=0;'
        'var bwMsgMetadataInRange=bwMsgPtrSafe&&(bwMsgPtr&3)==0&&bwMsgPtr+56<=HEAPU8.byteLength;'
        'var bwMsgStackHigh=bwMsgMetadataInRange?HEAPU32[bwMsgPtr+48>>2]:null;'
        'var bwMsgStackSize=bwMsgMetadataInRange?HEAPU32[bwMsgPtr+52>>2]:null;'
        'globalThis.__bwCaptureThreadParams={pthreadPtr:bwMsgPtr,startRoutine:'
        'Number(msgData.start_routine),arg:Number(msgData.arg),pointerSafe:bwMsgPtrSafe,'
        'pointerAligned:bwMsgPtrSafe&&(bwMsgPtr&3)==0,metadataInRange:bwMsgMetadataInRange,'
        'stackHigh:bwMsgStackHigh,stackSize:bwMsgStackSize,stackLow:'
        'bwMsgStackHigh===null||bwMsgStackSize===null?null:bwMsgStackHigh-bwMsgStackSize,'
        'memoryBytes:wasmMemory.buffer.byteLength,heap8Bytes:HEAP8.byteLength,'
        'heap32Length:HEAP32.length};'
        'var bwCaptureEntryStage=stage=>{growMemViews();var params=globalThis.__bwCaptureThreadParams;'
        'var metadataInRange=params.pointerSafe&&params.pointerAligned&&'
        'params.pthreadPtr+56<=HEAPU8.byteLength;var stackHigh=metadataInRange?'
        'HEAPU32[params.pthreadPtr+48>>2]:null;var stackSize=metadataInRange?'
        'HEAPU32[params.pthreadPtr+52>>2]:null;globalThis.__bwCaptureThreadEntryStages.push('
        '{stage:stage,pthreadPtr:params.pthreadPtr,startRoutine:params.startRoutine,arg:params.arg,'
        'metadataInRange:metadataInRange,stackCurrent:stackSave(),stackHigh:stackHigh,'
        'stackSize:stackSize,stackLow:stackHigh===null||stackSize===null?null:stackHigh-stackSize,'
        'memoryBytes:wasmMemory.buffer.byteLength,heap8Bytes:HEAP8.byteLength})};'
        'bwCaptureEntryStage("before-establish");establishStackSpace(msgData.pthread_ptr);'
        'bwCaptureEntryStage("after-establish");'
        '__emscripten_thread_init(msgData.pthread_ptr,0,0,1,0,0);'
        'bwCaptureEntryStage("after-thread-init");PThread.receiveOffscreenCanvases(msgData);'
        'PThread.threadInitTLS();bwCaptureEntryStage("after-tls");'
        '__emscripten_thread_mailbox_await(msgData.pthread_ptr);'
        'bwCaptureEntryStage("before-entry");if(!initializedJS){initializedJS=true}'
        'try{invokeEntryPoint(msgData.start_routine,msgData.arg)}'
    )
    main_marker = CAPTURE_MAIN_DIAGNOSTIC_DISPATCH_MARKER
    main_anchor = (
        'case 9:Module[d.handler](...d.args);break;default:if(cmd)err('
        '`worker sent an unknown command ${cmd}`)}};worker.onerror='
    )
    main_replacement = (
        'case 9:Module[d.handler](...d.args);break;'
        'case "bwCaptureAtomicError":{/*' + main_marker + '*/'
        'var bwAtomicDetail=Object.assign({},d.detail,{captureWorkerId:'
        'worker.__bwCaptureId??null});(globalThis.__bwCaptureAtomicDiagnostics??=[]).push('
        'bwAtomicDetail);err(`BW_SPLIT_CAPTURE_ATOMIC ${JSON.stringify(bwAtomicDetail)}`);break}'
        'case "bwCaptureThreadEntryError":{var bwEntryDetail=Object.assign({},d.detail,'
        '{captureWorkerId:worker.__bwCaptureId??null});'
        '(globalThis.__bwCaptureThreadEntryDiagnostics??=[]).push(bwEntryDetail);'
        'err(`BW_SPLIT_CAPTURE_THREAD_ENTRY ${JSON.stringify(bwEntryDetail)}`);break}'
        'default:if(cmd)err(`worker sent an unknown command ${cmd}`)}};worker.onerror='
    )
    if (marker in source or stage_marker in source or main_marker in source or
            'cmd:"bwCaptureThreadEntryError"' in source):
        raise WasmError("CAPTURE thread-entry diagnostics are already patched")
    entry_before = source.count(entry_anchor)
    stage_before = source.count(stage_anchor)
    main_before = source.count(main_anchor)
    source = replace_once(source, entry_anchor, entry_replacement, "CAPTURE entry trap diagnostics")
    source = replace_once(source, stage_anchor, stage_replacement, "CAPTURE entry stage diagnostics")
    source = replace_once(
        source, main_anchor, main_replacement, "CAPTURE page-main diagnostic dispatch"
    )
    marker_count = source.count(marker)
    stage_marker_count = source.count(stage_marker)
    post_count = source.count('cmd:"bwCaptureThreadEntryError"')
    listener_count = source.count(
        'if (message?.cmd === "bwCaptureThreadEntryError")'
    ) + source.count('if(message?.cmd==="bwCaptureThreadEntryError")')
    main_marker_count = source.count(main_marker)
    main_atomic_case_count = source.count('case "bwCaptureAtomicError"')
    main_entry_case_count = source.count('case "bwCaptureThreadEntryError"')
    if (marker_count != 1 or stage_marker_count != 1 or post_count != 1 or
            listener_count != 1 or main_marker_count != 1 or
            main_atomic_case_count != 1 or main_entry_case_count != 1):
        raise WasmError(
            "CAPTURE thread-entry diagnostic contract mismatch: "
            f"marker={marker_count} stage_marker={stage_marker_count} "
            f"post={post_count} listener={listener_count} main_marker={main_marker_count} "
            f"main_atomic={main_atomic_case_count} main_entry={main_entry_case_count}"
        )
    js_path.write_text(source, encoding="utf-8")
    return {
        "contract": "capture-pthread-entry-stack-diagnostics-v1",
        "marker": marker,
        "entry_anchor_count_before": entry_before,
        "entry_anchor_count_after": source.count(entry_anchor),
        "marker_count_after": marker_count,
        "stage_marker": stage_marker,
        "stage_anchor_count_before": stage_before,
        "stage_anchor_count_after": source.count(stage_anchor),
        "stage_marker_count_after": stage_marker_count,
        "stage_count_after": source.count('bwCaptureEntryStage("'),
        "main_dispatch_marker": main_marker,
        "main_dispatch_anchor_count_before": main_before,
        "main_dispatch_anchor_count_after": source.count(main_anchor),
        "main_dispatch_marker_count_after": main_marker_count,
        "main_atomic_case_count_after": main_atomic_case_count,
        "main_entry_case_count_after": main_entry_case_count,
        "post_count_after": post_count,
        "listener_count_after": listener_count,
        "stack_high_offset": 48,
        "stack_size_offset": 52,
    }


def patch_single_flight_runtime(js_path: Path, secondary_path: Path) -> dict[str, object]:
    """Bind the APPLY shard identity and remove stock synchronous lazy loading.

    Existing pool workers use the post-js bwSplitInstall command. Workers created
    after preload receive a distinct FIFO-ordered bwSplitInitialInstall message
    after cmd1 and before getNewWorker() can post cmd2. The generated core drains
    that install before the queued thread entry.
    """
    if not SINGLE_FLIGHT_SOURCE.is_file():
        raise WasmError(f"single-flight source missing: {SINGLE_FLIGHT_SOURCE}")
    runtime_source = SINGLE_FLIGHT_SOURCE.read_text(encoding="utf-8")
    if 'cache: "no-store"' in runtime_source or "cache: 'no-store'" in runtime_source:
        raise WasmError("single-flight shard request must remain service-worker cacheable")
    source = js_path.read_text(encoding="utf-8")
    if source.count(SINGLE_FLIGHT_RUNTIME_MARKER) != 1:
        raise WasmError(
            f"shipping JS must contain one {SINGLE_FLIGHT_RUNTIME_MARKER}; "
            f"found {source.count(SINGLE_FLIGHT_RUNTIME_MARKER)}"
        )
    source = replace_once(
        source,
        "var loadSplitModule=instantiateSync;",
        "var loadSplitModule=function(){throw new Error(\""
        + SINGLE_FLIGHT_LOADER_MARKER
        + ": deferred module is not preloaded\")};",
        "stock split loader initializer",
    )
    source = replace_once(
        source,
        "}else if(cmd==2){",
        "}else if(cmd==\"bwSplitInitialInstall\"){/*"
        + SINGLE_FLIGHT_INITIAL_DISPATCH_MARKER
        + "*/if(!bwSplitProcessWorkerInstall(msgData.module,msgData.generation,"
        "msgData.workerId,\"initial-before-start\")){throw new Error("
        "\"BW split FIFO initial install rejected\")}}else if(cmd==\"bwSplitInstall\"){/*"
        + SINGLE_FLIGHT_CORE_DISPATCH_MARKER
        + "*/bwSplitProcessWorkerInstall(msgData.module,msgData.generation,"
        "msgData.workerId,\"command\")}else if(cmd==2){",
        "pthread worker core dispatch",
    )
    replacements = {
        SECONDARY_FILENAME_SENTINEL: secondary_path.name,
        SECONDARY_BYTES_SENTINEL: str(secondary_path.stat().st_size),
        SECONDARY_SHA256_SENTINEL: sha256(secondary_path),
    }
    for sentinel, value in replacements.items():
        source = replace_once(source, sentinel, value, f"single-flight identity {sentinel}")
    if "var loadSplitModule=instantiateSync;" in source:
        raise WasmError("stock synchronous split loader remains reachable")
    required_markers = [
        SINGLE_FLIGHT_RUNTIME_MARKER,
        SINGLE_FLIGHT_LOADER_MARKER,
        SINGLE_FLIGHT_INITIAL_DISPATCH_MARKER,
        SINGLE_FLIGHT_CORE_DISPATCH_MARKER,
        "bwPrepareSplitSecondary",
        "bwSplitInstall",
        "bwSplitReady",
        "BW_SPLIT_SW_CACHEABLE_REQUEST_V1",
        "BW_SPLIT_CONTENT_ADDRESSED_URL_V1",
    ]
    missing = [marker for marker in required_markers if marker not in source]
    if missing:
        raise WasmError(f"single-flight generated markers missing: {missing}")
    if source.count(SINGLE_FLIGHT_CORE_DISPATCH_MARKER) != 1:
        raise WasmError("single-flight worker core dispatch marker is not unique")
    if source.count(SINGLE_FLIGHT_INITIAL_DISPATCH_MARKER) != 1:
        raise WasmError("single-flight FIFO initial dispatch marker is not unique")
    old_piggyback = (
        "bwSplitSecondaryModule,bwSplitGeneration,bwSplitWorkerId",
        "msgData.bwSplitSecondaryModule",
        "msgData.bwSplitGeneration",
        "msgData.bwSplitWorkerId",
    )
    if any(marker in source for marker in old_piggyback):
        raise WasmError("single-flight cmd1 secondary-module piggyback remains")
    js_path.write_text(source, encoding="utf-8")
    return {
        "contract": "page-single-fetch-compile-pthread-module-fanout-v1",
        "runtime_marker": SINGLE_FLIGHT_RUNTIME_MARKER,
        "loader_marker": SINGLE_FLIGHT_LOADER_MARKER,
        "worker_initial_install_marker": SINGLE_FLIGHT_INITIAL_DISPATCH_MARKER,
        "worker_core_dispatch_marker": SINGLE_FLIGHT_CORE_DISPATCH_MARKER,
        "initial_install_post_count": (
            source.count('cmd:"bwSplitInitialInstall"')
            + source.count('cmd: "bwSplitInitialInstall"')
        ),
        "initial_install_dispatch_count": source.count(SINGLE_FLIGHT_INITIAL_DISPATCH_MARKER),
        "cmd1_secondary_piggyback_absent": True,
        "source": {
            "path": str(SINGLE_FLIGHT_SOURCE),
            "bytes": SINGLE_FLIGHT_SOURCE.stat().st_size,
            "sha256": sha256(SINGLE_FLIGHT_SOURCE),
        },
        "secondary_identity": {
            "filename": secondary_path.name,
            "bytes": secondary_path.stat().st_size,
            "sha256": sha256(secondary_path),
        },
        "page_fetches": 1,
        "page_compiles": 1,
        "page_instances_max": 1,
        "worker_instances_max_each": 1,
        "pool_ack_count_minimum": 8,
        "ack_policy": "all-unique-current-workers-and-every-late-worker",
        "late_worker_delivery": "fifo-initial-install-before-thread-entry",
        "sync_lazy_loader": "disabled-fail-closed",
        "request_cache_policy": "normal-same-origin-service-worker-compatible",
        "request_url_suffix": secondary_path.name + "?sha256=" + sha256(secondary_path),
    }


def run(command: list[str]) -> str:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode:
        raise WasmError(
            "command failed: " + " ".join(command) + "\n" + completed.stdout + completed.stderr
        )
    return completed.stdout + completed.stderr


def verify_link_stack_policy(command: str) -> dict[str, object]:
    """Parse every Emscripten stack-setting token and require the shipping effective pair."""

    expected = {
        "STACK_SIZE": 33554432,
        "DEFAULT_PTHREAD_STACK_SIZE": 8388608,
    }
    occurrences: dict[str, list[int]] = {name: [] for name in expected}
    tokens = shlex.split(command)
    index = 0
    while index < len(tokens):
        token = tokens[index]
        setting = None
        if token == "-s":
            index += 1
            if index >= len(tokens):
                raise WasmError("link command ends with an incomplete -s setting")
            setting = tokens[index]
        elif token.startswith("-s"):
            setting = token[2:]
        if setting is not None:
            for name in expected:
                prefix = name + "="
                if setting.startswith(prefix):
                    raw_value = setting[len(prefix):]
                    if not re.fullmatch(r"[0-9]+", raw_value):
                        raise WasmError(f"link stack setting {name} is not an exact byte count: {raw_value!r}")
                    occurrences[name].append(int(raw_value, 10))
                    break
        index += 1

    for name, expected_value in expected.items():
        values = occurrences[name]
        if not values:
            raise WasmError(f"link command is missing -s{name}")
        if values[-1] != expected_value:
            raise WasmError(
                f"effective -s{name} is {values[-1]}, expected {expected_value}; occurrences={values}"
            )
    return {
        "contract": "proxy-main-32m-ordinary-pthread-8m-v1",
        "stack_size_occurrences": occurrences["STACK_SIZE"],
        "default_pthread_stack_size_occurrences": occurrences[
            "DEFAULT_PTHREAD_STACK_SIZE"
        ],
        "effective_stack_size": occurrences["STACK_SIZE"][-1],
        "effective_default_pthread_stack_size": occurrences[
            "DEFAULT_PTHREAD_STACK_SIZE"
        ][-1],
    }


def verify_link_command(args: argparse.Namespace) -> dict[str, object]:
    output = run(
        [str(args.ninja), "-C", str(args.build_dir), "-t", "commands", args.target]
    )
    required = ("-sSPLIT_MODULE=1", f"-sGLOBAL_BASE={args.reserve}")
    candidates = [
        line
        for line in output.splitlines()
        if args.wasm.name.replace(".wasm", ".js") in line and all(flag in line for flag in required)
    ]
    if len(candidates) != 1:
        raise WasmError(
            f"Ninja graph has {len(candidates)} browser links with required flags {required}"
        )
    command = candidates[0]
    stack_policy = verify_link_stack_policy(command)
    has_profile_post_js = "profile-export.js" in command
    has_single_flight_post_js = "single-flight.js" in command
    if args.mode == "capture" and not has_profile_post_js:
        raise WasmError("capture link command is missing profile-export.js")
    if args.mode == "capture" and str(PROFILE_EXPORT_SOURCE) not in command:
        raise WasmError("capture link command does not bind the exact profile-export.js path")
    if args.mode == "apply" and has_profile_post_js:
        raise WasmError("shipping apply link command still includes profile-export.js")
    if args.mode == "capture" and has_single_flight_post_js:
        raise WasmError("capture link command unexpectedly includes shipping single-flight runtime")
    if args.mode == "apply" and not has_single_flight_post_js:
        raise WasmError("shipping apply link command is missing single-flight.js")
    return {
        "sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "bytes": len(command.encode("utf-8")),
        "required_flags": list(required),
        "profile_post_js": has_profile_post_js,
        "single_flight_post_js": has_single_flight_post_js,
        "stack_policy": stack_policy,
        "ninja_target": args.target,
    }


def write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def exact_wasm_outputs(wasm_path: Path, expected: set[Path]) -> list[Path]:
    actual = {
        path.resolve()
        for path in wasm_path.parent.glob(wasm_path.stem + "*.wasm*")
        if path.is_file()
    }
    resolved_expected = {path.resolve() for path in expected}
    if actual != resolved_expected:
        missing = sorted(str(path) for path in resolved_expected - actual)
        unlisted = sorted(str(path) for path in actual - resolved_expected)
        raise WasmError(f"wasm output inventory mismatch: missing={missing} unlisted={unlisted}")
    return sorted(actual)


def verify_primary_controller_closure_source(
    source: str, controller_exports: list[str] | None = None
) -> dict[str, object]:
    """Prove every direct/return-call path from controller exports stays primary.

    Binaryen gives placeholder imports stable function identifiers in WAT. We
    parse balanced function forms, traverse all direct calls, require every
    target to be a body or explicitly classified import, and conservatively
    reject indirect/ref calls because their target closure is not enumerable.
    """
    selected_exports = controller_exports or SPLIT_CONTROLLER_EXPORTS
    exports = dict(re.findall(r'\(export\s+"([^"]+)"\s+\(func\s+(\$[^\s\)]+)\)\)', source))
    imports = set(
        re.findall(r'\(import\s+"[^"]+"\s+"[^"]+"\s+\(func\s+(\$[^\s\)]+)', source)
    )
    placeholder_imports = set(
        re.findall(r'\(import\s+"placeholder[^"]*"\s+"[^"]+"\s+\(func\s+(\$[^\s\)]+)', source)
    )
    starts = {name: exports.get(name) for name in selected_exports}
    missing = sorted(name for name, function in starts.items() if function is None)
    if missing:
        raise WasmError(f"controller exports absent from primary WAT: {missing}")

    bodies: dict[str, str] = {}
    cursor = 0
    marker = re.compile(r"\(func\s+(\$[^\s\)]+)")
    while match := marker.search(source, cursor):
        depth = 0
        end = match.start()
        in_string = False
        escaped = False
        for end in range(match.start(), len(source)):
            char = source[end]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end += 1
                    break
        body = source[match.start():end]
        if len(body) > len(bodies.get(match.group(1), "")):
            bodies[match.group(1)] = body
        cursor = end
    for imported in imports:
        bodies.pop(imported, None)

    edges = {
        function: set(re.findall(r"\((?:call|return_call)\s+(\$[^\s\)]+)", body))
        for function, body in bodies.items()
    }
    reachable: set[str] = set(starts.values())
    pending = list(reachable)
    while pending:
        function = pending.pop()
        body = bodies.get(function)
        if body is None:
            if function in imports and function not in placeholder_imports:
                raise WasmError(f"controller closure reaches non-allowlisted host import {function}")
            raise WasmError(f"controller closure reaches unclassified target {function}")
        forbidden = re.search(
            r"\((?:call_indirect|return_call_indirect|call_ref|return_call_ref|table\.(?:set|grow|fill|copy|init)|elem\.drop)\b",
            body,
        )
        if forbidden:
            raise WasmError(
                f"controller closure reaches {forbidden.group(0)[1:]} in {function}"
            )
        if re.search(r"\(ref\.func\b", body):
            raise WasmError(f"controller closure reaches ref.func in {function}")
        for target in edges.get(function, set()):
            if target in placeholder_imports:
                raise WasmError(f"controller closure reaches deferred placeholder {target}")
            if target not in bodies and target not in imports:
                raise WasmError(f"controller closure reaches missing target {target}")
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    return {
        "contract": "transitive-direct-call-closure-no-placeholder-v1",
        "controller_exports": starts,
        "reachable_primary_function_count": len(reachable),
        "reachable_placeholder_imports": [],
        "reachable_indirect_or_ref_calls": [],
        "placeholder_import_count": len(placeholder_imports),
        "verdict": "PASS",
    }


def tool_receipt(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise WasmError(f"required Binaryen tool missing: {path}")
    version = run([str(path), "--version"]).strip()
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256(path),
            "version": version}


def verify_primary_controller_closure(
    primary: Path, wasm_opt: Path, wasm_dis: Path, controller_exports: list[str] | None = None
) -> dict[str, object]:
    """Auth-grade index closure proof without materializing the multi-GB WAT."""
    layout = wasm_function_layout(primary)
    imported_count = int(layout["imported_function_count"])
    imports = layout["function_imports"]
    exports = layout["function_exports"]
    selected_exports = controller_exports or SPLIT_CONTROLLER_EXPORTS
    missing = sorted(set(selected_exports) - set(exports))
    if missing:
        raise WasmError(f"controller exports absent from primary: {missing}")
    root_indices = {name: int(exports[name]) for name in selected_exports}
    if any(value < imported_count for value in root_indices.values()):
        raise WasmError("controller export resolves to an imported function")
    roots = {name: str(value - imported_count) for name, value in root_indices.items()}
    placeholder_nodes = {
        f"fimport${row['index']}" for row in imports
        if str(row["module"]).startswith("placeholder")
    }
    opt = tool_receipt(wasm_opt)
    dis = tool_receipt(wasm_dis)
    graph_command = [str(wasm_opt), "--all-features", str(primary), "--print-call-graph"]
    graph = run(graph_command)
    edges: dict[str, set[str]] = {}
    for source, target in re.findall(r'^\s*"([^"]+)"\s*->\s*"([^"]+)";', graph, re.MULTILINE):
        edges.setdefault(source, set()).add(target)
    defined_nodes = set(re.findall(r'^\s*"(\d+)"\s*\[', graph, re.MULTILINE))
    expected_defined = int(layout["defined_function_count"])
    if len(defined_nodes) != expected_defined:
        raise WasmError(
            f"call graph defined-node population {len(defined_nodes)} != {expected_defined}"
        )
    reachable = set(roots.values())
    parent: dict[str, str] = {}
    pending = list(reachable)
    while pending:
        function = pending.pop(0)
        for target in edges.get(function, set()):
            if target not in reachable:
                parent[target] = function
                reachable.add(target)
                pending.append(target)
    hit = sorted(reachable & placeholder_nodes)
    if hit:
        path = [hit[0]]
        while path[-1] in parent:
            path.append(parent[path[-1]])
        raise WasmError(f"controller call graph reaches deferred placeholder: {list(reversed(path))}")
    unresolved = sorted(
        node for node in reachable
        if not (node.isdigit() or re.fullmatch(r"fimport\$\d+", node))
    )
    if unresolved:
        raise WasmError(f"controller call graph has unresolved nodes: {unresolved}")
    missing_defined = sorted(node for node in reachable if node.isdigit() and node not in defined_nodes)
    if missing_defined:
        raise WasmError(f"controller call graph omitted visited defined nodes: {missing_defined}")
    # The controller is C++ and may call only statically closed primary code.
    # Any reachable host import could trampoline through the table, so reject it
    # rather than maintaining an unverifiable broad allowlist.
    reachable_host_imports = sorted(
        node for node in reachable if node.startswith("fimport$") and node not in placeholder_nodes
    )
    if reachable_host_imports:
        raise WasmError(f"controller closure reaches non-allowlisted host imports: {reachable_host_imports}")

    # Stream wasm-dis stdout and retain only reachable function forms. Binaryen
    # names defined functions by their zero-based defined index, matching graph
    # nodes. This avoids a ~2 GiB temporary WAT/read_text allocation.
    dis_command = [str(wasm_dis), "--all-features", str(primary), "-o", "-"]
    process = subprocess.Popen(dis_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert process.stdout is not None
    current: str | None = None
    depth = 0
    in_block_comment = 0
    in_string = False
    escaped = False
    forbidden = re.compile(
        r"\((?:call_indirect|return_call_indirect|call_ref|return_call_ref|table\.(?:set|grow|fill|copy|init)|elem\.drop)\b"
    )
    reachable_placeholder_refs: list[str] = []
    forbidden_ops: list[dict[str, str]] = []
    inspected_reachable_defined: set[str] = set()
    def lexical_code(line: str) -> str:
        nonlocal in_block_comment, in_string, escaped
        out = []
        index = 0
        while index < len(line):
            pair = line[index:index + 2]
            char = line[index]
            if in_block_comment:
                if pair == "(;": in_block_comment += 1; index += 2; continue
                if pair == ";)": in_block_comment -= 1; index += 2; continue
                index += 1; continue
            if in_string:
                if escaped: escaped = False
                elif char == "\\": escaped = True
                elif char == '"': in_string = False
                index += 1; continue
            if pair == ";;": break
            if pair == "(;": in_block_comment += 1; index += 2; continue
            if char == '"': in_string = True; index += 1; continue
            out.append(char); index += 1
        return "".join(out)

    for line in process.stdout:
        code = lexical_code(line)
        start = re.match(r"^ \(func \$(\d+)\b", code)
        if start and depth == 0:
            current = start.group(1)
            depth = code.count("(") - code.count(")")
        elif current is not None:
            depth += code.count("(") - code.count(")")
        if current in reachable:
            inspected_reachable_defined.add(current)
            if match := forbidden.search(code):
                forbidden_ops.append({"function": current, "opcode": match.group(0)[1:]})
            if re.search(r"\(ref\.func\b", code):
                forbidden_ops.append({"function": current, "opcode": "ref.func"})
        if current is not None and depth == 0:
            current = None
    stderr = process.stderr.read() if process.stderr else ""
    returncode = process.wait()
    if returncode:
        raise WasmError(f"wasm-dis failed ({returncode}): {stderr}")
    if forbidden_ops:
        raise WasmError(f"controller closure reaches indirect/ref/table operation: {forbidden_ops}")
    if reachable_placeholder_refs:
        raise WasmError(f"controller closure ref.func reaches placeholder: {reachable_placeholder_refs}")
    expected_inspected = {node for node in reachable if node.isdigit()}
    if inspected_reachable_defined != expected_inspected:
        raise WasmError(
            "streamed WAT inspected reachable mismatch: "
            f"missing={sorted(expected_inspected - inspected_reachable_defined)} "
            f"unexpected={sorted(inspected_reachable_defined - expected_inspected)}"
        )
    return {
        "contract": "binary-index-callgraph-streamed-wat-closure-v1",
        "primary": {"path": str(primary.resolve()), "bytes": primary.stat().st_size,
                    "sha256": sha256(primary)},
        "roots": roots,
        "imported_function_count": imported_count,
        "placeholder_import_nodes": sorted(placeholder_nodes),
        "reachable_function_count": len(reachable),
        "inspected_reachable_defined_count": len(inspected_reachable_defined),
        "reachable_placeholder_paths": [],
        "unresolved_nodes": [],
        "forbidden_indirect_ref_table_ops": [],
        "tools": {"wasm_opt": opt, "wasm_dis": dis},
        "commands": {"call_graph": graph_command, "stream_wat": dis_command},
        "call_graph_output": {"bytes": len(graph.encode("utf-8")),
                              "sha256": hashlib.sha256(graph.encode("utf-8")).hexdigest()},
        "verdict": "PASS",
    }


def verify_capture_browser(capture: object, where: str) -> dict[str, object]:
    if not isinstance(capture, dict) or not isinstance(capture.get("browser"), dict):
        raise WasmError(f"{where}: capture browser proof absent")
    browser = capture["browser"]
    if (
        browser.get("nodeVersion") != CAPTURE_NODE_VERSION
        or browser.get("playwrightVersion") != CAPTURE_PLAYWRIGHT_VERSION
        or browser.get("pngjsVersion") != CAPTURE_PNGJS_VERSION
        or browser.get("version") != CAPTURE_CHROMIUM_VERSION
        or browser.get("headed") is not True
        or not isinstance(browser.get("playwrightRoot"), str)
        or not Path(browser["playwrightRoot"]).is_absolute()
    ):
        raise WasmError(f"{where}: capture browser tool identity mismatch")
    adapter = browser.get("adapter")
    if not isinstance(adapter, dict) or set(adapter) != ADAPTER_FIELDS:
        raise WasmError(f"{where}: hardware adapter proof fields mismatch")
    info = adapter.get("info")
    if (
        not isinstance(info, dict)
        or set(info) != ADAPTER_INFO_FIELDS
        or any(not isinstance(info[key], str) for key in ADAPTER_INFO_FIELDS)
    ):
        raise WasmError(f"{where}: hardware adapter info fields mismatch")
    platform = adapter.get("platform")
    expected_args = ["--enable-unsafe-webgpu"] + (["--use-angle=metal"] if platform == "darwin" else [])
    if platform not in {"darwin", "linux"} or browser.get("args") != expected_args:
        raise WasmError(f"{where}: platform browser arguments mismatch")
    identity = " ".join(info[key] for key in ("vendor", "architecture", "device", "description"))
    identity = identity.strip().lower()
    detail_identity = " ".join(info[key] for key in ("architecture", "device", "description")).strip()
    matches = [token for token in SOFTWARE_ADAPTER_TOKENS if token in identity]
    if re.search(r"(^|[^a-z0-9])cpu([^a-z0-9]|$)", identity):
        matches.append("cpu")
    fallback = adapter.get("isFallbackAdapter")
    if fallback is not None and type(fallback) is not bool:
        raise WasmError(f"{where}: fallback adapter flag has wrong type")
    if (
        adapter.get("contract") != ADAPTER_CONTRACT
        or adapter.get("status") != "ACCEPTED"
        or adapter.get("present") is not True
        or adapter.get("powerPreference") != "high-performance"
        or fallback is True
        or not identity
        or not detail_identity
        or matches
        or adapter.get("softwareMatches") != []
        or adapter.get("reason") != "accepted-hardware"
    ):
        raise WasmError(f"{where}: capture did not bind an accepted hardware WebGPU adapter")
    return browser


def verify_profile_receipt(args: argparse.Namespace, original: Path) -> dict[str, object]:
    if not args.profile_receipt or not args.profile_receipt.is_file():
        raise WasmError("apply requires an existing --profile-receipt")
    receipt = json.loads(args.profile_receipt.read_text(encoding="utf-8"))
    if receipt.get("schema") != "blender-web.wasm-split-profile-union.v2" or receipt.get("status") != "PASS":
        raise WasmError("profile receipt is not strict union-v2 PASS")
    if receipt.get("contract") != "binaryen-in-memory-boolean-union-v1":
        raise WasmError("profile receipt contract mismatch")
    output = receipt.get("output")
    if not isinstance(output, dict) or Path(str(output.get("path", ""))).resolve() != args.profile:
        raise WasmError("profile receipt output path does not select --profile")
    profile_identity = {"bytes": args.profile.stat().st_size, "sha256": sha256(args.profile)}
    if output.get("bytes") != profile_identity["bytes"] or output.get("sha256") != profile_identity["sha256"]:
        raise WasmError("selected profile identity does not match profile receipt")
    original_identity = {"bytes": original.stat().st_size, "sha256": sha256(original)}
    if receipt.get("captured_original") != original_identity:
        raise WasmError("captured original identity does not match current .wasm.orig")
    capture_rows = receipt.get("capture_receipts")
    if not isinstance(capture_rows, list) or len(capture_rows) < 2:
        raise WasmError("profile receipt must bind at least two source captures")
    if receipt.get("capture_scenarios") != ["success", "terminal-error"]:
        raise WasmError("profile receipt must bind success and terminal-error controller captures")
    capture_receipt_paths: set[Path] = set()
    capture_scenarios: set[str] = set()
    verified_captures = []
    for row in capture_rows:
        if not isinstance(row, dict) or not isinstance(row.get("receipt"), dict):
            raise WasmError("invalid source capture row")
        receipt_row = row["receipt"]
        capture_path = Path(str(receipt_row.get("path", ""))).resolve()
        if capture_path in capture_receipt_paths or not capture_path.is_file():
            raise WasmError(f"duplicate or absent capture receipt: {capture_path}")
        capture_receipt_paths.add(capture_path)
        actual_capture_identity = {
            "path": str(capture_path),
            "bytes": capture_path.stat().st_size,
            "sha256": sha256(capture_path),
        }
        if receipt_row != actual_capture_identity:
            raise WasmError(f"source capture receipt identity mismatch: {capture_path}")
        capture = json.loads(capture_path.read_text(encoding="utf-8"))
        if capture.get("schema") != "blender-web.wasm-split-profile.v1" or capture.get("status") != "PASS":
            raise WasmError(f"source capture is not strict PASS: {capture_path}")
        verify_capture_browser(capture, str(capture_path))
        scenario = capture.get("scenario")
        if scenario not in {"success", "terminal-error"} or scenario in capture_scenarios:
            raise WasmError(f"source capture scenario invalid or duplicated: {capture_path}")
        capture_scenarios.add(scenario)
        if row.get("scenario") != scenario or capture.get("result", {}).get("controller", {}).get(
            "status"
        ) != "PASS":
            raise WasmError(f"source capture controller proof mismatch: {capture_path}")
        captured_original = capture.get("provenance", {}).get("binaries", {}).get("wasm.orig")
        if not isinstance(captured_original, dict) or {
            "bytes": captured_original.get("bytes"),
            "sha256": captured_original.get("sha256"),
        } != original_identity:
            raise WasmError(f"source capture original mismatch: {capture_path}")
        profile_row = row.get("profile")
        capture_profile = capture.get("artifacts", {}).get("profile-hot.data")
        if not isinstance(profile_row, dict) or not isinstance(capture_profile, dict):
            raise WasmError(f"source capture profile provenance absent: {capture_path}")
        capture_profile_path = Path(str(profile_row.get("path", ""))).resolve()
        if not capture_profile_path.is_file() or {
            "path": str(capture_profile_path),
            "bytes": capture_profile_path.stat().st_size,
            "sha256": sha256(capture_profile_path),
        } != profile_row:
            raise WasmError(f"source capture profile identity mismatch: {capture_path}")
        repo = Path(__file__).resolve().parents[1]
        recorded_path = Path(str(capture_profile.get("path", "")))
        if not recorded_path.is_absolute():
            recorded_path = repo / recorded_path
        if recorded_path.resolve() != capture_profile_path or \
           capture_profile.get("bytes") != profile_row["bytes"] or \
           capture_profile.get("sha256") != profile_row["sha256"]:
            raise WasmError(f"source capture profile row mismatch: {capture_path}")
        verified_captures.append(actual_capture_identity)
    if capture_scenarios != {"success", "terminal-error"}:
        raise WasmError("source captures do not cover both controller scenarios")
    return {
        "path": str(args.profile_receipt),
        "bytes": args.profile_receipt.stat().st_size,
        "sha256": sha256(args.profile_receipt),
        "schema": receipt["schema"],
        "status": receipt["status"],
        "captured_original": original_identity,
        "source_capture_receipts": verified_captures,
    }


def capture(args: argparse.Namespace, original: Path, receipt: Path) -> None:
    link_command = verify_link_command(args)
    if not PROFILE_EXPORT_SOURCE.is_file():
        raise WasmError(f"capture profile source missing: {PROFILE_EXPORT_SOURCE}")
    profile_export_source = PROFILE_EXPORT_SOURCE.read_text(encoding="utf-8")
    for marker in (
        "BW_SPLIT_CAPTURE_PREENTRY_ATTESTATION_V1",
        'worker.__bwCaptureLoadState = "ready-before-entry"',
        'Module["bwCaptureAttestPageReady"]',
        'Module["bwCaptureResumeAfterStable"]',
        "postApplyProbeCount",
    ):
        if marker not in profile_export_source:
            raise WasmError(f"capture profile source lacks persisted attestation marker: {marker}")
    original_facts = wasm_facts(original)
    verify_reserved_shared_memory(original_facts, args.reserve)
    if PROFILE_MARKER not in args.js.read_text(encoding="utf-8"):
        raise WasmError(f"capture JS is missing {PROFILE_MARKER}")
    patch_pthread_guard(args.js)
    shared_memory_view_refresh = patch_shared_memory_view_refresh(args.js)
    pthread_memory_range_sync = patch_pthread_memory_range_sync(args.js)
    capture_probe_dispatch = patch_capture_probe_dispatch(args.js)
    capture_atomic_diagnostics = patch_capture_atomic_diagnostics(args.js)
    capture_thread_entry_diagnostics = patch_capture_thread_entry_diagnostics(args.js)
    if args.js.read_text(encoding="utf-8").count(
        "BW_SPLIT_CAPTURE_PREENTRY_ATTESTATION_V1"
    ) != 1:
        raise WasmError("capture generated JS must contain exactly one pre-entry attestation marker")

    with tempfile.TemporaryDirectory(prefix="bw-split-capture-", dir=args.wasm.parent) as temp_dir:
        instrumented = Path(temp_dir) / args.wasm.name
        run(
            [
                str(args.wasm_split),
                "--instrument",
                "--in-memory",
                *BINARYEN_FEATURES,
                str(original),
                "-o",
                str(instrumented),
            ]
        )
        instrumented_facts = wasm_facts(instrumented)
        if "__write_profile" not in instrumented_facts["exports"]:
            raise WasmError("instrumented module does not export __write_profile")
        os.replace(instrumented, args.wasm)

    outputs = exact_wasm_outputs(args.wasm, {args.wasm, original})

    write_json(
        receipt,
        {
            "schema": 1,
            "mode": "capture",
            "verdict": "PASS",
            "contract": "shared-main-memory-profile-v1",
            "reserve_bytes": args.reserve,
            "original": {"path": str(original), "bytes": original.stat().st_size, "sha256": sha256(original)},
            "instrumented": {
                "path": str(args.wasm),
                "bytes": args.wasm.stat().st_size,
                "sha256": sha256(args.wasm),
            },
            "js": {"path": str(args.js), "bytes": args.js.stat().st_size,
                   "sha256": sha256(args.js), "pthread_guard": MARKER},
            "capture_probe_dispatch": capture_probe_dispatch,
            "capture_atomic_diagnostics": capture_atomic_diagnostics,
            "capture_thread_entry_diagnostics": capture_thread_entry_diagnostics,
            "shared_memory_view_refresh": shared_memory_view_refresh,
            "pthread_memory_range_sync": pthread_memory_range_sync,
            "link_command": link_command,
            "profile_export": {
                "path": str(PROFILE_EXPORT_SOURCE),
                "bytes": PROFILE_EXPORT_SOURCE.stat().st_size,
                "sha256": sha256(PROFILE_EXPORT_SOURCE),
                "persisted_pre_entry_attestation": True,
                "post_apply_probe_counter": True,
                "pre_entry_marker": "BW_SPLIT_CAPTURE_PREENTRY_ATTESTATION_V1",
                "pre_entry_marker_count": args.js.read_text(encoding="utf-8").count(
                    "BW_SPLIT_CAPTURE_PREENTRY_ATTESTATION_V1"
                ),
            },
            "finalizer": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__))},
            "binaryen_features": BINARYEN_FEATURES,
            "facts": original_facts,
            "wasm_inventory": [
                {
                    "role": "instrumented_capture" if path == args.wasm else "original_build_only",
                    "filename": path.name,
                    "path": str(path),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                    "shipped": False,
                    "critical": False,
                }
                for path in outputs
            ],
            "inventory_policy": {
                "glob": args.wasm.stem + "*.wasm*",
                "unlisted": "reject",
                "capture_artifact_is_not_shippable": True,
                "prior_receipt_invalidated_before_mutation": args.prior_receipt_invalidated,
            },
        },
    )


def secondary_name(wasm_path: Path, placeholder_modules: list[str]) -> str:
    if len(placeholder_modules) != 1:
        raise WasmError(f"expected one placeholder module, found {placeholder_modules}")
    module = placeholder_modules[0]
    if module == "placeholder":
        return wasm_path.stem + ".deferred.wasm"
    prefix = "placeholder."
    if not module.startswith(prefix) or not module[len(prefix):]:
        raise WasmError(f"invalid placeholder module {module!r}")
    return wasm_path.stem + "." + module[len(prefix):] + ".wasm"


def apply_profile(args: argparse.Namespace, original: Path, receipt: Path) -> None:
    if not args.profile or not args.expected_orig_sha256:
        raise WasmError("apply requires --profile and --expected-orig-sha256")
    if not args.profile.is_file() or args.profile.stat().st_size == 0:
        raise WasmError(f"profile is absent or empty: {args.profile}")
    link_command = verify_link_command(args)
    if PROFILE_MARKER in args.js.read_text(encoding="utf-8") or "bwWriteSplitProfile" in args.js.read_text(
        encoding="utf-8"
    ):
        raise WasmError("shipping apply JS still exposes the profile-only API")
    apply_source = args.js.read_text(encoding="utf-8")
    for capture_probe_marker in (
        CAPTURE_PROBE_CORE_DISPATCH_MARKER,
        "BW_SPLIT_CAPTURE_ATOMIC_DIAG_V1",
        CAPTURE_THREAD_ENTRY_DIAG_MARKER,
        CAPTURE_THREAD_ENTRY_STAGE_MARKER,
        CAPTURE_MAIN_DIAGNOSTIC_DISPATCH_MARKER,
        'cmd=="bwCaptureProbe"',
        'cmd:"bwCaptureProbeAck"',
        'cmd:"bwCaptureAtomicError"',
        'cmd:"bwCaptureThreadEntryError"',
    ):
        if capture_probe_marker in apply_source:
            raise WasmError("shipping apply JS still contains CAPTURE probe core glue")
    original_hash = sha256(original)
    if original_hash != args.expected_orig_sha256:
        raise WasmError(
            f".wasm.orig hash {original_hash} != profile-bound {args.expected_orig_sha256}"
        )
    original_facts = wasm_facts(original)
    verify_reserved_shared_memory(original_facts, args.reserve)
    controller_keep = controller_keep_functions(wasm_function_layout(original))
    profile_receipt = verify_profile_receipt(args, original)
    patch_pthread_guard(args.js)
    shared_memory_view_refresh = patch_shared_memory_view_refresh(args.js)
    pthread_memory_range_sync = patch_pthread_memory_range_sync(args.js)

    with tempfile.TemporaryDirectory(prefix="bw-split-apply-", dir=args.wasm.parent) as temp_dir:
        temp = Path(temp_dir)
        primary = temp / "primary.wasm"
        secondary = temp / "secondary.wasm"
        run(
            [
                str(args.wasm_split),
                "--split",
                *BINARYEN_FEATURES,
                "--profile",
                str(args.profile),
                "--keep-funcs",
                ",".join(controller_keep["functions"]),
                "--placeholdermap",
                "--symbolmap",
                str(original),
                "-o1",
                str(primary),
                "-o2",
                str(secondary),
            ]
        )
        primary_facts = wasm_facts(primary)
        placeholders = [
            name for name in primary_facts["import_modules"] if name.startswith("placeholder")
        ]
        secondary_path = args.wasm.with_name(secondary_name(args.wasm, placeholders))

        stale = sorted(
            path.name
            for path in args.wasm.parent.glob(args.wasm.stem + ".*.wasm")
            if path not in {original, secondary_path}
        )
        if stale:
            raise WasmError(f"stale split modules must be removed explicitly before apply: {stale}")

        placeholder_map = primary.with_suffix(primary.suffix + ".placeholders")
        primary_symbols = primary.with_suffix(primary.suffix + ".symbols")
        secondary_symbols = secondary.with_suffix(secondary.suffix + ".symbols")
        for path in (placeholder_map, primary_symbols, secondary_symbols):
            if not path.is_file() or path.stat().st_size == 0:
                raise WasmError(f"wasm-split did not emit required map: {path.name}")

        map_root = args.wasm.with_name(args.wasm.name + ".split-maps")
        map_root.mkdir(parents=True, exist_ok=True)
        installed_maps: list[dict[str, object]] = []
        for source in (placeholder_map, primary_symbols, secondary_symbols):
            target = map_root / source.name
            shutil.copyfile(source, target)
            installed_maps.append(
                {"path": str(target), "bytes": target.stat().st_size, "sha256": sha256(target)}
            )

        primary_exports = set(primary_facts["exports"])
        missing_controller_exports = sorted(set(SPLIT_CONTROLLER_EXPORTS) - primary_exports)
        secondary_names = {
            line.split(":", 1)[1].strip()
            for line in secondary_symbols.read_text(encoding="utf-8").splitlines()
            if ":" in line
        }
        deferred_controller_exports = sorted(set(SPLIT_CONTROLLER_EXPORTS) & secondary_names)
        if missing_controller_exports or deferred_controller_exports:
            raise WasmError(
                "pre-shard split controller is not closed in primary: "
                f"missing_exports={missing_controller_exports} "
                f"deferred_symbols={deferred_controller_exports}"
            )
        controller_closure = {
            "contract": "all-pre-shard-controller-exports-primary-v2",
            "exports": SPLIT_CONTROLLER_EXPORTS,
            "keep_functions": controller_keep,
            "primary_export_count": len(primary_exports),
            "missing_primary_exports": missing_controller_exports,
            "deferred_controller_symbols": deferred_controller_exports,
            "placeholder_map": {
                "path": str((map_root / placeholder_map.name).resolve()),
                "bytes": (map_root / placeholder_map.name).stat().st_size,
                "sha256": sha256(map_root / placeholder_map.name),
            },
            "primary_symbols": {
                "path": str((map_root / primary_symbols.name).resolve()),
                "bytes": (map_root / primary_symbols.name).stat().st_size,
                "sha256": sha256(map_root / primary_symbols.name),
            },
            "secondary_symbols": {
                "path": str((map_root / secondary_symbols.name).resolve()),
                "bytes": (map_root / secondary_symbols.name).stat().st_size,
                "sha256": sha256(map_root / secondary_symbols.name),
            },
            "verdict": "PASS",
        }
        controller_closure["transitive_direct_call_proof"] = verify_primary_controller_closure(
            primary, args.wasm_split.with_name("wasm-opt"), args.wasm_split.with_name("wasm-dis")
        )

        os.replace(primary, args.wasm)
        os.replace(secondary, secondary_path)

    single_flight = patch_single_flight_runtime(args.js, secondary_path)

    outputs = exact_wasm_outputs(args.wasm, {args.wasm, original, secondary_path})
    wasm_inventory = []
    for path in outputs:
        if path == args.wasm:
            role, shipped, critical, request_phase = "primary", True, True, "stage0"
        elif path == secondary_path:
            role, shipped, critical, request_phase = (
                "deferred",
                True,
                False,
                "after_semantic_first_interaction",
            )
        else:
            role, shipped, critical, request_phase = "original_build_only", False, False, "never"
        wasm_inventory.append(
            {
                "role": role,
                "filename": path.name,
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "shipped": shipped,
                "critical": critical,
                "request_phase": request_phase,
            }
        )

    write_json(
        receipt,
        {
            "schema": 1,
            "mode": "apply",
            "verdict": "PASS",
            "contract": "shared-main-memory-profile-v1",
            "reserve_bytes": args.reserve,
            "original": {"path": str(original), "bytes": original.stat().st_size, "sha256": original_hash},
            "profile": {
                "path": str(args.profile),
                "bytes": args.profile.stat().st_size,
                "sha256": sha256(args.profile),
            },
            "profile_receipt": profile_receipt,
            "primary": {"path": str(args.wasm), "bytes": args.wasm.stat().st_size, "sha256": sha256(args.wasm)},
            "secondary": {
                "path": str(secondary_path),
                "bytes": secondary_path.stat().st_size,
                "sha256": sha256(secondary_path),
            },
            "js": {
                "path": str(args.js),
                "sha256": sha256(args.js),
                "pthread_guard": MARKER,
                "single_flight_runtime": SINGLE_FLIGHT_RUNTIME_MARKER,
                "stock_sync_loader_absent": True,
            },
            "single_flight": single_flight,
            "shared_memory_view_refresh": shared_memory_view_refresh,
            "pthread_memory_range_sync": pthread_memory_range_sync,
            "controller_closure": controller_closure,
            "link_command": link_command,
            "finalizer": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__))},
            "binaryen_features": BINARYEN_FEATURES,
            "placeholder_modules": placeholders,
            "maps": installed_maps,
            "facts": original_facts,
            "wasm_inventory": wasm_inventory,
            "inventory_policy": {
                "glob": args.wasm.stem + "*.wasm*",
                "unlisted": "reject",
                "bundle_roles": ["primary", "deferred"],
                "build_only_roles": ["original_build_only"],
                "profile_export_absent": True,
                "prior_receipt_invalidated_before_mutation": args.prior_receipt_invalidated,
            },
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("capture", "apply"), required=True)
    parser.add_argument("--wasm", type=Path, required=True)
    parser.add_argument("--js", type=Path, required=True)
    parser.add_argument("--wasm-split", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--ninja", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--target", default="blender_browser")
    parser.add_argument("--reserve", type=int, default=DEFAULT_RESERVE)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--profile-receipt", type=Path)
    parser.add_argument("--expected-orig-sha256")
    args = parser.parse_args()

    args.wasm = args.wasm.resolve()
    args.js = args.js.resolve()
    args.wasm_split = args.wasm_split.resolve()
    args.receipt = args.receipt.resolve()
    args.ninja = args.ninja.resolve()
    args.build_dir = args.build_dir.resolve()
    if args.profile:
        args.profile = args.profile.resolve()
    if args.profile_receipt:
        args.profile_receipt = args.profile_receipt.resolve()

    if args.reserve != DEFAULT_RESERVE:
        raise WasmError(f"reserve must match post-js contract: {DEFAULT_RESERVE}")
    for path in (args.wasm, args.js, args.wasm_split, args.ninja):
        if not path.is_file():
            raise WasmError(f"required file missing: {path}")
    original = Path(str(args.wasm) + ".orig")
    if not original.is_file():
        raise WasmError(f"SPLIT_MODULE original missing: {original}")
    expected_receipt = args.wasm.with_name(args.wasm.stem + ".split-build.json")
    if args.receipt != expected_receipt:
        raise WasmError(
            f"receipt must be exact wasm sibling {expected_receipt}; got {args.receipt}"
        )
    args.prior_receipt_invalidated = args.receipt.exists()
    # A failed/interrupted finalizer must never leave a prior PASS receipt beside
    # freshly relinked or partially replaced bytes. The new receipt is installed
    # atomically by write_json only after every mode-specific check succeeds.
    if args.prior_receipt_invalidated:
        args.receipt.unlink()

    if args.mode == "capture":
        capture(args, original, args.receipt)
    else:
        apply_profile(args, original, args.receipt)
    print(f"BW_WASM_SPLIT_{args.mode.upper()}_PASS {args.receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

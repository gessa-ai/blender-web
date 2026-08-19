#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Adversarial self-checks for the pre-shard controller closure proof."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
from pathlib import Path


FINALIZER = Path(__file__).resolve().parents[2] / "scripts/finalize-wasm-split.py"
SPEC = importlib.util.spec_from_file_location("finalize_wasm_split", FINALIZER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def module(body: str, imports: str = "") -> str:
    return f'''(module
      {imports}
      (func $entry {body})
      (export "controller" (func $entry))
    )'''


def expect_pass(label: str, source: str) -> None:
    result = MODULE.verify_primary_controller_closure_source(source, ["controller"])
    if result["verdict"] != "PASS":
        raise AssertionError(f"{label}: {result}")


def expect_fail(label: str, source: str, needle: str) -> None:
    try:
        MODULE.verify_primary_controller_closure_source(source, ["controller"])
    except MODULE.WasmError as error:
        if needle not in str(error):
            raise AssertionError(f"{label}: {error!s} lacks {needle!r}") from error
    else:
        raise AssertionError(f"{label}: unexpectedly passed")


def main() -> None:
    expect_pass("direct", module("(call $leaf)") + "\n(func $leaf)")
    expect_pass("transitive", module("(call $middle)") + "\n(func $middle (call $leaf))\n(func $leaf)")
    expect_fail("host import", module('(call $host)', '(import "env" "host" (func $host))'),
                "non-allowlisted host import")
    expect_fail(
        "placeholder",
        module('(call $cold)', '(import "placeholder" "1" (func $cold))'),
        "deferred placeholder",
    )
    expect_fail(
        "transitive placeholder",
        module("(call $middle)", '(import "placeholder.x" "2" (func $cold))') +
        "\n(func $middle (call $cold))",
        "deferred placeholder",
    )
    expect_fail(
        "return call",
        module('(return_call $cold)', '(import "placeholder" "3" (func $cold))'),
        "deferred placeholder",
    )
    for opcode in ("call_indirect", "return_call_indirect", "call_ref", "return_call_ref"):
        expect_fail(opcode, module(f"({opcode} (i32.const 0))"), opcode)
    expect_fail(
        "ref.func placeholder",
        module('(drop (ref.func $cold))', '(import "placeholder" "4" (func $cold))'),
        "ref.func",
    )
    expect_fail("table mutation", module("(table.set (i32.const 0) (ref.null func))"), "table.set")
    expect_fail("missing target", module("(call $absent)"), "missing target")
    repo = Path(__file__).resolve().parents[2]
    wasm_as = repo / "tools/emsdk/upstream/bin/wasm-as"
    wasm_opt = repo / "tools/emsdk/upstream/bin/wasm-opt"
    wasm_dis = repo / "tools/emsdk/upstream/bin/wasm-dis"
    production_fixtures = {
        "direct": ('(module (func $leaf) (func $entry (call $leaf)) '
                   '(export "controller" (func $entry)))', None),
        "transitive": ('(module (func $leaf) (func $mid (call $leaf)) '
                       '(func $entry (call $mid)) (export "controller" (func $entry)))', None),
        "placeholder_direct": ('(module (import "placeholder" "1" (func $cold)) '
                               '(func $entry (call $cold)) (export "controller" (func $entry)))',
                               "deferred placeholder"),
        "placeholder_transitive": ('(module (import "placeholder.x" "2" (func $cold)) '
                                   '(func $mid (call $cold)) (func $entry (call $mid)) '
                                   '(export "controller" (func $entry)))', "deferred placeholder"),
        "host_import": ('(module (import "env" "host_callback" (func $host)) '
                        '(func $entry (call $host)) (export "controller" (func $entry)))',
                        "non-allowlisted host import"),
        "return_call_placeholder": ('(module (import "placeholder" "3" (func $cold)) '
                                    '(func $entry (return_call $cold)) '
                                    '(export "controller" (func $entry)))', "deferred placeholder"),
        "indirect": ('(module (type $t (func)) (table 1 funcref) '
                     '(func $entry (call_indirect (type $t) (i32.const 0))) '
                     '(export "controller" (func $entry)))', "indirect/ref/table operation"),
        "ref_func_chain": ('(module (import "placeholder" "4" (func $cold)) '
                           '(func $helper (call $cold)) '
                           '(func $entry (drop (ref.func $helper))) '
                           '(export "controller" (func $entry)))', "indirect/ref/table operation"),
        "table_set": ('(module (table 1 funcref) '
                      '(func $entry (table.set (i32.const 0) (ref.null func))) '
                      '(export "controller" (func $entry)))', "indirect/ref/table operation"),
    }
    with tempfile.TemporaryDirectory(prefix="bw-closure-fixtures-") as temp:
        root = Path(temp)
        for label, (wat_source, expected_error) in production_fixtures.items():
            wat = root / f"{label}.wat"; wasm = root / f"{label}.wasm"
            wat.write_text(wat_source, encoding="utf-8")
            subprocess.run([str(wasm_as), "--all-features", str(wat), "-o", str(wasm)], check=True)
            if expected_error is None:
                result = MODULE.verify_primary_controller_closure(
                    wasm, wasm_opt, wasm_dis, ["controller"]
                )
                if result["verdict"] != "PASS": raise AssertionError(result)
            else:
                try:
                    MODULE.verify_primary_controller_closure(wasm, wasm_opt, wasm_dis, ["controller"])
                except MODULE.WasmError as error:
                    if expected_error not in str(error):
                        raise AssertionError(
                            f"production fixture {label}: {error!s} lacks {expected_error!r}"
                        ) from error
                else:
                    raise AssertionError(f"production fixture {label} unexpectedly passed")
    # A comment that names a forbidden opcode must not itself fail a real
    # S-expression lexer. The production proof uses Binaryen call graph plus
    # function-scoped streamed WAT; this small parser selfcheck remains focused
    # on direct/return-call closure behavior.
    print("controller-closure selfcheck: 2 source positive, 10 source negative, 9 production fixtures PASS")


if __name__ == "__main__":
    main()

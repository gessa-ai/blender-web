#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check M6 EEVEE thresholds against the pinned upstream runner."""

import ast
import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "upstream/tests/python/eevee_render_tests.py"
MANIFEST = ROOT / "sandbox/m6-prep/manifest.tsv"
PLAN = ROOT / "sandbox/m6-prep/suite_plan.tsv"
TARGET_COUNTS = {
    "colorspace": 2,
    "transparency": 2,
    "shadow": 4,
    "raycast": 7,
    "principled_bsdf": 15,
}
TARGET_TOTAL = 30


def numeric_value(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return numeric_value(node.left) / numeric_value(node.right)
    raise AssertionError(f"unsupported threshold expression at line {node.lineno}")


def report_setting(statement):
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return None
    call = statement.value
    if not isinstance(call.func, ast.Attribute) or not call.args:
        return None
    names = {
        "set_fail_threshold": "fail_threshold",
        "set_fail_percent": "fail_percent",
    }
    key = names.get(call.func.attr)
    return (key, numeric_value(call.args[0])) if key else None


def startswith_directory(node):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr != "startswith" or len(node.args) != 1:
        return None
    receiver = node.func.value
    argument = node.args[0]
    if (
        isinstance(receiver, ast.Name)
        and receiver.id == "test_dir_name"
        and isinstance(argument, ast.Constant)
        and isinstance(argument.value, str)
    ):
        return argument.value
    return None


def upstream_thresholds():
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"), filename=str(RUNNER))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    test_dir_assignment = next(
        statement
        for statement in main.body
        if isinstance(statement, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "test_dir_name" for target in statement.targets)
    )

    defaults = {}
    for statement in main.body:
        if statement is test_dir_assignment:
            break
        setting = report_setting(statement)
        if setting:
            defaults[setting[0]] = setting[1]
    assert set(defaults) == {"fail_threshold", "fail_percent"}, "runner defaults not found"

    expected = {directory: dict(defaults) for directory in TARGET_COUNTS}
    for node in ast.walk(main):
        if not isinstance(node, ast.If):
            continue
        directory = startswith_directory(node.test)
        if directory not in expected:
            continue
        for statement in node.body:
            setting = report_setting(statement)
            if setting:
                expected[directory][setting[0]] = setting[1]
    return expected


def data_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.reader(handle, delimiter="\t") if row and not row[0].startswith("#")]


def check_close(actual, expected, label):
    assert math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=5e-10), (
        f"{label}: expected {expected:.12g}, found {actual}"
    )


def main():
    assert sum(TARGET_COUNTS.values()) == TARGET_TOTAL, "target category counts do not total 30"
    expected = upstream_thresholds()
    assert set(expected) == set(TARGET_COUNTS), (
        f"upstream threshold categories changed: {sorted(expected)}"
    )

    rows = [row for row in data_rows(MANIFEST) if row[0] == "eevee"]
    assert len(rows) == TARGET_TOTAL, f"expected {TARGET_TOTAL} EEVEE manifest rows, found {len(rows)}"
    counts = {directory: 0 for directory in expected}
    tests = set()
    for engine, directory, test, _blend, _golden, threshold, percent in rows:
        assert directory in expected, f"unexpected EEVEE manifest category: {directory}"
        test_key = (directory, test)
        assert test_key not in tests, f"duplicate EEVEE manifest test: {directory}/{test}"
        tests.add(test_key)
        counts[directory] += 1
        check_close(threshold, expected[directory]["fail_threshold"], f"{engine}/{test} threshold")
        check_close(percent, expected[directory]["fail_percent"], f"{engine}/{test} fail percent")
    assert counts == TARGET_COUNTS, f"target manifest row counts changed: {counts}"

    plan_eevee_rows = [row for row in data_rows(PLAN) if row[0] == "eevee"]
    assert len(plan_eevee_rows) == len(TARGET_COUNTS), (
        f"expected {len(TARGET_COUNTS)} EEVEE suite-plan rows, found {len(plan_eevee_rows)}"
    )
    plan_rows = {}
    for engine, directory, threshold, percent in plan_eevee_rows:
        key = (engine, directory)
        assert key not in plan_rows, f"duplicate suite-plan row: {engine}/{directory}"
        plan_rows[key] = (threshold, percent)
    assert {directory for engine, directory in plan_rows if engine == "eevee"} == set(expected), (
        f"EEVEE suite-plan categories changed: {sorted(directory for _, directory in plan_rows)}"
    )
    for directory, settings in expected.items():
        threshold, percent = plan_rows[("eevee", directory)]
        check_close(threshold, settings["fail_threshold"], f"suite plan eevee/{directory} threshold")
        check_close(percent, settings["fail_percent"], f"suite plan eevee/{directory} fail percent")

    total = sum(counts.values())
    assert total == TARGET_TOTAL
    print(f"PASS: {total} EEVEE manifest rows and their suite-plan sources match {RUNNER.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

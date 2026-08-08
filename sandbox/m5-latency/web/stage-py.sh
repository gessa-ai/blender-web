#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Refresh the served Python bundle (web/py/gen/) for the M5 latency harness from
# the REAL sources so nothing drifts. gen/ is git-ignored (a build artifact).
#
# Sources (unchanged authorities):
#   sandbox/m5-latency/web/py/m5_latency.py                     -> gen/m5_latency.py
#   sandbox/m5-latency/web/py/latency_runner.py                 -> gen/latency_runner.py
#   upstream/tests/python/ui_simulate/modules/easy_keys.py      -> gen/easy_keys.py
#   upstream/tests/python/ui_simulate/modules/ui_test_utils.py  -> gen/ui_test_utils.py
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$(pwd)"
GEN="$ROOT/sandbox/m5-latency/web/py/gen"
mkdir -p "$GEN"

cp "$ROOT/sandbox/m5-latency/web/py/m5_latency.py"                      "$GEN/m5_latency.py"
cp "$ROOT/sandbox/m5-latency/web/py/latency_runner.py"                  "$GEN/latency_runner.py"
cp "$ROOT/upstream/tests/python/ui_simulate/modules/easy_keys.py"      "$GEN/easy_keys.py"
cp "$ROOT/upstream/tests/python/ui_simulate/modules/ui_test_utils.py"  "$GEN/ui_test_utils.py"

echo "staged 4 files into $GEN"
ls -la "$GEN"

#!/usr/bin/env bash
echo "milestone: M0 (toolchain+oracle) — harness v0, no suites registered yet"
[ -f "$(dirname "$0")/../scripts/bootstrap.done" ] && echo "upstream: cloned" || echo "upstream: PENDING (scripts/bootstrap.sh)"

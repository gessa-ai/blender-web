#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Serialize ninja invocations across concurrent wave workers sharing ONE build tree.
# Concurrent ninja processes on one build.ninja race on .ninja_log/.ninja_deps; a single
# ninja run already saturates all cores, so serializing RUNS costs ~nothing — the wave's
# parallelism is in error-FIXING, not compiling.
#
# Usage: scripts/ninja-locked.sh <ninja args...>   (workers wrap this in buildwrap.sh)
set -uo pipefail
LOCK="/tmp/blender-web-ninja.lock"
STALE_SECS=3600
while ! mkdir "$LOCK" 2>/dev/null; do
  if [ -f "$LOCK/pid" ]; then
    PID=$(cat "$LOCK/pid" 2>/dev/null || echo "")
    NOW=$(date +%s); TS=$(cat "$LOCK/ts" 2>/dev/null || echo "$NOW")
    if [ -n "$PID" ] && ! kill -0 "$PID" 2>/dev/null; then
      echo "ninja-locked: removing stale lock (dead pid $PID)" >&2; rm -rf "$LOCK"; continue
    fi
    if [ $((NOW - TS)) -gt $STALE_SECS ]; then
      echo "ninja-locked: removing stale lock (age >${STALE_SECS}s)" >&2; rm -rf "$LOCK"; continue
    fi
  fi
  sleep 5
done
echo "$$" > "$LOCK/pid"; date +%s > "$LOCK/ts"
trap 'rm -rf "$LOCK"' EXIT INT TERM
ninja "$@"

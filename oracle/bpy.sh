#!/usr/bin/env bash
# Runs pinned native Blender headless. M0.3 installs the binary and points BLENDER_BIN here.
BLENDER_BIN="${BLENDER_BIN:-$(dirname "$0")/blender-5.2.0/Blender.app/Contents/MacOS/Blender}"
[ -x "$BLENDER_BIN" ] || { echo "oracle not installed yet (M0.3): $BLENDER_BIN missing" >&2; exit 2; }
exec "$BLENDER_BIN" -b --factory-startup "$@"

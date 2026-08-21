#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Fail-closed identity checks for the integrated shader-frontend parity driver.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DAWN_PIN="36cf1fae0cd8a81a4fb4580751648b80b2e6255c"
SELFCHECK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/bw-shader-frontend-selfcheck.XXXXXX")"
cleanup()
{
  if [ -d "$SELFCHECK_DIR" ]; then
    case "$(basename "$SELFCHECK_DIR")" in
      bw-shader-frontend-selfcheck.*) find "$SELFCHECK_DIR" -depth -delete ;;
      *) echo "ERROR: refusing to clean unexpected self-check directory" >&2; return 1 ;;
    esac
  fi
}
trap cleanup EXIT

WRONG_DAWN_OUT="$SELFCHECK_DIR/wrong-dawn-out"
WRONG_NODE_OUT="$SELFCHECK_DIR/wrong-node-out"
WRONG_NODE="$SELFCHECK_DIR/wrong-node"
printf '%s\n' '#!/usr/bin/env bash' "printf '%s\\n' v99.0.0" >"$WRONG_NODE"
chmod +x "$WRONG_NODE"

if OUT="$WRONG_DAWN_OUT" DAWN_SRC="$ROOT" bash "$HERE/build.sh" \
  >"$SELFCHECK_DIR/wrong-dawn.stdout" \
  2>"$SELFCHECK_DIR/wrong-dawn.stderr"
then
  echo "ERROR: wrong Dawn checkout was accepted" >&2
  exit 1
fi
if [ -e "$WRONG_DAWN_OUT" ]; then
  echo "ERROR: wrong Dawn checkout allocated evidence" >&2
  exit 1
fi
if [ -s "$SELFCHECK_DIR/wrong-dawn.stdout" ] ||
   ! grep -Eq \
     "^ERROR: Dawn pin mismatch: expected $DAWN_PIN, got [0-9a-f]{40}$" \
     "$SELFCHECK_DIR/wrong-dawn.stderr"
then
  echo "ERROR: wrong Dawn rejection diagnostic differs" >&2
  exit 1
fi

if OUT="$WRONG_NODE_OUT" NODE="$WRONG_NODE" bash "$HERE/build.sh" \
  >"$SELFCHECK_DIR/wrong-node.stdout" \
  2>"$SELFCHECK_DIR/wrong-node.stderr"
then
  echo "ERROR: wrong Node identity was accepted" >&2
  exit 1
fi
if [ -e "$WRONG_NODE_OUT" ]; then
  echo "ERROR: wrong Node identity allocated evidence" >&2
  exit 1
fi
if [ -s "$SELFCHECK_DIR/wrong-node.stdout" ] ||
   ! grep -qx 'ERROR: expected Node v22.16.0, got v99.0.0' \
     "$SELFCHECK_DIR/wrong-node.stderr"
then
  echo "ERROR: wrong Node rejection diagnostic differs" >&2
  exit 1
fi

echo "SHADER_FRONTEND_INTEGRATED_SELFCHECK_PASS wrong_dawn=zero-allocation wrong_node=zero-allocation"

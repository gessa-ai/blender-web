#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

# Reproducible entry point for the Linux native oracle.  Runtime networking is
# disabled: oracle checks consume only files explicitly mounted from the caller.
set -euo pipefail

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SCRIPT_SOURCE" ]]; do
  SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)"
  LINK_TARGET="$(readlink "$SCRIPT_SOURCE")"
  if [[ "$LINK_TARGET" = /* ]]; then
    SCRIPT_SOURCE="$LINK_TARGET"
  else
    SCRIPT_SOURCE="$SCRIPT_DIR/$LINK_TARGET"
  fi
done
SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)"
SCRIPT_SOURCE="$SCRIPT_DIR/$(basename "$SCRIPT_SOURCE")"
ROOT="$(cd "$(dirname "$SCRIPT_SOURCE")/.." && pwd)"
WORK_ROOT="$(pwd -P)"
DOCKERFILE="$ROOT/containers/oracle/Dockerfile"
IMAGE="${BLENDER_ORACLE_IMAGE:-blender-web/oracle:5.2.0-fbe6228777e7}"
PLATFORM="linux/amd64"
# Exact pinned Blender commit timestamp. BuildKit honors SOURCE_DATE_EPOCH when
# writing image/config/layer timestamps; disabling provenance avoids a fresh
# attestation timestamp changing an otherwise byte-identical image digest.
SOURCE_DATE_EPOCH="1783956011"

usage() {
  cat >&2 <<'EOF'
usage: scripts/oracle-container.sh COMMAND [ARGS...]

commands:
  selfcheck        validate pins and file structure without building an image
  build            build the pinned linux/amd64 oracle image
  verify           build, then verify Blender version/bpy and oiiotool
  blender ARGS...  run Blender headless with the caller's directory at /work
  oiiotool ARGS... run pinned oiiotool with the caller's directory at /work
  version          print the pinned Blender and oiiotool versions
  with-env COMMAND [ARGS...]
                   run a command with container-backed Blender/oiiotool shims
EOF
}

require_docker() {
  command -v docker >/dev/null 2>&1 || {
    echo "oracle container: docker CLI is not installed" >&2
    exit 2
  }
  docker info >/dev/null 2>&1 || {
    echo "oracle container: docker daemon is unavailable" >&2
    exit 2
  }
}

build_image() {
  require_docker
  docker build \
    --platform "$PLATFORM" \
    --provenance=false \
    --build-arg "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH" \
    --file "$DOCKERFILE" \
    --tag "$IMAGE" \
    "$ROOT/containers/oracle"
}

run_image() {
  require_docker
  docker run --rm \
    --platform "$PLATFORM" \
    --network none \
    --user "$(id -u):$(id -g)" \
    --env HOME=/tmp \
    --volume "$WORK_ROOT:/work" \
    --workdir /work \
    "$@"
}

translated_args=()
translate_work_args() {
  translated_args=()
  local argument
  for argument in "$@"; do
    if [[ "$argument" == "$WORK_ROOT" ]]; then
      translated_args+=("/work")
    elif [[ "$argument" == "$WORK_ROOT/"* ]]; then
      translated_args+=("/work/${argument#"$WORK_ROOT"/}")
    else
      translated_args+=("$argument")
    fi
  done
}

case "${0##*/}" in
  blender-oracle)
    set -- blender "$@"
    ;;
  oiiotool)
    set -- oiiotool "$@"
    ;;
esac

command_name="${1:-}"
if [[ -z "$command_name" ]]; then
  usage
  exit 2
fi
shift

case "$command_name" in
  selfcheck)
    exec python3 "$ROOT/scripts/m0-selfcheck.py"
    ;;
  build)
    build_image
    ;;
  verify)
    build_image
    run_image "$IMAGE" --version \
      | grep --fixed-strings 'Blender 5.2.0'
    run_image "$IMAGE" --background --factory-startup --python-expr \
      "import bpy; assert sorted(bpy.data.objects.keys()) == ['Camera', 'Cube', 'Light']; print('M0_ORACLE_BPY_OK')" \
      | grep --fixed-strings 'M0_ORACLE_BPY_OK'
    run_image --entrypoint /usr/bin/oiiotool "$IMAGE" --version \
      | grep --fixed-strings '2.4.17.0'
    echo "M0_ORACLE_CONTAINER_OK"
    ;;
  blender)
    require_docker
    translate_work_args "$@"
    exec docker run --rm \
      --platform "$PLATFORM" \
      --network none \
      --user "$(id -u):$(id -g)" \
      --env HOME=/tmp \
      --volume "$WORK_ROOT:/work" \
      --workdir /work \
      "$IMAGE" --background --factory-startup "${translated_args[@]}"
    ;;
  oiiotool)
    require_docker
    translate_work_args "$@"
    exec docker run --rm \
      --platform "$PLATFORM" \
      --network none \
      --user "$(id -u):$(id -g)" \
      --env HOME=/tmp \
      --volume "$WORK_ROOT:/work" \
      --workdir /work \
      --entrypoint /usr/bin/oiiotool \
      "$IMAGE" "${translated_args[@]}"
    ;;
  version)
    run_image "$IMAGE" --version
    run_image --entrypoint /usr/bin/oiiotool "$IMAGE" --version
    ;;
  with-env)
    if [[ "$#" -eq 0 ]]; then
      echo "oracle container: with-env requires a command" >&2
      usage
      exit 2
    fi
    shim_dir="$(mktemp -d /tmp/blender-web-oracle.XXXXXX)"
    ln -s "$SCRIPT_SOURCE" "$shim_dir/blender-oracle"
    ln -s "$SCRIPT_SOURCE" "$shim_dir/oiiotool"
    cleanup_shims() {
      rm -f "$shim_dir/blender-oracle" "$shim_dir/oiiotool"
      rmdir "$shim_dir" 2>/dev/null || true
    }
    trap cleanup_shims EXIT
    set +e
    BLENDER_BIN="$shim_dir/blender-oracle" PATH="$shim_dir:$PATH" "$@"
    command_status=$?
    set -e
    exit "$command_status"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "oracle container: unknown command: $command_name" >&2
    usage
    exit 2
    ;;
esac

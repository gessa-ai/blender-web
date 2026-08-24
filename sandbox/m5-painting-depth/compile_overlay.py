#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compile a patched painting source with a locked product graph's exact command."""

from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commands-log", type=Path, required=True)
    parser.add_argument("--relative", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    lines = args.commands_log.read_text(encoding="utf-8").splitlines()
    source_suffix = "/" + args.relative.as_posix()
    matches = [line for line in lines if line.rstrip().endswith(source_suffix)]
    if len(matches) != 1:
        raise SystemExit(
            f"expected one compile command for {args.relative}, found {len(matches)}"
        )

    argv = shlex.split(matches[0])
    while "-MD" in argv:
        argv.remove("-MD")
    for option in ("-MT", "-MF"):
        while option in argv:
            index = argv.index(option)
            del argv[index : index + 2]

    source_index = next(
        (index for index, value in enumerate(argv) if value.endswith(source_suffix)), None
    )
    if source_index is None:
        raise SystemExit("compile source argument missing")
    output_index = argv.index("-o") + 1
    source = args.source.resolve()
    argv[source_index] = str(source)
    argv[output_index] = str(args.output.resolve())
    argv.insert(source_index, "-I" + str(source.parent))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(argv, check=False)
    if result.returncode != 0:
        return result.returncode
    if not args.output.is_file() or args.output.stat().st_size == 0:
        raise SystemExit("scratch object missing after successful compiler exit")
    print(
        "M5_PAINTING_DEPTH_TU_COMPILE_PASS "
        f"source={args.relative} compiler={Path(argv[0]).name} "
        f"bytes={args.output.stat().st_size}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

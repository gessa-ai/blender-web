#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0

"""Adversarial checks for buildwrap's same-second log allocation."""

from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FIXED_STAMP = "20991231T235959"
LOG_PATTERN = re.compile(
    rf"^ledger/buildlogs/{FIXED_STAMP}-[0-9]+(?:-[0-9]+)?[.]log$"
)


def install_fixture(root: Path) -> tuple[Path, dict[str, str]]:
    wrapper = root / "harness" / "buildwrap.sh"
    wrapper.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "harness" / "buildwrap.sh", wrapper)

    fake_bin = root / "fake-bin"
    fake_bin.mkdir()
    fake_date = fake_bin / "date"
    fake_date.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"${1-}\" = -u ] && [ \"${2-}\" = +%Y%m%dT%H%M%S ]; then\n"
        f"  printf '%s\\n' {FIXED_STAMP}\n"
        "else\n"
        "  exec /usr/bin/date \"$@\"\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_date.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    return wrapper, env


def invoke(wrapper: Path, env: dict[str, str], label: str) -> tuple[str, Path]:
    result = subprocess.run(
        [str(wrapper), "/usr/bin/printf", "%s", label],
        cwd=wrapper.parents[1],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"wrapper failed for {label!r}: rc={result.returncode} stderr={result.stderr!r}"
        )
    match = re.search(r"\[log: (ledger/buildlogs/[^]]+[.]log)\]", result.stdout)
    if match is None:
        raise AssertionError(f"missing log path for {label!r}: {result.stdout!r}")
    relative = match.group(1)
    if LOG_PATTERN.fullmatch(relative) is None:
        raise AssertionError(f"unexpected collision-proof log name: {relative!r}")
    return label, wrapper.parents[1] / relative


def invoke_forced_collisions(
    wrapper: Path, env: dict[str, str]
) -> list[tuple[str, Path]]:
    """Source concurrent wrappers under one Bash PID to force suffix allocation."""
    count = 16
    script = f"""
for index in $(seq 0 {count - 1}); do
  (
    set -- /usr/bin/printf %s "forced-$index"
    source "$0"
  ) &
done
wait
"""
    result = subprocess.run(
        ["/bin/bash", "-c", script, str(wrapper)],
        cwd=wrapper.parents[1],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"forced-collision run failed: rc={result.returncode} stderr={result.stderr!r}"
        )

    relatives = re.findall(r"\[log: (ledger/buildlogs/[^]]+[.]log)\]", result.stdout)
    if len(relatives) != count or len(set(relatives)) != count:
        raise AssertionError(
            f"forced-collision log paths are not unique: {len(relatives)=}"
        )

    pid_pattern = re.compile(
        rf"^{FIXED_STAMP}-([0-9]+)(?:-[0-9]+)?[.]log$"
    )
    pids = set()
    forced_results = []
    for relative in relatives:
        if LOG_PATTERN.fullmatch(relative) is None:
            raise AssertionError(f"unexpected forced-collision log name: {relative!r}")
        path = wrapper.parents[1] / relative
        match = pid_pattern.fullmatch(path.name)
        if match is None:
            raise AssertionError(f"could not parse allocator PID: {path.name!r}")
        pids.add(match.group(1))
        forced_results.append((path.read_text(encoding="utf-8"), path))

    if len(pids) != 1:
        raise AssertionError(f"fixture did not force one allocator basename: {pids!r}")
    expected = {f"forced-{index}" for index in range(count)}
    if {label for label, _path in forced_results} != expected:
        raise AssertionError("forced-collision log content was lost or overwritten")
    return forced_results


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="bw-buildwrap-selfcheck-") as tmp:
        root = Path(tmp)
        wrapper, env = install_fixture(root)

        labels = [f"sequential-{index}" for index in range(4)]
        results = [invoke(wrapper, env, label) for label in labels]

        concurrent_labels = [f"concurrent-{index}" for index in range(32)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
            futures = [
                pool.submit(invoke, wrapper, env, label) for label in concurrent_labels
            ]
            results.extend(future.result() for future in futures)

        results.extend(invoke_forced_collisions(wrapper, env))

        paths = [path for _label, path in results]
        if len(set(paths)) != len(paths):
            raise AssertionError("same-second wrapper invocations reused a log path")

        on_disk = sorted((root / "ledger" / "buildlogs").glob("*.log"))
        if set(on_disk) != set(paths):
            raise AssertionError(
                f"log inventory mismatch: expected={len(paths)} actual={len(on_disk)}"
            )
        for label, path in results:
            if path.read_text(encoding="utf-8") != label:
                raise AssertionError(f"log content was overwritten: {path.name}")

    print(
        "BUILDWRAP_COLLISION_SELFCHECK_OK "
        "sequential=4 concurrent=32 forced_collision=16 unique=52"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

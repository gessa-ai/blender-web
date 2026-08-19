# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Execute the exact embedded runtime state-monitor predicate."""

from pathlib import Path
import re


DRIVER = Path(__file__).with_name("verify_blender_split_runtime.mjs")


def main() -> None:
    source = DRIVER.read_text(encoding="utf-8")
    match = re.search(r"const PY_MONITOR = String\.raw`([\s\S]*?)`;", source)
    assert match, "embedded Python monitor missing"
    monitor = match.group(1)
    start = monitor.index('    signature=(s["mode"],s["verts"]) if s is not None else None')
    end = monitor.index(
        '    if s is not None and s["mode"] == "OBJECT" and s["verts"] > 8', start
    )
    exact_block = monitor[start:end]
    namespace: dict[str, object] = {}
    exec(
        "_bwsr={}\nemitted=[]\n"
        "def _bwsr_emit(kind,value): emitted.append((kind,dict(value)))\n"
        "def step(s):\n" + exact_block,
        namespace,
    )
    step = namespace["step"]
    emitted = namespace["emitted"]
    object_16 = {"mode": "OBJECT", "verts": 16}
    object_24 = {"mode": "OBJECT", "verts": 24}
    step(object_16)
    step(object_16)
    step(object_24)
    assert [row[1]["verts"] for row in emitted] == [16, 24]
    assert object_16["mode"] == object_24["mode"]
    assert object_16["verts"] != object_24["verts"]
    assert not (object_16["mode"] != object_24["mode"]), "old mode-only oracle control"
    print("BW_RUNTIME_STATE_MONITOR_TEST PASS same-mode-topology=1 duplicate-suppressed=1")


if __name__ == "__main__":
    main()

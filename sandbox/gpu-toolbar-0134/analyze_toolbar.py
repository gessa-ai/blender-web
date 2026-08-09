#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reproduce the r58 toolbar premise-correction measurements."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
THRESHOLD = 0.016

INPUTS = {
    "native": ROOT / "sandbox/m4-golden-prep/goldens/workspace_1280x720.png",
    "pre0134": ROOT / "sandbox/i18n-r45/captures/r47-workspace_1280x720.png",
    "current": ROOT / "sandbox/m4-d9-gate/evidence/workspace_1280x720.png",
    "r28b_baseline": ROOT
    / "platform_web/shell/evidence/m4-r28b-baseline-00-fullwindow.png",
    "r28b_alwaysload": ROOT
    / "platform_web/shell/evidence/m4-r28b-ab-alwaysload-00-fullwindow.png",
}

REGIONS = {
    "toolbar": (0, 28, 60, 649),
    "icon_strip": (7, 52, 52, 456),
    "seam": (48, 28, 64, 649),
}

PARTITIONS = {
    "toolbar": (0, 28, 60, 649),
    "viewport": (60, 28, 1051, 649),
    "right_rail": (1051, 28, 1280, 649),
    "bottom": (0, 649, 1280, 720),
    "topbar": (0, 0, 1280, 28),
}


def load(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def crop(image: np.ndarray, rect: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = rect
    return image[y0:y1, x0:x1]


def delta(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.max(np.abs(a.astype(np.float32) - b.astype(np.float32)) / 255.0, axis=2)


def stats(a: np.ndarray, b: np.ndarray) -> tuple[int, int, float, float]:
    difference = delta(a, b)
    failed = int(np.count_nonzero(difference > THRESHOLD))
    total = int(difference.size)
    return failed, total, 100.0 * failed / total, float(difference.max())


def components(mask: np.ndarray, x_offset: int = 0, y_offset: int = 0):
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    output = []
    for y, x in zip(*np.where(mask)):
        if seen[y, x]:
            continue
        stack = [(int(y), int(x))]
        seen[y, x] = True
        points = []
        while stack:
            current_y, current_x = stack.pop()
            points.append((current_y, current_x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    next_y = current_y + dy
                    next_x = current_x + dx
                    if not (0 <= next_y < height and 0 <= next_x < width):
                        continue
                    if mask[next_y, next_x] and not seen[next_y, next_x]:
                        seen[next_y, next_x] = True
                        stack.append((next_y, next_x))
        xs = [point[1] + x_offset for point in points]
        ys = [point[0] + y_offset for point in points]
        output.append(
            {
                "size": len(points),
                "bbox": (min(xs), min(ys), max(xs), max(ys)),
                "points": points,
            }
        )
    return sorted(output, key=lambda item: item["size"], reverse=True)


def format_stats(values: tuple[int, int, float, float]) -> str:
    failed, total, percent, maximum = values
    return f"failed={failed}/{total} percent={percent:.6f} max={maximum:.9f}"


def main() -> None:
    print("# SPDX-FileCopyrightText: 2026 blender-web contributors")
    print("# SPDX-License-Identifier: CC0-1.0")
    print(f"threshold=max_channel_abs>{THRESHOLD}")
    images = {name: load(path) for name, path in INPUTS.items()}
    for name, path in INPUTS.items():
        height, width = images[name].shape[:2]
        print(f"input {name}: path={path.relative_to(ROOT)} size={width}x{height} sha256={digest(path)}")

    print("\n[toolbar comparisons against native]")
    for name, rect in REGIONS.items():
        native = crop(images["native"], rect)
        print(f"{name} rect={rect}")
        print(f"  pre0134 {format_stats(stats(native, crop(images['pre0134'], rect)))}")
        print(f"  current {format_stats(stats(native, crop(images['current'], rect)))}")

    toolbar_rect = REGIONS["toolbar"]
    current_toolbar_diff = delta(
        crop(images["native"], toolbar_rect), crop(images["current"], toolbar_rect)
    )
    toolbar_components = components(
        current_toolbar_diff > THRESHOLD,
        x_offset=toolbar_rect[0],
        y_offset=toolbar_rect[1],
    )
    print("\n[current toolbar connected components, 8-connected]")
    print(f"count={len(toolbar_components)}")
    for item in toolbar_components:
        print(f"size={item['size']} bbox={item['bbox']}")

    print("\n[icon-strip coordinate shift control]")
    x0, y0, x1, y1 = REGIONS["icon_strip"]
    native = images["native"][y0:y1, x0:x1]
    for candidate_name in ("pre0134", "current"):
        print(candidate_name)
        candidate = images[candidate_name]
        for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
            shifted = candidate[y0 + dy : y1 + dy, x0 + dx : x1 + dx]
            print(f"  dx={dx:+d} dy={dy:+d} {format_stats(stats(native, shifted))}")

    print("\n[r28b load/store A/B baseline versus always-load]")
    for name, rect in REGIONS.items():
        print(
            f"{name} {format_stats(stats(crop(images['r28b_baseline'], rect), crop(images['r28b_alwaysload'], rect)))}"
        )

    print("\n[current D-9 disjoint mass]")
    partition_failed = 0
    for name, rect in PARTITIONS.items():
        values = stats(crop(images["native"], rect), crop(images["current"], rect))
        partition_failed += values[0]
        print(f"{name} rect={rect} {format_stats(values)}")
    print(f"partition_failed_sum={partition_failed}")
    print(
        "whole_window "
        + format_stats(stats(images["native"], images["current"]))
    )

    bottom_rect = PARTITIONS["bottom"]
    bottom_native = crop(images["native"], bottom_rect)
    bottom_current = crop(images["current"], bottom_rect)
    bottom_mask = delta(bottom_native, bottom_current) > THRESHOLD
    bottom_components = components(bottom_mask, y_offset=bottom_rect[1])
    perimeter = bottom_components[0]
    status_total = sum(item["size"] for item in bottom_components[1:])
    print("\n[current bottom connected components, 8-connected]")
    print(f"count={len(bottom_components)}")
    print(f"perimeter size={perimeter['size']} bbox={perimeter['bbox']}")
    print(f"status_hints components={len(bottom_components) - 1} pixels={status_total}")
    for item in bottom_components[1:]:
        print(f"  size={item['size']} bbox={item['bbox']}")

    pairs = Counter(
        (
            tuple(int(value) for value in bottom_native[y, x]),
            tuple(int(value) for value in bottom_current[y, x]),
        )
        for y, x in perimeter["points"]
    )
    print("perimeter_color_pairs_top2")
    for (native_rgb, current_rgb), count in pairs.most_common(2):
        print(f"  pixels={count} native={native_rgb} current={current_rgb}")


if __name__ == "__main__":
    main()

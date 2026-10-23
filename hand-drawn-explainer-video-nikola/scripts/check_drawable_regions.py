#!/usr/bin/env python3
"""检查逐笔故事源图的语义区域是否适合独立落墨。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def rect(element: dict) -> tuple[int, int, int, int]:
    region = element["region"]
    return int(region["x"]), int(region["y"]), int(region["width"]), int(region["height"])


def intersection(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))


def gap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = max(bx - (ax + aw), ax - (bx + bw), 0)
    dy = max(by - (ay + ah), ay - (by + bh), 0)
    return math.hypot(dx, dy)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查逐笔源图的区域重叠、留白和跨区连通线")
    parser.add_argument("image")
    parser.add_argument("annotation")
    parser.add_argument("--report", required=True)
    parser.add_argument("--min-gutter-ratio", type=float, default=0.035,
                        help="区域矩形最小间距占画面宽度的比例，默认 3.5%%")
    parser.add_argument("--bridge-min-pixels", type=int, default=80,
                        help="同时进入多个区域的连通前景最小像素数")
    args = parser.parse_args()

    image = cv2.imread(args.image, cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"无法读取图片：{args.image}")
    annotation = json.loads(Path(args.annotation).read_text(encoding="utf-8"))
    height, width = image.shape[:2]
    expected = annotation.get("canvas", {})
    errors: list[dict] = []
    warnings: list[dict] = []
    elements = sorted(annotation.get("elements", []), key=lambda item: item.get("sequence", 0))
    regions = [(item.get("id", str(index)), rect(item)) for index, item in enumerate(elements)]

    if expected.get("width") != width or expected.get("height") != height:
        errors.append({"type": "canvas_mismatch", "image": [width, height], "annotation": expected})

    for region_id, (x, y, region_width, region_height) in regions:
        if min(x, y, region_width, region_height) < 0 or x + region_width > width or y + region_height > height or region_width == 0 or region_height == 0:
            errors.append({"type": "region_out_of_bounds", "region": region_id,
                           "rect": [x, y, region_width, region_height]})

    min_gutter = round(width * args.min_gutter_ratio)
    pair_metrics = []
    for index, (a_id, a) in enumerate(regions):
        for b_id, b in regions[index + 1:]:
            overlap = intersection(a, b)
            distance = gap(a, b)
            pair_metrics.append({"a": a_id, "b": b_id, "overlapPixels": overlap,
                                 "gutterPixels": round(distance, 1)})
            if overlap:
                errors.append({"type": "region_overlap", "a": a_id, "b": b_id, "pixels": overlap})
            elif distance < min_gutter:
                warnings.append({"type": "gutter_too_small", "a": a_id, "b": b_id,
                                 "pixels": round(distance, 1), "recommendedMinimum": min_gutter})

    # 清晰墨线和高饱和色块进入前景；亮、低饱和的轻微纸纹通常被排除。
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    foreground = ((gray < 150) | ((hsv[:, :, 1] > 70) & (hsv[:, :, 2] < 235))).astype(np.uint8)
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground, 8)
    region_masks = []
    for _, (x, y, region_width, region_height) in regions:
        mask = np.zeros((height, width), np.uint8)
        mask[y:y + region_height, x:x + region_width] = 1
        region_masks.append(mask)
    bridges = []
    for label in range(1, component_count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < args.bridge_min_pixels:
            continue
        component = labels == label
        touched = [regions[index][0] for index, mask in enumerate(region_masks)
                   if np.count_nonzero(component & (mask > 0)) >= 12]
        if len(touched) > 1:
            bridges.append({"regions": touched, "pixels": area})
    if bridges:
        errors.append({"type": "foreground_bridges_regions", "components": bridges})

    report = {
        "passed": not errors,
        "image": str(Path(args.image).resolve()),
        "annotation": str(Path(args.annotation).resolve()),
        "canvas": [width, height],
        "minGutterPixels": min_gutter,
        "pairs": pair_metrics,
        "errors": errors,
        "warnings": warnings,
        "note": "自动检查用于拦截明显重叠和跨区连线，仍需人工逐区播放确认。",
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

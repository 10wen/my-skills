#!/usr/bin/env python3
"""白板动画 annotation.json 的轻量预检。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_rect(rect: object, prefix: str, canvas_w: int, canvas_h: int) -> list[str]:
    if not isinstance(rect, dict):
        return [f"{prefix} 必须是对象"]
    errors: list[str] = []
    for key in ("x", "y", "width", "height"):
        if not _is_int(rect.get(key)):
            errors.append(f"{prefix}.{key} 必须是整数")
    if errors:
        return errors
    x, y = rect["x"], rect["y"]
    width, height = rect["width"], rect["height"]
    if width <= 0 or height <= 0:
        errors.append(f"{prefix} 的宽高必须大于 0")
    if x < 0 or y < 0 or x + width > canvas_w or y + height > canvas_h:
        errors.append(f"{prefix} 超出画布 {canvas_w}x{canvas_h}")
    return errors


def validate_annotation(annotation: object, image_size: tuple[int, int] | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(annotation, dict):
        return ["标注根节点必须是对象"], warnings

    canvas = annotation.get("canvas")
    if not isinstance(canvas, dict) or not _is_int(canvas.get("width")) or not _is_int(canvas.get("height")):
        return ["canvas.width 和 canvas.height 必须是整数"], warnings
    canvas_w, canvas_h = canvas["width"], canvas["height"]
    if canvas_w <= 0 or canvas_h <= 0:
        errors.append("画布宽高必须大于 0")
    if image_size and image_size != (canvas_w, canvas_h):
        errors.append(f"标注画布 {canvas_w}x{canvas_h} 与原图 {image_size[0]}x{image_size[1]} 不一致")

    elements = annotation.get("elements")
    if not isinstance(elements, list) or not elements:
        return errors + ["elements 必须是非空数组"], warnings

    windows: list[tuple[int, int, str]] = []
    sequences: list[int] = []
    for index, element in enumerate(elements, start=1):
        prefix = f"elements[{index}]"
        if not isinstance(element, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        label = str(element.get("label") or element.get("id") or prefix)
        sequence = element.get("sequence")
        if not _is_int(sequence) or sequence < 1:
            errors.append(f"{label}.sequence 必须是从 1 开始的整数")
        else:
            sequences.append(sequence)
        errors.extend(_check_rect(element.get("region"), f"{label}.region", canvas_w, canvas_h))
        reveal = element.get("reveal")
        if not isinstance(reveal, dict):
            errors.append(f"{label}.reveal 必须是对象")
            continue
        start_ms, duration_ms = reveal.get("startMs"), reveal.get("durationMs")
        if not _is_int(start_ms) or start_ms < 0:
            errors.append(f"{label}.reveal.startMs 必须是非负整数")
        if not _is_int(duration_ms) or duration_ms <= 0:
            errors.append(f"{label}.reveal.durationMs 必须是正整数")
        if _is_int(start_ms) and _is_int(duration_ms) and duration_ms > 0:
            windows.append((start_ms, start_ms + duration_ms, label))
        protected = reveal.get("protectedRegions", [])
        if not isinstance(protected, list):
            errors.append(f"{label}.reveal.protectedRegions 必须是数组")
        else:
            for protected_index, rect in enumerate(protected, start=1):
                errors.extend(_check_rect(rect, f"{label}.protectedRegions[{protected_index}]", canvas_w, canvas_h))

    if sequences and sorted(sequences) != list(range(1, len(sequences) + 1)):
        warnings.append("sequence 不是从 1 开始连续排列；实际渲染顺序以 startMs 为准")
    windows.sort()
    for previous, current in zip(windows, windows[1:]):
        if current[0] < previous[1]:
            warnings.append(f"{previous[2]} 与 {current[2]} 的绘制时间窗重叠")
    if windows:
        last_end = max(end for _, end, _ in windows)
        scene_ms = annotation.get("sceneDurationMs")
        if _is_int(scene_ms) and scene_ms < last_end + 500:
            warnings.append(f"sceneDurationMs 建议至少为 {last_end + 500}，以保留 0.5 秒完整画面")
    return errors, warnings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="检查白板动画 annotation.json")
    parser.add_argument("annotation")
    args = parser.parse_args(argv)
    try:
        annotation = json.loads(Path(args.annotation).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[err] 无法读取标注: {exc}", file=sys.stderr)
        return 1
    errors, warnings = validate_annotation(annotation)
    for warning in warnings:
        print(f"[warn] {warning}")
    for error in errors:
        print(f"[err] {error}", file=sys.stderr)
    if errors:
        return 1
    print("ANNOTATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

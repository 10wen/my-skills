#!/usr/bin/env python3
"""Extract exact semantic-boundary frames into a labeled contact sheet.

The input JSON is intentionally project-agnostic:
{
  "checks": [
    {"label": "scene-01-left-end", "timeMs": 3200},
    {"label": "scene-01-right-start", "timeMs": 3500}
  ]
}
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import av
from PIL import Image, ImageDraw, ImageFont


def frame_at(container: av.container.InputContainer, stream: av.video.stream.VideoStream,
             time_ms: int) -> Image.Image:
    target_seconds = max(0, time_ms) / 1000
    container.seek(int(target_seconds * 1_000_000), any_frame=False, backward=True)
    candidate = None
    for frame in container.decode(stream):
        candidate = frame
        if frame.time is not None and frame.time >= target_seconds:
            break
    if candidate is None:
        raise RuntimeError(f"无法读取 {time_ms}ms 附近的视频帧")
    return candidate.to_image().convert("RGB")


def main() -> int:
    parser = argparse.ArgumentParser(description="按语义边界时间抽帧并生成联系表")
    parser.add_argument("--video", required=True)
    parser.add_argument("--checks", required=True, help="包含 checks[{label,timeMs}] 的 JSON")
    parser.add_argument("--output", required=True)
    parser.add_argument("--columns", type=int, default=2)
    parser.add_argument("--thumb-width", type=int, default=720)
    args = parser.parse_args()

    video = Path(args.video).resolve()
    checks_path = Path(args.checks).resolve()
    output = Path(args.output).resolve()
    data = json.loads(checks_path.read_text(encoding="utf-8"))
    checks = data.get("checks", [])
    if not checks:
        raise SystemExit("checks 不能为空")

    frames: list[tuple[str, int, Image.Image]] = []
    with av.open(str(video)) as container:
        stream = container.streams.video[0]
        for item in checks:
            label = str(item.get("label", "check"))
            time_ms = int(item["timeMs"])
            if time_ms < 0:
                raise ValueError(f"检查点不能为负数：{label}={time_ms}ms")
            frames.append((label, time_ms, frame_at(container, stream, time_ms)))

    columns = max(1, args.columns)
    margin = 20
    label_height = 44
    sample = frames[0][2]
    thumb_width = max(240, args.thumb_width)
    thumb_height = round(sample.height * thumb_width / sample.width)
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new(
        "RGB",
        (columns * thumb_width + (columns + 1) * margin,
         rows * (thumb_height + label_height) + (rows + 1) * margin),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (label, time_ms, frame) in enumerate(frames):
        row, column = divmod(index, columns)
        x = margin + column * (thumb_width + margin)
        y = margin + row * (thumb_height + label_height + margin)
        thumb = frame.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (x, y + label_height))
        safe_label = label.encode("ascii", "replace").decode("ascii")
        draw.text((x, y + 8), f"{safe_label}  {time_ms / 1000:.3f}s", fill="black", font=font)

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)
    print(json.dumps({
        "output": str(output),
        "checks": len(frames),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Finalize multi-scene stroke-story videos deterministically.

The helper always normalizes scene size, frame rate and timestamps. Approved
source images are overlaid only when the caller explicitly requests it after a
visual end-frame comparison; unconditional overlays can create a late crop/zoom
flash even when the stroke render is already complete.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True, encoding="utf-8", errors="replace")
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"命令失败（{completed.returncode}）：{detail[-3000:]}")


def ass_filter(path: Path) -> str:
    value = path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
    return f"ass='{value}'"


def main() -> int:
    parser = argparse.ArgumentParser(description="统一时间基准并合成逐笔故事视频；源图补全须显式启用")
    parser.add_argument("--manifest", required=True, help="项目清单 JSON")
    parser.add_argument("--ffmpeg", required=True, help="可运行的 FFmpeg 绝对路径")
    parser.add_argument("--output", required=True, help="最终 MP4")
    parser.add_argument("--fade-ms", type=int, default=650, help="每幕末尾源图淡入时长，默认650ms")
    parser.add_argument("--lead-ms", type=int, default=900, help="淡入开始距幕尾的时间，默认900ms")
    parser.add_argument(
        "--source-overlay",
        choices=("never", "always"),
        default="never",
        help="是否在每幕末尾淡入批准源图；默认 never，只有末帧对照确认漏色后才用 always",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    root = manifest_path.parent
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    ffmpeg = str(Path(args.ffmpeg).resolve())
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    width = int(data.get("width", 1920))
    height = int(data.get("height", 1080))
    fps = int(data.get("fps", 30))
    scenes = data.get("scenes", [])
    if not scenes:
        raise SystemExit("manifest.scenes 不能为空")

    with tempfile.TemporaryDirectory(prefix="stroke-finalize-") as tmp_name:
        tmp = Path(tmp_name)
        finalized: list[Path] = []
        total_ms = 0
        for index, scene in enumerate(scenes, start=1):
            video = (root / scene["video"]).resolve()
            duration_ms = int(scene["durationMs"])
            if not video.is_file():
                raise FileNotFoundError(f"第{index}幕视频缺失：{video}")
            total_ms += duration_ms
            scene_out = tmp / f"scene-{index:03d}.mp4"
            if args.source_overlay == "always":
                image_value = scene.get("image")
                if not image_value:
                    raise KeyError(f"第{index}幕启用源图补全但未提供 image")
                image = (root / image_value).resolve()
                if not image.is_file():
                    raise FileNotFoundError(f"第{index}幕源图缺失：{image}")
                fade_ms = min(args.fade_ms, max(1, duration_ms // 3))
                fade_start = max(0, duration_ms - args.lead_ms) / 1000
                overlay = (
                    f"[1:v]scale={width}:{height},format=rgba,"
                    f"fade=t=in:st={fade_start:.3f}:d={fade_ms / 1000:.3f}:alpha=1[full];"
                    "[0:v][full]overlay=0:0:shortest=1,format=yuv420p"
                )
                run([
                    ffmpeg, "-loglevel", "error", "-y", "-i", str(video), "-loop", "1", "-i", str(image),
                    "-filter_complex", overlay, "-t", f"{duration_ms / 1000:.3f}", "-r", str(fps),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-an", str(scene_out),
                ])
            else:
                run([
                    ffmpeg, "-loglevel", "error", "-y", "-i", str(video),
                    "-vf", f"fps={fps},scale={width}:{height}:flags=lanczos,format=yuv420p",
                    "-t", f"{duration_ms / 1000:.3f}", "-r", str(fps),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-an", str(scene_out),
                ])
            finalized.append(scene_out)

        concat_file = tmp / "concat.txt"
        concat_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in finalized), encoding="utf-8")
        merged = tmp / "visual.mp4"
        run([
            ffmpeg, "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-vf", f"fps={fps},scale={width}:{height}:flags=lanczos,format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-an", str(merged),
        ])

        narration = data.get("narration")
        ass = data.get("ass")
        if narration:
            command = [ffmpeg, "-loglevel", "error", "-y", "-i", str(merged), "-i", str((root / narration).resolve())]
            if ass:
                command += ["-vf", ass_filter(root / ass)]
            command += [
                "-af", "apad=pad_dur=1", "-t", f"{total_ms / 1000:.3f}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
            ]
            run(command)
        else:
            output.write_bytes(merged.read_bytes())

    print(json.dumps({
        "output": str(output),
        "durationMs": total_ms,
        "scenes": len(scenes),
        "sourceOverlay": args.source_overlay,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

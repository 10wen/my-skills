"""Validate the bundled stroke-story backend with a local smoke render.

This script never installs dependencies or calls a paid API.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_BACKEND = ROOT / "vendor" / "srt-whiteboard-animation"


def default_backend_python(backend: Path) -> Path:
    windows = backend / ".venv" / "Scripts" / "python.exe"
    posix = backend / ".venv" / "bin" / "python"
    return windows if windows.exists() or not posix.exists() else posix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", type=Path, default=BUNDLED_BACKEND)
    parser.add_argument("--backend-python", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    backend = args.backend.resolve()
    python = (args.backend_python or default_backend_python(backend)).resolve()
    checks: list[dict[str, object]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    required = [
        backend / "scripts" / "render_stream_whiteboard.py",
        backend / "scripts" / "stream_render.py",
        backend / "scripts" / "annotation_schema.py",
        backend / "assets" / "drawing-hand.png",
    ]
    record("backend_files", all(path.is_file() for path in required), "Require bundled renderer, schema, core and hand asset.")
    record("backend_python", python.is_file(), "Require an existing isolated Python executable.")

    if all(path.is_file() for path in required) and python.is_file():
        env_check = subprocess.run(
            [str(python), "-c", "import av,cv2,numpy; from PIL import Image; print('ok')"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        record("python_dependencies", env_check.returncode == 0, "Require PyAV, OpenCV, NumPy and Pillow.")

        help_check = subprocess.run(
            [str(python), str(required[0]), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        help_text = help_check.stdout + help_check.stderr
        record(
            "renderer_options",
            help_check.returncode == 0 and "skeleton" in help_text and "contour-wipe" in help_text,
            "Renderer must expose skeleton ink and contour-wipe color modes.",
        )

        if env_check.returncode == 0 and help_check.returncode == 0:
            with tempfile.TemporaryDirectory(prefix="stroke-story-preflight-") as tmp:
                tmp_path = Path(tmp)
                image = tmp_path / "smoke.png"
                annotation = tmp_path / "smoke.annotation.json"
                output = tmp_path / "smoke.mp4"
                make_assets = (
                    "from PIL import Image,ImageDraw; import json,sys; "
                    "im=Image.new('RGB',(360,640),(245,235,215)); d=ImageDraw.Draw(im); "
                    "d.ellipse((80,130,280,330),outline=(35,35,35),width=12); "
                    "d.line((110,410,250,520),fill=(35,35,35),width=12); im.save(sys.argv[1]); "
                    "a={'sceneId':'smoke','canvas':{'width':360,'height':640},'sceneDurationMs':1200,'elements':["
                    "{'id':'main','label':'smoke','sequence':1,'narrativeRole':'smoke','subtitle':'smoke','type':'character',"
                    "'region':{'x':40,'y':80,'width':280,'height':500},'reveal':{'direction':'top_to_bottom','startMs':100,'durationMs':900,'maskPaddingPx':10,'protectedRegions':[]},"
                    "'handPath':{'start':[180,100],'end':[180,560],'easing':'easeInOut'}}]}; "
                    "open(sys.argv[2],'w',encoding='utf-8').write(json.dumps(a,ensure_ascii=False))"
                )
                asset_result = subprocess.run(
                    [str(python), "-c", make_assets, str(image), str(annotation)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                render_result = subprocess.run(
                    [
                        str(python), str(required[0]), str(image), str(annotation), str(output), str(required[3]),
                        "--ink-path", "skeleton", "--color-fill", "contour-wipe", "--cap-long-edge", "320",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=90,
                ) if asset_result.returncode == 0 else None
                record(
                    "skeleton_smoke_render",
                    bool(render_result and render_result.returncode == 0 and output.is_file() and output.stat().st_size > 1000),
                    "Render a small local MP4 without network or paid requests.",
                )
                if output.is_file():
                    decode = subprocess.run(
                        [str(python), "-c", "import av,sys; c=av.open(sys.argv[1]); print(sum(1 for _ in c.decode(video=0)))", str(output)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    try:
                        frame_count = int(decode.stdout.strip())
                    except ValueError:
                        frame_count = 0
                    record("smoke_video_decode", decode.returncode == 0 and frame_count > 1, "Smoke MP4 must decode more than one frame.")

    report = {
        "passed": bool(checks) and all(bool(item["passed"]) for item in checks),
        "paid_requests": 0,
        "installs": 0,
        "backend": str(backend),
        "backend_provenance": "bundled vendor/srt-whiteboard-animation (MIT)",
        "checks": checks,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Static regression checks for hand-drawn-explainer-video-nikola."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    skill = text("SKILL.md")
    zh = text("SKILL.zh-CN.md")
    workflow = text("references/stroke-story-workflow.md")
    islands = text("references/semantic-island-storytelling.md")
    quality = text("references/quality-and-delivery.md")
    prefs = json.loads(text("preferences.json"))
    checks = {
        "frontmatter_name": "name: hand-drawn-explainer-video-nikola" in skill,
        "trigger_routes": all(x in skill for x in (
            "两条制作路线", "边讲边画", "双语义岛只是逐笔故事的一种画面组织方法", "程序动画")),
        "bundled_backend": "vendor/srt-whiteboard-animation" in skill and "不包含第二份 `SKILL.md`" in skill,
        "no_silent_svg_fallback": "不以 SVG 动画冒充真实逐笔绘制" in skill,
        "liufei_voice_default": prefs.get("speaker") == "zh_male_liufei_uranus_bigtts"
        and prefs.get("voice_resource") == "seed-tts-2.0"
        and prefs.get("voice_provider") == "volcengine_openspeech",
        "credential_policy": "Never store credentials" in prefs.get("credentials", ""),
        "chinese_entry": "经过解码和画面抽检的 MP4" in zh,
        "backend_runtime_files": all((ROOT / p).is_file() for p in (
            "vendor/srt-whiteboard-animation/scripts/render_stream_whiteboard.py",
            "vendor/srt-whiteboard-animation/scripts/annotation_schema.py",
            "vendor/srt-whiteboard-animation/assets/drawing-hand.png",
            "vendor/srt-whiteboard-animation/LICENSE",
            "vendor/srt-whiteboard-animation/UPSTREAM.md",
        )),
        "backend_not_triggerable": not (ROOT / "vendor/srt-whiteboard-animation/SKILL.md").exists(),
        "skeleton_default": prefs.get("stroke_story_ink_path") == "skeleton",
        "preflight_documented": "stroke_story_preflight.py" in workflow and "prepare_env.py" in workflow,
        "audio_complexity_budget": "区域可用时长 ÷ 线条与色块复杂度" in islands,
        "deterministic_keywords": "确定性 ASS/HTML 文字层" in islands,
        "hand_speed_boundary": "hand-follow" in workflow and "不改变旁白、笔迹" in workflow,
        "final_overlay_opt_in": "--source-overlay never" in workflow,
        "tail_frame_qa": "最后 0.3–0.5 秒" in quality,
        "style_docs": all((ROOT / p).is_file() for p in (
            "references/xiaohei-style.md", "references/q-human-story-style.md", "docs/STYLES.md")),
        "public_docs": all((ROOT / p).is_file() for p in (
            "README.md", "docs/INSTALL.md", "docs/CONFIGURATION.md", "SECURITY.md", "CONTRIBUTING.md")),
        "license_files": all((ROOT / p).is_file() for p in (
            "LICENSE", "LICENSE-MEDIA.md", "THIRD_PARTY_NOTICES.md",
            "references/hand-drawn-video-prompts-LICENSE.txt")),
        "readme_contact_and_routes": all(x in text("README.md") for x in (
            "https://x.com/Nikola314159", "商用Skills_完整手绘视频", "逐笔“边说边画”", "## 致谢")),
        "no_low_quality_tts_fallback": all(x in text("references/voiceover.md") for x in (
            "zh_male_liufei_uranus_bigtts", "电脑系统朗读", "edge-tts", "配音缺口")),
        "examples": all((ROOT / p).is_file() for p in (
            "examples/stroke-story/steve-jobs/steve-jobs-biography.mp4",
            "examples/stroke-story/yuefa-sanzhang/yuefa-sanzhang-16x9-stroke-story.mp4",
            "examples/stroke-story/yuefa-sanzhang/editable-project.zip",
            "examples/program-animation/skill-demo/index.html",
            "examples/program-animation/skill-demo/what-is-skill-sample.mp4",
        )),
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

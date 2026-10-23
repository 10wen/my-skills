# Contributing

Keep one triggerable Skill: do not add another nested `SKILL.md` under `vendor/` or examples. New behavior should state its trigger boundary, dependencies, cost/network effects and verification method.

Before a pull request:

1. Run `python scripts/setup_check.py` and `python scripts/quick_validate.py`.
2. Compile Python scripts and run relevant media smoke tests.
3. Check relative Markdown links and scan for credentials, personal paths and generated caches.
4. If updating the bundled backend, preserve its MIT license, update `UPSTREAM.md` and run `stroke_story_preflight.py`.
5. Do not commit `node_modules`, `.venv`, generated GSAP files, private narration or unlicensed media.

Style presets should be reproducible rules, not requests to imitate a living artist. Examples must disclose third-party names and provide the rights needed for public redistribution.

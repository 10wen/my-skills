# Upstream provenance

- Project: `srt-whiteboard-animation`
- Upstream: https://github.com/geeklee/srt-whiteboard-animation
- License: MIT; see `LICENSE` in this directory.
- Bundled snapshot commit: `325c5c71525ca17e0a0b91d0a6b000f9698feff0`
- Baseline parent: `523ae9398e8b270b29febdd003ca24e69f4ece41`

This repository bundles only the runtime scripts, preview asset, drawing-hand asset, tests and license. The upstream `SKILL.md`, agent metadata and Git history are intentionally excluded so this package exposes one triggerable Skill.

The bundled snapshot includes local renderer hardening used by the public Skill, including annotation-schema checks, hand-size controls, and installation from the repository's constrained `requirements-media.txt`. When updating it, compare upstream, retain the MIT notice, document the new commit and rerun the smoke render.

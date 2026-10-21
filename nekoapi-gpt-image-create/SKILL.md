---
name: nekoapi-gpt-image-create
description: Generate raster images with the user's NekoAPI-gpt-image provider and gpt-image-2, without changing the active chat model. Use when the user asks to create a new image, illustration, product visual, or other bitmap asset through NekoAPI. This skill generates images; it does not edit existing images.
---

# NekoAPI GPT Image Create

Use `scripts/generate.py` in this skill directory for image generation. It uses Python 3.11+ standard library only. It sends the prompt to the provider's `/images/generations` endpoint with `gpt-image-2` and saves the returned PNG.

## Credentials

The script reads the `NekoAPI-gpt-image` Codex provider from `~/.cc-switch/cc-switch.db` at runtime. The provider does not need to be active, so the chat model stays as it is. On another machine or agent environment without that CC Switch entry, set both `NEKOAPI_IMAGE_BASE_URL` (HTTPS URL ending in `/v1`) and `NEKOAPI_IMAGE_API_KEY` in the local process environment. `CC_SWITCH_DB` can point to a different CC Switch database. Never include a key in a command argument, prompt, output file, or chat response.

## Generate

Run with the Python 3.11+ interpreter available to the agent and the absolute path to this skill's script:

```bash
python3 /path/to/nekoapi-gpt-image-create/scripts/generate.py \
  --prompt "A small red paper lantern on a white background" \
  --quality medium \
  --size 1024x1024 \
  --out /absolute/path/to/output/imagegen/red-lantern.png
```

Replace the example path, prompt, and filename for the task. For a dry-run without an API call, add `--dry-run`. Use a fresh output filename; the script refuses to overwrite an existing image. Save project assets inside the relevant project, and report the final absolute path. Inspect the output before presenting it. If the agent interface supports inline local images, show the result inline.

The script supports new image generation only. For edits, use another appropriate tool or tell the user that this skill does not support editing.

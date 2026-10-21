"""Generate an image through NekoAPI without third-party Python packages."""

import argparse
import base64
import json
import os
import sqlite3
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PROVIDER_NAME = "NekoAPI-gpt-image"
DEFAULT_DB = Path.home() / ".cc-switch" / "cc-switch.db"


@dataclass(frozen=True)
class Provider:
    base_url: str
    api_key: str


def validate_provider(base_url: str, api_key: str) -> Provider:
    base_url = base_url.rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Image provider needs an HTTPS base URL")
    if not api_key:
        raise ValueError("Image provider API key is missing")
    return Provider(base_url, api_key)


def resolve_provider(db_path: Path = DEFAULT_DB) -> Provider:
    env_url = os.environ.get("NEKOAPI_IMAGE_BASE_URL", "")
    env_key = os.environ.get("NEKOAPI_IMAGE_API_KEY", "")
    if env_url or env_key:
        if not env_url or not env_key:
            raise ValueError(
                "Set both NEKOAPI_IMAGE_BASE_URL and NEKOAPI_IMAGE_API_KEY"
            )
        return validate_provider(env_url, env_key)

    db_path = Path(os.environ.get("CC_SWITCH_DB", str(db_path))).expanduser()
    if not db_path.is_file():
        raise ValueError(f"CC Switch database not found: {db_path}")
    with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT settings_config FROM providers WHERE app_type = ? AND name = ?",
            ("codex", PROVIDER_NAME),
        ).fetchone()
    if row is None:
        raise ValueError(f"CC Switch provider not found: {PROVIDER_NAME}")
    settings = json.loads(row[0])
    config = tomllib.loads(settings["config"])
    model_provider = config["model_providers"][config["model_provider"]]
    return validate_provider(
        model_provider["base_url"], settings["auth"]["OPENAI_API_KEY"]
    )


def build_payload(prompt: str, size: str, quality: str) -> dict:
    if not prompt.strip():
        raise ValueError("Prompt cannot be empty")
    return {
        "model": "gpt-image-2",
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": 1,
    }


def generate(provider: Provider, payload: dict) -> dict:
    request = Request(
        provider.base_url + "/images/generations",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + provider.api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=180) as response:
        return json.load(response)


def save_image(response: dict, output: Path) -> None:
    image = base64.b64decode(response["data"][0]["b64_json"], validate=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as image_file:
        image_file.write(image)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate an image via NekoAPI")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument(
        "--quality", choices=("low", "medium", "high", "auto"), default="medium"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        provider = resolve_provider()
        payload = build_payload(args.prompt, args.size, args.quality)
        if args.out.exists():
            raise FileExistsError(f"Output already exists: {args.out}")
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "endpoint": provider.base_url + "/images/generations",
                        "payload": payload,
                        "out": str(args.out),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        save_image(generate(provider, payload), args.out)
        print(f"Wrote {args.out.resolve()}")
        return 0
    except HTTPError as exc:
        try:
            detail = json.load(exc).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            detail = ""
        print(f"Image API returned HTTP {exc.code}: {detail}", file=sys.stderr)
    except (ValueError, KeyError, IndexError, TypeError, FileExistsError,
            tomllib.TOMLDecodeError, URLError, OSError) as exc:
        print(f"Image generation failed: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

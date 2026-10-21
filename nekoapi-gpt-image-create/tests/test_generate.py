import base64
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.generate import build_payload, resolve_provider, save_image


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "cc-switch.db"
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "CREATE TABLE providers (app_type TEXT, name TEXT, settings_config TEXT)"
            )
            for name, url, key in (
                ("NekoAPI-gpt-image", "https://image.example/v1", "image-key"),
                ("Chat", "https://chat.example/v1", "chat-key"),
            ):
                settings = {
                    "auth": {"OPENAI_API_KEY": key},
                    "config": (
                        'model_provider = "custom"\n'
                        '[model_providers.custom]\n'
                        f'base_url = "{url}"\n'
                    ),
                }
                connection.execute(
                    "INSERT INTO providers VALUES (?, ?, ?)",
                    ("codex", name, json.dumps(settings)),
                )

    def tearDown(self):
        self.temp.cleanup()

    def test_uses_named_cc_switch_provider(self):
        with patch.dict("os.environ", {}, clear=True):
            provider = resolve_provider(self.db)
        self.assertEqual(provider.base_url, "https://image.example/v1")
        self.assertEqual(provider.api_key, "image-key")

    def test_environment_pair_overrides_cc_switch(self):
        env = {
            "NEKOAPI_IMAGE_BASE_URL": "https://portable.example/v1/",
            "NEKOAPI_IMAGE_API_KEY": "portable-key",
        }
        with patch.dict("os.environ", env, clear=True):
            provider = resolve_provider(self.db)
        self.assertEqual(provider.base_url, "https://portable.example/v1")
        self.assertEqual(provider.api_key, "portable-key")

    def test_rejects_partial_environment_configuration(self):
        with patch.dict(
            "os.environ", {"NEKOAPI_IMAGE_API_KEY": "key"}, clear=True
        ):
            with self.assertRaisesRegex(ValueError, "both"):
                resolve_provider(self.db)


class GenerationTests(unittest.TestCase):
    def test_payload_uses_gpt_image_model(self):
        self.assertEqual(
            build_payload("A lantern", "1024x1024", "low"),
            {
                "model": "gpt-image-2",
                "prompt": "A lantern",
                "size": "1024x1024",
                "quality": "low",
                "n": 1,
            },
        )

    def test_saves_image_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "picture.png"
            response = {
                "data": [{"b64_json": base64.b64encode(b"image").decode()}]
            }
            save_image(response, output)
            self.assertEqual(output.read_bytes(), b"image")
            with self.assertRaises(FileExistsError):
                save_image(response, output)


if __name__ == "__main__":
    unittest.main()

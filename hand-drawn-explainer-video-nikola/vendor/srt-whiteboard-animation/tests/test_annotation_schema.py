from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from annotation_schema import validate_annotation  # noqa: E402


def annotation(region: dict | None = None) -> dict:
    return {
        "canvas": {"width": 100, "height": 80},
        "sceneDurationMs": 1200,
        "elements": [
            {
                "id": "subject",
                "label": "主体",
                "sequence": 1,
                "region": region or {"x": 10, "y": 10, "width": 60, "height": 50},
                "reveal": {"startMs": 0, "durationMs": 500, "protectedRegions": []},
            }
        ],
    }


class AnnotationSchemaTests(unittest.TestCase):
    def test_valid_annotation(self) -> None:
        errors, warnings = validate_annotation(annotation(), (100, 80))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_region_outside_canvas_is_error(self) -> None:
        errors, _ = validate_annotation(
            annotation({"x": 90, "y": 70, "width": 20, "height": 20}),
            (100, 80),
        )
        self.assertTrue(any("超出画布" in error for error in errors))

    def test_image_size_mismatch_is_error(self) -> None:
        errors, _ = validate_annotation(annotation(), (120, 80))
        self.assertTrue(any("与原图" in error for error in errors))

    def test_overlap_is_warning(self) -> None:
        data = annotation()
        data["elements"].append(
            {
                "id": "second",
                "label": "结果",
                "sequence": 2,
                "region": {"x": 20, "y": 20, "width": 40, "height": 30},
                "reveal": {"startMs": 300, "durationMs": 400, "protectedRegions": []},
            }
        )
        errors, warnings = validate_annotation(data, (100, 80))
        self.assertEqual(errors, [])
        self.assertTrue(any("时间窗重叠" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()

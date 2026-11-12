from __future__ import annotations

import logging
import unittest
from pathlib import PureWindowsPath

import yaml

from ocd_colt.exception import ValidationError
from ocd_colt.kape_config import load_targets_config
from ocd_colt.targets_models import KapeTarget, KapeTargets
from tests.utils import get_absolute_path


def _parse_yaml(subdir: str, filename: str) -> dict:
    """Load and parse a file from tests/data/<subdir>/."""
    with (get_absolute_path("data") / subdir / filename).open("r") as f:
        return yaml.safe_load(f)


class TestKapeTargetModel(unittest.TestCase):
    """Validate KapeTarget Pydantic model against test tkape files."""

    def _target(self, subdir: str, filename: str) -> dict:
        return _parse_yaml(subdir, filename)["Targets"][0]

    def test_valid_target_parses(self):
        t = KapeTarget.from_dict(self._target("valid", "valid.tkape"))
        self.assertEqual(t.name, "$MFT")
        self.assertEqual(t.category, "FileSystem")
        self.assertIsInstance(t.path, PureWindowsPath)
        self.assertFalse(t.recursive)

    def test_missing_name_raises(self):
        data = self._target("missing_target_name", "missing_target_name.tkape")
        with self.assertRaises(ValidationError) as ctx:
            KapeTarget.from_dict(data)
        self.assertIn("Name", str(ctx.exception))

    def test_missing_category_raises(self):
        data = self._target("missing_target_category", "missing_target_category.tkape")
        with self.assertRaises(ValidationError) as ctx:
            KapeTarget.from_dict(data)
        self.assertIn("Category", str(ctx.exception))

    def test_missing_path_raises(self):
        data = self._target("missing_target_path", "missing_target_path.tkape")
        with self.assertRaises(ValidationError) as ctx:
            KapeTarget.from_dict(data)
        self.assertIn("Path", str(ctx.exception))

    def test_null_path_raises(self):
        data = self._target("null_path", "null_path.tkape")
        with self.assertRaises(ValidationError):
            KapeTarget.from_dict(data)

    def test_bad_type_recursive_raises(self):
        data = self._target("bad_type_recursive", "bad_type_recursive.tkape")
        with self.assertRaises(ValidationError):
            KapeTarget.from_dict(data)

    def test_bad_type_maxsize_raises(self):
        data = self._target("bad_type_maxsize", "bad_type_maxsize.tkape")
        with self.assertRaises(ValidationError):
            KapeTarget.from_dict(data)

    def test_valid_document_parses(self):
        doc = KapeTargets.from_dict(_parse_yaml("valid", "valid.tkape"))
        self.assertEqual(doc.description, "MFT acquisition")
        self.assertEqual(len(doc.targets), 1)
        self.assertEqual(doc.guid, "aaaaaaaa-0000-0000-0000-000000000001")

    def test_missing_id_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            KapeTargets.from_dict(_parse_yaml("missing_doc_id", "missing_doc_id.tkape"))
        self.assertIn("Id", str(ctx.exception))

    def test_missing_description_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            KapeTargets.from_dict(_parse_yaml("missing_doc_description", "missing_doc_description.tkape"))
        self.assertIn("Description", str(ctx.exception))

    def test_missing_targets_raises(self):
        with self.assertRaises(ValidationError) as ctx:
            KapeTargets.from_dict(_parse_yaml("missing_doc_targets", "missing_doc_targets.tkape"))
        self.assertIn("Targets", str(ctx.exception))

    def test_malformed_yaml_raises(self):
        with self.assertRaises(yaml.YAMLError):
            _parse_yaml("malformed_yaml", "malformed_yaml.tkape")

    def test_valid_file_is_loaded(self):
        result = load_targets_config(get_absolute_path("data") / "valid")
        self.assertIn("valid", result)
        self.assertEqual(result["valid"].description, "MFT acquisition")

    def test_key_is_lowercase_stem(self):
        result = load_targets_config(get_absolute_path("data") / "valid")
        self.assertIn("valid", result)

    def test_missing_target_name_is_skipped(self):
        result = load_targets_config(get_absolute_path("data") / "missing_target_name")
        self.assertEqual(result, {})

    def test_missing_target_category_is_skipped(self):
        result = load_targets_config(get_absolute_path("data") / "missing_target_category")
        self.assertEqual(result, {})

    def test_missing_target_path_is_skipped(self):
        result = load_targets_config(get_absolute_path("data") / "missing_target_path")
        self.assertEqual(result, {})

    def test_missing_doc_id_is_skipped(self):
        result = load_targets_config(get_absolute_path("data") / "missing_doc_id")
        self.assertEqual(result, {})

    def test_missing_doc_description_is_skipped(self):
        result = load_targets_config(get_absolute_path("data") / "missing_doc_description")
        self.assertEqual(result, {})

    def test_missing_doc_targets_is_skipped(self):
        result = load_targets_config(get_absolute_path("data") / "missing_doc_targets")
        self.assertEqual(result, {})

    def test_malformed_yaml_is_skipped(self):
        result = load_targets_config(get_absolute_path("data") / "malformed_yaml")
        self.assertEqual(result, {})

    def test_bad_type_recursive_is_skipped(self):
        result = load_targets_config(get_absolute_path("data") / "bad_type_recursive")
        self.assertEqual(result, {})

    def test_bad_type_maxsize_is_skipped(self):
        result = load_targets_config(get_absolute_path("data") / "bad_type_maxsize")
        self.assertEqual(result, {})

    def test_null_path_is_skipped(self):
        result = load_targets_config(get_absolute_path("data") / "null_path")
        self.assertEqual(result, {})

    def test_invalid_file_logs_warning(self):
        with self.assertLogs("ocd_colt.kape_config", level=logging.WARNING) as log_ctx:
            load_targets_config(get_absolute_path("data") / "malformed_yaml")
        self.assertTrue(any("malformed_yaml.tkape" in msg for msg in log_ctx.output))

    def test_valid_and_invalid_loaded_together(self):
        result = load_targets_config(get_absolute_path("data") / "mixed")
        self.assertIn("valid", result)
        self.assertNotIn("malformed_yaml", result)

    def test_disabled_directory_is_skipped(self):
        result = load_targets_config(get_absolute_path("data") / "disabled_dir")
        self.assertEqual(result, {})

    def test_empty_directory_returns_empty_dict(self):
        result = load_targets_config(get_absolute_path("data") / "empty")
        self.assertEqual(result, {})

    def test_non_tkape_extension_is_ignored(self):
        result = load_targets_config(get_absolute_path("data") / "non_tkape_ext")
        self.assertEqual(result, {})

    def test_user_path_replaced_with_wildcard(self):
        doc = KapeTargets.from_dict(_parse_yaml("user_path", "mouse_without_borders.tkape"))
        # First three targets have %user% in path — must be replaced with *
        for i in range(3):
            self.assertIn("*", doc.targets[i].path.parts, f"targets[{i}].path should contain *")
            self.assertNotIn("%user%", doc.targets[i].path.parts, f"targets[{i}].path should not contain %user%")
        # Fourth target has no %user% and no wildcard
        self.assertNotIn("%user%", doc.targets[3].path.parts)
        self.assertNotIn("*", doc.targets[3].path.parts)


if __name__ == "__main__":
    unittest.main()

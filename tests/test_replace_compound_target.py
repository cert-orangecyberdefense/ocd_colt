from __future__ import annotations

import logging
import unittest

from ocd_colt.kape_config import load_targets_config, replace_compound_target
from tests.utils import get_absolute_path


class TestReplaceCompoundTarget(unittest.TestCase):
    """Tests for replace_compound_target() using fixture files in tests/data/compound_targets/."""

    @classmethod
    def setUpClass(cls):
        cls.targets_dir = load_targets_config(get_absolute_path("data") / "compound_targets")

    # ------------------------------------------------------------------
    # Leaf targets (no .tkape references)
    # ------------------------------------------------------------------

    def test_leaf_targets_returned_as_is(self):
        """Targets whose Path does not end in .tkape are returned unchanged."""
        result, _ = replace_compound_target(self.targets_dir["$mft"], self.targets_dir, set())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "$MFT")

    def test_leaf_with_multiple_targets(self):
        """All concrete targets from a leaf file are returned."""
        # $J.tkape contains 4 targets ($J x2, $Max x2 — covering ADS and non-ADS)
        result, _ = replace_compound_target(self.targets_dir["$j"], self.targets_dir, set())
        self.assertEqual(len(result), 4)

    # ------------------------------------------------------------------
    # Compound expansion
    # ------------------------------------------------------------------

    def test_compound_expands_all_leaf_targets(self):
        """A compound file is replaced by the union of all referenced leaves' targets."""
        # CSIRT_0_filesystem references $J (4), $LogFile (1), $MFT (1) → 6 total
        result, _ = replace_compound_target(self.targets_dir["filesystem"], self.targets_dir, set())
        self.assertEqual(len(result), 6)

    def test_compound_target_names_come_from_leaves(self):
        """Expanded targets carry names from their leaf definitions, not the compound entry."""
        result, _ = replace_compound_target(self.targets_dir["filesystem"], self.targets_dir, set())
        names = {t.name for t in result}
        self.assertIn("$MFT", names)
        self.assertIn("$J", names)
        self.assertIn("$LogFile", names)

    # ------------------------------------------------------------------
    # Mixed: direct target + .tkape reference in the same compound
    # ------------------------------------------------------------------

    def test_mixed_keeps_direct_targets_and_expands_references(self):
        """Direct (non-.tkape) targets are kept; .tkape refs are expanded."""
        result, _ = replace_compound_target(self.targets_dir["compound_mixed"], self.targets_dir, set())
        names = [t.name for t in result]
        self.assertIn("DirectTarget", names)
        self.assertIn("$MFT", names)
        self.assertEqual(len(result), 2)

    # ------------------------------------------------------------------
    # Missing reference
    # ------------------------------------------------------------------

    def test_missing_reference_is_skipped(self):
        """A .tkape reference that is not in targets_dir produces no targets."""
        result, _ = replace_compound_target(self.targets_dir["compound_missing"], self.targets_dir, set())
        self.assertEqual(result, [])

    def test_missing_reference_logs_warning(self):
        """A missing .tkape reference emits a warning containing the file name."""
        with self.assertLogs("ocd_colt.kape_config", level=logging.WARNING) as log_ctx:
            replace_compound_target(self.targets_dir["compound_missing"], self.targets_dir, set())
        self.assertTrue(any("nonexistent.tkape" in msg for msg in log_ctx.output))

    # ------------------------------------------------------------------
    # Deduplication via GUID
    # ------------------------------------------------------------------

    def test_duplicate_reference_yields_targets_once(self):
        """The same .tkape file referenced twice is expanded only on the first occurrence."""
        # compound_dedup references $MFT.tkape twice → $MFT targets should appear once
        result, _ = replace_compound_target(self.targets_dir["compound_dedup"], self.targets_dir, set())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "$MFT")

    def test_processed_guid_is_returned(self):
        """The returned processed_id set includes the GUIDs of all expanded KapeTargets."""
        mft_guid = self.targets_dir["$mft"].guid
        _, processed = replace_compound_target(self.targets_dir["compound_dedup"], self.targets_dir, set())
        self.assertIn(mft_guid, processed)

    def test_pre_populated_processed_id_skips_target(self):
        """A .tkape reference whose GUID is already in processed_id is skipped entirely."""
        mft_guid = self.targets_dir["$mft"].guid
        result, _ = replace_compound_target(
            self.targets_dir["compound_dedup"],
            self.targets_dir,
            processed_id={mft_guid},
        )
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # Circular references
    # ------------------------------------------------------------------

    def test_circular_reference_terminates(self):
        """Mutually referencing compounds terminate without infinite recursion."""
        # compound_circular_a → compound_circular_b → compound_circular_a (cycle)
        # Both are pure-compound with no direct targets, so the result is empty.
        result, _ = replace_compound_target(self.targets_dir["compound_circular_a"], self.targets_dir, set())
        self.assertEqual(result, [])

    def test_circular_reference_both_guids_in_processed(self):
        """After resolving a cycle, both GUIDs are recorded in processed_id."""
        guid_a = self.targets_dir["compound_circular_a"].guid
        guid_b = self.targets_dir["compound_circular_b"].guid
        _, processed = replace_compound_target(self.targets_dir["compound_circular_a"], self.targets_dir, set())
        self.assertIn(guid_a, processed)
        self.assertIn(guid_b, processed)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import typing
import unittest

from dissect.target import Target

from ocd_colt.extraction import extract_from_target
from ocd_colt.kape_config import get_targets_list, load_targets_config
from tests.utils import get_absolute_path

if typing.TYPE_CHECKING:
    from dissect.target.filesystem import FilesystemEntry


class Test_extract_from_target(unittest.TestCase):
    """Make extraction test"""

    @classmethod
    def setUpClass(cls):
        cls.target = Target.open(get_absolute_path("data") / "windows10.compressed.qcow2")
        cls.targets_dir = load_targets_config(get_absolute_path("data") / "KapeTarget")

    def test_usn_j(self):
        j = get_targets_list(["$J"], self.targets_dir)
        self.assertEqual(len(j), 4)
        target_list: list[tuple[FilesystemEntry, str | None]] = extract_from_target(self.target, j)
        self.assertEqual(len(target_list), 2)
        target_list.sort(key=lambda x: x[1])
        self.assertEqual(target_list[0][0].name.lower(), "$usnjrnl:$j")
        self.assertEqual(target_list[0][0].path.lower(), "/c:/$extend/$usnjrnl:$j")

    def test_full(self):
        j = get_targets_list(["test"], self.targets_dir)
        self.assertEqual(len(j), 115)
        target_list = extract_from_target(self.target, j)
        self.assertEqual(len(target_list), 923)

    def test_regex(self):
        targets = get_targets_list(["regex"], load_targets_config(get_absolute_path("data") / "filemask_regex"))
        self.assertEqual(len(targets), 1)
        target_list: list[tuple[FilesystemEntry, str | None]] = extract_from_target(self.target, targets)
        self.assertEqual(len(target_list), 2)
        target_list.sort(key=lambda x: x[0].path)
        self.assertEqual(target_list[0][0].path.lower(), "/c:/windows/system32/winevt/logs/setup.evtx")
        self.assertEqual(target_list[1][0].path.lower(), "/c:/windows/system32/winevt/logs/system.evtx")

    # TODO : test EFi partition skipped

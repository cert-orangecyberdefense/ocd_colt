from __future__ import annotations

import typing
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from dissect.target import Target

from ocd_colt.cli import process_target
from ocd_colt.kape_config import get_targets_list, load_targets_config
from ocd_colt.output.zip import ZipOutput
from tests.utils import get_absolute_path

if typing.TYPE_CHECKING:
    from ocd_colt.targets_models import KapeTarget


class Test_extract_from_target(unittest.TestCase):
    """Make full test"""

    EXPECTED_BASE_FILE = 2

    @classmethod
    def setUpClass(cls):
        cls.target = Target.open(get_absolute_path("data") / "windows10.compressed.qcow2")
        cls.targets_dir = load_targets_config(get_absolute_path("data") / "KapeTarget")

    def test_usn_j(self):
        """Test usnJ copied without issue. Does not use any prefix."""
        j: list[KapeTarget] = get_targets_list(["$J"], self.targets_dir)
        with TemporaryDirectory(prefix="test_colt_output_zip_test_usn_j") as tmp_dir:
            out_zip = Path(tmp_dir) / "test.zip"
            output = ZipOutput(
                enable_long_file_name=False,
                path=out_zip,
                path_prefix="",
                compress=True,
                deduplicate_sha1=False,
            )
            process_target(self.target, j, output)
            with zipfile.ZipFile(out_zip) as z_file:
                name_list = z_file.namelist()
                self.assertIn("c/$extend/$j", name_list)
                self.assertIn("c/$extend/$max", name_list)
                self.assertIn(".ocd_colt", name_list)
                max_info = z_file.getinfo("c/$extend/$max")
                self.assertEqual(32, max_info.file_size)
                j_info = z_file.getinfo("c/$extend/$j")
                self.assertEqual(337808, j_info.file_size)
                self.assertEqual("test.zip", (zipfile.Path(z_file) / ".ocd_colt").read_text())

    def test_usn_j_with_prefix(self):
        """Test usnJ copied without issue. Use target prefix."""
        j: list[KapeTarget] = get_targets_list(["$J"], self.targets_dir)
        with TemporaryDirectory(prefix="test_colt_output_zip_test_usn_j_with_prefix") as tmp_dir:
            out_zip = Path(tmp_dir) / "test.zip"
            output = ZipOutput(
                enable_long_file_name=False,
                path=out_zip,
                path_prefix="target",
                compress=True,
                deduplicate_sha1=False,
            )
            process_target(self.target, j, output)
            with zipfile.ZipFile(out_zip) as z_file:
                name_list = z_file.namelist()
                self.assertIn("target/c/$extend/$j", name_list)
                self.assertIn("target/c/$extend/$max", name_list)
                self.assertIn(".ocd_colt", name_list)
                max_info = z_file.getinfo("target/c/$extend/$max")
                self.assertEqual(32, max_info.file_size)
                j_info = z_file.getinfo("target/c/$extend/$j")
                self.assertEqual(337808, j_info.file_size)
                self.assertEqual("test.zip", (zipfile.Path(z_file) / ".ocd_colt").read_text())

    def test_full_with_prefix(self):
        full_test = get_targets_list(["test"], self.targets_dir)
        with TemporaryDirectory(prefix="test_colt_output_zip_test_full_with_prefix") as tmp_dir:
            out_zip = Path(tmp_dir) / "test.zip"
            output = ZipOutput(
                enable_long_file_name=False,
                path=out_zip,
                path_prefix="target",
                compress=True,
                deduplicate_sha1=False,
            )
            process_target(self.target, full_test, output)
            with zipfile.ZipFile(out_zip) as z_file:
                name_list = z_file.namelist()
                self.assertEqual(870, len(name_list))
                self.assertIn("target/c/$extend/$j", name_list)
                # Path with %user% placeholder
                self.assertIn("target/c/users/vagrant/appdata/local/microsoft/windows/usrclass.dat", name_list)

                usrclass_info = z_file.getinfo("target/c/users/vagrant/appdata/local/microsoft/windows/usrclass.dat")
                self.assertEqual(3407872, usrclass_info.file_size)
                self.assertIn(".ocd_colt", name_list)

    def test_full_without_prefix(self):
        full_test = get_targets_list(["test"], self.targets_dir)
        with TemporaryDirectory(prefix="test_colt_output_zip_test_full_without_prefix") as tmp_dir:
            out_zip = Path(tmp_dir) / "test.zip"
            output = ZipOutput(
                enable_long_file_name=False,
                path=out_zip,
                path_prefix="",
                compress=True,
                deduplicate_sha1=False,
            )
            process_target(self.target, full_test, output)
            with zipfile.ZipFile(out_zip) as z_file:
                name_list = z_file.namelist()
                self.assertEqual(870, len(name_list))
                self.assertIn("c/$extend/$j", name_list)
                # Path with %user% placeholder
                self.assertIn("c/users/vagrant/appdata/local/microsoft/windows/usrclass.dat", name_list)

                usrclass_info = z_file.getinfo("c/users/vagrant/appdata/local/microsoft/windows/usrclass.dat")
                self.assertEqual(3407872, usrclass_info.file_size)
                self.assertIn(".ocd_colt", name_list)

    def test_deduplicate_sha1(self):
        """Test with and without deduplicate sha1"""
        EXPECTED_EVTX_FILE = 150

        EXPECTED_DEDUP_EVTX_FILE = 101
        evtx_test = get_targets_list(["eventlogs"], self.targets_dir)
        with TemporaryDirectory(prefix="test_colt_output_zip_test_deduplicate_sha1") as tmp_dir:
            out_zip = Path(tmp_dir) / "eventlogs.zip"
            output = ZipOutput(
                enable_long_file_name=False,
                path=out_zip,
                path_prefix="",
                compress=True,
                deduplicate_sha1=False,
            )
            process_target(self.target, evtx_test, output)
            with zipfile.ZipFile(out_zip) as z_file:
                name_list = z_file.namelist()
                self.assertEqual(EXPECTED_EVTX_FILE + self.EXPECTED_BASE_FILE, len(name_list))
                self.assertIn("c/windows/system32/winevt/logs/application.evtx", name_list)
                self.assertListEqual([], list(f for f in name_list if f.lower().endswith("_skiplog.csv")))

        with TemporaryDirectory(prefix="test_colt_output_zip_test_deduplicate_sha1") as tmp_dir:
            out_zip = Path(tmp_dir) / "eventlogs_dedup.zip"
            output = ZipOutput(
                enable_long_file_name=False,
                path=out_zip,
                path_prefix="",
                compress=True,
                deduplicate_sha1=True,
            )
            process_target(self.target, evtx_test, output)
            with zipfile.ZipFile(out_zip) as z_file:
                name_list = z_file.namelist()
                skip_log_file = next(f for f in name_list if f.lower().endswith("_skiplog.csv"))
                # Copy log file not present in base

                self.assertEqual(EXPECTED_DEDUP_EVTX_FILE + self.EXPECTED_BASE_FILE + 1, len(name_list))
                self.assertIn("c/windows/system32/winevt/logs/application.evtx", name_list)
                skip_log_content = (zipfile.Path(z_file) / skip_log_file).read_text().splitlines()
                self.assertEqual((EXPECTED_EVTX_FILE - EXPECTED_DEDUP_EVTX_FILE) + 1, len(skip_log_content))

    def test_long_filename(self):
        EXPECTED_SCH_TASK_FILE_COUNT: int = 196
        LONG_FILE_COUNT = 2
        sch_task_test = get_targets_list(["ScheduledTasks"], self.targets_dir)
        PREFIX = 73 * "a"
        with TemporaryDirectory(prefix="test_colt_output_zip_test_long_filename_false") as tmp_dir:
            out_zip = Path(tmp_dir) / "sch_task_test.zip"
            output = ZipOutput(
                enable_long_file_name=False,
                path=out_zip,
                path_prefix=PREFIX,
                compress=True,
                deduplicate_sha1=True,
            )
            process_target(self.target, sch_task_test, output)
            with zipfile.ZipFile(out_zip) as z_file:
                name_list = z_file.namelist()
                self.assertEqual(EXPECTED_SCH_TASK_FILE_COUNT + self.EXPECTED_BASE_FILE, len(name_list))
                self.assertIn(
                    PREFIX + "/"
                    "c/windows/system32/tasks/microsoft/windows/"
                    "active directory rights management services client"
                    "/ad rms rights policy template management (automated)",
                    name_list,
                )
                self.assertListEqual([], list(f for f in name_list if f.lower().endswith("_skiplog.csv")))

        with TemporaryDirectory(prefix="test_colt_output_zip_test_long_filename_false") as tmp_dir:
            out_zip = Path(tmp_dir) / "sch_task_test.zip"
            output = ZipOutput(
                enable_long_file_name=True,
                path=out_zip,
                path_prefix=PREFIX,
                compress=True,
                deduplicate_sha1=True,
            )
            process_target(self.target, sch_task_test, output)
            with zipfile.ZipFile(out_zip) as z_file:
                name_list = z_file.namelist()
                self.assertEqual(
                    EXPECTED_SCH_TASK_FILE_COUNT + self.EXPECTED_BASE_FILE + LONG_FILE_COUNT, len(name_list)
                )
                self.assertNotIn(
                    PREFIX + "/"
                    "c/windows/system32/tasks/microsoft/windows/"
                    "active directory rights management services client"
                    "/ad rms rights policy template management (automated)",
                    name_list,
                )
                LONG_FILES = [f for f in name_list if f.lower().startswith(PREFIX + "/longfilenames/")]
                self.assertEqual(4, len(LONG_FILES))
                PATH_INFO_FILES = [f for f in LONG_FILES if f.lower().endswith("_originalpathinfo.txt")]
                self.assertEqual(2, len(PATH_INFO_FILES))
                PATH_INFO_CONTENT = {f: (zipfile.Path(z_file) / f).read_text() for f in PATH_INFO_FILES}
                self.assertListEqual(
                    [
                        "C:\\Windows\\System32\\Tasks\\Microsoft\\Windows\\Active Directory Rights "
                        "Management Services Client\\AD RMS Rights Policy Template Management "
                        "(Automated)",
                        "C:\\Windows\\System32\\Tasks\\Microsoft\\Windows\\Active Directory Rights "
                        "Management Services Client\\AD RMS Rights Policy Template Management "
                        "(Manual)",
                    ],
                    list(PATH_INFO_CONTENT.values()),
                )
                automated_file_info = next(
                    k
                    for k, v in PATH_INFO_CONTENT.items()
                    if v == "C:\\Windows\\System32\\Tasks\\Microsoft\\Windows\\Active Directory Rights "
                    "Management Services Client\\AD RMS Rights Policy Template Management "
                    "(Automated)"
                ).partition("_")[0]
                automated_file_content = (zipfile.Path(z_file) / automated_file_info).read_bytes()
                self.assertEqual(3978, len(automated_file_content))

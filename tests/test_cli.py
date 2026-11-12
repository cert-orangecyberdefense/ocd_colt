from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import Path as ZipPath
from zipfile import ZipFile

from ocd_colt.cli import main
from tests.utils import get_absolute_path


class Test_extract_from_target(unittest.TestCase):
    """Test including cli"""

    @classmethod
    def setUpClass(cls):
        cls.vmdk_path = get_absolute_path("data") / "windows10.compressed.qcow2"
        cls.kape_target_path = get_absolute_path("data") / "KapeTarget"

    def test_list(self):
        captured_output = io.StringIO()
        with patch("sys.argv", ["ocd_colt", "--list"]), contextlib.redirect_stdout(captured_output):
            self.assertEqual(0, main())
            output = captured_output.getvalue()
            # Raw containers list
            self.assertIn("vmdk", output)
            # Loaders list
            self.assertIn("vmx", output)
            self.assertIn("Available loaders", output)

        with patch("sys.argv", ["ocd_colt", "-l"]), contextlib.redirect_stdout(captured_output):
            self.assertEqual(0, main())
            output = captured_output.getvalue()
            # Raw containers list
            self.assertIn("vmdk", output)
            # Loaders list
            self.assertIn("vmx", output)
            self.assertIn("Available loaders", output)

    def test_zip_out(self):
        captured_output = io.StringIO()
        captured_stderr = io.StringIO()
        with (
            tempfile.TemporaryDirectory(prefix="test_ocd_colt_") as tmp_dir,
            patch(
                "sys.argv",
                [
                    "ocd_colt",
                    "--in",
                    str(self.vmdk_path),
                    "--out",
                    str(tmp_dir),
                    "-T",
                    "zip",
                    "--config_dir",
                    str(self.kape_target_path),
                    "--target",
                    "test",
                ],
            ),
            contextlib.redirect_stdout(captured_output),
            contextlib.redirect_stderr(captured_stderr),
        ):
            ret_code = main()
            self.assertEqual(0, ret_code)
            zip_archive = next(Path(tmp_dir).iterdir())
            self.assertIn("VAGRANT", zip_archive.name)
            self.assertTrue(zip_archive.is_file())
            with ZipFile(zip_archive, mode="r") as zf:
                zp = ZipPath(zf)
                dot_ocd_colt = zp / ".ocd_colt"
                self.assertTrue(dot_ocd_colt)
                self.assertEqual(dot_ocd_colt.read_text(), zip_archive.name)
                mft = zp / "target" / "c" / "$mft"
                self.assertTrue(mft.exists())
                self.assertEqual(zf.getinfo("target/c/$mft").file_size, 436994048)
                self.assertEqual(zf.getinfo("target/c/$extend/$j").file_size, 337808)
                self.assertEqual(len(zf.infolist()), 742)

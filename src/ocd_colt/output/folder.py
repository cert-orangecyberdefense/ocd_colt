"""
From https://github.com/fox-it/acquire/blob/main/acquire/outputs/dir.py#L50
"""

from __future__ import annotations

import csv
import logging
import platform
import shutil
import typing
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, BinaryIO, TextIO

from ocd_colt.output.base import Output

if typing.TYPE_CHECKING:
    from dissect.target.filesystem import FilesystemEntry

logger = logging.getLogger(__name__)


class FolderOutput(Output):
    _copy_file_writer: Any | None = None
    _skip_file_writer: Any | None = None
    _copy_log_file: TextIO | None = None
    _skip_log_file: TextIO | None = None
    _directory_permission = 0o755

    def __init__(
        self, path: Path, enable_long_file_name=True, deduplicate_sha1: bool = True, file_permission: int = 0o444
    ) -> None:
        """
        Existing output path
        :param path:
        """
        self.path = path
        self.path_prefix = str(path.resolve().absolute())
        # todo : check perm
        self.file_permission = file_permission
        self.start_time = datetime.now(tz=timezone.utc)
        super().__init__(enable_long_file_name=enable_long_file_name, deduplicate_sha1=deduplicate_sha1)

    def write(
        self,
        output_path: str,
        fh: BinaryIO,
        entry: FilesystemEntry | Path | None,
        size: int | None = None,
    ) -> tuple[bool, str]:
        """Write a file-like object to the output.

        Args:
            output_path: The path of the entry in the output.
            fh: The file-like object of the entry to write.
            entry: The optional filesystem entry to write.
            size: The optional file size in bytes of the entry to write.
        """
        if platform.system() == "Windows":
            output_path = output_path.replace(":", "_")

        full_output_path = self.path.joinpath(output_path.lstrip("/"))
        full_output_path.parent.mkdir(exist_ok=True, parents=True, mode=self._directory_permission)
        if full_output_path.exists():
            logger.warning("File already exist, skipping")
            return False, "AlreadyExists"
        with full_output_path.open("wb") as f:
            shutil.copyfileobj(fh, f)
        full_output_path.chmod(self.file_permission)
        return True, ""

    def handle_long_filename(self, source_file: FilesystemEntry) -> Path:
        long_dir = self.path / self.LONG_FILENAME_PATH
        guid = str(uuid.uuid4())
        dst_file = long_dir / f"{guid}{Path(source_file.name).suffix}"
        long_dir.mkdir(exist_ok=True, parents=True, mode=self._directory_permission)
        with (long_dir / f"{guid}_OriginalPathInfo.txt").open("wb") as fh:
            fh.write(
                self.format_entry_name_to_str_path(PureWindowsPath(*Path(source_file.path).parts[1:])).encode("utf-8")
            )
        return dst_file.relative_to(self.path)

    @property
    def skip_log_writer(self):
        if not self._skip_file_writer:
            skip_log_filename = self.start_time.strftime(f"{self.kape_filename_date_format}_SkipLog.csv")
            self._skip_log_file = (self.path / skip_log_filename).open(mode="a", errors="backslashreplace")
            self._skip_file_writer = csv.writer(self._skip_log_file)
            self._skip_file_writer.writerow(["SourceFile", "SourceFileSha1", "Reason"])
        return self._skip_file_writer

    @property
    def copy_log_writer(self):
        # TODO
        if not self._copy_file_writer:
            copy_log_filename = self.start_time.strftime(f"{self.kape_filename_date_format}_CopyLog.csv")
            self._copy_log_file = (self.path / copy_log_filename).open(mode="a", errors="backslashreplace")
            self._copy_file_writer = csv.writer(self._copy_log_file)
            self._copy_file_writer.writerow(
                [
                    "CopiedTimestamp",
                    "SourceFile",
                    "DestinationFile",
                    "FileSize",
                    "SourceFileSha1",
                    "DeferredCopy",
                    "CreatedOnUtc",
                    "ModifiedOnUtc",
                    "LastAccessedOnUtc",
                    "CopyDuration",
                ]
            )
        return self._copy_file_writer

    def close(self) -> None:
        with suppress(IOError):
            if self._copy_log_file:
                self._copy_log_file.close()
                self._copy_log_file = None
            if self._skip_log_file:
                self._skip_log_file.close()
                self._skip_log_file = None

    def rotate_logs_files(self):
        """
        Rotate skip/copy log files
        :return:
        """
        with suppress(IOError):
            if self._copy_log_file:
                self._copy_log_file.close()
                self._copy_log_file = None
                self._copy_file_writer = None
            if self._skip_log_file:
                self._skip_log_file.close()
                self._skip_log_file = None
                self._skip_file_writer = None

        self.start_time = datetime.now(tz=timezone.utc)

    def __str__(self):
        return f"FolderOutput({self.path.absolute()})"

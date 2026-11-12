"""
from https://github.com/fox-it/acquire/blob/c284e87df0d1d40ca78aa70d29395923259db423/acquire/outputs/zip.py
"""

from __future__ import annotations

import codecs
import contextlib
import csv
import io
import logging
import shutil
import stat
import tempfile
import typing
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, BinaryIO

from ocd_colt.output.base import Output

if typing.TYPE_CHECKING:
    from io import BytesIO

    from dissect.target.filesystem import FilesystemEntry

logger = logging.getLogger(__name__)

ZIP_COMPRESSION_METHODS = {"deflate": zipfile.ZIP_DEFLATED, "bzip2": zipfile.ZIP_BZIP2, "lzma": zipfile.ZIP_LZMA}


class ZipOutput(Output):
    """Zip archive acquire output format. Output can be compressed and/or encrypted.

    Args:
        path: The path to write the zip archive to.
        path_prefix: folder root to every files in the archive.
        compress: Whether to compress the zip archive.
        compression_method: Compression method to use (Default: Deflate). Supports "deflate", "bzip2", "lzma".
    """

    _copy_file_tmp: BytesIO | None = None
    _copy_file_writer: Any | None = None
    _skip_file_writer: Any | None = None
    _skip_file_tmp: BytesIO | None = None
    console_log = io.StringIO("")

    def __init__(
        self,
        path: Path,
        path_prefix: str,
        compress: bool = False,
        compression_method: str = "deflate",
        enable_long_file_name: bool = True,
        deduplicate_sha1: bool = True,
    ) -> None:
        ext = ".zip" if ".zip" not in path.suffixes else ""

        self._fh = None
        self.path = path.with_suffix(path.suffix + ext)
        self.path_prefix = path_prefix.rstrip("/")
        if self.path_prefix:
            self.path_prefix += "/"
        self.start_time = datetime.now(tz=timezone.utc)
        if compress:
            self.compression = ZIP_COMPRESSION_METHODS.get(compression_method, zipfile.ZIP_DEFLATED)
        else:
            self.compression = zipfile.ZIP_STORED

        self.archive = zipfile.ZipFile(self.path, mode="w", compression=self.compression, allowZip64=True)
        super().__init__(enable_long_file_name=enable_long_file_name, deduplicate_sha1=deduplicate_sha1)

    def write(
        self,
        output_path: str,
        fh: BinaryIO,
        entry: FilesystemEntry | Path | None = None,
        size: int | None = None,
    ) -> tuple[bool, str]:
        """Write a filesystem entry or file-like object to a zip file.

        Args:
            output_path: The path of the entry in the output format.
            fh: The file-like object of the entry to write.
            entry: The optional filesystem entry of the entry to write.
            size: The optional file size in bytes of the entry to write.
        """
        zip_filename = output_path.lstrip("/")
        if self.path_prefix:
            zip_filename = self.path_prefix + zip_filename
        try:
            self.archive.getinfo(zip_filename)
            logger.warning("File already in archive %s, skipping", zip_filename)
            return False, "AlreadyExist"
        except KeyError as _:
            # Exception raised on missing element
            pass
        lstat = None
        size = size or getattr(fh, "size", None)

        if size is None and fh.seekable():
            offset = fh.tell()
            fh.seek(0, io.SEEK_END)
            size = fh.tell()
            fh.seek(offset)

        info = zipfile.ZipInfo()
        info.filename = zip_filename
        info.file_size = size or 0
        info.compress_type = self.compression

        if entry:
            info.external_attr = self._get_external_attr(entry)

            if entry.is_symlink():
                # System which created ZIP archive, 3 = Unix; 0 = Windows
                # Windows does not have symlinks, so this must be a unixoid system
                info.create_system = 3

            lstat = entry.lstat()
            if lstat:
                # Python zipfile module does not support timestamps before 1980
                dt = datetime.fromtimestamp(lstat.st_mtime)
                year = max(dt.year, 1980)
                info.date_time = (year, dt.month, dt.day, dt.hour, dt.minute, dt.second)

        with self.archive.open(info, "w") as zfh:
            shutil.copyfileobj(fh, zfh)
        return True, ""

    def close(self) -> None:
        """Closes the archive file."""
        with self.archive.open(".ocd_colt", "w") as fh:
            fh.write(self.path.name.encode("utf-8"))
            fh.close()
        self.archive.close()
        if self._fh:
            self._fh.close()

    def _get_external_attr(self, entry: FilesystemEntry) -> int:
        """Return the appropriate external attributes of the entry."""

        # The Python zipfile module accepts the 16-bit "Mode" field (that stores st_mode field from
        # struct stat, containing user/group/other permissions, setuid/setgid and symlink info, etc) of the
        # ASi extra block for Unix as bits 16-31 of the external_attr
        unix_st_mode = stat.S_IFREG

        if entry.is_symlink():
            unix_st_mode = stat.S_IFLNK
        elif entry.is_dir():
            unix_st_mode = stat.S_IFDIR

        unix_st_mode = (
            unix_st_mode
            | stat.S_IRUSR
            | stat.S_IWUSR
            | stat.S_IXUSR
            | stat.S_IRGRP
            | stat.S_IWGRP
            | stat.S_IXGRP
            | stat.S_IROTH
            | stat.S_IWOTH
            | stat.S_IXOTH
        ) << 16

        return unix_st_mode

    def __del__(self):
        with contextlib.suppress(Exception):
            self.close()

    @property
    def copy_log_file(self) -> io.BytesIO:
        if not self._copy_file_tmp:
            self._copy_file_tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
                mode="w+b", suffix=".csv", prefix="kape_extractor_copy_", delete=True
            )
        return self._copy_file_tmp

    @property
    def skip_log_file(self) -> io.BytesIO:
        if not self._skip_file_tmp:
            self._skip_file_tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
                mode="w+b", suffix=".csv", prefix="kape_extractor_skip_", delete=True
            )
        return self._skip_file_tmp

    @property
    def copy_log_writer(self):
        if self._copy_file_writer is None:
            StreamWriter = codecs.getwriter("utf-8")
            self._copy_file_writer = csv.writer(StreamWriter(self.copy_log_file))
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

    @property
    def skip_log_writer(self):
        if self._skip_file_writer is None:
            StreamWriter = codecs.getwriter("utf-8")
            self._skip_file_writer = csv.writer(StreamWriter(self.skip_log_file))
            self._skip_file_writer.writerow(["SourceFile", "SourceFileSha1", "Reason"])
        return self._skip_file_writer

    def handle_long_filename(self, source_file: FilesystemEntry) -> Path:
        """
        Return path to copy file name.
        create associated guid file in LongFileNames/ _OriginalPathInfo.txt
        :param source_file:
        :return:
        """
        long_dir = Path(self.LONG_FILENAME_PATH)
        guid = str(uuid.uuid4())
        dst_file = long_dir / f"{guid}{Path(source_file.name).suffix}"
        with self.archive.open(f"{self.path_prefix}{long_dir}/{guid}_OriginalPathInfo.txt", "w") as fh:
            fh.write(
                self.format_entry_name_to_str_path(PureWindowsPath(*Path(source_file.path).parts[1:])).encode("utf-8")
            )
        return dst_file

    def copy_log_file_into_archive(self, start_time: datetime):
        if self._copy_file_tmp:
            copy_log_filename = start_time.strftime(f"{self.kape_filename_date_format}_CopyLog.csv")
            with self.archive.open(f"{self.path_prefix}{copy_log_filename}", "w") as fh:
                self._copy_file_tmp.seek(0)
                shutil.copyfileobj(self._copy_file_tmp, fh)
                self._copy_file_tmp.close()
                self._copy_file_writer = None
                self._copy_file_tmp = None

    def skip_log_file_into_archive(self, start_time: datetime):
        if self._skip_file_tmp:
            skip_log_filename = start_time.strftime(f"{self.kape_filename_date_format}_SkipLog.csv")
            with self.archive.open(f"{self.path_prefix}{skip_log_filename}", "w") as fh:
                self._skip_file_tmp.seek(0)
                shutil.copyfileobj(self._skip_file_tmp, fh)
                self._skip_file_tmp.close()
                self._skip_file_writer = None
                self._skip_file_tmp = None

    def rotate_logs_files(self):
        """
        Rotate skip/copy log files
        :return:
        """
        self.copy_log_file_into_archive(self.start_time)
        self.skip_log_file_into_archive(self.start_time)
        self.start_time = datetime.now(tz=timezone.utc)

    def __str__(self):
        return f"ZipOutput({self.path.absolute()})"

from __future__ import annotations

import abc
import io
import logging
import typing
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import BinaryIO

from dissect.util.stream import RunlistStream

if typing.TYPE_CHECKING:
    from datetime import timedelta
    from os import stat_result

    from dissect.target.filesystem import FilesystemEntry

logger = logging.getLogger(__name__)


def read_usn_journal(journal: BinaryIO) -> tuple[BinaryIO, int]:
    """Usn is a sparse file, special method to identify size.

    References:
         https://github.com/fox-it/acquire/blob/c284e87df0d1d40ca78aa70d29395923259db423/acquire/acquire.py#L330
    """
    if isinstance(journal, RunlistStream):
        i = 0
        while journal.runlist[i][0] is None:
            journal.seek(journal.runlist[i][1] * journal.block_size, io.SEEK_CUR)
            i += 1
        size = journal.size - journal.tell()
    else:
        size = journal.size

    return journal, size


class Output(abc.ABC):
    """Base class to implement acquire output formats with.

    New output formats must sub-class this class.
    """

    path_prefix: str
    kape_date_format = "%Y-%m-%d %H:%M:%S.%f0"
    kape_filename_date_format = "%Y-%m-%dT%H_%M_%S_%f0"
    enable_long_file_name = True
    LONG_FILENAME_PATH = "LongFileNames".lower()

    def __init__(self, enable_long_file_name: bool = True, deduplicate_sha1: bool = True, **kwargs):
        self.enable_long_file_name = enable_long_file_name
        self.deduplicate_sha1 = deduplicate_sha1
        self.seen_sha1: set = set()

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
        raise NotImplementedError()

    def write_entry(
        self,
        output_path: str,
        entry: FilesystemEntry | Path,
        size: int | None = None,
    ) -> tuple[bool, str]:
        """Write a filesystem entry to the output.

        Args:
            output_path: The path of the entry in the output.
            entry: The filesystem entry to write.
            size: The optional file size in bytes of the entry to write.
        """
        logger.debug("Writing entry %s into %s", str(entry), output_path)

        """
        dirty special handle for usn
        """
        if entry.name.lower() != "$Usnjrnl:$J".lower():
            with entry.open() as fh:
                return self.write(output_path, fh, entry=entry, size=size)
        else:
            with entry.open() as f:
                fh, size = read_usn_journal(f)
                return self.write(output_path, fh, entry=entry, size=size)

    def write_bytes(
        self,
        output_path: str,
        data: bytes,
        entry: FilesystemEntry | Path | None = None,
        size: int | None = None,
    ) -> None:
        """Write raw bytes to the output format.

        Args:
            output_path: The path of the entry in the output.
            data: The raw bytes to write.
            entry: The optional filesystem entry to write.
            size: The optional file size in bytes of the entry to write.
        """

        stream = io.BytesIO(data)
        self.write(output_path, stream, entry=entry, size=size)

    def close(self) -> None:
        """Closes the output."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def copy_log_writer(self):
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def skip_log_writer(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def handle_long_filename(self, source_file: FilesystemEntry) -> Path:
        raise NotImplementedError()

    def format_entry_name_to_str_path(self, windows_path: PureWindowsPath) -> str:
        return windows_path.drive + "\\" + str(windows_path)[len(windows_path.drive) :]

    def append_copy_log_file(
        self,
        copied_timestamp: datetime,
        source_file: PureWindowsPath,
        destination_file: Path,
        file_size: int,
        source_file_sha1: str,
        created_on_utc: datetime | None,
        modified_on_utc: datetime | None,
        last_accessed_on_utc: datetime | None,
        copy_duration: timedelta,
        deferred_copy: bool,
    ):
        self.copy_log_writer.writerow(
            [
                copied_timestamp.strftime(self.kape_date_format),
                self.format_entry_name_to_str_path(source_file),
                str(destination_file),
                file_size,
                source_file_sha1.upper(),
                "True" if deferred_copy else "False",
                created_on_utc.strftime(self.kape_date_format) if created_on_utc else "N/A",
                modified_on_utc.strftime(self.kape_date_format) if modified_on_utc else "N/A",
                last_accessed_on_utc.strftime(self.kape_date_format) if last_accessed_on_utc else "N/A",
                str(copy_duration).split(".")[0],
            ]
        )

    def get_ts_as_datetime_from_source_stat(self, source_stat: stat_result, attr: str) -> datetime | None:
        if attr_as_int := getattr(source_stat, attr, None):
            with suppress(ValueError):
                return datetime.fromtimestamp(attr_as_int, tz=timezone.utc)
        return None

    def copy_entry(
        self,
        source: FilesystemEntry,
        save_as_file_name: str | None = None,
        dry_run=False,
    ):
        sha1 = source.sha1()
        if sha1 in self.seen_sha1 and self.deduplicate_sha1:
            logger.debug("Skipping %s, already seen", source.path)
            self.append_skip_log_file(PureWindowsPath(*Path(source.path).parts), sha1)
            return
        self.seen_sha1.add(sha1)
        start = datetime.now()

        source_stat = source.stat()
        file_size = source_stat.st_size
        created_on_utc = self.get_ts_as_datetime_from_source_stat(source_stat, "st_birthtime")
        modified_on_utc = self.get_ts_as_datetime_from_source_stat(source_stat, "st_mtime")
        last_accessed_on_utc = self.get_ts_as_datetime_from_source_stat(source_stat, "st_atime")
        as_windows_path = PureWindowsPath(*Path(source.path).parts[1:])
        dst_file = Path(as_windows_path.drive[0].upper()) / Path(*Path(source.path).parts[2:-1])
        if save_as_file_name:
            dst_file /= save_as_file_name
        else:
            dst_file /= as_windows_path.name
        # 215 = hard coded value in kape
        if len(str(dst_file) + str(self.path_prefix)) > 215 and self.enable_long_file_name:
            logger.warning("Long filename : %s", source)
            dst_file = self.handle_long_filename(source)
        logger.debug("Copying entry %s into %s", source, dst_file)
        ok, reason = self.write_entry(dst_file.as_posix().lower(), source)
        if ok:
            self.append_copy_log_file(
                datetime.now(tz=timezone.utc),
                source_file=PureWindowsPath(*Path(source.path).parts),
                destination_file=dst_file,
                file_size=file_size,
                source_file_sha1=sha1,
                created_on_utc=created_on_utc,
                modified_on_utc=modified_on_utc,
                last_accessed_on_utc=last_accessed_on_utc,
                copy_duration=datetime.now() - start,
                deferred_copy=False,
            )
        else:
            self.append_skip_log_file(PureWindowsPath(*Path(source.path).parts), sha1, reason)

    def append_skip_log_file(self, source_file: PureWindowsPath, sha1: str, reason: str = "Deduped"):
        self.skip_log_writer.writerow([self.format_entry_name_to_str_path(source_file), sha1.upper(), reason])

    def rotate_logs_files(self):  # noqa: B027
        """
        Rotate skip/copy log files
        :return:
        """
        pass

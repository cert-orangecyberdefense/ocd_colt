from __future__ import annotations

import io
import logging
import typing
import uuid
from pathlib import Path
from typing import BinaryIO

from ocd_colt.output.base import Output

if typing.TYPE_CHECKING:
    from datetime import datetime, timedelta
    from pathlib import PureWindowsPath

    from dissect.target.filesystem import FilesystemEntry

logger = logging.getLogger(__name__)


class DryRunOutput(Output):
    path_prefix = "target"

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
        if size is None and fh.seekable():
            offset = fh.tell()
            fh.seek(0, io.SEEK_END)
            size = fh.tell()
            fh.seek(offset)
        self.logger.info("Writing %s bytes to %s from %s", size, output_path, entry)
        return True, ""

    @property
    def logger(self) -> logging.Logger:
        return logger

    def close(self) -> None:
        """Closes the output."""
        return None

    def append_skip_log_file(self, source_file: PureWindowsPath, sha1: str):
        self.logger.info("[SKIP]%s,%s,%s", source_file, sha1, "Deduped")

    def handle_long_filename(self, source_file: FilesystemEntry) -> Path:
        self.logger.info("[LONGFILENAME]%s", source_file.path)
        return Path(self.LONG_FILENAME_PATH) / str(uuid.uuid4())

    def append_copy_log_file(
        self,
        copied_timestamp: datetime,
        source_file: PureWindowsPath,
        destination_file: Path,
        file_size: int,
        source_file_sha1: str,
        created_on_utc: datetime,
        modified_on_utc: datetime,
        last_accessed_on_utc: datetime,
        copy_duration: timedelta,
        deferred_copy: bool,
    ):
        pass

    @property
    def copy_log_writer(self):
        pass

    @property
    def skip_log_writer(self):
        pass

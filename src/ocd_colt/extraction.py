from __future__ import annotations

import logging
import re
import string
import typing
from collections import defaultdict
from pathlib import Path
from uuid import UUID

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

    from dissect.target import Target
    from dissect.target.filesystem import Filesystem, FilesystemEntry

    from ocd_colt.targets_models import KapeTarget

logger = logging.getLogger(__name__)


def process_drive_with_target(
    kape_target: KapeTarget, target: Target, prefix: str
) -> list[tuple[FilesystemEntry, str | None]]:
    """
    Generate list of entry/dst path that must be copied from a target

    :param kape_target:
    :param target:
    :param prefix:
    :return:
    """
    logger.debug(
        "Processing target on %s : %s : %s : %s", prefix, kape_target.name, kape_target.path, kape_target.file_mask
    )
    collect_entries = []
    path_part = list(kape_target.path.parts[1:])
    fs_to_glob = target.fs.get(f"/{prefix}:")
    path_dir = list([f for f in fs_to_glob.glob_ext(str(Path(*path_part))) if f.is_dir()])
    # recurse over directory
    if kape_target.recursive:
        for p in list(path_dir):
            for d in p.recurse():
                if d.is_dir():
                    path_dir.append(d)
    if kape_target.file_mask.lower().startswith("regex:"):
        file_mask_pattern = kape_target.file_mask[6:]
        # May crash on bad target
        # Only regex on default Kape file is `regex:*.+\.(db|db-wal|db-shm)` (for bitdefender target)
        # This does not crash in .Net event in starting * is useless, but it crash in python..
        if file_mask_pattern.startswith("*"):
            file_mask_pattern = file_mask_pattern[1:]
    else:
        file_mask_pattern = (
            kape_target.file_mask.replace(
                ".",
                "\\.",
            )
            .replace("*", "(.+)?")
            .replace("$", "\\$")
        )
    file_mask_pattern = rf"\A{file_mask_pattern}\Z"
    try:
        re_file_mask_pattern = re.compile(file_mask_pattern, re.IGNORECASE)
    except re.error:
        logger.warning("Fail to compile regex for following target : %s (%s)", kape_target.name, file_mask_pattern)
        return []
    for dir_to_search in path_dir:
        logger.debug("[%s]Processing %s", kape_target.name, dir_to_search)
        # special handle for ADS are they are not list in list_dir
        if ":" in kape_target.file_mask and not kape_target.file_mask.lower().startswith("regex:"):
            if dir_to_search.exists(kape_target.file_mask):
                collect_entries.append((dir_to_search.get(kape_target.file_mask), kape_target.save_as_file_name))
        else:
            for f in dir_to_search.listdir_ext():
                if (
                    f.is_file()
                    and re_file_mask_pattern.match(f.name)
                    and (kape_target.max_size is None or kape_target.max_size > f.stat().st_size)
                    and (kape_target.min_size is None or kape_target.min_size < f.stat().st_size)
                ):
                    collect_entries.append((f, kape_target.save_as_file_name))

    return collect_entries


def yield_fs_tuples(target: Target) -> Iterator[tuple[str, Filesystem]]:
    """
    Inspired from https://github.com/fox-it/acquire/blob/c284e87df0d1d40ca78aa70d29395923259db423/acquire/acquire.py#L162
    """
    available_disk = list(string.ascii_lowercase[2:])
    mount_lookup = defaultdict(list)
    for mount, fs in target.fs.mounts.items():
        if re.match("[a-z]:", mount) and mount[0] in available_disk:
            available_disk.remove(mount[0])
            mount_lookup[fs].append(mount[0].upper())
    for fs in target.filesystems:
        # https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ns-winioctl-partition_information_gpt

        if fs.volume and fs.volume.type in [
            UUID("DE94BBA4-06D1-4D40-A16A-BFD50179D6AC").bytes_le,
            # GPT Windows Recovery Environment (Windows RE) partition id is de94bba4-06d1-4d40-a16a-bfd50179d6ac
            0x27,  # MBR : Parition type is 0x27 :
            # https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-7/dd744364(v=ws.10)?redirectedfrom=MSDN
            UUID("C12A7328-F81F-11D2-BA4B-00A0C93EC93B").bytes_le,  # Also skip
            # EFI partition : GUID C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        ]:
            logger.debug("Skipping %s - Windows Recovery Environment or EFI ", fs)
            continue
        if fs in mount_lookup:
            mountpoints = mount_lookup[fs]
            name_mountpoint = ""
            for main_mountpoint in mountpoints:
                if main_mountpoint != "sysvol":
                    name_mountpoint = main_mountpoint
                    break
        else:
            name_mountpoint = available_disk[0].upper()
            available_disk.remove(name_mountpoint.lower())
            logger.warning("Unmounted NTFS filesystem found %s, assigning drive : %s", fs, name_mountpoint)
        yield name_mountpoint, fs


def extract_from_target(target: Target, kape_target: list[KapeTarget]) -> list[tuple[FilesystemEntry, str | None]]:
    to_copy: list[tuple[FilesystemEntry, str | None]] = []
    tuple_fs = []

    for name_mountpoint, fs in yield_fs_tuples(target):
        logger.debug("testing if %s is valid", name_mountpoint)
        try:
            next(fs.iterdir("/"))
            tuple_fs.append((name_mountpoint, fs))
        except Exception as _ruf:
            logger.debug("%s is not a valide mountpoint", name_mountpoint)
            pass

    for name_mountpoint, fs in tuple_fs:
        if f"{name_mountpoint.lower()}:" not in target.fs.mounts:
            logger.warning("Mounting (arbitrary drive letter) %s to %s", fs, name_mountpoint.lower())
            target.fs.mount(f"{name_mountpoint.lower()}:", fs)
    for name_mountpoint, _fs in tuple_fs:
        if len(name_mountpoint) == 1:
            logger.info("Processing drive %s", name_mountpoint)
            for i in kape_target:
                to_copy.extend(process_drive_with_target(i, target, name_mountpoint))
        else:
            logger.warning("Skipping mountpoint : %s (not a drive)", name_mountpoint)
    return to_copy

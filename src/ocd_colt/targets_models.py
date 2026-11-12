from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PureWindowsPath

from ocd_colt.exception import ValidationError


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string, got {type(value).__name__}")
    return value


def _optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValidationError(f"{field_name} must be a int, got {type(value).__name__}")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{field_name} must be a bool, got {type(value).__name__}")
    return value


def _require_windows_path(value: object, field_name: str) -> PureWindowsPath:
    as_str = _require_str(value, field_name)
    as_path = PureWindowsPath(as_str)
    path_part = list(as_path.parts)
    if "%user%" in path_part:
        path_part[path_part.index("%user%")] = "*"
    return PureWindowsPath(*path_part)


@dataclass
class KapeTarget:
    name: str
    category: str
    path: PureWindowsPath
    recursive: bool = False
    always_add_to_queue: bool = False
    save_as_file_name: str | None = None
    file_mask: str = "*"
    comment: str = ""
    max_size: int | None = None
    min_size: int | None = None

    @classmethod
    def from_dict(cls, data: dict) -> KapeTarget:
        for required in ("Name", "Category", "Path"):
            if required not in data:
                raise ValidationError(f"Missing required field: {required}")

        save_as_file_name = data.get("SaveAsFileName")
        if save_as_file_name is not None:
            save_as_file_name = _require_str(save_as_file_name, "SaveAsFileName")

        return cls(
            name=_require_str(data["Name"], "Name"),
            category=_require_str(data["Category"], "Category"),
            path=_require_windows_path(data["Path"], "Path"),
            recursive=_require_bool(data.get("Recursive", False), "Recursive"),
            always_add_to_queue=_require_bool(data.get("AlwaysAddToQueue", False), "AlwaysAddToQueue"),
            save_as_file_name=save_as_file_name,
            file_mask=_require_str(data.get("FileMask", "*"), "FileMask"),
            comment=_require_str(data.get("Comment", ""), "Comment"),
            max_size=_optional_int(data.get("MaxSize"), "MaxSize"),
            min_size=_optional_int(data.get("MinSize"), "MinSize"),
        )


@dataclass
class KapeTargets:
    description: str
    author: str
    version: str
    guid: str
    recreate_directories: bool
    targets: list[KapeTarget]
    embedded_guid: set[str] = field(default_factory=set)

    @classmethod
    def from_dict(cls, data: dict) -> KapeTargets:
        for required in ("Description", "Author", "Version", "Id", "RecreateDirectories", "Targets"):
            if required not in data:
                raise ValidationError(f"Missing required field: {required}")

        targets_raw = data["Targets"]
        if not isinstance(targets_raw, list):
            raise ValidationError(f"Targets must be a list, got {type(targets_raw).__name__}")

        return cls(
            description=str(data["Description"]),
            author=str(data["Author"]),
            version=str(data["Version"]),  # coerce numbers to str, matching prior behaviour
            guid=str(data["Id"]),
            recreate_directories=bool(data["RecreateDirectories"]),
            targets=[KapeTarget.from_dict(t) for t in targets_raw],
        )

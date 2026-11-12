from __future__ import annotations

import logging
import typing

import yaml
from yaml.parser import ParserError

from ocd_colt.exception import ValidationError
from ocd_colt.targets_models import KapeTargets

if typing.TYPE_CHECKING:
    from pathlib import Path

    from ocd_colt.targets_models import KapeTarget

logger = logging.getLogger(__name__)


def replace_compound_target(
    target_to_replace: KapeTargets, targets_dir: dict[str, KapeTargets], processed_id: set[str]
) -> tuple[list[KapeTarget], set[str]]:
    """
    Replace compound target with "True" kape target
    :param target_to_replace:
    :param targets_dir:
    :param processed_id:  guid to ignore (prevent duplicate)
    :return:
    """
    ret: list[KapeTarget] = []
    for target in target_to_replace.targets:
        if target.path.suffix.lower() == ".tkape":
            target_name = target.path.stem.lower()
            if target_name in targets_dir:
                embedded_target = targets_dir[target_name]
                if embedded_target.guid not in processed_id:
                    processed_id.add(embedded_target.guid)
                    targets_to_append, new_processed_id = replace_compound_target(
                        embedded_target, targets_dir, processed_id
                    )
                    ret.extend(targets_to_append)
                    processed_id = {*processed_id, *new_processed_id}
            else:
                logger.warning("Reference to non existent tkape file : %s", target.path)
        else:
            ret.append(target)
    return ret, processed_id


def load_targets_config(config_dir: Path) -> dict[str, KapeTargets]:
    """
    Load files from disque and replace compound target
    :param config_dir:
    :return:
    """
    ret_dict: dict[str, KapeTargets] = {}
    file: Path
    for file in config_dir.rglob("*.tkape"):
        try:
            if file.parent.name.lower() != "!disabled":
                target_name = file.stem
                with file.open("r", errors="backslashreplace") as f:
                    as_dict = yaml.safe_load(f)
                    as_target = KapeTargets.from_dict(as_dict)
                    ret_dict[target_name.lower()] = as_target
        except ParserError as exc:
            logger.warning("Fail to parse %s : %s", file, exc)
        except ValidationError as exc:
            logger.warning("Fail to validate structure of %s : %s", file, exc)
        except OSError as exc:
            logger.warning("Fail to read %s : %s", file, exc)
    return ret_dict


def get_targets_list(targets_name: list[str], targets_dir: dict[str, KapeTargets]) -> list[KapeTarget]:
    """
    Generate list of target from user provided list of target_name
    :param targets_dir:
    :param targets_name:
    :return:
    """
    res = []
    # prevent multiple load of same target/ci
    processed_guid = set()
    for t_name in targets_name:
        t_name = t_name.lower()
        if t_name.endswith(".tkape"):
            t_name = t_name[: -len(".tkape")]
        t_object = targets_dir.get(t_name)
        if t_object is None:
            logger.warning("Target not found %s", t_name)
            continue
        if t_object.guid in processed_guid:
            continue
        processed_guid.add(t_object.guid)

        kape_target_to_add, new_processed_guid = replace_compound_target(t_object, targets_dir, processed_guid)
        res.extend(kape_target_to_add)
        processed_guid = {*processed_guid, *new_processed_guid}
    return res

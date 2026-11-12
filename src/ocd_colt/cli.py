#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import importlib.resources
import logging
import sys
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

from dissect.target import Target
from dissect.target.container import CONTAINERS
from dissect.target.helpers import keychain
from dissect.target.helpers.docs import INDENT_STEP, get_docstring
from dissect.target.loader import LOADERS_BY_SCHEME

from ocd_colt.extraction import extract_from_target
from ocd_colt.kape_config import get_targets_list, load_targets_config
from ocd_colt.output.dry_run import DryRunOutput
from ocd_colt.output.folder import FolderOutput
from ocd_colt.output.zip import ZipOutput

if TYPE_CHECKING:
    import io

    from dissect.target.filesystem import FilesystemEntry

    from ocd_colt.output.base import Output
    from ocd_colt.targets_models import KapeTarget

DEFAULT_TARGET = None

logger = logging.getLogger(__name__)


def argparser_type_dir(a_value):
    """Function to be used as argument type of an argument parser. Ensure param is a directory.

    Example:
        $ parser.add_argument("-o", "--output", help="Output directory", type=argparser_type_dir, default=".")

    Args:
        a_value:

    Returns:

    """
    path = Path(a_value).absolute()
    if path.exists() and not path.is_dir():
        raise argparse.ArgumentTypeError(f"{path} must be a directory (or a non existing location)")
    return path


def gen_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kape like extract from kape configuration on cold disk (VMDK, E01 etc..)."
    )
    # Doe not support multiple file yep.
    parser.add_argument(
        "-i",
        "--in",
        type=str,
        help="Input file. Support loader://file syntax used by dissect. E.g. `vmx://path/to/file.vmx`.",
        dest="infile",
        required=True,
    )

    parser.add_argument(
        "-c",
        "--config_dir",
        type=Path,
        help="directory containing kape target definition (tkape files), (default: %(default)s).",
        dest="target_config_dir",
        required=not importlib.resources.files("ocd_colt").joinpath("data").joinpath("kape_configuration").is_dir(),
        default=None,
    )
    parser.add_argument(
        "-t",
        "--target",
        type=str,
        help="Kape target configuration to use (may be comma separated eg: Evtx,FS), (default: %(default)s).",
        dest="targets",
        required=DEFAULT_TARGET is None,
        default=DEFAULT_TARGET,
    )
    parser.add_argument(
        "--deduplicate",
        help="Deduplicate files based on sha1), (default: %(default)s).",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "-L",
        "--long_file_name",
        help="Copy long file name (path > 215) in the LongFileNames directory, (default: %(default)s).",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "-l",
        "--list",
        help="List loader and associated scheme",
        action="store_true",
        default=False,
    )
    parser.add_argument("--dry_run", help="Only print file that will be copied", dest="dry_run", action="store_true")
    parser.add_argument(
        "-T",
        "--type",
        help="Output type (zip or folder), (default: %(default)s).",
        choices=["zip", "folder"],
        default="zip",
    )
    parser.add_argument("-o", "--output", help="Output directory", type=argparser_type_dir, default=".")
    parser.add_argument(
        "--path_prefix",
        help="Prefix path to use in zip. E.g copy data to target/C instead of C/, (default: %(default)s).",
        type=str,
        default="target",
    )
    parser.add_argument("-K", "--keychain-file", type=Path, help="keychain file in CSV format.")
    parser.add_argument("-Kv", "--keychain-value", help="passphrase, recovery key or key file path value")
    parser.add_argument(
        "-d",
        "--debug",
        help="Debug log level",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.INFO,
    )
    parser.add_argument(
        "-q",
        "--quiet",
        help="WARNING log level",
        action="store_const",
        dest="loglevel",
        const=logging.WARNING,
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s  {version('ocd_colt')}")
    return parser


def set_logger(loglevel: int):
    _logger = logging.getLogger("ocd_colt")
    _logger.setLevel(loglevel)
    formatter = logging.Formatter("[%(relativeCreated)dms]%(funcName)s:%(lineno)d | %(levelname)s - %(message)s")
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    _logger.addHandler(ch)


def copy_content(infile: io.TextIOWrapper, outfile: io.TextIOWrapper):
    outfile.write(infile.read())
    outfile.flush()


def process_target(target: Target, kape_targets: list[KapeTarget], output: Output):
    """Process a dissect target with a list of kape tkape targets."""

    to_copy_list: list[tuple[FilesystemEntry, str | None]] = list(set(extract_from_target(target, kape_targets)))
    to_copy_list.sort(key=lambda x: str(x[0]))
    last_source = None
    last_drive = None
    last_save_as_filename = None
    start = datetime.datetime.now(tz=datetime.timezone.utc)
    logger.info("Start copying file, %s files to copy", len(to_copy_list))
    for source, save_as_filename in to_copy_list:
        # create one log file by drive
        if last_drive != str(source)[:2]:
            output.rotate_logs_files()
            last_drive = str(source)[:2]

        if last_source != str(source) or last_save_as_filename != save_as_filename:
            try:
                output.copy_entry(source, save_as_filename)
                last_source = str(source)
                last_save_as_filename = save_as_filename
            except Exception:
                logger.warning("Fail to copy 1 entry : %s : %s", str(source), save_as_filename)
    output.rotate_logs_files()
    output.close()
    logger.info(
        "Processing ended. Copying into %s, copy duration : %s ",
        output,
        datetime.datetime.now(tz=datetime.timezone.utc) - start,
    )


def print_loader_list():
    loaders_info = {}
    for key, loader in LOADERS_BY_SCHEME.items():
        try:
            docstring = get_docstring(loader, "No documentation.").splitlines()[0].strip()
            loaders_info[key] = docstring
        except ImportError:
            continue
    loaders = sorted(loaders_info.items())
    print("Available loaders:")
    for loader_name, loader_description in loaders:
        if loader_name == "raw":
            containers = ", ".join(x.__type__ for x in CONTAINERS)
            print(f"{INDENT_STEP}{loader_name} - {loader_description} : {containers}")
        else:
            print(f"{INDENT_STEP}{loader_name} - {loader_description}")


def main() -> int:
    parser = gen_argparse()
    if ("-l" in sys.argv) or ("--list" in sys.argv):
        print_loader_list()
        return 0
    try:
        args = parser.parse_args()
    except SystemExit as e:
        return e.code
    infile: str = args.infile

    output_dir: Path = args.output
    out_type = args.type
    enable_long_file_name: bool = args.long_file_name
    deduplicate_sha1 = args.deduplicate

    path_prefix: str = args.path_prefix

    set_logger(args.loglevel)
    logger.debug("DEBUG MODE")
    if args.keychain_value:
        keychain.register_wildcard_value(args.keychain_value)
    if args.keychain_file:
        keychain.register_keychain_file(args.keychain_file)
    if args.target_config_dir:
        target_dir = load_targets_config(args.target_config_dir)
    else:
        with importlib.resources.as_file(
            importlib.resources.files("ocd_colt").joinpath("data").joinpath("kape_configuration")
        ) as t:
            target_dir = load_targets_config(t)
    user_target = get_targets_list(args.targets.split(","), target_dir)

    output_dir.mkdir(exist_ok=True, parents=True)
    try:
        target = Target.open(infile)
    except Exception as e:
        logger.error("%s", e)
        return 1
    if target.os != "windows":
        logger.warning(
            "Target is not a windows system : identified os : %s, target %s. May not run as expected", target.os, target
        )
    if target.hostname is None:
        target.hostname = "Unknown"
    output: Output = DryRunOutput(args.long_file_name)
    if out_type == "zip" and not args.dry_run:
        zip_name = target.hostname.upper() + datetime.datetime.now().strftime("-%Y-%m-%d-%H-%M-%S")
        out_zip = output_dir / f"{zip_name}.zip"
        if out_zip.exists():
            logger.error("Output :  already exist, skipping target %s", out_zip, target)
            return 1
        output = ZipOutput(
            enable_long_file_name=enable_long_file_name,
            path=out_zip,
            path_prefix=path_prefix,
            compress=True,
            deduplicate_sha1=deduplicate_sha1,
        )
    elif out_type == "folder" and not args.dry_run:
        output = FolderOutput(
            enable_long_file_name=enable_long_file_name, path=output_dir, deduplicate_sha1=deduplicate_sha1
        )

    process_target(target, user_target, output)
    return 0


if __name__ == "__main__":
    sys.exit(main())

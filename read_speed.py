#!/usr/bin/python3

"""Test case for Apport's current implementation for file2pkg."""

import argparse
import gzip
import os
import pathlib
import re
from collections.abc import Callable

from apport.logging import memdbg
from contents_common import get_contents_filenames, measure_duration


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", default="amd64")
    parser.add_argument(
        "-r",
        "--release",
        default="noble",
        choices=["bionic", "focal", "jammy", "noble", "oracular"],
    )
    parser.add_argument("--mirror", default="http://de.archive.ubuntu.com/ubuntu/")
    parser.add_argument(
        "-d",
        "--delete-cache",
        action="store_true",
        help="Delete cache and force recreation",
    )
    parser.add_argument("-c", "--cache", default="contents_cache")
    parser.add_argument("-p", "--only-proposed", action="store_true")
    parser.add_argument("-s", "--print-sum", action="store_true")
    parser.add_argument(
        "-j", "--jammy", action="store_const", const="jammy", dest="release"
    )
    parser.add_argument(
        "-n", "--noble", action="store_const", const="noble", dest="release"
    )
    parser.add_argument(
        "-o", "--oracular", action="store_const", const="oracular", dest="release"
    )
    return parser.parse_args()


def _update_given_file2pkg_mapping(contents_filename: str, dist: str) -> None:
    file2pkg: dict[bytes, bytes] = {}
    path_exclude_pattern = re.compile(
        rb"^:|(boot|var|usr/(include|src|[^/]+/include"
        rb"|share/(doc|gocode|help|icons|locale|man|texlive)))/"
    )
    with gzip.open(contents_filename, "rb") as contents:
        if dist in {"trusty", "xenial"}:
            # the first 32 lines are descriptive only for these
            # releases
            for _ in range(32):
                next(contents)

        for line in contents:
            if path_exclude_pattern.match(line):
                continue
            path, column2 = line.rsplit(maxsplit=1)
            package = column2.split(b",")[0].split(b"/")[-1]
            if path in file2pkg:
                if package == file2pkg[path]:
                    continue
                # if the package was updated use the update
                # b/c everyone should have packages from
                # -updates and -security installed
            file2pkg[path] = package


def _just_read(contents_filename: str, dist: str) -> None:
    with gzip.open(contents_filename, "rb") as contents:
        if dist in {"trusty", "xenial"}:
            # the first 32 lines are descriptive only for these
            # releases
            for _ in range(32):
                next(contents)

        for _ in contents:
            pass


def _filter_unwanted(contents_filename: str, dist: str) -> None:
    path_exclude_pattern = re.compile(
        rb"^:|(boot|var|usr/(include|src|[^/]+/include"
        rb"|share/(doc|gocode|help|icons|locale|man|texlive)))/"
    )
    with gzip.open(contents_filename, "rb") as contents:
        if dist in {"trusty", "xenial"}:
            # the first 32 lines are descriptive only for these
            # releases
            for _ in range(32):
                next(contents)

        for line in contents:
            if path_exclude_pattern.match(line):
                continue


def _parse_path_package(contents_filename: str, dist: str) -> None:
    path_exclude_pattern = re.compile(
        rb"^:|(boot|var|usr/(include|src|[^/]+/include"
        rb"|share/(doc|gocode|help|icons|locale|man|texlive)))/"
    )
    with gzip.open(contents_filename, "rb") as contents:
        if dist in {"trusty", "xenial"}:
            # the first 32 lines are descriptive only for these
            # releases
            for _ in range(32):
                next(contents)

        for line in contents:
            if path_exclude_pattern.match(line):
                continue
            # pylint: disable=unused-variable
            path, column2 = line.rsplit(maxsplit=1)
            package = column2.split(b",")[0].split(b"/")[-1]


def _is_up_to_date(mapping_file: pathlib.Path, contents_filenames: list[str]) -> bool:
    if not mapping_file.exists():
        return False
    database_stat = mapping_file.stat()
    if database_stat.st_size == 0:
        return False

    for contents_filename in contents_filenames:
        mtime = os.stat(contents_filename).st_mtime
        if mtime >= database_stat.st_mtime:
            return False
    return True


def _measure(
    contents_filenames: list[str], func: Callable[[str, str], None], dist: str
) -> None:
    name = func.__name__.replace("_", " ").strip()
    with measure_duration(name):
        for contents_filename in contents_filenames:
            with measure_duration(f"{name} '{contents_filename}'"):
                func(contents_filename, dist)


def main() -> None:
    """Entry point."""
    args = _parse_args()

    if args.only_proposed:
        pockets = ["-proposed"]
    else:
        pockets = ["-proposed", "", "-security", "-updates"]
    pathlib.Path(args.cache).mkdir(parents=True, exist_ok=True)

    contents_filenames = get_contents_filenames(
        args.cache, args.release, args.arch, args.mirror, pockets
    )
    _measure(contents_filenames, _just_read, args.release)
    _measure(contents_filenames, _filter_unwanted, args.release)
    _measure(contents_filenames, _parse_path_package, args.release)
    _measure(contents_filenames, _update_given_file2pkg_mapping, args.release)
    memdbg("end")


if __name__ == "__main__":
    with measure_duration("Total"):
        main()

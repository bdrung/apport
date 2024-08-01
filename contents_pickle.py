#!/usr/bin/python3

"""Test case for Apport's current implementation for file2pkg."""

import gzip
import os
import pathlib
import pickle
import re

from apport.logging import memdbg
from contents_common import (
    measure_duration,
    parse_args_and_common_main,
    run_access_tests_binary,
)


def _update_given_file2pkg_mapping(
    file2pkg: dict[bytes, bytes], contents_filename: str, dist: str
) -> None:
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


def _get_file2pkg_mapping(
    mapping_file: pathlib.Path, release: str, contents_filenames: list[str]
) -> dict[bytes, bytes]:
    if _is_up_to_date(mapping_file, contents_filenames):
        with measure_duration("Load"):
            with open(mapping_file, "rb") as fp:
                return pickle.load(fp)

    file2pkg: dict[bytes, bytes] = {}
    with measure_duration("Creation"):
        for contents_filename in contents_filenames:
            _update_given_file2pkg_mapping(file2pkg, contents_filename, release)
    _save_contents_mapping(mapping_file, file2pkg)
    return file2pkg


def _save_contents_mapping(mapping_file, file2deb):
    try:
        with measure_duration("Save"):
            with open(mapping_file, "wb") as fp:
                pickle.dump(file2deb, fp)
    # rather than crashing on systems with little memory just don't
    # write the crash file
    except MemoryError:
        pass


def main() -> None:
    """Entry point."""
    args, mapping_db, content_filenames = parse_args_and_common_main(".pickle")
    file2pkg = _get_file2pkg_mapping(mapping_db, args.release, content_filenames)
    run_access_tests_binary(file2pkg, args)
    memdbg("end")


if __name__ == "__main__":
    with measure_duration("Total"):
        main()

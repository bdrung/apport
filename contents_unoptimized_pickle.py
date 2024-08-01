#!/usr/bin/python3

"""Test case for Apport's current implementation for file2pkg."""

import gzip
import os
import pathlib
import pickle

from apport.logging import memdbg
from contents_common import (
    measure_duration,
    parse_args_and_common_main,
    run_access_tests_binary,
)


def _update_given_file2pkg_mapping(
    file2pkg: dict[bytes, bytes], contents_filename: str, dist: str
) -> None:
    with gzip.open(contents_filename, "rb") as contents:
        line_num = 0
        for line in contents:
            line_num += 1
            # the first 32 lines are descriptive only for these
            # releases
            if dist in {"trusty", "xenial"} and line_num < 33:
                continue
            path = line.split()[0]
            if path.split(b"/")[0] == b"usr":
                if path.split(b"/")[1] not in (
                    b"lib",
                    b"libexec",
                    b"libx32",
                    b"bin",
                    b"sbin",
                    b"share",
                    b"games",
                    b"Brother",
                ):
                    continue
                if path.split(b"/")[1] == b"share" and path.split(b"/")[2] in {
                    b"doc",
                    b"icons",
                    b"man",
                    b"texlive",
                    b"gocode",
                    b"locale",
                    b"help",
                }:
                    continue
                package = line.split()[-1].split(b",")[0].split(b"/")[-1]
            elif path.split(b"/")[0] in {b"lib", b"bin", b"sbin", b"etc"}:
                package = line.split()[-1].split(b",")[0].split(b"/")[-1]
            else:
                continue
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
    args, mapping_db, content_filenames = parse_args_and_common_main(".pickle_old")
    file2pkg = _get_file2pkg_mapping(mapping_db, args.release, content_filenames)
    run_access_tests_binary(file2pkg, args)
    memdbg("end")


if __name__ == "__main__":
    with measure_duration("Total"):
        main()

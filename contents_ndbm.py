#!/usr/bin/python3

"""Test case for caching the contents files in a SQLite database."""

import dbm.ndbm
import gzip
import pathlib
import re
from collections.abc import Iterator, Mapping

from apport.logging import memdbg
from contents_common import (
    measure_duration,
    parse_args_and_common_main,
    run_access_tests_binary,
)
from contents_dbm import TestPath2PackageDBM


class Path2Package(Mapping[bytes, bytes]):
    """Filename to Debian package dictionary-like object.

    A backing database is open on init and close on object deletion.
    """

    def __init__(self, database_file: pathlib.Path) -> None:
        assert database_file.suffix == ".db"
        self.database_file = database_file
        if not database_file.exists() or database_file.stat().st_size == 0:
            flags = "c"
        else:
            flags = "r"
        self.database = dbm.ndbm.open(str(self.database_file.with_suffix("")), flags)

    def __del__(self) -> None:
        """Close the database connection on object deletion."""
        if hasattr(self, "database"):
            self.database.close()

    def __getitem__(self, key: bytes) -> bytes:
        return self.database[key]

    def __iter__(self) -> Iterator[bytes]:
        return iter(self.database.keys())

    def __len__(self) -> int:
        return len(self.database)

    def __setitem__(self, key: bytes, value: bytes) -> None:
        """Set new value in datadase."""
        self.database[key] = value

    def is_empty(self) -> bool:
        """Check if the database is empty."""
        return len(self) == 0

    def update_from_contents_file(self, contents_filename: str, dist: str) -> None:
        """Update database with entries from the Contents file.

        Existing paths will be overwritten by new entries.
        """
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
                self[path] = package


def _get_file2pkg_mapping(
    database_filename: pathlib.Path, release: str, contents_filenames: list[str]
) -> Path2Package:
    mapping_db = Path2Package(database_filename)
    if mapping_db.is_empty():
        with measure_duration("Creation"):
            for contents_filename in contents_filenames:
                mapping_db.update_from_contents_file(contents_filename, release)
    return mapping_db


def main() -> None:
    """Entry point."""
    args, mapping_db, content_filenames = parse_args_and_common_main(".ndbm.db")
    file2pkg = _get_file2pkg_mapping(mapping_db, args.release, content_filenames)
    run_access_tests_binary(file2pkg, args)
    memdbg("end")


class TestPath2PackageNDBM(TestPath2PackageDBM):
    """Test Path2Package class."""

    SUFFIX = ".ndbm.db"
    _Path2PackageClass = Path2Package  # type: ignore[assignment]


del TestPath2PackageDBM


if __name__ == "__main__":
    with measure_duration("Total"):
        main()

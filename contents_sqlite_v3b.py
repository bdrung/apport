#!/usr/bin/python3

"""Test case for caching the contents files in a SQLite database.

Use normalized form and store the package names in a separate packages
table. To save disk space, split the beginning of the path and store
them in a separate directories table.
"""

import pathlib

from apport.logging import memdbg
from contents_common import (
    measure_duration,
    parse_args_and_common_main,
    run_access_tests,
)
from contents_sqlite_v1 import TestPath2Package
from contents_sqlite_v3 import Path2Package as Path2PackageV3


class Path2Package(Path2PackageV3):
    """Path to Debian package mapping.

    A backing SQLite database is open on __init__ and closed on object
    deletion. The data is stored in normalized form.

    If database_file is set to `None` an in-memory database will be used.
    """

    @staticmethod
    def _split_path(path: str) -> tuple[str, str]:
        parts = path.split("/", maxsplit=4)
        return "/".join(parts[:-1]), parts[-1]


def _get_file2pkg_mapping(
    database_filename: pathlib.Path, release: str, contents_filenames: list[str]
) -> Path2Package:
    mapping_db = Path2Package(database_filename)
    if mapping_db.is_empty():
        with measure_duration("Creation"):
            for contents_filename in contents_filenames:
                mapping_db.update_from_contents_file(contents_filename, release)
    return mapping_db


def _suffix_from_filename() -> str:
    name = pathlib.Path(__file__).name
    assert name.startswith("contents_sqlite") and name.endswith(".py")
    return f"{name[15:-3]}.sqlite3"


def main() -> None:
    """Entry point."""
    args, mapping_db, content_filenames = parse_args_and_common_main(
        _suffix_from_filename()
    )
    file2pkg = _get_file2pkg_mapping(mapping_db, args.release, content_filenames)
    if args.print_sum:
        file2pkg.print_summary()
    run_access_tests(file2pkg, args)
    memdbg("end")


class TestPath2PackageV3b(TestPath2Package):
    """Test Path2Package class."""

    _Path2PackageClass = Path2Package  # type: ignore[assignment]


del TestPath2Package


if __name__ == "__main__":
    with measure_duration("Total"):
        main()

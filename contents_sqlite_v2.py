#!/usr/bin/python3

"""Test case for caching the contents files in a SQLite database.

Use a normalized form and store the package names in a separate packages table.
"""

import gzip
import pathlib
import re
import sqlite3
from collections.abc import Iterator, Mapping

from apport.logging import memdbg
from contents_common import (
    measure_duration,
    parse_args_and_common_main,
    run_access_tests,
)
from contents_sqlite_v1 import TestPath2Package


class _Value2ID(Mapping[str, int]):
    """Inverse cache for a integer key to string value database table."""

    def __init__(self) -> None:
        self.data: dict[str, int] = {}
        self.max_id: int = 0

    def __getitem__(self, key: str) -> int:
        return self.data[key]

    def __len__(self) -> int:
        return len(self.data)

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def add(self, value: str) -> int:
        """Add a new value to the cache and return the assigned ID."""
        self.max_id += 1
        self.data[value] = self.max_id
        return self.max_id


class Path2Package(Mapping[str, str]):
    """Path to Debian package mapping.

    A backing SQLite database is open on __init__ and closed on object
    deletion. The data is stored in normalized form.

    If database_file is set to `None` an in-memory database will be used.
    """

    def __init__(self, database_file: pathlib.Path | None = None) -> None:
        self.database_file = database_file
        self.connection = self._connect()
        if (
            database_file is None
            or not database_file.exists()
            or database_file.stat().st_size == 0
        ):
            self._create_tables()
            self.package_id_cache = _Value2ID()
        else:
            # FIXME: load cache
            self.package_id_cache = _Value2ID()

    def __del__(self) -> None:
        """Close the SQLite database connection on object deletion."""
        if hasattr(self, "connection"):
            self.connection.close()

    def _connect(self) -> sqlite3.Connection:
        """Opens a connection to the SQLite database file.

        If database_file is set to `None` an in-memory database will be used.
        """
        if self.database_file:
            database = f"file://{self.database_file.absolute()}"
        else:
            database = ":memory:"
        connection = sqlite3.connect(database)
        if hasattr(connection, "autocommit"):
            connection.autocommit = False
        return connection

    def _create_tables(self) -> None:
        """Create SQLite database tables."""
        cursor = self.connection.cursor()
        cursor.executescript(
            "CREATE TABLE packages ("
            "  id integer PRIMARY KEY NOT NULL,"
            "  package text NOT NULL UNIQUE"
            ");"
            "CREATE TABLE path_package ("
            "  path TEXT PRIMARY KEY NOT NULL,"
            "  package_id integer NOT NULL,"
            "  FOREIGN KEY (package_id)"
            "    REFERENCES packages(id)"
            ");"
        )
        self.connection.commit()

    def __getitem__(self, key: str) -> str:
        cursor = self.connection.execute(
            "SELECT package FROM path_package "
            "LEFT JOIN packages ON path_package.package_id = packages.id "
            "WHERE path = ?",
            (key,),
        )
        found = cursor.fetchone()
        if found is None:
            raise KeyError(key)
        return found[0]

    def __iter__(self) -> Iterator[str]:
        cursor = self.connection.execute(
            "SELECT path FROM path_package ORDER BY path ASC"
        )
        while True:
            found = cursor.fetchone()
            if found is None:
                return
            yield found[0]

    def __len__(self) -> int:
        cursor = self.connection.execute("SELECT COUNT(*) FROM path_package")
        found = cursor.fetchone()
        assert found is not None
        return found[0]

    def __setitem__(self, key: str, value: str) -> None:
        """Set new value in datadase.

        Warning: The new value is only inserted into the database but
        not committed for better performance. A database commit needs
        to be done to persist the change.
        """
        package_id = self.package_id_cache.get(value)
        if package_id is None:
            package_id = self.package_id_cache.add(value)
            self.connection.execute(
                "INSERT INTO packages VALUES(?, ?)", (package_id, value)
            )
        self.connection.execute(
            "INSERT INTO path_package VALUES(?, ?) "
            "ON CONFLICT(path) DO UPDATE SET package_id=excluded.package_id",
            (key, package_id),
        )

    def is_empty(self) -> bool:
        """Check if the database is empty."""
        cursor = self.connection.execute("SELECT 1 FROM path_package LIMIT 1")
        return cursor.fetchone() is None

    @staticmethod
    def _insert_many(
        cursor: sqlite3.Cursor,
        new_package_id: list[tuple[int, str]],
        new_path_package: list[tuple[str, int]],
    ) -> None:
        if new_package_id:
            cursor.executemany("INSERT INTO packages VALUES(?, ?)", new_package_id)
            new_package_id.clear()
        cursor.executemany(
            "INSERT INTO path_package VALUES(?, ?) "
            "ON CONFLICT(path) DO UPDATE SET package_id=excluded.package_id",
            new_path_package,
        )
        new_path_package.clear()

    def update_from_contents_file(
        self, contents_filename: str, dist: str, group_inserts: int = 100
    ) -> None:
        """Update database with entries from the Contents file.

        Existing paths will be overwritten by new entries.
        """
        cursor = self.connection.cursor()
        new_path_package: list[tuple[str, int]] = []
        new_package_id: list[tuple[int, str]] = []

        path_exclude_pattern = re.compile(
            r"^:|(boot|var|usr/(include|src|[^/]+/include"
            r"|share/(doc|gocode|help|icons|locale|man|texlive)))/"
        )
        with gzip.open(contents_filename, "rt") as contents:
            if dist in {"trusty", "xenial"}:
                # the first 32 lines are descriptive only for these
                # releases
                for _ in range(32):
                    next(contents)

            # paths: list[tuple[str]] = []
            # current_package: str | None = None
            for line in contents:
                if path_exclude_pattern.match(line):
                    continue
                path, column2 = line.rsplit(maxsplit=1)
                package = column2.split(",")[0].split("/")[-1]

                package_id = self.package_id_cache.get(package)
                if package_id is None:
                    package_id = self.package_id_cache.add(package)
                    new_package_id.append((package_id, package))
                new_path_package.append((path, package_id))
                if len(new_path_package) > group_inserts:
                    self._insert_many(cursor, new_package_id, new_path_package)
        if new_path_package:
            self._insert_many(cursor, new_package_id, new_path_package)
        self.connection.commit()

    def __contains__(self, o: object) -> bool:
        if not isinstance(o, str):
            return False
        cursor = self.connection.execute(
            "SELECT 1 FROM path_package WHERE path = ?", (o,)
        )
        return cursor.fetchone() is not None

    def print_summary(self) -> None:
        """Print number of entries in the database."""
        packages = self.connection.execute("SELECT COUNT(*) FROM packages").fetchone()
        assert packages is not None
        print(f"Entries in packages table: {packages[0]:,}")
        assert len(self.package_id_cache) == packages[0]


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


class TestPath2PackageV2(TestPath2Package):
    """Test Path2Package class."""

    _Path2PackageClass = Path2Package  # type: ignore[assignment]


del TestPath2Package

if __name__ == "__main__":
    with measure_duration("Total"):
        main()

#!/usr/bin/python3

"""Test case for caching the contents files in a SQLite database.

split filename into path and name and store them in normal form.

Slow and the names tables has to many entries to fit into memory.

$ du -s contents_cache/*noble-amd* | sort -n
333108	contents_cache/contents_mapping-noble-amd64_v3.sqlite3
673468	contents_cache/contents_mapping-noble-amd64_v2.sqlite3
728960	contents_cache/contents_mapping-noble-amd64.sqlite3
"""

import gzip
import os
import pathlib
import re
import sqlite3
from collections.abc import Iterable, Iterator, Mapping

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
            self.directory_id_cache = _Value2ID()
            self.name_id_cache = _Value2ID()
        else:
            # FIXME: load cache
            self.package_id_cache = _Value2ID()
            self.directory_id_cache = _Value2ID()
            self.name_id_cache = _Value2ID()

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
            "CREATE TABLE names ("
            "  id integer PRIMARY KEY NOT NULL,"
            "  name text NOT NULL UNIQUE"
            ");"
            "CREATE TABLE directories ("
            "  id integer PRIMARY KEY NOT NULL,"
            "  directory text NOT NULL UNIQUE"
            ");"
            "CREATE TABLE directory_name_package ("
            "  directory_id integer NOT NULL,"
            "  name_id integer NOT NULL,"
            "  package_id integer NOT NULL,"
            "  PRIMARY KEY (directory_id, name_id),"
            "  FOREIGN KEY (directory_id) REFERENCES directories(id)"
            "  FOREIGN KEY (name_id) REFERENCES names(id)"
            "  FOREIGN KEY (package_id) REFERENCES packages(id)"
            ");"
        )
        self.connection.commit()

    def __getitem__(self, key: str) -> str:
        cursor = self.connection.execute(
            "SELECT package FROM directory_name_package "
            "LEFT JOIN directories "
            "ON directory_name_package.directory_id = directories.id "
            "LEFT JOIN names "
            "ON directory_name_package.name_id = names.id "
            "LEFT JOIN packages "
            "ON directory_name_package.package_id = packages.id "
            "WHERE directory = ? AND name = ?",
            os.path.split(key),
        )
        found = cursor.fetchone()
        if found is None:
            raise KeyError(key)
        return found[0]

    def __iter__(self) -> Iterator[str]:
        cursor = self.connection.execute(
            "SELECT directory, name FROM directory_name_package "
            "LEFT JOIN directories "
            "ON directory_name_package.directory_id = directories.id "
            "LEFT JOIN names "
            "ON directory_name_package.name_id = names.id "
            "ORDER BY directory ASC, name ASC"
        )
        while True:
            found = cursor.fetchone()
            if found is None:
                return
            yield f"{found[0]}/{found[1]}"

    def __len__(self) -> int:
        cursor = self.connection.execute("SELECT COUNT(*) FROM directory_name_package")
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
        directory, name = os.path.split(key)
        directory_id = self.directory_id_cache.get(directory)
        if directory_id is None:
            directory_id = self.directory_id_cache.add(directory)
            self.connection.execute(
                "INSERT INTO directories VALUES(?, ?)", (directory_id, directory)
            )
        name_id = self.name_id_cache.get(name)
        if name_id is None:
            name_id = self.name_id_cache.add(name)
            self.connection.execute("INSERT INTO names VALUES(?, ?)", (name_id, name))
        self.connection.execute(
            "INSERT INTO directory_name_package VALUES(?, ?, ?) "
            "ON CONFLICT(directory_id, name_id) "
            "DO UPDATE SET package_id=excluded.package_id",
            (directory_id, name_id, package_id),
        )

    def is_empty(self) -> bool:
        """Check if the database is empty."""
        cursor = self.connection.execute("SELECT 1 FROM directory_name_package LIMIT 1")
        return cursor.fetchone() is None

    @staticmethod
    def _insert_many(
        cursor: sqlite3.Cursor,
        new_package_id: Iterable[tuple[int, str]],
        new_directory_id: Iterable[tuple[int, str]],
        new_name_id: Iterable[tuple[int, str]],
        new_path_package: Iterable[tuple[int, int, int]],
    ) -> None:
        if new_package_id:
            cursor.executemany("INSERT INTO packages VALUES(?, ?)", new_package_id)
        if new_directory_id:
            cursor.executemany("INSERT INTO directories VALUES(?, ?)", new_directory_id)
        if new_name_id:
            cursor.executemany("INSERT INTO names VALUES(?, ?)", new_name_id)
        cursor.executemany(
            "INSERT INTO directory_name_package VALUES(?, ?, ?) "
            "ON CONFLICT(directory_id, name_id) "
            "DO UPDATE SET package_id=excluded.package_id",
            new_path_package,
        )

    # pylint: disable-next=too-many-locals
    def update_from_contents_file(
        self, contents_filename: str, dist: str, group_inserts: int = 100
    ) -> None:
        """Update database with entries from the Contents file.

        Existing paths will be overwritten by new entries.
        """
        cursor = self.connection.cursor()
        new_path_package: list[tuple[int, int, int]] = []
        new_package_id: list[tuple[int, str]] = []
        new_directory_id: list[tuple[int, str]] = []
        new_name_id: list[tuple[int, str]] = []

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

                directory, name = os.path.split(path)
                name_id = self.name_id_cache.get(name)
                if name_id is None:
                    name_id = self.name_id_cache.add(name)
                    new_name_id.append((name_id, name))
                directory_id = self.directory_id_cache.get(directory)
                if directory_id is None:
                    directory_id = self.directory_id_cache.add(directory)
                    new_directory_id.append((directory_id, directory))

                new_path_package.append((directory_id, name_id, package_id))
                if len(new_path_package) > group_inserts:
                    self._insert_many(
                        cursor,
                        new_package_id,
                        new_directory_id,
                        new_name_id,
                        new_path_package,
                    )
                    new_path_package = []
                    new_package_id = []
                    new_directory_id = []
                    new_name_id = []
        if new_path_package:
            self._insert_many(
                cursor, new_package_id, new_directory_id, new_name_id, new_path_package
            )
        self.connection.commit()

    def __contains__(self, o: object) -> bool:
        if not isinstance(o, str):
            return False
        cursor = self.connection.execute(
            "SELECT 1 FROM directory_name_package "
            "LEFT JOIN directories "
            "ON directory_name_package.directory_id = directories.id "
            "LEFT JOIN names "
            "ON directory_name_package.name_id = names.id "
            "WHERE directory = ? AND name = ?",
            os.path.split(o),
        )
        return cursor.fetchone() is not None

    def print_summary(self) -> None:
        """Print number of entries in the database."""
        packages = self.connection.execute("SELECT COUNT(*) FROM packages").fetchone()
        assert packages is not None
        print(f"Entries in packages table: {packages[0]:,}")
        assert len(self.package_id_cache) == packages[0]

        directories = self.connection.execute(
            "SELECT COUNT(*) FROM directories"
        ).fetchone()
        assert directories is not None
        print(f"Entries in directories table: {directories[0]:,}")
        assert len(self.directory_id_cache) == directories[0]

        names = self.connection.execute("SELECT COUNT(*) FROM names").fetchone()
        assert names is not None
        print(f"Entries in names table: {names[0]:,}")
        assert len(self.name_id_cache) == names[0]


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


class TestPath2PackageNormalized(TestPath2Package):
    """Test Path2Package class."""

    _Path2PackageClass = Path2Package  # type: ignore[assignment]


del TestPath2Package

if __name__ == "__main__":
    with measure_duration("Total"):
        main()

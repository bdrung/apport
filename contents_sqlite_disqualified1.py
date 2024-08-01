#!/usr/bin/python3

"""Test case for caching the contents files in a SQLite database.

Use normal form (separate packages table), but do not cache packages table
locally. Disqualified because too slow.
"""

import gzip
import pathlib
import re
import sqlite3
from collections.abc import Callable, Iterable, Iterator, Mapping

from apport.logging import memdbg
from contents_common import (
    measure_duration,
    parse_args_and_common_main,
    run_access_tests,
)
from contents_sqlite_v1 import TestPath2Package


class Path2Package(Mapping[str, str]):
    """Path to Debian package mapping.

    A backing SQLite database is open on __init__ and closed on object
    deletion. The data is stored in normalized form.

    If database_file is set to `None` an in-memory database will be used.
    """

    V = 1

    def __init__(self, database_file: pathlib.Path | None = None) -> None:
        self.database_file = database_file
        self.connection = self._connect()
        if (
            database_file is None
            or not database_file.exists()
            or database_file.stat().st_size == 0
        ):
            self._create_tables()
            self.package_id_cache: dict[str, int] = {}
            self.max_package_id = 0
        else:
            # FIXME: load cache
            self.package_id_cache = {}
            self.max_package_id = 0

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
            # "CREATE UNIQUE INDEX idx_packages_id "
            # "ON packages(id);"
            # "CREATE UNIQUE INDEX idx_path_package_path "
            # "ON path_package(path);"
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

    def _setitem_v1(self, key: str, value: str) -> None:
        """Set new value in datadase."""
        found = self.connection.execute(
            "SELECT id from packages WHERE package = ?", (value,)
        ).fetchone()
        if found is None:
            found = self.connection.execute(
                "INSERT INTO packages (package) VALUES(?) RETURNING id", (value,)
            ).fetchone()
            assert found is not None
        package_id = found[0]

        self.connection.execute(
            "INSERT INTO path_package VALUES(?, ?) "
            "ON CONFLICT(path) DO UPDATE SET package_id=excluded.package_id",
            (key, package_id),
        )

    def _setitem_v2(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO packages (package) VALUES(?) "
            "ON CONFLICT (package) DO NOTHING RETURNING id",
            (value,),
        )
        self.connection.execute(
            "INSERT INTO path_package "
            "VALUES(?, (SELECT id FROM packages WHERE package = ?)) "
            "ON CONFLICT(path) DO UPDATE SET package_id=excluded.package_id",
            (key, value),
        )

    def __setitem__(self, key: str, value: str) -> None:
        """Set new value in datadase.

        Warning: The new value is only inserted into the database but
        not committed for better performance. A database commit needs
        to be done to persist the change.
        """
        self._setitem_v1(key, value)

    @staticmethod
    def _insert_many(
        cursor: sqlite3.Cursor, paths: Iterable[tuple[str]], package: str
    ) -> None:
        found = cursor.execute(
            "SELECT id from packages WHERE package = ?", (package,)
        ).fetchone()
        if found is None:
            found = cursor.execute(
                "INSERT INTO packages (package) VALUES(?) RETURNING id", (package,)
            ).fetchone()
            assert found is not None
        package_id = found[0]

        cursor.executemany(
            f"INSERT INTO path_package VALUES(?, {package_id}) "
            f"ON CONFLICT(path) DO UPDATE SET package_id=excluded.package_id",
            paths,
        )

    @staticmethod
    def _cursor_setitem_v1(cursor: sqlite3.Cursor, key: str, value: str) -> None:
        """Set new value in datadase."""
        found = cursor.execute(
            "SELECT id from packages WHERE package = ?", (value,)
        ).fetchone()
        if found is None:
            found = cursor.execute(
                "INSERT INTO packages (package) VALUES(?) RETURNING id", (value,)
            ).fetchone()
            assert found is not None
        package_id = found[0]

        cursor.execute(
            "INSERT INTO path_package VALUES(?, ?) "
            "ON CONFLICT(path) DO UPDATE SET package_id=excluded.package_id",
            (key, package_id),
        )

    def is_empty(self) -> bool:
        """Check if the database is empty."""
        cursor = self.connection.execute("SELECT 1 FROM path_package LIMIT 1")
        return cursor.fetchone() is None

    def update_from_contents_file_setitem(
        self, contents_filename: str, dist: str, setitem: Callable
    ) -> None:
        """Update database with entries from the Contents file.

        Existing paths will be overwritten by new entries.
        """
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

            for line in contents:
                if path_exclude_pattern.match(line):
                    continue
                path, column2 = line.rsplit(maxsplit=1)
                package = column2.split(",")[0].split("/")[-1]
                setitem(path, package)
        self.connection.commit()

    def update_from_contents_file_setitem_cursor(
        self, contents_filename: str, dist: str, _insert_one: Callable
    ) -> None:
        """Update database with entries from the Contents file.

        Existing paths will be overwritten by new entries.
        """
        cursor = self.connection.cursor()

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

            for line in contents:
                if path_exclude_pattern.match(line):
                    continue
                path, column2 = line.rsplit(maxsplit=1)
                package = column2.split(",")[0].split("/")[-1]
                _insert_one(cursor, path, package)
        self.connection.commit()

    def update_from_contents_file_group(
        self, contents_filename: str, dist: str, group_inserts: int = 100
    ) -> None:
        """Update database with entries from the Contents file.

        Existing paths will be overwritten by new entries.
        """
        cursor = self.connection.cursor()

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

            paths: list[tuple[str]] = []
            current_package: str | None = None
            for line in contents:
                if path_exclude_pattern.match(line):
                    continue
                path, column2 = line.rsplit(maxsplit=1)
                package = column2.split(",")[0].split("/")[-1]

                if current_package != package or len(paths) > group_inserts:
                    if paths:
                        assert current_package
                        self._insert_many(cursor, paths, current_package)
                    paths = [(path,)]
                    current_package = package
                else:
                    paths.append((path,))
        if paths:
            assert current_package
            self._insert_many(cursor, paths, current_package)
        self.connection.commit()

    @staticmethod
    def _insert_many_cached(
        cursor: sqlite3.Cursor,
        new_package_id: Iterable[tuple[int, str]],
        new_path_package: Iterable[tuple[str, int]],
    ) -> None:
        if new_package_id is not None:
            cursor.executemany("INSERT INTO packages VALUES(?, ?)", new_package_id)
        cursor.executemany(
            "INSERT INTO path_package VALUES(?, ?) "
            "ON CONFLICT(path) DO UPDATE SET package_id=excluded.package_id",
            new_path_package,
        )

    def update_from_contents_file_cached(
        self, contents_filename: str, dist: str, group_inserts: int = 100
    ) -> None:
        """Update database with entries from the Contents file.

        Existing paths will be overwritten by new entries.
        """
        cursor = self.connection.cursor()

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

            new_path_package: list[tuple[str, int]] = []
            new_package_id: list[tuple[int, str]] = []

            # paths: list[tuple[str]] = []
            # current_package: str | None = None
            for line in contents:
                if path_exclude_pattern.match(line):
                    continue
                path, column2 = line.rsplit(maxsplit=1)
                package = column2.split(",")[0].split("/")[-1]

                package_id = self.package_id_cache.get(package)
                if package_id is None:
                    self.max_package_id += 1
                    package_id = self.max_package_id
                    self.package_id_cache[package] = package_id
                    new_package_id.append((package_id, package))
                new_path_package.append((path, package_id))
                if len(new_path_package) > group_inserts:
                    self._insert_many_cached(cursor, new_package_id, new_path_package)
                    new_path_package = []
                    new_package_id = []
        if new_path_package:
            self._insert_many_cached(cursor, new_package_id, new_path_package)
        self.connection.commit()

    def update_from_contents_file(
        self, contents_filename: str, dist: str, group_inserts: int = 100
    ) -> None:
        """Update database with entries from the Contents file.

        Existing paths will be overwritten by new entries.

        Set v and test the code with:
        ```
        time ./contents_sqlite2.py --release noble -r
        ```
        The reference:
        ```
        time ./contents_sqlite.py --release noble -r
        ```

        Results
        =======

        * reference: 15s
        * contents_sqlite.py with __setitem__ mod: 20s
        * group (v = 1): 18s
        * _cursor_setitem_v1 (v = 2): 26s
        * _setitem_v1 (v = 3): 28s
        * _setitem_v2 (v = 4): 37s
        """
        if self.V == 1:
            self.update_from_contents_file_group(contents_filename, dist, group_inserts)
        elif self.V == 2:
            self.update_from_contents_file_setitem_cursor(
                contents_filename, dist, self._cursor_setitem_v1
            )
        elif 3 <= self.V <= 4:
            setitem = {1: self._setitem_v1, 2: self._setitem_v2}[self.V - 2]
            self.update_from_contents_file_setitem(contents_filename, dist, setitem)
        elif self.V == 5:
            self.update_from_contents_file_cached(
                contents_filename, dist, group_inserts
            )
        else:
            raise NotImplementedError()

    def __contains__(self, o: object) -> bool:
        if not isinstance(o, str):
            return False
        cursor = self.connection.execute(
            "SELECT 1 FROM path_package WHERE path = ?", (o,)
        )
        return cursor.fetchone() is not None


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
    run_access_tests(file2pkg, args)
    memdbg("end")


class TestPath2PackageV1(TestPath2Package):
    """Test Path2Package class."""

    _Path2PackageClass = Path2Package  # type: ignore[assignment]


class _Path2PackageV2(Path2Package):
    V = 2


class TestPath2PackageV2(TestPath2Package):
    """Test Path2Package class."""

    _Path2PackageClass = _Path2PackageV2  # type: ignore[assignment]


class _Path2PackageV3(Path2Package):
    V = 3


class TestPath2PackageV3(TestPath2Package):
    """Test Path2Package class."""

    _Path2PackageClass = _Path2PackageV3  # type: ignore[assignment]


class _Path2PackageV4(Path2Package):
    V = 4


class TestPath2PackageV4(TestPath2Package):
    """Test Path2Package class."""

    _Path2PackageClass = _Path2PackageV4  # type: ignore[assignment]


class _Path2PackageV5(Path2Package):
    V = 5


class TestPath2PackageV5(TestPath2Package):
    """Test Path2Package class."""

    _Path2PackageClass = _Path2PackageV5  # type: ignore[assignment]


del TestPath2Package


if __name__ == "__main__":
    with measure_duration("Total"):
        main()

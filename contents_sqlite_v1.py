#!/usr/bin/python3

"""Test case for caching the contents files in a SQLite database.

Use SQLite as simple key-value store (keep it simple).
"""

import gzip
import pathlib
import re
import sqlite3
import tempfile
import unittest
import unittest.mock
from collections.abc import Iterator, Mapping
from unittest.mock import MagicMock

from apport.logging import memdbg
from contents_common import (
    measure_duration,
    parse_args_and_common_main,
    run_access_tests,
)


class Path2Package(Mapping[str, str]):
    """Path to Debian package mapping.

    A backing SQLite database is open on __init__ and closed on object
    deletion. The data is stored in unnormalized form for creation speed
    and code simplicity.

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
        cursor.execute(
            "CREATE TABLE path_package("
            "  path TEXT PRIMARY KEY UNIQUE NOT NULL,"
            "  package TEXT NOT NULL)"
        )
        self.connection.commit()

    def __getitem__(self, key: str) -> str:
        cursor = self.connection.execute(
            "SELECT package FROM path_package WHERE path = ?", (key,)
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
        self.connection.execute(
            "INSERT INTO path_package VALUES(?, ?) "
            "ON CONFLICT(path) DO UPDATE SET package=excluded.package",
            (key, value),
        )

    def is_empty(self) -> bool:
        """Check if the database is empty."""
        cursor = self.connection.execute("SELECT 1 FROM path_package LIMIT 1")
        return cursor.fetchone() is None

    @staticmethod
    def _insert_many(cursor: sqlite3.Cursor, path2pkg: Mapping[str, str]) -> None:
        cursor.executemany(
            "INSERT INTO path_package VALUES(?, ?) "
            "ON CONFLICT(path) DO UPDATE SET package=excluded.package",
            path2pkg.items(),
        )

    def update_from_contents_file(
        self, contents_filename: str, dist: str, group_inserts: int = 100
    ) -> None:
        """Update database with entries from the Contents file.

        Existing paths will be overwritten by new entries.
        """
        cursor = self.connection.cursor()
        path2pkg = {}

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

                path2pkg[path] = package
                if len(path2pkg) >= group_inserts:
                    self._insert_many(cursor, path2pkg)
                    path2pkg = {}
        if path2pkg:
            self._insert_many(cursor, path2pkg)
        self.connection.commit()

    def __contains__(self, o: object) -> bool:
        if not isinstance(o, str):
            return False
        cursor = self.connection.execute(
            "SELECT package FROM path_package WHERE path = ?", (o,)
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


class TestPath2Package(unittest.TestCase):
    """Test Path2Package class."""

    _Path2PackageClass = Path2Package

    def test_contents_skip_xenial_header(self) -> None:
        """Test _update_given_file2pkg_mapping skipping xenial Contents header."""
        # Header taken from
        # http://archive.ubuntu.com/ubuntu/dists/xenial/Contents-amd64.gz
        contents = """\
This file maps each file available in the Ubuntu
system to the package from which it originates.  It includes packages
from the DIST distribution for the ARCH architecture.

You can use this list to determine which package contains a specific
file, or whether or not a specific file is available.  The list is
updated weekly, each architecture on a different day.

When a file is contained in more than one package, all packages are
listed.  When a directory is contained in more than one package, only
the first is listed.

The best way to search quickly for a file is with the Unix `grep'
utility, as in `grep <regular expression> CONTENTS':

 $ grep nose Contents
 etc/nosendfile                                          net/sendfile
 usr/X11R6/bin/noseguy                                   x11/xscreensaver
 usr/X11R6/man/man1/noseguy.1x.gz                        x11/xscreensaver
 usr/doc/examples/ucbmpeg/mpeg_encode/nosearch.param     graphics/ucbmpeg
 usr/lib/cfengine/bin/noseyparker                        admin/cfengine

This list contains files in all packages, even though not all of the
packages are installed on an actual system at once.  If you want to
find out which packages on an installed Debian system provide a
particular file, you can use `dpkg --search <filename>':

 $ dpkg --search /usr/bin/dselect
 dpkg: /usr/bin/dselect


FILE                                                    LOCATION
:sexsend:sexget:					    universe/web/fex
bin/afio						    multiverse/utils/afio
bin/archdetect						    utils/archdetect-deb
"""
        # pylint: disable-next=protected-access
        file2pkg = self._Path2PackageClass()
        open_mock = unittest.mock.mock_open(read_data=contents)
        with unittest.mock.patch("gzip.open", open_mock):
            file2pkg.update_from_contents_file("/fake_Contents", "xenial", 2)

        self.assertEqual(
            dict(file2pkg), {"bin/afio": "afio", "bin/archdetect": "archdetect-deb"}
        )
        open_mock.assert_called_once_with("/fake_Contents", "rt")

    def test_contents_path_filering(self) -> None:
        """Test _update_given_file2pkg_mapping to ignore unrelevant files."""
        # Test content taken from
        # http://archive.ubuntu.com/ubuntu/dists/noble/Contents-amd64.gz
        contents = """\
bin/ip							    net/iproute2
boot/ipxe.efi						    admin/grub-ipxe
etc/dput.cf						    devel/dput
lib/nut/clone						    admin/nut-server
sbin/hdparm						    admin/hdparm
usr/Brother/inf/braddprinter				    multiverse/text/brother-lpr-drivers-laser
usr/aarch64-linux-gnu/include/ar.h			    libdevel/libc6-dev-arm64-cross
usr/bin/git						    vcs/git
usr/bin/xz						    utils/xz-utils
usr/games/etr						    universe/games/extremetuxracer
usr/include/apache2/os.h				    httpd/apache2-dev
usr/include/x86_64-linux-gnu/bits/endian.h		    libdevel/libc6-dev
usr/lib/7zip/7z.so					    universe/utils/7zip
usr/lib/debug/.build-id/31/1c9c9b30d6991fb903ab459173c66eb8e7e895.debug debug/libc6-dbg
usr/libexec/coreutils/libstdbuf.so			    utils/coreutils
usr/libx32/ld.so					    libs/libc6-x32
usr/sbin/zic						    libs/libc-bin
usr/share/dicom3tools/gen.so				    universe/graphics/dicom3tools
usr/share/doc/0install					    universe/admin/0install
usr/share/gocode/src/launchpad.net/mgo			    universe/devel/golang-gopkg-mgo.v2-dev
usr/share/help/C/eog/default.page			    gnome/eog
usr/share/icons/gnome-colors-common/32x32/apps/konsole.png\
  universe/gnome/gnome-colors-common
usr/share/locale/de/LC_MESSAGES/apt.mo			    admin/apt
usr/share/man/de/man1/man.1.gz				    doc/man-db
usr/share/texlive/index.html				    universe/tex/texlive-base
usr/src/broadcom-sta.tar.xz				    restricted/admin/broadcom-sta-source
var/lib/ieee-data/iab.txt				    net/ieee-data
"""

        # pylint: disable-next=protected-access
        file2pkg = self._Path2PackageClass()
        open_mock = unittest.mock.mock_open(read_data=contents)
        with unittest.mock.patch("gzip.open", open_mock):
            file2pkg.update_from_contents_file("Contents-amd64", "noble", 10)

        self.assertEqual(
            dict(file2pkg),
            {
                "bin/ip": "iproute2",
                "etc/dput.cf": "dput",
                "lib/nut/clone": "nut-server",
                "sbin/hdparm": "hdparm",
                "usr/Brother/inf/braddprinter": "brother-lpr-drivers-laser",
                "usr/bin/git": "git",
                "usr/lib/debug/.build-id/31/1c9c9b30d6991fb903ab459173c66eb8e7e895"
                ".debug": "libc6-dbg",
                "usr/bin/xz": "xz-utils",
                "usr/games/etr": "extremetuxracer",
                "usr/lib/7zip/7z.so": "7zip",
                "usr/libexec/coreutils/libstdbuf.so": "coreutils",
                "usr/libx32/ld.so": "libc6-x32",
                "usr/sbin/zic": "libc-bin",
                "usr/share/dicom3tools/gen.so": "dicom3tools",
            },
        )
        open_mock.assert_called_once_with("Contents-amd64", "rt")

    def test_contents_parse_path_with_spaces(self) -> None:
        """Test _update_given_file2pkg_mapping to parse Contents file correctly."""
        # Test content taken from
        # http://archive.ubuntu.com/ubuntu/dists/noble/Contents-amd64.gz
        contents = (
            "usr/lib/iannix/Tools/JavaScript Library.js\t\t    "
            "universe/sound/iannix\n"
            "usr/lib/python3/dist-packages/ilorest/extensions/BIOS COMMANDS"
            "/__init__.py universe/python/ilorest\n"
        )

        # pylint: disable-next=protected-access
        file2pkg = self._Path2PackageClass()
        open_mock = unittest.mock.mock_open(read_data=contents)
        with unittest.mock.patch("gzip.open", open_mock):
            file2pkg.update_from_contents_file("Contents-amd64", "noble")

        self.assertEqual(
            dict(file2pkg),
            {
                "usr/lib/iannix/Tools/JavaScript Library.js": "iannix",
                "usr/lib/python3/dist-packages/ilorest/extensions/BIOS COMMANDS"
                "/__init__.py": "ilorest",
            },
        )
        open_mock.assert_called_once_with("Contents-amd64", "rt")

    def test_path2package(self) -> None:
        """Basic tests for Path2Package class."""
        path2package = self._Path2PackageClass()
        self.assertEqual(dict(path2package), {})
        self.assertEqual(len(path2package), 0)
        self.assertTrue(path2package.is_empty())
        path2package["usr/bin/man"] = "man-db"
        path2package["bin/ip"] = "iproute2"
        self.assertEqual(
            dict(path2package), {"bin/ip": "iproute2", "usr/bin/man": "man-db"}
        )
        self.assertEqual(len(path2package), 2)
        self.assertEqual(path2package["bin/ip"], "iproute2")
        self.assertEqual(path2package.get("usr/bin/man"), "man-db")
        self.assertIsNone(path2package.get("usr/src/broadcom-sta.tar.xz"))
        self.assertFalse(path2package.is_empty())
        self.assertIn("bin/ip", path2package)
        self.assertNotIn("usr/bin/git", path2package)
        self.assertNotIn(42, path2package)

    def test_path2package_overwrite(self) -> None:
        """Test Path2Package to overwrite existing values."""
        path2package = self._Path2PackageClass()
        path2package["path/to/file"] = "package1"
        self.assertEqual(path2package["path/to/file"], "package1")
        path2package["path/to/file"] = "package2"
        self.assertEqual(path2package["path/to/file"], "package2")

    def test_path2package_create_and_reopen(self) -> None:
        """Test Path2Package for openening an existing database."""
        with tempfile.NamedTemporaryFile(suffix=".sqlite3") as db_file:
            path2package = self._Path2PackageClass(pathlib.Path(db_file.name))
            self.assertEqual(dict(path2package), {})
            self.assertTrue(path2package.is_empty())
            path2package["bin/ip"] = "iproute2"
            path2package.connection.commit()
            del path2package

            path2package = self._Path2PackageClass(pathlib.Path(db_file.name))
            self.assertEqual(dict(path2package), {"bin/ip": "iproute2"})
            self.assertFalse(path2package.is_empty())

    @unittest.mock.patch("sqlite3.connect")
    def test_path2package_clean_deletion_on_failure(
        self, connect_mock: MagicMock
    ) -> None:
        """Test clean Path2Package deletion on __init__ failure."""
        connect_mock.side_effect = sqlite3.OperationalError
        with self.assertRaises(sqlite3.OperationalError):
            self._Path2PackageClass(pathlib.Path("/non-existing.sqlite3"))


if __name__ == "__main__":
    with measure_duration("Total"):
        main()

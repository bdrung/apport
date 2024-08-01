#!/usr/bin/python3

"""Test case for caching the contents files in a SQLite database."""

import dbm.gnu
import gzip
import pathlib
import re
import tempfile
import unittest
import unittest.mock
from collections.abc import Iterator, Mapping

from apport.logging import memdbg
from contents_common import (
    measure_duration,
    parse_args_and_common_main,
    run_access_tests_binary,
)


class Path2Package(Mapping[bytes, bytes]):
    """Filename to Debian package dictionary-like object.

    A backing database is open on init and close on object deletion.
    """

    def __init__(self, database_file: pathlib.Path) -> None:
        self.database_file = database_file
        if not database_file.exists() or database_file.stat().st_size == 0:
            flags = "cf"
        else:
            flags = "rf"
        self.database = dbm.gnu.open(str(self.database_file), flags)

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
        self.database.sync()


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
    args, mapping_db, content_filenames = parse_args_and_common_main(".dbm")
    file2pkg = _get_file2pkg_mapping(mapping_db, args.release, content_filenames)
    run_access_tests_binary(file2pkg, args)
    memdbg("end")


class TestPath2PackageDBM(unittest.TestCase):
    """Test Path2Package class."""

    SUFFIX = ".dbm"
    _Path2PackageClass = Path2Package

    def test_contents_skip_xenial_header(self) -> None:
        """Test _update_given_file2pkg_mapping skipping xenial Contents header."""
        # Header taken from
        # http://archive.ubuntu.com/ubuntu/dists/xenial/Contents-amd64.gz
        contents = b"""\
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
        with tempfile.NamedTemporaryFile(suffix=self.SUFFIX) as db_file:
            file2pkg = self._Path2PackageClass(pathlib.Path(db_file.name))
        open_mock = unittest.mock.mock_open(read_data=contents)
        with unittest.mock.patch("gzip.open", open_mock):
            file2pkg.update_from_contents_file("/fake_Contents", "xenial")

        self.assertEqual(
            dict(file2pkg), {b"bin/afio": b"afio", b"bin/archdetect": b"archdetect-deb"}
        )
        open_mock.assert_called_once_with("/fake_Contents", "rb")

    def test_contents_path_filering(self) -> None:
        """Test _update_given_file2pkg_mapping to ignore unrelevant files."""
        # Test content taken from
        # http://archive.ubuntu.com/ubuntu/dists/noble/Contents-amd64.gz
        contents = b"""\
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
        with tempfile.NamedTemporaryFile(suffix=self.SUFFIX) as db_file:
            file2pkg = self._Path2PackageClass(pathlib.Path(db_file.name))
        open_mock = unittest.mock.mock_open(read_data=contents)
        with unittest.mock.patch("gzip.open", open_mock):
            file2pkg.update_from_contents_file("Contents-amd64", "noble")

        self.assertEqual(
            {k.decode(): v.decode() for k, v in file2pkg.items()},
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
        open_mock.assert_called_once_with("Contents-amd64", "rb")

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
        with tempfile.NamedTemporaryFile(suffix=self.SUFFIX) as db_file:
            file2pkg = self._Path2PackageClass(pathlib.Path(db_file.name))
        open_mock = unittest.mock.mock_open(read_data=contents.encode())
        with unittest.mock.patch("gzip.open", open_mock):
            file2pkg.update_from_contents_file("Contents-amd64", "noble")

        self.assertEqual(
            {k.decode(): v.decode() for k, v in file2pkg.items()},
            {
                "usr/lib/iannix/Tools/JavaScript Library.js": "iannix",
                "usr/lib/python3/dist-packages/ilorest/extensions/BIOS COMMANDS"
                "/__init__.py": "ilorest",
            },
        )
        open_mock.assert_called_once_with("Contents-amd64", "rb")

    def test_path2package(self) -> None:
        """Basic tests for Path2Package class."""
        with tempfile.NamedTemporaryFile(suffix=self.SUFFIX) as db_file:
            path2package = self._Path2PackageClass(pathlib.Path(db_file.name))
        self.assertEqual(path2package, {})
        self.assertEqual(len(path2package), 0)
        self.assertTrue(path2package.is_empty())
        path2package[b"usr/bin/man"] = b"man-db"
        path2package[b"bin/ip"] = b"iproute2"
        self.assertEqual(
            dict(path2package), {b"bin/ip": b"iproute2", b"usr/bin/man": b"man-db"}
        )
        self.assertEqual(len(path2package), 2)
        self.assertEqual(path2package[b"bin/ip"], b"iproute2")
        self.assertEqual(path2package.get(b"usr/bin/man"), b"man-db")
        self.assertIsNone(path2package.get(b"usr/src/broadcom-sta.tar.xz"))
        self.assertFalse(path2package.is_empty())
        self.assertIn(b"bin/ip", path2package)
        self.assertNotIn(b"usr/bin/git", path2package)

    def test_path2package_create_and_reopen(self) -> None:
        """Test Path2Package for openening an existing database."""
        with tempfile.NamedTemporaryFile(suffix=self.SUFFIX) as db_file:
            path2package = self._Path2PackageClass(pathlib.Path(db_file.name))
            self.assertEqual(path2package, {})
            self.assertTrue(path2package.is_empty())
            path2package[b"bin/ip"] = b"iproute2"
            del path2package

            path2package = self._Path2PackageClass(pathlib.Path(db_file.name))
            self.assertEqual(dict(path2package), {b"bin/ip": b"iproute2"})
            self.assertFalse(path2package.is_empty())


if __name__ == "__main__":
    with measure_duration("Total"):
        main()

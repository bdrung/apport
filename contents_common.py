"""Common functions used by all contents test cases."""

import argparse
import contextlib
import datetime
import http.client
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator, Mapping


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


def _fetch_contents_file(
    contents_filename: str, mtime: float | None, dist: str, arch: str, mirror: str
) -> bool:
    update = False
    url = f"{mirror}/dists/{dist}/Contents-{arch}.gz"
    if mtime:
        # HTTPConnection requires server name e.g.
        # archive.ubuntu.com
        server = urllib.parse.urlparse(url)[1]
        conn = http.client.HTTPConnection(server)
        conn.request("HEAD", urllib.parse.urlparse(url)[2])
        res = conn.getresponse()
        modified_str = res.getheader("last-modified", None)
        if modified_str:
            modified = datetime.datetime.strptime(
                modified_str, "%a, %d %b %Y %H:%M:%S %Z"
            )
            update = modified > datetime.datetime.fromtimestamp(mtime)
        else:
            update = True
        # don't update the file if it is empty
        if res.getheader("content-length", None) == "40":
            update = False
    else:
        update = True
    if update:
        # self._contents_update = True
        try:
            # hard to change, pylint: disable=consider-using-with
            src = urllib.request.urlopen(url)
        except OSError:
            # we ignore non-existing pockets, but we do crash
            # if the release pocket doesn't exist
            if "-" not in dist:
                raise
            return False

        with open(contents_filename, "wb") as f:
            while True:
                data = src.read(1000000)
                if not data:
                    break
                f.write(data)
        src.close()
        assert os.path.exists(contents_filename)
    return True


def _get_contents_file(
    map_cachedir: str, dist: str, arch: str, mirror: str
) -> str | None:
    contents_filename = os.path.join(map_cachedir, f"{dist}-Contents-{arch}.gz")
    # check if map exists and is younger than a day; if not, we need
    # to refresh it
    try:
        mtime = os.stat(contents_filename).st_mtime
        age = int(time.time() - mtime)
    except OSError:
        mtime = None
        age = None

    if age is None or age >= 86400:
        if not _fetch_contents_file(contents_filename, mtime, dist, arch, mirror):
            return None

    return contents_filename


def get_contents_filenames(
    map_cachedir: str, release: str, arch: str, mirror: str, pockets: Iterable[str]
) -> list[str]:
    """Cache Contents files for given release and architecture locally."""
    # this is ordered by likelihood of installation with the most common
    # last
    # XXX - maybe we shouldn't check -security and -updates if it is the
    # devel release as they will be old and empty
    contents_filenames = []
    for pocket in pockets:
        dist = f"{release}{pocket}"
        contents_filename = _get_contents_file(map_cachedir, dist, arch, mirror)
        if contents_filename is None:
            continue
        contents_filenames.append(contents_filename)
    return contents_filenames


def parse_args_and_common_main(
    database_suffix: str,
) -> tuple[argparse.Namespace, pathlib.Path, list[str]]:
    """Parse command line arguments and fetch the content files."""
    args = _parse_args()

    if args.only_proposed:
        pockets = ["-proposed"]
        content = f"{args.release}-proposed-{args.arch}"
    else:
        pockets = ["-proposed", "", "-security", "-updates"]
        content = f"{args.release}-{args.arch}"
    pathlib.Path(args.cache).mkdir(parents=True, exist_ok=True)

    mapping_db = (
        pathlib.Path(args.cache) / f"contents_mapping-{content}{database_suffix}"
    )
    if args.delete_cache:
        if mapping_db.is_dir():
            for file in mapping_db.glob("*"):
                file.unlink()
            mapping_db.rmdir()
        else:
            mapping_db.unlink(missing_ok=True)

    contents_filenames = get_contents_filenames(
        args.cache, args.release, args.arch, args.mirror, pockets
    )

    return args, mapping_db, contents_filenames


def duration_str(duration: float) -> str:
    """Return duration in the biggest useful time unit (hours, minutes, seconds, ms)."""
    if duration < 1:
        return f"{duration * 1000:.3f} ms"
    if duration < 60:
        return f"{duration:.3f} s"
    minutes = int(duration // 60)
    if duration < 3600:
        return f"{minutes} min {duration % 60:.3f} s (= {duration:.3f} s)"

    return (
        f"{minutes // 60} h {minutes % 60} min {duration % 60:.3f} s"
        f" (= {duration:.3f} s)"
    )


@contextlib.contextmanager
def measure_duration(name: str) -> Iterator[None]:
    """Measure duration within the context and print the result afterwards."""
    start = time.perf_counter()
    yield
    duration = time.perf_counter() - start
    print(f"{name} duration: {duration_str(duration)}")


def run_access_tests(file2pkg: Mapping[str, str], args: argparse.Namespace) -> None:
    """Run read test cases on a string dictionary-like object."""
    if args.print_sum:
        print(f"Total entries: {len(file2pkg):,}")
    with measure_duration("Access"):
        if args.only_proposed:
            for _ in range(100):
                assert file2pkg.get("usr/bin/not-existing") is None
                assert file2pkg.get("usr/share/not-existing") is None
                assert (
                    file2pkg["usr/x86_64-w64-mingw32/bin/mpicalc.exe"]
                    == "libgcrypt-mingw-w64-dev"
                )
                assert file2pkg["etc/apparmor.d/abstractions/python"] == "apparmor"
        else:
            for _ in range(100):
                assert file2pkg["usr/bin/divide-by-zero"]
                assert file2pkg.get("usr/bin/not-existing") is None
                assert file2pkg["bin/ed"]
                assert file2pkg["usr/bin/man"]
                assert file2pkg.get("usr/share/not-existing") is None


def run_access_tests_binary(
    file2pkg: Mapping[bytes, bytes], args: argparse.Namespace
) -> None:
    """Run read test cases on a binary dictionary."""
    if args.print_sum:
        print(f"Total entries: {len(file2pkg):,}")
    with measure_duration("Access"):
        if args.only_proposed:
            for _ in range(100):
                assert file2pkg.get(b"usr/bin/not-existing") is None
                assert file2pkg.get(b"usr/share/not-existing") is None
                assert (
                    file2pkg[b"usr/x86_64-w64-mingw32/bin/mpicalc.exe"]
                    == b"libgcrypt-mingw-w64-dev"
                )
                assert file2pkg[b"etc/apparmor.d/abstractions/python"] == b"apparmor"
        else:
            for _ in range(100):
                assert file2pkg[b"usr/bin/divide-by-zero"]
                assert file2pkg.get(b"usr/bin/not-existing") is None
                assert file2pkg[b"bin/ed"]
                assert file2pkg[b"usr/bin/man"]
                assert file2pkg.get(b"usr/share/not-existing") is None

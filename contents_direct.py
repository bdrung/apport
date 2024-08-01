#!/usr/bin/python3

"""Test case for direct reading the contents files.

Result: Two reads are already slower than building the database.
"""

import gzip
import re
from collections.abc import Iterator, Mapping

from apport.logging import memdbg
from contents_common import measure_duration, parse_args_and_common_main


class _DirectPath2Package(Mapping[bytes, bytes]):
    def __init__(self, content_filenames: list[str], release: str) -> None:
        self.content_filenames = content_filenames
        self.release = release

    def __getitem__(self, key: bytes) -> bytes:
        with measure_duration("Getitem"):
            key_pattern = re.compile(re.escape(key) + b"\\s")
            for contents_filename in self.content_filenames:
                with gzip.open(contents_filename, "rb") as contents:
                    if self.release in {"trusty", "xenial"}:
                        # the first 32 lines are descriptive only for these
                        # releases
                        for _ in range(32):
                            next(contents)

                    for line in contents:
                        if key_pattern.match(line):
                            path, column2 = line.rsplit(maxsplit=1)
                            assert path == key
                            package = column2.split(b",")[0].split(b"/")[-1]
                            return package
            raise KeyError(key)

    def __iter__(self) -> Iterator[bytes]:
        raise NotImplementedError(
            f"__iter__ not implemented for {self.__class__.__name__}"
        )

    def __len__(self) -> int:
        raise NotImplementedError(
            f"__len__ not implemented for {self.__class__.__name__}"
        )


def main() -> None:
    """Entry point."""
    args, _, content_filenames = parse_args_and_common_main(".direct")
    file2pkg = _DirectPath2Package(list(reversed(content_filenames)), args.release)
    assert file2pkg.get(b"usr/bin/not-existing") is None

    # run_access_tests_binary(file2pkg, args)
    if args.only_proposed:
        assert file2pkg.get(b"usr/bin/not-existing") is None
        assert (
            file2pkg[b"usr/x86_64-w64-mingw32/bin/mpicalc.exe"]
            == b"libgcrypt-mingw-w64-dev"
        )
    else:
        assert file2pkg[b"usr/bin/divide-by-zero"]
        assert file2pkg.get(b"usr/bin/not-existing") is None

    memdbg("end")


if __name__ == "__main__":
    with measure_duration("Total"):
        main()

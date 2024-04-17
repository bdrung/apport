#!/usr/bin/python3
# pylint: disable=import-private-name,missing-docstring,protected-access

import os
import pathlib
import shutil
import sys
import tempfile
import typing

import apt
import apt_pkg

import tests.system.test_packaging_apt_dpkg
from apport.packaging_impl.apt_dpkg import impl as packaging
from tests.system.test_packaging_apt_dpkg import _setup_foonux_config


def de_ubuntu_archive_uri(arch=None):
    """Return archive URI for the given architecture."""
    if arch is None:
        arch = packaging.get_system_architecture()
    if arch in {"amd64", "i386"}:
        return "http://de.archive.ubuntu.com/ubuntu"
    return "http://de.ports.ubuntu.com/ubuntu-ports"


tests.system.test_packaging_apt_dpkg._ubuntu_archive_uri = de_ubuntu_archive_uri


def _build_apt_sandbox(aptroot, apt_dir, distro_name, release_codename, origins):
    packaging._build_apt_sandbox(
        aptroot, apt_dir, distro_name, release_codename, origins
    )


def _clear_apt_cache() -> None:
    # The rootdir option to apt.Cache modifies the global state
    apt_pkg.config.clear("Dir")
    apt_pkg.init_config()
    apt_pkg.init_system()


def _sandbox_cache(
    aptroot, apt_dir, fetch_progress, distro_name, release_codename, origins, arch
):  # pylint: disable=too-many-arguments
    """Build apt sandbox and return apt.Cache(rootdir=) (initialized
    lazily).

    Clear the package selection on subsequent calls.
    """
    _clear_apt_cache()
    _build_apt_sandbox(aptroot, apt_dir, distro_name, release_codename, origins)
    rootdir = os.path.abspath(aptroot)
    _sandbox_apt_cache = apt.Cache(rootdir=rootdir)
    _sandbox_apt_cache_arch = arch
    try:
        # We don't need to update this multiple times.
        _sandbox_apt_cache.update(fetch_progress)
    except apt.cache.FetchFailedException as error:
        print(f"***{str(error)}***")
        print(f"***{repr(error)}***")
        raise SystemError(str(error)) from error
    _sandbox_apt_cache.open()
    return _sandbox_apt_cache


def main(
    verbose: bool, delete_cache: bool, test: typing.Literal["update", "fetch_packages"]
) -> None:
    with tempfile.TemporaryDirectory() as workdir:
        print(f"workdir = {workdir}", file=sys.stderr)
        configdir = pathlib.Path(workdir) / "config"
        rootdir = pathlib.Path(workdir) / "root"
        cachedir = pathlib.Path(workdir) / "cache"
        configdir.mkdir()
        rootdir.mkdir()
        cachedir.mkdir()

        codename = "jammy"
        release = _setup_foonux_config(
            str(configdir), "deb822", updates=True, release=codename
        )
        print(f"release = {release}", file=sys.stderr)

        architecture = packaging.get_system_architecture()
        if not verbose:
            fetch_progress = apt.progress.base.AcquireProgress()
        else:
            fetch_progress = apt.progress.text.AcquireProgress()
        apt_dir = os.path.join(configdir, release)
        mirror = packaging._get_primary_mirror_from_apt_sources(apt_dir)
        print(f"mirror = {mirror}", file=sys.stderr)
        packaging.set_mirror(mirror)
        aptroot = os.path.join(cachedir, "system", "", "apt")
        if not os.path.isdir(aptroot):
            os.makedirs(aptroot)

        apt.apt_pkg.config.set("APT::Architecture", architecture)
        apt.apt_pkg.config.set("Acquire::Languages", "none")
        # directly connect to Launchpad when downloading deb files
        apt.apt_pkg.config.set("Acquire::http::Proxy::api.launchpad.net", "DIRECT")
        apt.apt_pkg.config.set("Acquire::http::Proxy::launchpad.net", "DIRECT")

        apt_cache = _sandbox_cache(
            aptroot,
            apt_dir,
            fetch_progress,
            packaging.get_distro_name(),
            codename,
            None,
            architecture,
        )
        fetcher = apt.apt_pkg.Acquire(fetch_progress)
        if test == "fetch_packages":
            apt_cache["coreutils-dbgsym"].mark_install(False, False)

        while True:
            if verbose:
                progress_msg = "-" * 40 + "\n"
            else:
                progress_msg = "."
            print(progress_msg, end="", file=sys.stderr, flush=True)
            if test == "update":
                _sandbox_cache(
                    aptroot,
                    apt_dir,
                    fetch_progress,
                    packaging.get_distro_name(),
                    codename,
                    None,
                    architecture,
                )
                if delete_cache:
                    shutil.rmtree(cachedir)
                    cachedir.mkdir()
            elif test == "fetch_packages":
                apt_cache.fetch_archives(fetcher=fetcher)


if __name__ == "__main__":
    # main(True, True, "update")
    main(True, False, "fetch_packages")

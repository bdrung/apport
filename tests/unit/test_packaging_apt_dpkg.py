import os
import shutil
import subprocess
import tempfile
import time
import unittest
import unittest.mock

from apport.packaging_impl.apt_dpkg import impl
from tests.helper import skip_if_command_is_missing


@skip_if_command_is_missing("dpkg")
class TestUnitPackagingAptDpkg(unittest.TestCase):
    # pylint: disable=protected-access

    def setUp(self):
        # save and restore configuration file
        self.orig_conf = impl.configuration
        self.orig_environ = os.environ.copy()
        self.workdir = tempfile.mkdtemp()
        os.environ["HOME"] = self.workdir
        # reset internal caches between tests
        impl._apt_cache = None
        impl._sandbox_apt_cache = None

    def tearDown(self):
        impl.configuration = self.orig_conf
        os.environ.clear()
        os.environ.update(self.orig_environ)
        shutil.rmtree(self.workdir)

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("glob.glob")
    def test_get_file_package_library(self, glob_mock, run_mock):
        glob_mock.return_value = [
            "/var/lib/dpkg/info/apt.list",
            "/var/lib/dpkg/info/libc6:amd64.list",
        ]
        run_mock.side_effect = [
            subprocess.CompletedProcess(
                args=None, returncode=0, stdout=b"", stderr=b""
            ),
            subprocess.CompletedProcess(
                args=None,
                returncode=0,
                stdout=b"/var/lib/dpkg/info/libc6:amd64.list",
                stderr=b"",
            ),
        ]
        self.assertEqual(
            impl.get_file_package("/lib/x86_64-linux-gnu/libc.so.6"),
            "libc6",
        )
        glob_mock.assert_called_once_with("/var/lib/dpkg/info/*.list")
        self.assertEqual(
            [call.args[0] for call in run_mock.call_args_list],
            [
                ["dpkg-divert", "--list", "/lib/x86_64-linux-gnu/libc.so.6"],
                [
                    "fgrep",
                    "-lxm",
                    "1",
                    "--",
                    "/lib/x86_64-linux-gnu/libc.so.6",
                    "/var/lib/dpkg/info/apt.list",
                    "/var/lib/dpkg/info/libc6:amd64.list",
                ],
            ],
        )

    @unittest.mock.patch("subprocess.run")
    @unittest.mock.patch("glob.glob")
    def test_get_file_package_foreign_architecture(self, glob_mock, run_mock):
        glob_mock.return_value = [
            "/var/lib/dpkg/info/apt.list",
            "/var/lib/dpkg/info/libnss-nis:i386.list",
        ]
        run_mock.side_effect = [
            subprocess.CompletedProcess(
                args=None, returncode=0, stdout=b"", stderr=b""
            ),
            subprocess.CompletedProcess(
                args=None,
                returncode=0,
                stdout=b"/var/lib/dpkg/info/libnss-nis:i386.list",
                stderr=b"",
            ),
        ]
        self.assertEqual(
            impl.get_file_package("/lib/i386-linux-gnu/libnss_nis.so.2.0.0"),
            "libnss-nis",
        )
        glob_mock.assert_called_once_with("/var/lib/dpkg/info/*.list")
        # run_mock.assert_has_calls([unittest.mock.call(["dpkg-"]), unittest.mock.call(["fgrep"])])
        # self.assertEqual(run_mock.call_count, 2, run_mock.call_args_list)
        self.assertEqual(
            [call.args[0] for call in run_mock.call_args_list],
            [
                [
                    "dpkg-divert",
                    "--list",
                    "/lib/i386-linux-gnu/libnss_nis.so.2.0.0",
                ],
                [
                    "fgrep",
                    "-lxm",
                    "1",
                    "--",
                    "/lib/i386-linux-gnu/libnss_nis.so.2.0.0",
                    "/var/lib/dpkg/info/libnss-nis:i386.list",
                ],
            ],
        )

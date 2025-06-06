"""Send reports about ubuntu-desktop-bootstrap to the correct Launchpad
project."""

# pylint: disable=invalid-name
# pylint: enable=invalid-name

import re
from pathlib import Path

from apport import Report, hookutils
from apport.ui import HookUI


def attach_journal(report: Report, log_map: dict[str, Path]) -> None:
    """Attach installer environment journal log to report.

    Appends the installer specific journal to the log map if it exists,
    otherwise appends the system journal to the report directly.
    """
    installer_journal = Path("/var/log/installer/installer-journal.txt")
    if installer_journal.exists():
        log_map["InstallerJournal"] = installer_journal
    else:
        report["SystemJournal"] = hookutils.recent_syslog(re.compile("."))


def add_info(report: Report, unused_ui: HookUI) -> None:
    """Send reports about ubuntu-desktop-bootstrap to the correct Launchpad
    project."""
    report["SourcePackage"] = "ubuntu-desktop-bootstrap"
    # rewrite this section so the report goes to the project in Launchpad
    report[
        "CrashDB"
    ] = """\
{
    "impl": "launchpad",
    "project": "ubuntu-desktop-provision",
    "bug_pattern_url": "http://people.canonical.com/"
    "~ubuntu-archive/bugpatterns/bugpatterns.xml",
}
"""

    # Check if the snap was updated
    # TODO: Add logic to support this outside of the live environment.
    #       It may be possible someone wants to report a bug against the
    #       installer after first boot.
    report["SnapUpdated"] = str(Path("/run/subiquity/updating").exists())

    prefix = Path("/var/log/installer/")
    curtin_dir = prefix / "curtin-install/"
    log_map = {
        "SubiquityLog": prefix / "subiquity-server-debug.log",
        "CurtinLog": prefix / "curtin-install.log",
        "CurtinError.tar": prefix / "curtin-errors.tar",
        "ProbeData": prefix / "block/probe-data.json",
        "UdbLog": prefix / "ubuntu_bootstrap.log",
        "SubiquityTraceback": prefix / "subiquity-traceback.txt",
        "CurtinAptConfig": prefix / "curtin-install/subiquity-curtin-apt.conf",
        "CurtinCurthooksConfig": curtin_dir / "subiquity-curthooks.conf",
        "CurtinExtractConfig": curtin_dir / "subiquity-extract.conf",
        "CurtinInitialConfig": curtin_dir / "subiquity-initial.conf",
        "CurtinPartitioningConfig": curtin_dir / "subiquity-partitioning.conf",
    }

    attach_journal(report, log_map)

    hookutils.attach_hardware(report)

    # Attach logs if they exist
    # The conventional way to attach logs would be to use the
    # hookutils.attach_file_if_exists method, but since subiquity logs
    # are mostly locked down with root r/w only then we will get a permission
    # error if the caller does not have permissions. Ask for elevated
    # permissions instead of requiring users know to run with sudo or similar
    command_mapping = {}
    for name, path in log_map.items():
        if path.exists():
            command_mapping[name] = f"cat {path.resolve()}"

    hookutils.attach_root_command_outputs(report, command_mapping)

    # Always set reports to private since we might collect sensitive data
    report["LaunchpadPrivate"] = "1"

"""Helper function for debugging.

Usage: Set the environment variable APPORT_DEBUG to 1 or "all" to enable
all log output. To restrict it to certain section, specify a comma-separated
list of sections.
"""

import inspect
import os
import pathlib
import sys
import time
import types
import typing

import problem_report

APPORT_DEBUG = {
    section for section in os.environ.get("APPORT_DEBUG", "").split() if section
}
START_TIME = time.perf_counter()


# pylint: disable-next=too-few-public-methods
class _ReportFormatter:
    def __init__(self, report: problem_report.ProblemReport) -> None:
        self.report = report

    def __repr__(self) -> str:
        return f"{self.report.__class__.__name__}({self.report['ProblemType']!r})"


def _replace_complex_objects(value: typing.Any) -> typing.Any:
    if isinstance(value, problem_report.ProblemReport):
        return _ReportFormatter(value)
    return value


def print_function_call(frame: types.FrameType) -> None:
    """Print the function call of the given frame."""
    args, varargs, varkw, locals_ = inspect.getargvalues(frame)
    function = frame.f_code.co_name
    if args and args[0] == "self":
        del args[0]
        class_name = locals_["self"].__class__.__name__
        function = f"{class_name}.{function}"
    locals_ = {name: _replace_complex_objects(value) for name, value in locals_.items()}
    arguments = inspect.formatargvalues(args, varargs, varkw, locals_)
    time_ = time.perf_counter() - START_TIME
    sys.stderr.write(f"[{time_:11.6f}] {function}{arguments} called.\n")


def log(msg: str) -> None:
    """Print the message prefixed with the callers function."""
    current_frame = inspect.currentframe()
    assert current_frame is not None
    frame = current_frame.f_back
    assert frame is not None

    args, _, _, locals_ = inspect.getargvalues(frame)
    function = frame.f_code.co_name
    if args and args[0] == "self":
        del args[0]
        class_name = locals_["self"].__class__.__name__
        function = f"{class_name}.{function}"

    time_ = time.perf_counter() - START_TIME
    sys.stderr.write(f"[{time_:11.6f}] {function}:{frame.f_lineno}: {msg}\n")


def log_call(section: str | None = None, frame: types.FrameType | None = None) -> None:
    """Log the function call of the calling function.

    If section is not specify, the source code file name (without .py
    extension) is used.
    """
    if frame is None:
        current_frame = inspect.currentframe()
        assert current_frame is not None
        frame = current_frame.f_back
        assert frame is not None
    if section is None:
        section = pathlib.PurePath(frame.f_code.co_filename).stem
    if not (section in APPORT_DEBUG or "all" in APPORT_DEBUG or "1" in APPORT_DEBUG):
        return
    print_function_call(frame)

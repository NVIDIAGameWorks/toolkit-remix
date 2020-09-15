"""RepoMan command to run different test suites.

Example:
    > tools/test_runner.bat --help
    > tools/test_runner.sh --suite kittests
    > tools/test_runner.bat --suite pythontests -c release -e='-p test_battle*.py'

Attributes:
    TEST_SUITES (Dict): Specifies supported test suites and functions to run them.
"""

import os
import logging
import fnmatch
import argparse
import sys
import glob
import time
from typing import List, Dict
from string import Template


import omni.repo.man

logger = logging.getLogger(os.path.basename(__file__))

SEPARATOR = "=" * 80

STARTUP_TESTS = [
    {
        # Run all experiences that start with "kit-"" (only mini one currently, because of TC)
        "include": ["kit-*mini*${shell_ext}"],
        "exclude": [],
        "args": ["--carb/app/quitAfter=10"],  # Quit after 10 updates
    }
]

PYTHON_TESTS = [
    {
        # Run all tests experiences (ones that start with "tests-")
        "include": ["tests-*${shell_ext}"],
        "exclude": [],
        "args": [],
        "tc_report_enabled": False,  # Python tests have builtin reporting
    }
]

_ONLY_LIST = False


def is_running_under_teamcity():
    return bool(os.getenv("TEAMCITY_VERSION"))


def get_exe_ext(platform: str) -> str:
    return ".exe" if platform == "windows-x86_64" else ""


def get_shell_ext(platform: str) -> str:
    return ".bat" if platform == "windows-x86_64" else ".sh"


def get_execution_prefix(root: str, platform_host: str, linbuild_profile: str) -> str:
    return (
        []
        if (platform_host == "windows-x86_64" or linbuild_profile is None)
        else ["_build/host-deps/linbuild/linbuild.sh", f"--with-volume={root}", f"--profile={linbuild_profile}", "--"]
    )


def escape_value(value):
    quote = {"'": "|'", "|": "||", "\n": "|n", "\r": "|r", "[": "|[", "]": "|]"}
    return "".join(quote.get(x, x) for x in value)


def teamcity_message(messageName, **properties):
    current_time = time.time()
    (current_time_int, current_time_fraction) = divmod(current_time, 1)
    current_time_struct = time.localtime(current_time_int)
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S.", current_time_struct) + "%03d" % (int(current_time_fraction * 1000))
    message = "##teamcity[%s timestamp='%s'" % (messageName, timestamp)

    for k in sorted(properties.keys()):
        value = properties[k]
        if value is None:
            continue
        message += f" {k}='{escape_value(str(value))}'"

    message += "]\n"

    sys.stdout.write(message)
    sys.stdout.flush()


def teamcity_report_fail(test_id, fail_type, err):
    teamcity_message("testFailed", name=test_id, fail_type=fail_type, message=err)


def teamcity_start_test(test_id):
    teamcity_message("testStarted", name=test_id, captureStandardOutput="true")


def teamcity_stop_test(test_id):
    teamcity_message("testFinished", name=test_id)


def run_unittests(root: str, platform_host: str, config: str, linbuild_profile: str, extra_args: List = []):
    executable = f"test.unit{get_exe_ext(platform_host)}"

    args = []
    if is_running_under_teamcity():
        args.append("-r teamcity")
    args.extend(extra_args)

    omni.repo.man.run_process([f"{root}/_build/{platform_host}/{config}/{executable}"] + args, exit_on_error=True)


def glob_files(path: str, config: Dict, platform_host: str):
    mapping = omni.repo.man.get_platform_file_mapping(platform_host)
    includes = [Template(p).substitute(mapping) for p in config.get("include", [])]
    excludes = [Template(p).substitute(mapping) for p in config.get("exclude", [])]

    def match(s, patterns):
        return any(fnmatch.fnmatch(s, p) for p in patterns)

    files = []
    for f in glob.glob(path + "/*"):
        filename = os.path.basename(f)
        if match(filename, includes) and not match(filename, excludes):
            files.append(f)

    return files


def _run_cmd_tests(
    tests: List[Dict], root: str, platform_host: str, config: str, linbuild_profile: str, extra_args: List = []
):
    bin_folder = f"{root}/_build/{platform_host}/{config}"

    os.environ["PYTHONPATH"] = ""  # Don't propagagate current ENV into the test (e.g. packman path is set there)

    # We will run all tests regardless of failure
    fail_count = 0
    total = 0

    exec_prefix = get_execution_prefix(root, platform_host, linbuild_profile)
    mapping = omni.repo.man.get_platform_file_mapping(platform_host)
    mapping["root"] = root.replace("\\", "/")

    for test in tests:

        tc_report_enabled = test.get("tc_report_enabled", True) and not _ONLY_LIST

        for file in glob_files(bin_folder, test, platform_host):
            total = total + 1

            # Allow tokens (like ${root}) in args too:
            args = [Template(arg).substitute(mapping) for arg in test.get("args", [])]
            cmd = exec_prefix + [file] + args + extra_args

            # TC reporting
            test_id = "StartupTest:" + ("_".join(cmd))
            if tc_report_enabled:
                teamcity_start_test(test_id)

            if _ONLY_LIST:
                print(f"> " + (" ".join(cmd)))
                continue

            # Run process
            print(SEPARATOR)
            returncode = omni.repo.man.run_process(cmd, exit_on_error=False)

            # Report failure and mark overall run as failure
            if returncode != 0:
                if tc_report_enabled:
                    teamcity_report_fail(test_id, "Error", f"Exit code: {returncode}")
                fail_count = fail_count + 1
            else:
                print("Process exited successfully.")
            print(SEPARATOR)

            if tc_report_enabled:
                teamcity_stop_test(test_id)

    # Exit with non-zero code on failure
    if fail_count > 0:
        print(f"[ERROR] {fail_count} tests processes failed out of {total}.")
        sys.exit(1)
    else:
        if _ONLY_LIST:
            print(f"Found {total} tests processes to run.")
        else:
            print(f"[Ok] All {total} tests processes returned 0.")


def run_startuptests(root: str, platform_host: str, config: str, linbuild_profile: str, extra_args: List = []):
    return _run_cmd_tests(STARTUP_TESTS, root, platform_host, config, linbuild_profile, extra_args)


def run_pythontests(root: str, platform_host: str, config: str, linbuild_profile: str, extra_args: List = []):
    return _run_cmd_tests(PYTHON_TESTS, root, platform_host, config, linbuild_profile, extra_args)


TEST_SUITES = {"unittests": run_unittests, "pythontests": run_pythontests, "startuptests": run_startuptests}


def setup_repo_tool(parser, config):
    platform_host = omni.repo.man.get_and_validate_host_platform(["windows-x86_64", "linux-x86_64"])
    repo_folders = omni.repo.man.get_repo_paths()
    parser.name = "Universal Test Runner"
    parser.add_argument(
        "-x",
        "--clean",
        dest="clean",
        default=False,
        action="store_true",
        help="Clean run (force extract package again).",
    )
    parser.add_argument(
        "--suite", dest="suite", choices=TEST_SUITES.keys(), default="unittests", help="Test suite to run."
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        required=False,
        default="debug",
        help="Config to run test against (debug or release). (default: %(default)s)",
    )
    parser.add_argument(
        "-e",
        "--extra-arg",
        action="append",
        dest="extra_args",
        default=[],
        help='Extra argument to pass. Can be specified multiple times. E.g. -e="--help"',
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        dest="list",
        default=False,
        help="List tests and exit without running them.",
    )

    def run_tool(options, config):
        global _ONLY_LIST
        _ONLY_LIST = options.list

        root_folder = repo_folders["root"]

        logger.info(f"Running test suite: {options.suite}...")
        TEST_SUITES[options.suite](root_folder, platform_host, options.config, None, options.extra_args)

    return run_tool

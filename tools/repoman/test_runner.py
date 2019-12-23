import os
import sys
import glob
import shutil
import logging
import argparse
import base64
import hashlib
from typing import List

import packmanapi
import repoman

repoman.bootstrap()
import omni.repo.man

logger = logging.getLogger(os.path.basename(__file__))

ARCHIVE_PATTERN = "_builtpackages/omniverse-kit*.7z"


def is_running_under_teamcity():
    return bool(os.getenv("TEAMCITY_VERSION"))


def get_exe_ext(platform: str) -> str:
    return ".exe" if platform == "windows-x86_64" else ""

def get_shell_ext(platform: str) -> str:
    return ".bat" if platform == "windows-x86_64" else ".sh"


def run_unittests(root: str, platform_host: str, config: str, extra_args: List = []):
    executable = f"test.unit{get_exe_ext(platform_host)}"

    args = []
    if is_running_under_teamcity():
        args.append("-r teamcity")
    args.extend(extra_args)

    omni.repo.man.run_process(
        [f"{root}/_build/{platform_host}/{config}/{executable}"] + args, exit_on_error=True
    )


def run_pythontests(root: str, platform_host: str, config: str, extra_args: List = []):
    """Run python (bindings) unit tests"""

    paths = omni.repo.man.get_repo_paths()
    omni.repo.man.pip_install("teamcity-messages", paths["pip_packages"], module="teamcity")
    import teamcity

    unittest_module = "teamcity.unittestpy" if teamcity.is_running_under_teamcity() else "unittest"

    path_to_extensions = f"{root}/_build/{platform_host}/{config}/extensions"
    os.environ["PYTHONPATH"] += os.pathsep.join([paths["pip_packages"], path_to_extensions])

    kit_bin = f"{root}/_build/target-deps/kit_sdk/_build/{platform_host}/{config}"

    tests_folder = os.path.join(paths["root"], "source/tests/python")
    args = ["-m", unittest_module, "discover", "-s", tests_folder] + extra_args
    python_exe = "python.bat" if platform_host == "windows-x86_64" else "python.sh"
    python_path = f"{kit_bin}/{python_exe}"
    omni.repo.man.run_process([python_path] + args, exit_on_error=True)


def run_kittests(root: str, platform_host: str, config: str, extra_args: List = []):
    """Run python tests suite inside of Kit"""

    executable = f"example.app{get_shell_ext(platform_host)}"
    args = ["--exec", '"run_tests.py"']
    args.extend(extra_args)
    omni.repo.man.run_process([f"{root}/_build/{platform_host}/{config}/{executable}"] + args, exit_on_error=True)




TEST_SUITES = {
    "unittests": run_unittests,
    "pythontests": run_pythontests,
    "kittests": run_kittests
}


def main():
    platform_host = omni.repo.man.get_and_validate_host_platform(["windows-x86_64", "linux-x86_64"])
    repo_folders = omni.repo.man.get_repo_paths()

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
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
        help="Extra argument to pass. Can be specified multiple times. E.g. -e=\"--help\"",
    )

    options = parser.parse_args()

    root_folder = repo_folders["root"]

    logger.info(f"Running test suite: {options.suite}...")
    TEST_SUITES[options.suite](root_folder, platform_host, options.config, options.extra_args)


if __name__ == "__main__":
    main()

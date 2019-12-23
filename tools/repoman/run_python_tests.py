import os
import sys
import logging
import argparse

logger = logging.getLogger(os.path.basename(__file__))


def main():
    import repoman

    repoman.bootstrap()
    import omni.repo.man

    parser = argparse.ArgumentParser()
    parser.prog = "run_python_tests"
    parser.description = "Run python tests against bindings of Carbonite interfaces."
    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        required=False,
        default="debug",
        help="Config to run test against (debug or release). (default: %(default)s)",
    )
    parser.add_argument(
        "-p",
        "--pattern",
        dest="pattern",
        required=False,
        default="test*.py",
        help="Pattern to match tests (default: %(default)s)",
    )

    options = parser.parse_args()

    platform_host = omni.repo.man.get_and_validate_host_platform(["windows-x86_64", "linux-x86_64", "linux-aarch64"])
    platform_target = platform_host

    # First folder in sys.path is directory of current script, it contains teamcity.py which will interfere with
    # teamcity module we install down below, thus:
    sys.path.pop(0)

    repo_folders = omni.repo.man.get_repo_paths()
    omni.repo.man.pip_install("teamcity-messages", repo_folders["pip_packages"], module="teamcity")

    libraries_path = os.path.join(repo_folders["build"], platform_host, options.config)
    bindings_path = os.path.join(libraries_path, "bindings-python")

    os.environ["PYTHONPATH"] += os.pathsep.join([bindings_path, repo_folders["pip_packages"]])
    os.environ["PATH"] += os.pathsep + libraries_path
    os.environ["CARB_APP_PATH"] = libraries_path

    if platform_target == "windows-x86_64":
        python_bin = os.path.join(repo_folders["target_deps"], "python/python.exe")
    else:
        python_bin = os.path.join(repo_folders["target_deps"], "python/bin/python3.6")

    # Report using teamcity messages only on teamcity itself
    import teamcity

    unittest_module = "teamcity.unittestpy" if teamcity.is_running_under_teamcity() else "unittest"

    tests_folder = os.path.join(repo_folders["root"], "source/tests/python")
    omni.repo.man.run_process(
        [python_bin, "-m", unittest_module, "discover", "-s", tests_folder, "-p", options.pattern], exit_on_error=True
    )


if __name__ == "__main__":
    main()

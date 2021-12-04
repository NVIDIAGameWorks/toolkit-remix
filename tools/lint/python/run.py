"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import argparse
import contextlib
import glob
import io
import os
import sys

import lint_utils
import packmanapi

REPO_ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../../..")
REPO_DEPS_FILE = os.path.join(REPO_ROOT, "deps/repo-deps.packman.xml")
EXCLUDES = [".vscode", "_build", "_compiler", "_repo", ".git", ".eggs", ".venv", "tools"]
FORCE_INCLUDE = ["lint"]  # folder that are in excludes but we want to force


def bootstrap():
    """Bootstrap all omni.repo modules.

    Pull with packman from repo.packman.xml and add them all to python sys.path to enable importing."""
    with contextlib.redirect_stdout(io.StringIO()):
        deps = packmanapi.pull(REPO_DEPS_FILE)
    for dep_path in deps.values():
        if dep_path not in sys.path:
            sys.path.append(dep_path)


def setup_argument_parser(parser: argparse.ArgumentParser):
    parser.prog = "isort_and_lint"
    parser.description = "Isort and lint staged Python files."
    parser.add_argument("-v", "--verify", action="store_true", dest="verify", required=False, default=False)
    parser.add_argument("--all-files", action="store_true", dest="all_files", required=False, default=False)


def get_default_argument_parser() -> argparse.ArgumentParser:
    """Default argument parser for format tool """

    parser = argparse.ArgumentParser()
    setup_argument_parser(parser)
    return parser


def check_excludes(filename):
    if any(file in FORCE_INCLUDE for file in os.path.normpath(filename.lower()).split(os.sep)):
        return False
    if any(exclude in os.path.normpath(filename.lower()).split(os.sep) for exclude in EXCLUDES):
        return True
    return False


def main():
    """Main function
    Quick implementation of linters. Waiting for: OM-36519 and OM-36518"""
    bootstrap()
    import omni.repo.format
    import omni.repo.man

    parser = get_default_argument_parser()
    options = parser.parse_args()

    if not options.all_files:
        files = lint_utils.get_modified_files()
    else:
        files = glob.glob("**/*.py", recursive=True)

    # filter
    filtered_files = [filename for filename in files if not check_excludes(filename) and os.path.isfile(filename)]
    if filtered_files:
        result_files = list(filter(lambda x: x.lower().endswith(".py"), filtered_files))
        if result_files:
            repo_folders = omni.repo.man.get_repo_paths(REPO_ROOT)
            pip_packages_path = repo_folders["pip_packages"]
            omni.repo.man.pip_install("isort", pip_packages_path)
            omni.repo.man.pip_install("flake8", pip_packages_path)
            omni.repo.man.pip_install("pep8-naming", pip_packages_path, module="pep8ext_naming")
            omni.repo.man.pip_install("flake8-docstrings", pip_packages_path, module="flake8_docstrings")
            omni.repo.man.pip_install("flake8-builtins", pip_packages_path, module="flake8_builtins")
            omni.repo.man.pip_install("flake8-bugbear", pip_packages_path, module="bugbear")
            omni.repo.man.pip_install("flake8-comprehensions", pip_packages_path, module="flake8_comprehensions")
            omni.repo.man.pip_install("flake8-return", pip_packages_path, module="flake8_return")
            omni.repo.man.pip_install("flake8-pep3101", pip_packages_path, module="flake8_pep3101")
            omni.repo.man.pip_install("flake8-simplify", pip_packages_path, module="flake8_simplify")
            flake8_config = os.path.join(os.path.dirname(os.path.realpath(__file__)), ".flake8")

            return_codes = []

            chunks_size = 10
            chunks = [result_files[x : x + chunks_size] for x in range(0, len(result_files), chunks_size)]  # noqa: E203

            for chunk in chunks:
                with omni.repo.man.change_envvar("PYTHONPATH", pip_packages_path):
                    args = [sys.executable, "-m", "isort", "--profile", "black"]
                    if options.verify:
                        args.append("--check")
                    args.extend(chunk)
                    return_codes.append(omni.repo.man.run_process(args))
                    args = [sys.executable, "-m", "flake8", f"--config={flake8_config}"]
                    args.extend(chunk)
                    return_codes.append(omni.repo.man.run_process(args))
            if set(return_codes) != {0}:
                sys.exit(1)


if __name__ == "__main__":
    main()

import os
import sys
import logging
import argparse

logger = logging.getLogger(os.path.basename(__file__))

DEPS = {
    "repo_format": {
        "version": "0.2.7",
        "link_path_host": "repo_format",
        # "source_path_host": "C:/projects/repo/repo_format",  # DEVELOPMENT
        "remotes": ["gitlab-repo"],
        "add_to_sys_path": True,
    }
}

CPP_FILES_TO_FORMAT = [
    "include/**/*.h",
    "include/**/*.inl",
    "include/**/*.cpp",
    "include/**/*.c",
    "source/**/*.h",
    "source/**/*.inl",
    "source/**/*.cpp",
    "source/**/*.c",
]


def main():
    import repoman

    repoman.bootstrap()
    import omni.repo.man

    platform_host = omni.repo.man.get_and_validate_host_platform(["windows-x86_64", "linux-x86_64"])

    parser = argparse.ArgumentParser()
    parser.prog = "format"
    parser.description = "Format all C++ code (with clang-format) and all python code (with black)."
    parser.add_argument(
        "-p",
        "--python-only",
        action="store_true",
        dest="python_only",
        required=False,
        help="Only run python code formatting.",
    )
    parser.add_argument(
        "-c", "--cpp-only", action="store_true", dest="cpp_only", required=False, help="Only run C++ code formatting."
    )
    parser.add_argument("-v", "--verify", action="store_true", dest="verify", required=False, default=False)
    options = parser.parse_args()

    repo_folders = omni.repo.man.get_repo_paths()
    omni.repo.man.fetch_deps(DEPS, platform_host, repo_folders["host_deps"])

    import omni.repo.format

    # C++ format:
    if not options.python_only:
        return_code = omni.repo.format.format_cpp(
            root=repo_folders["root"], file_patterns=CPP_FILES_TO_FORMAT, verify=options.verify, config_file=__file__
        )
        omni.repo.format.update_copyright_for_git_modified_files()
        if options.verify and return_code != 0:
            logger.error("C++ formatting verification failed.")
            sys.exit(return_code)

    # Python format:
    if not options.cpp_only:
        exclude = omni.repo.format.DEFAULT_PY_EXCLUDE
        # exclude += "|/glob2/"
        return_code = omni.repo.format.format_py(
            repo_folders["root"], repo_folders["pip_packages"], exclude=exclude, verify=options.verify
        )
        if options.verify and return_code != 0:
            logger.error("Python formatting verification failed.")
            sys.exit(return_code)


if __name__ == "__main__":
    main()

import os
import sys
import platform
import argparse

import logging
import re

from typing import List

import packmanapi


logger = logging.getLogger(os.path.basename(__file__))

DEPS = {
    "repo_build": {
        "version": "0.4.5",
        "link_path_host": "repo_build",
        # "source_path_host": "C:/projects/repo/repo_build", # DEVELOPMENT
        "remotes": ["gitlab-repo"],
        "add_to_sys_path": True,
    },
    "repo_fileutils": {
        "version": "2.0.3",
        "link_path_host": "repo_fileutils",
        # "source_path_host": "C:/projects/repo/repo_fileutils", # DEVELOPMENT
        "remotes": ["gitlab-repo"],
        "add_to_sys_path": True,
    },
}


def clean():
    logger.info("cleaning repo:")
    folders = ["_build", "_compiler", "_builtpackages"]

    root = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..")
    for folder in folders:
        folder = os.path.abspath(os.path.join(root, folder))
        # having to do the platform check because its safer when you might be removing
        # folders with windows junctions.
        if os.path.exists(folder):
            logger.info(f"removing folder: {folder}")
            if platform.system() == "Windows":
                os.system("rmdir /q /s %s > nul 2>&1" % folder)
            else:
                os.system("rm -r -f %s > /dev/null 2>&1" % folder)
            if os.path.exists(folder):
                logger.warn(
                    f"{folder} was not successfully removed, most probably due to a file lock on 1 or more of the files."
                )


def stage_files(platform_target: str, configs: List[str]):
    import omni.repo.man
    import omni.repo.fileutils

    logger.info("doing file copy and folder linking")

    repo_folders = omni.repo.man.get_repo_paths()
    omni.repo.man.pip_install("toml", repo_folders["pip_packages"])
    import toml

    prebuild_dict = toml.load(repo_folders["prebuild_toml"])

    extra_mapping = {
        "kit_sdk": os.path.join(repo_folders["target_deps"], "kit_sdk")
    }
    with omni.repo.man.change_cwd(repo_folders["root"]):
        omni.repo.fileutils.copy_and_link_using_dict_for_platform(prebuild_dict, platform_target, configs, extra_mapping=extra_mapping)


def setup_vscode_env(platform_target: str, configs: List[str]):
    import omni.repo.man

    repo_folders = omni.repo.man.get_repo_paths()

    # Use target python as default python for VSCode
    # packmanapi.link(os.path.join(repo_folders["host_deps"], "python"), os.environ["PM_python_PATH"])

    # Install python packages configured to be used in VSCode project settings
    omni.repo.man.pip_install("flake8", repo_folders["pip_packages"])
    omni.repo.man.pip_install("black", repo_folders["pip_packages"], version="19.3b0")

    VSCODE_PYTHON_PATH = [
        repo_folders["pip_packages"],
        os.path.join(repo_folders["host_deps"], "repo_man"),
        os.path.join(repo_folders["host_deps"], "repo_build"),
        os.path.join(repo_folders["host_deps"], "repo_fileutils"),
        os.path.join(repo_folders["host_deps"], "repo_format"),
        os.path.join(repo_folders["root"], "tools/repoman"),
    ]

    # Create env file for every config setting up PATH and PYTHONPATH to properly load python bindings for intellisense
    # This file is pointed in settings.json file to be used by vscode python
    build_path = repo_folders["build"]
    os.makedirs(build_path, exist_ok=True)
    for config in configs:
        libraries_path = os.path.join(build_path, platform_target, config)
        bindings_path = os.path.join(libraries_path, "bindings-python")
        python_path = os.pathsep.join(
            ["${PYTHONPATH}", os.environ.get("PYTHONPATH"), bindings_path] + VSCODE_PYTHON_PATH
        )
        with open(os.path.join(build_path, f"python_{config}.env"), "w") as f:
            f.write("PATH=${{PATH}}{0}{1}\n".format(os.pathsep, libraries_path))
            f.write(f"PYTHONPATH={python_path}\n")


def main():
    import repoman

    repoman.configure_logging()

    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.prog = "build"
    parser.description = """
Build command does the following:

    1. Fetch dependencies using packman
    2. Stage files (copy files and link folder using prebuild.toml, setup vscode env)
    3. Generate projects
    4. Build projects

This is done for both "release" and "debug" configuration.

Use various flag to control which steps you want to be executed.

By default host platform is used as target platform.
    """
    parser.add_argument(
        "-s", "--stage", action="store_true", dest="stage_and_stop", required=False, help="Stage files and stop."
    )
    parser.add_argument(
        "-g",
        "--generate",
        action="store_true",
        dest="generate_and_stop",
        required=False,
        help="Generate projects and stop.",
    )
    parser.add_argument("-c", "--clean", action="store_true", dest="clean", required=False, help="Clean repo and exit.")
    parser.add_argument(
        "-x", "--rebuild", action="store_true", dest="rebuild", required=False, help="Clean repo before building."
    )
    parser.add_argument("-j", "--jobs", dest="jobs", required=False, default=-1)
    parser.add_argument("-q", "--quiet", action="store_true", dest="quiet", required=False, default=False)
    parser.add_argument(
        "-d",
        "--debug-only",
        action="store_true",
        dest="debug_only",
        required=False,
        help='Only do "debug" configuration',
    )
    parser.add_argument(
        "-r",
        "--release-only",
        action="store_true",
        dest="release_only",
        required=False,
        help='Only do "release" configuration',
    )
    parser.add_argument("-p", "--platform-target", dest="platform_target", required=False)

    if sys.platform != "win32":
        parser.add_argument(
            "--no-docker",
            dest="use_docker",
            action="store_false",
            required=False,
            default=True,
            help="Build without docker.",
        )

    options = parser.parse_args()

    # Clean folders?
    if options.clean:
        clean()
        return

    if options.rebuild:
        clean()

    # Load repoman only now to not mess with clean step which will remove host-deps folder.
    import repoman

    repoman.bootstrap()
    import omni.repo.man

    platform_host = omni.repo.man.get_and_validate_host_platform(["windows-x86_64", "linux-x86_64", "linux-aarch64"])
    repo_folders = omni.repo.man.get_repo_paths()
    omni.repo.man.fetch_deps(DEPS, platform_host, repo_folders["host_deps"])

    import omni.repo.build

    # By default target platform equals host platform
    platform_target = options.platform_target
    if platform_target is None:
        platform_target = platform_host

    # Special cases for aarch64: wayland vs x11. To be cleaned up with a more generic solution.
    if platform_target == "linux-aarch64":
        if platform_target == platform_host:
            subplatform = "%s-desktop" % platform_target
        else:
            subplatform = "%s-embedded" % platform_target
    else:
        subplatform = None

    # Select configurations to work with
    configs = ["debug", "release"]
    if options.release_only:
        configs = ["release"]
    if options.debug_only:
        configs = ["debug"]

    # Pull all build dependencies
    logger.info("pulling all packman dependencies")
    packmanapi.pull(repo_folders["target_deps_xml"], platform=platform_target)
    if subplatform is not None:
        packmanapi.pull(repo_folders["target_deps_xml"], subplatform)
    packmanapi.pull(repo_folders["host_deps_xml"], platform=platform_host)

    # Copy and link folders/files step
    stage_files(platform_target, configs)

    # Setup python env for vs code
    setup_vscode_env(platform_target, configs)

    if options.stage_and_stop:
        return

    is_windows = platform_host == "windows-x86_64"

    # Relaunch this build script in linbuild (a docker buildroot jail) on linux
    # if not yet in such an environment.
    if not is_windows and options.use_docker and "LINBUILD_EMBEDDED" not in os.environ:
        # Search for package paths which need to be volume mapped in to the
        # buildroot container.  This would be, anything not one of: a
        # subdirectory of the current working directory or something in
        # packman's package cache root.
        re_pkgname_from_pm_path_key = re.compile(r"^PM_(\w+)_PATH$")
        user_dep_volumes, default_volumes = [], [os.path.abspath(os.curdir), os.environ["PM_PACKAGES_ROOT"]]

        for key in os.environ:
            match = re_pkgname_from_pm_path_key.match(key)
            if not match:
                continue
            _, pkgpath = match.groups()[0], os.environ[key]
            if not any([pkgpath.startswith(volume) for volume in default_volumes]):
                user_dep_volumes.append(pkgpath)

        os.execv(
            "_build/host-deps/linbuild/linbuild.sh",
            ["_build/host-deps/linbuild/linbuild.sh"]
            + ["--with-volume=%s" % x for x in user_dep_volumes]
            + ["--", "tools/packman/python.sh"]
            + sys.argv,
        )

    # Setup and run actual repo.build tool. It will generate and optionally build solutions.
    repo_root = repo_folders["root"]
    premake_file = repo_folders["premake_file"]
    premake_exec = "premake5.exe" if is_windows else "premake5"
    premake_tool = os.path.join(repo_folders["host_deps"], "premake", premake_exec)
    do_build = not options.generate_and_stop

    use_msbuild = is_windows
    if use_msbuild:
        msbuild_tool = os.path.join(repo_folders["host_deps"], r"msvc\MSBuild\15.0\Bin\MSBuild.exe")
        vs_version = "vs2017"
        sln = os.path.join(repo_folders["compiler"], rf"{vs_version}\Carbonite.sln")
        omni.repo.build.build_with_msbuild(
            repo_root=repo_root,
            premake_file=premake_file,
            premake_tool=premake_tool,
            msbuild_tool=msbuild_tool,
            sln=sln,
            platform_target=platform_target,
            configs=configs,
            vs_version=vs_version,
            quiet=options.quiet,
            jobs=options.jobs,
            generate_projects=True,
            build=do_build,
        )
    else:
        omni.repo.build.build_with_make(
            repo_root=repo_root,
            premake_file=premake_file,
            premake_tool=premake_tool,
            platform_target=platform_target,
            configs=configs,
            quiet=options.quiet,
            jobs=options.jobs,
            generate_projects=True,
            build=do_build,
        )


if __name__ == "__main__":
    main()

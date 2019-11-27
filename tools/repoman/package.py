import os
import argparse
import datetime
import logging

import repoman

repoman.bootstrap()

logger = logging.getLogger(os.path.basename(__file__))

REPO_PACKAGE = "5.0.0"

DEPS = {
    "repo_package": {"version": REPO_PACKAGE, "link_path_host": "repo_package", "add_to_sys_path": True},
    "git": {"version": "2.17.0-windows-x86_64", "platforms": "windows-x86_64"},
}


def package(pkg_desc, platform_target: str):
    import omni.repo.package

    omni.repo.package.package(pkg_desc)


def package_unittests(pkg_desc, platform_target: str):
    import omni.repo.package

    omni.repo.package.package(pkg_desc)

    # Temporary workaround to combine both old and new UT versioning
    pkg_desc.name = "test_binaries"
    pkg_desc.version = ""
    pkg_desc.ziponly = True

    omni.repo.package.package(pkg_desc)

    repo_folders = omni.repo.man.get_repo_paths()

    created_package_name = os.path.join(repo_folders["root"], "_builtpackages/test_binaries@%s.zip" % (platform_target))
    if os.path.exists(created_package_name):
        old_package_name = os.path.join(repo_folders["root"], "_builtpackages/test_binaries-%s.zip" % (platform_target))
        print("Workaround for the old TeamCity config: renaming %s to %s" % (created_package_name, old_package_name))
        os.rename(created_package_name, old_package_name)
    else:
        print("WARNING! Workaround is present, but file wasn't created!")


def package_symbols(pkg_desc, platform_target: str):
    import omni.repo.package

    pkg_desc.ziponly = True
    omni.repo.package.package(pkg_desc)


PACKAGES = {
    "sdk": ("carb_sdk", package, ["debug", "release"]),
    "sdk+plugins": ("carb_sdk+plugins", package, ["debug", "release"]),
    "unittests": ("carb_unittests", package_unittests, ["release"]),
    "symbols": ("windows_symbols", package_symbols, ["debug", "release"]),
}


def run_command():
    import omni.repo.man

    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--platform-target", dest="platform_target", required=False)

    parser.add_argument("-m", "--mode", dest="mode", choices=PACKAGES.keys(), required=True)
    parser.add_argument("-n", "--name", dest="name", help="override name of package", required=False)
    options = parser.parse_args()

    platform_host = omni.repo.man.get_and_validate_host_platform(["windows-x86_64", "linux-x86_64"])
    # By default target platform equals host platform
    platform_target = options.platform_target
    if platform_target is None:
        platform_target = platform_host

    omni.repo.man.validate_platform(platform_target, ["windows-x86_64", "linux-x86_64", "linux-aarch64"], "target")

    repo_folders = omni.repo.man.get_repo_paths()

    omni.repo.man.fetch_deps(DEPS, platform_host, repo_folders["host_deps"])

    # Use current year in UTC time zone as major version
    PKG_BUILD = "%d" % datetime.datetime.utcnow().year

    import omni.repo.package

    # this is temp and should be removed i nthe near future.
    omni.repo.package.nvfilecopy.warn_if_not_exist = True

    if os.getenv("BUILD_NUMBER"):
        package_version = os.getenv("BUILD_NUMBER")
    else:
        package_version = "%s#%s" % (PKG_BUILD, omni.repo.man.get_git_branch())

    def get_label_name(pkg_name):
        return "%s@%s-%s.latest.txt" % (pkg_name, PKG_BUILD, platform_target)

    pkg_desc = omni.repo.package.PackageDesc()
    pkg_desc.custom_platform = platform_target
    pkg_desc.version = package_version
    pkg_desc.append_git_hash = False
    pkg_desc.output_folder = "_builtpackages"
    pkg_desc.remove_pycache = True

    omni.repo.man.pip_install("toml", repo_folders["pip_packages"])
    import toml

    package_dict = toml.load(os.path.join(repo_folders["root"], "package.toml"))

    package_name, package_fn, configs = PACKAGES[options.mode]
    pkg_desc.files = []
    pkg_desc.files.extend(
        omni.repo.man.gather_files_from_dict_for_platform(package_dict, package_name, platform_target, configs)
    )

    if options.name is not None:
        package_name = options.name

    pkg_desc.name = package_name
    pkg_desc.label_name = get_label_name(pkg_desc.name)

    package_fn(pkg_desc, platform_target)


if __name__ == "__main__" or __name__ == "__mp_main__":
    run_command()

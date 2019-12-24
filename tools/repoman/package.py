import os
import argparse
import datetime
import logging

import repoman

repoman.bootstrap()
import omni.repo.man
import omni.repo.package


logger = logging.getLogger(os.path.basename(__file__))


def package(pkg_desc, platform_target: str):
    omni.repo.package.package(pkg_desc)


PACKAGES = {"example_extensions": ("example_extensions", package, ["debug", "release"])}


def run_command():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--platform-target", dest="platform_target", required=False)
    parser.add_argument(
        "-m",
        "--mode",
        dest="mode",
        choices=PACKAGES.keys(),
        default=next(iter(PACKAGES)),
        help="Package to produce. (default: %(default)s)",
    )
    parser.add_argument("-n", "--name", dest="name", help="override name of package", required=False)
    options = parser.parse_args()

    platform_host = omni.repo.man.get_and_validate_host_platform(["windows-x86_64", "linux-x86_64"])
    # By default target platform equals host platform
    platform_target = options.platform_target
    if platform_target is None:
        platform_target = platform_host

    omni.repo.man.validate_platform(platform_target, ["windows-x86_64", "linux-x86_64", "linux-aarch64"], "target")

    repo_folders = omni.repo.man.get_repo_paths()

    # Use current year in UTC time zone as major version
    PKG_BUILD = "%d" % datetime.datetime.utcnow().year

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
    pkg_desc.output_folder = "_build/packages"
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

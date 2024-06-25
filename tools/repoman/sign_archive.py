import argparse
import os
import shutil
import sys

import packmanapi
import repoman

repoman.bootstrap()

import omni.repo.man
import omni.repo.codesign

platform_host = omni.repo.man.get_and_validate_host_platform(["windows-x86_64"])
repo_folders = omni.repo.man.get_repo_paths()
script_dir = os.path.dirname(os.path.realpath(__file__))
repo_root = repo_folders["root"]


def sign_binaries():
    script_argv = ["sign", "-i", repo_folders["unsignedpackages"], "-o", repo_folders["signedpackages"], "-np"]

    json_file = os.path.join(script_dir, "..", "buildscripts", "signing_process.json")

    if os.path.isfile(json_file):
        script_argv.append("-j")
        script_argv.append(json_file)

    omni.repo.codesign.codesign.main(script_argv)

    files = os.listdir(repo_folders["signedpackages"])
    src = os.path.join(repo_folders["signedpackages"], files[0])
    dst = os.path.join(repo_folders["signedpackages"], files[0].replace(".zip", ".signed.zip"))
    os.rename(src, dst)
    # packmanapi.push(path=dst, remotes=["cloudfront_upload"], container="zip", force=False)


def upload_artifacts():
    print("##teamcity[publishArtifacts '_signedpackages/*']")


if __name__ == "__main__" or __name__ == "__mp_main__":
    sign_binaries()

    upload_artifacts()

"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""
import os
import pathlib
import platform
import subprocess

REPO_ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "../..")
REPO_EXTS = os.path.join(REPO_ROOT, "source/extensions")


def is_file_modified():
    import omni.repo.man as repo_man
    git_path = repo_man.find_git_path()
    result = []
    p = subprocess.Popen([git_path, "merge-base", "origin/master", "HEAD"], stdout=subprocess.PIPE, encoding="utf8")
    for f in p.stdout:
        head = f.split()
        p = subprocess.Popen([git_path, "diff", "--name-only", head[0]], stdout=subprocess.PIPE, encoding="utf8")
        for f in p.stdout:
            elements = f.split()
            result.extend(elements)
        break

    return result


def get_last_published_extension(ext_names):
    # we use Kit for that
    script = pathlib.Path(REPO_ROOT).joinpath('tools', 'utils', 'print_published_extensions.py').resolve()
    exts_list = ",".join(ext_names)
    script_args = f"{script} {exts_list}"
    cmd = [
        str(
            pathlib.Path(REPO_ROOT).joinpath(
                "_build",
                "windows-x86_64",
                "release",
                "kit",
                "kit.exe" if platform.system().lower() == "windows" else "kit"
            ).resolve()
        ),
        "--empty",
        "--enable",
        "omni.kit.registry.nucleus",
        "--exec", f"\"{script_args}\""
    ]
    p = subprocess.Popen(" ".join(cmd), shell=True, stdout=subprocess.PIPE, encoding="utf8")
    last_version = []
    for f in p.stdout:
        if "Last version: " in f:
            last_version.append(f.split("Last version: ")[-1].strip())
    return last_version


def run():
    import omni.repo.man as repo_man
    from omni.repo.kit_tools import bump

    repo_folders = repo_man.get_repo_paths()
    repo_man.pip_install_multiple([["semver==3.0.0", "semver"]], repo_folders["pip_packages"])

    ext_folders = repo_man.resolve_tokens(REPO_EXTS)
    time_out = 0
    i = 0
    # we loop again and again (brute force still...) until there is no more extensions to update
    while True:
        repo_man.run_process(
            [
                pathlib.Path(REPO_ROOT).joinpath("repo" + ".bat" if platform.system().lower() == "windows" else ".sh"),
                "build",
                "-r",
                "-u",
                "--fetch-only"
            ],
            exit_on_error=True
        )

        # grab modified files
        modified_files = is_file_modified()

        # filter only modified extensions
        exts = list(bump.get_all_extensions([ext_folders]))
        modified_exts = []

        extension_changed = False
        for ext in exts:
            for modified_file in modified_files:
                if f"/{ext.name}/" in modified_file:
                    if ext in modified_exts:
                        continue
                    modified_exts.append(ext)
                    break
        last_ext_versions = get_last_published_extension([modified_ext.name for modified_ext in modified_exts])
        for modified_ext in modified_exts:
            print(f"Checking {modified_ext.name}")
            for last_ext_version in last_ext_versions:
                if last_ext_version == modified_ext.ext_id:
                    txt = "### Changed\n"
                    txt += "- Update deps"
                    bump.bump_extension(modified_ext, "patch", txt)
                    extension_changed = True
                    break

        if not extension_changed:
            i += 1
            print(f"Took {i} loops to update")
            break
        time_out += 1
        if time_out == 10:
            raise ValueError(f"Something is wrong. Stopping")


def setup_repo_tool(parser, _):
    parser.prog = "auto_update_deps"
    parser.description = (
        "Update all dependencies and bump the versions of extensions which rely on the updated dependencies"
    )

    def run_repo_tool(options, config):
        run()

    return run_repo_tool

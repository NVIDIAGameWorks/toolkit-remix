import argparse
import json
import os
import shutil
from pathlib import Path

import omni.repo.ci
from omni.repo.man import resolve_tokens

ROOT = Path(resolve_tokens("${root}"))
KIT_APP = "lightspeed.app.trex"
ETM_LIST_APP = "omni.etm.list.lightspeed_rtx"


# Copy from omni.ext.get_extension_name
def _get_extension_name(ext_id: str) -> str:
    """
    Convert 'omni.foo-tag-1.2.3' to 'omni.foo-tag'
    Convert 'omni.foo-1.2.3-rc.1' to 'omni.foo'
    Convert 'omni.foo-tag-1.2.3-rc.1' to 'omni.foo-tag'
    """
    a, b, *_ = ext_id.split("-") + [""]
    if b and not b[0:1].isdigit():
        return f"{a}-{b}"
    return a


def _ext_id_to_fullname_and_version(ext_id) -> tuple[str, str]:
    """
    Convert 'omni.foo-tag-1.2.3' to ('omni.foo-tag', '1.2.3'); 'omni.bar-1.2.3' to ('omni.bar', '1.2.3')
    """
    name = _get_extension_name(ext_id)
    version = ext_id[len(name) + 1 :]
    return name, version


def _check_and_print_diff(last_extension_ids: set[str], current_extension_ids: set[str]) -> bool:
    if last_extension_ids == current_extension_ids:
        return False

    last_ids = set(_ext_id_to_fullname_and_version(ext_id) for ext_id in last_extension_ids)
    current_ids = set(_ext_id_to_fullname_and_version(ext_id) for ext_id in current_extension_ids)

    added = current_ids - last_ids
    removed = last_ids - current_ids

    print("> Changes in dependencies:")
    printed = set()
    if added and removed:
        # Print version changes
        print(">> Version changes:")
        for a_name, a_version in added:
            for r_name, r_version in removed:
                if a_name == r_name:
                    printed.add((a_name, a_version))
                    printed.add((r_name, r_version))
                    print(f"  {a_name}: {r_version} -> {a_version}")

    if added - printed:
        print(">> Added:")
        for name, version in added - printed:
            print(f"  {name}: {version}")

    if removed - printed:
        print(">> Removed:")
        for name, version in removed - printed:
            print(f"  {name}: {version}")

    return True


def _generate() -> bool:
    # Dump full dependencies of all template extensions.
    deps_filename = "deps.json"
    omni.repo.ci.launch(
        [
            "${root}/_build/${platform}/release/kit${shell_ext}",
            "--no-window",
            "--enable",
            "omni.kit.loop",
            "--enable",
            "omni.kit.registry.nucleus",
            "--ext-folder",
            "templates",
            "--exec",
            f"tools/ci/scripts/dump_full_dependencies.py {KIT_APP} {ETM_LIST_APP} {deps_filename}",
        ]
    )
    with open(deps_filename, "r") as fr:
        result = json.loads(fr.read())
        app_version = result["next_version"]
        extension_ids = result["dependencies"]
        last_extension_ids = result["last_dependencies"]

    # Hardcoded the dependencies on Windows. Fix that in a better way later
    extension_ids.append("omni.kit.cadence_reality_dc_design-1.0.8")
    extension_ids.append("omni.kit.converter.patchmanager-1.0.31")
    extension_ids.append("omni.kit.converter.vtk-3.0.4")

    # Check difference of dependencies
    have_new_version = True
    if not last_extension_ids:
        print("> No previous dependencies found")
    elif not _check_and_print_diff(set(last_extension_ids), set(extension_ids)):
        print("> No changes in dependencies")
        have_new_version = False
        app_version = result["current_version"]
        # Continue to write the same version into the file. This is useful for some usages locally.

    dependencies = []
    for extension_id in sorted(extension_ids):
        name, version = _ext_id_to_fullname_and_version(extension_id)
        if f"{name}-{version}" != extension_id:
            raise ValueError(f"extension id in a invalid format: {extension_id}")
        dependencies.append(f'"{name}" = {{ version = "{version}" }}')

    # NOTE:
    # * Make `version` be aligned with Kit major and minor versions.
    # * Do not use writeTarget.kit=true because we'll also need to test exension compatibility with previous versions of Kit.
    # * When we'll work on the next major version of Kit, use a different extnsion name such as omni.etm.list.kit_app_template.107.
    dependencies_str = "\n".join(dependencies)
    message = f'''\
[package]
title = "ETM test list for {KIT_APP}"
version = "{app_version}"
description = """Track extensions that are tested by ETM. This file is generated from {KIT_APP}."""

[dependencies]
{dependencies_str}
'''

    output_path = str(ROOT / f"source/apps/{ETM_LIST_APP}.kit")
    with open(output_path, "w") as fw:
        fw.write(message)
    if have_new_version:
        print(f"> Wrote a new version {app_version} into {output_path}")
    else:
        print(f"> Wrote the same version {app_version} into {output_path}")
    return have_new_version


def main(args: argparse.Namespace):
    # 1. Fetch Kit and generate the project.
    # source/apps is required before running `repo build -r -g`
    # -r is required when running in CI env.
    omni.repo.ci.launch(["${root}/repo${shell_ext}",
                         "build",
                         "-r",
                         "-g",
                         "--",
                         "--/app/extensions/generateVersionLockSkipLocalExts=0",
                         "--/app/extensions/generateVersionLockSkipCoreExts=0",
                         ])

    # 2. Generate omni.etm.list.lightspeed_rtx.kit.
    if _generate():
        print("> Generated omni.etm.list.lightspeed_rtx")
        # 3. Use tools from Kit to publish omni.etm.list.lightspeed_rtx
        omni.repo.ci.launch(["${root}/repo${shell_ext}", "publish_exts"])

    print("> Done")

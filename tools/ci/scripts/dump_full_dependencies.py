import json
import sys

import omni.kit.app


def _get_current_version(manager, ext_name) -> tuple[int, int, int]:
    kit_major_minor = list(map(int, omni.kit.app.get_app().get_kit_version_short().split(".")))
    # Find out the latest version with the same major and minor versions in the remote registry.
    for package in manager.fetch_extension_versions(ext_name):
        if not manager.get_registry_extension_dict(package["id"]):
            continue
        version = package["version"]
        if version[0] == kit_major_minor[0] and version[1] == kit_major_minor[1]:
            return version[0], version[1], version[2]

    # No version found in the remote registry, use the current Kit version.
    return int(kit_major_minor[0]), int(kit_major_minor[1]), -1


def _get_last_dependencies(manager, ext_id: str) -> list[str]:
    ext_info = manager.get_registry_extension_dict(ext_id)
    if not ext_info:
        print(f"> No extension info in {ext_id}")
        return []
    dependencies = ext_info.get("dependencies", [])
    print(f"> Found {len(dependencies)} dependencies in {ext_id}")
    return list(sorted(f"{name}-{info['version']}" for name, info in dependencies.items()))


def _get_ext_ids(manager, kit_app_name: str) -> list[str]:
    result, exts, err = manager.solve_extensions([kit_app_name], add_enabled=False, return_only_disabled=False)
    print(f"> Found {len(exts)} extensions in local {kit_app_name}")
    num_in_kit = 0
    num_in_core = 0
    num_apps = 0
    num_invalid = 0
    num_in_local = 0
    num_self = 0
    ext_ids = []
    for e in exts:
        id_ = e["id"]
        ext_info = manager.get_registry_extension_dict(id_)
        if not ext_info:
            ext_info = manager.get_extension_dict(id_)
            if not ext_info:
                print(f"Invalid extension: {id_}")
                num_invalid += 1
                continue
            if ext_info.get("isCore", False):
                num_in_core += 1
                continue
            print(f"Skip local: {id_}")
            num_in_local += 1
            continue
        if ext_info.get("package/target/kitHash", None):
            num_in_kit += 1
            continue
        ext_name = ext_info.get("package/name", None)
        if ext_name == kit_app_name:
            num_self += 1
            continue
        # Skip the apps that are defined as .kit files in ETM testing.
        # Use a name test as it takes lots of code to get the field isKitFile from the full metadata via `omni.client`.
        if ext_name and ext_name.startswith("lightspeed.app."):
            num_apps += 1
            continue
        ext_id = ext_info.get("package/id", None)
        ext_ids.append(ext_id)
    ext_ids.sort()
    print(
        f"    Use {len(ext_ids)} extensions (Skip {num_in_kit} in Kit, {num_in_core} in Kit Core, "
        f"{num_self} self, {num_in_local} in local, {num_invalid} invalid, {num_apps} apps.)"
    )
    return ext_ids


def main():
    if len(sys.argv) != 4:
        print("Required arguments: <kit_app_name> <generated_extension_name> <output_filename>")
        print("Example: lightspeed.app.trex omni.etm.list.lightspeed_rtx deps.json")
        print("")
        print("Reads the full dependencies and writes them to a file.")
        print("Also write the next version number for <generated_extension_name>.")
        print(
            "If the extension does not exist, <major>.<minor>.0 is written, where <major> and <minor> are the major and minor version of the Kit."
        )
        omni.kit.app.get_app().post_quit(1)
        return

    kit_app_name = sys.argv[1]
    output_extension_name = sys.argv[2]
    filename = sys.argv[3]

    manager = omni.kit.app.get_app_interface().get_extension_manager()
    manager.sync_registry()

    current_version = _get_current_version(manager, output_extension_name)
    last_dependencies = []
    if current_version[2] == -1:
        print(f"> Use a new major/minor version: {current_version[0]}.{current_version[1]}.0")
    else:
        last_dependencies = _get_last_dependencies(
            manager, f"{output_extension_name}-{'.'.join(map(str, current_version))}"
        )
    ext_ids = _get_ext_ids(manager, kit_app_name)

    next_version = (current_version[0], current_version[1], current_version[2] + 1)
    out = {
        "current_version": ".".join(map(str, current_version)) if current_version[2] >= 0 else None,
        "next_version": ".".join(map(str, next_version)),
        "dependencies": ext_ids,
        "last_dependencies": last_dependencies,
    }
    with open(filename, "w") as fw:
        json.dump(out, fw, indent=2)
    print(f"> Wrote dependencies to {filename}")

    omni.kit.app.get_app().post_quit(0)


main()

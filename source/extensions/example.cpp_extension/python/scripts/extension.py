import os
import omni.kit.extensions


def get_extension():
    """Kit looks for this function to get an extension object. Returns new extension instance."""

    # Extension root folder
    ext_folder = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

    # Load plugin from exact library located inside of own extension package. Use provided utility to build correct
    # platform and config dependent relative path, e.g. bin/windows-x86_64/debug/my.dll
    lib_path = omni.kit.extensions.build_plugin_path(ext_folder, "example.cpp_extension.plugin")

    # NativeExtension is a simple helper which loads and unload a plugin. Copy paste it and change if you want more control.
    return omni.kit.extensions.NativeExtension(lib_path)

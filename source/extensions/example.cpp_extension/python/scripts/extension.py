import os
import omni.kit.minimal
import omni.kit.extensions


class Extension:
    """
    Minimal extension to run C++ plugin from python extension. That basically allows also writing extensions in C++.

    Minimal interface is used, but one have their own interface exposed via python bindings. The C++ plugin itself can use
    any of other Carbonite plugins available.

    When extension is disabled C++ plugin is released, that means it can be changed/recompiled and then loaded again. That
    enables quick iteration cycles while developing.
    """

    def __init__(self):
        ext_folder = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

        # Load plugin from exact library located inside of own extension package. Use provided utility to build correct
        # platform and config dependent relative path, e.g. bin/windows-x86_64/debug/my.dll
        lib_path = omni.kit.extensions.build_plugin_path(ext_folder, "example.cpp_extension.plugin")
        self._ext = omni.kit.minimal.acquire_minimal_interface(library_path=lib_path)

    def on_shutdown(self):
        # Releasing an interface unloads shared library
        omni.kit.minimal.release_minimal_interface(self._ext)


def get_extension():
    return Extension()

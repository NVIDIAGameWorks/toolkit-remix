import os
import omni.kit.extensions
from ..bindings import _mixed_extension


class Extension:
    def __init__(self):
        ext_folder = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        lib_path = omni.kit.extensions.build_plugin_path(ext_folder, "example.mixed_extension.plugin")
        self._mixed_extension = _mixed_extension.acquire_mixed_extension_interface(library_path=lib_path)

    def on_shutdown(self):
        _mixed_extension.release_mixed_extension_interface(self._mixed_extension)


def get_extension():
    return Extension()

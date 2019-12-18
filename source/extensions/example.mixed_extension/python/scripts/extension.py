import os
import omni.kit.extensions
from ..bindings import _flex
from .menu import FlexMenu


class Extension:
    def __init__(self):
        ext_folder = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        lib_path = omni.kit.extensions.build_plugin_path(ext_folder, "omni.flex.plugin")
        self._flex = _flex.acquire_flex_interface(library_path=lib_path)
        self._menu = FlexMenu(self._flex)

    def on_shutdown(self):
        _flex.release_flex_interface(self._flex)
        self._menu.shutdown()
        self._menu = None


def get_extension():
    return Extension()

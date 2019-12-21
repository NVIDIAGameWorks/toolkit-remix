import os
import omni.kit.extensions
from ..bindings import _battle_simulator


class Extension:
    def __init__(self):
        ext_folder = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        lib_path = omni.kit.extensions.build_plugin_path(ext_folder, "example.mixed_extension.plugin")
        self._battle_simulator = _battle_simulator.acquire_battle_simulator_interface(library_path=lib_path)

    def on_shutdown(self):
        _battle_simulator.release_battle_simulator_interface(self._battle_simulator)


def get_extension():
    return Extension()

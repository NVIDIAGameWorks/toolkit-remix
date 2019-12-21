import sys
from contextlib import contextmanager
import omni.kit.ui


EXTENSION_NAME = "Demo Python Only Extension"
EXTENSION_DESC = "Description."


class Extension:
    """
    Demo Extension.
    """

    def get_name(self):
        return EXTENSION_NAME

    def get_description(self):
        return EXTENSION_DESC

    def _on_press(self):
        self._x = self._x + 1
        self._button.text = "( 0 {0} 0 )".format('_' * self._x)

    def on_startup(self):
        self._window = omni.kit.ui.Window(EXTENSION_NAME, 300, 150)
        layout = self._window.layout

        self._button = layout.add_child(omni.kit.ui.Button("Press me"))
        self._button.set_clicked_fn(lambda *_: self._on_press())
        self._x = 0



def get_extension():
    return Extension()

import omni.kit.ui
from .funwindow import FunWindow


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

    def on_startup(self):
        self._window = FunWindow()

    def on_shutdown(self):
        self._window.on_shutdown()


def get_extension():
    return Extension()

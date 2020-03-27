import omni.ext
import omni.kit.ui
from .funwindow import FunWindow


class Extension(omni.ext.IExt):
    """
    Demo Extension.
    """

    def on_startup(self):
        self._window = FunWindow()

    def on_shutdown(self):
        self._window.on_shutdown()

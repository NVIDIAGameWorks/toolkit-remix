import omni.kit.ui


class FunWindow:
    """
    Window with a button.
    """
    def _on_press(self):
        self._x = self._x + 1
        self._button.text = "( 0 {0} 0 )".format('_' * self._x)

    def __init__(self):
        self._window = omni.kit.ui.Window("Fun Window", 300, 150)
        layout = self._window.layout

        self._button = layout.add_child(omni.kit.ui.Button("Press me"))
        self._button.set_clicked_fn(lambda *_: self._on_press())
        self._x = 0

    def on_shutdown(self):
        self._window = None
        self._button = None

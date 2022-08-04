from omni import ui
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class CustomErrorModel(ui.AbstractValueModel):
    def __init__(self, value: str = None):
        self._value = value
        super().__init__()

    def set_value(self, value):
        """Reimplemented set"""
        if value != self._value:
            # Tell the widget that the model is changed
            self._value = value
            self._value_changed()

    def get_value_as_string(self):
        return self._value


class ErrorPopup:
    """Creates a modal window with a status label and a progress bar inside.
    Args:
        title (str): Title of this window.
        message (str): Error message to display in a label.
        details (str): Error details to display in a string field.
    """

    def __init__(self, title, message, details):
        self.__default_attr = {
            "_title": None,
            "_message": None,
            "_details": None,
            "_popup": None,
            "_buttons": None,
            "_message_label": None,
            "_details_label": None,
            "_okay_button": None,
        }
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self._title = title
        self._message = message
        self._details = details
        self._popup = None
        self._buttons = []

        self.__build_ui()

    def __enter__(self):
        self._popup.visible = True
        return self

    def __exit__(self, type_, value, trace):
        self._popup.visible = False

    def show(self):
        self._popup.visible = True

    def hide(self):
        self._popup.visible = False

    def is_visible(self):
        return self._popup.visible

    def __build_ui(self):
        self._popup = ui.Window(self._title, visible=False, height=0, dockPreference=ui.DockPreference.DISABLED)
        self._popup.flags = (
            ui.WINDOW_FLAGS_NO_COLLAPSE
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_MOVE
        )

        with self._popup.frame:
            with ui.VStack(height=0):
                ui.Spacer(width=0, height=ui.Pixel(8))
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(8), height=0)
                    self._message_label = ui.Label(self._message, word_wrap=True, alignment=ui.Alignment.CENTER)
                    ui.Spacer(width=ui.Pixel(8), height=0)
                if self._details:
                    ui.Spacer(width=0, height=ui.Pixel(8))
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8), height=0)
                        self._details_label = ui.StringField(
                            CustomErrorModel(self._details), multiline=True, read_only=True, height=ui.Pixel(96)
                        )
                        ui.Spacer(width=ui.Pixel(8), height=0)
                ui.Spacer(width=0, height=ui.Pixel(8))
                with ui.HStack():
                    ui.Spacer(height=0)
                    self._okay_button = ui.Button("Okay", width=ui.Pixel(64), height=0)
                    self._okay_button.set_clicked_fn(self.hide)
                    self._buttons.append(self._okay_button)
                    ui.Spacer(height=0)
                ui.Spacer(width=0, height=ui.Pixel(8))

    def destroy(self):
        for button in self._buttons:
            button.set_clicked_fn(None)

        _reset_default_attrs(self)

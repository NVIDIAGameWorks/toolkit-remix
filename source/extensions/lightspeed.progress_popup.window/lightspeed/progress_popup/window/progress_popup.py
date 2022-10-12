from omni import ui


class CustomProgressModel(ui.AbstractValueModel):
    def __init__(self):
        super().__init__()
        self._value = 0.0

    def set_value(self, value):
        """Reimplemented set"""
        try:
            value = float(value)
        except ValueError:
            value = None
        if value != self._value:
            # Tell the widget that the model is changed
            self._value = value
            self._value_changed()

    def get_value_as_float(self):
        return self._value

    def get_value_as_string(self):
        return str(int(self._value * 100)) + "%"


class ProgressPopup:
    """Creates a modal window with a status label and a progress bar inside.
    Args:
        title (str): Title of this window.
        cancel_button_text (str): It will have a cancel button by default. This is the title of it.
        cancel_button_fn (function): The callback after cancel button is clicked.
        status_text (str): The status text.
        min_value: The min value of the progress bar. It's 0 by default.
        max_value: The max value of the progress bar. It's 100 by default.
        dark_style: If it's to use dark style or light style. It's dark stye by default.
    """

    def __init__(self, title, cancel_button_text="Cancel", cancel_button_fn=None, status_text="", modal=True):
        self._status_text = status_text
        self._title = title
        self._cancel_button_text = cancel_button_text
        self._cancel_button_fn = cancel_button_fn
        self._progress_bar_model = None
        self._modal = False
        self._popup = None
        self._buttons = []
        self._build_ui()

    def destroy(self):
        self._cancel_button_fn = None
        self._progress_bar_model = None
        for button in self._buttons:
            button.set_clicked_fn(None)
        self._popup = None

    def __enter__(self):
        self._popup.visible = True
        return self

    def __exit__(self, type_, value, trace):
        self._popup.visible = False

    def set_cancel_fn(self, on_cancel_button_clicked):
        self._cancel_button_fn = on_cancel_button_clicked

    def set_progress(self, progress):
        self._progress_bar.model.set_value(progress)

    def get_progress(self):
        return self._progress_bar.model.get_value_as_float()

    progress = property(get_progress, set_progress)

    def set_status_text(self, status_text):
        self._status_label.text = status_text

    def get_status_text(self):
        return self._status_label.text

    status_text = property(get_status_text, set_status_text)

    def show(self):
        self._popup.visible = True

    def hide(self):
        self._popup.visible = False

    def is_visible(self):
        return self._popup.visible

    def _on_cancel_button_fn(self):
        self.hide()
        if self._cancel_button_fn:
            self._cancel_button_fn()

    def _build_ui(self):
        self._popup = ui.Window(
            self._title, visible=False, width=600, height=0, dockPreference=ui.DockPreference.DISABLED
        )
        self._popup.flags = (
            ui.WINDOW_FLAGS_NO_COLLAPSE
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_MOVE
        )

        if self._modal:
            self._popup.flags = self._popup.flags | ui.WINDOW_FLAGS_MODAL

        with self._popup.frame:
            with ui.VStack(height=0):
                ui.Spacer(height=10)
                with ui.HStack(height=0):
                    ui.Spacer()
                    self._status_label = ui.Label(self._status_text, word_wrap=True, width=0, height=0)
                    ui.Spacer()
                ui.Spacer(height=10)
                with ui.HStack(height=0):
                    ui.Spacer()
                    self._progress_bar_model = CustomProgressModel()
                    self._progress_bar = ui.ProgressBar(
                        self._progress_bar_model, width=300, style={"color": 0xFFFF9E3D}
                    )
                    ui.Spacer()
                ui.Spacer(height=5)
                with ui.HStack(height=0):
                    ui.Spacer(height=0)
                    cancel_button = ui.Button(self._cancel_button_text, width=0, height=0)
                    cancel_button.set_clicked_fn(self._on_cancel_button_fn)
                    self._buttons.append(cancel_button)
                    ui.Spacer(height=0)
                ui.Spacer(width=0, height=10)

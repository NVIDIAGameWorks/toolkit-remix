import sys
from contextlib import contextmanager
import omni.kit.pipapi
import omni.kit.commands
import omni.kit.ui


EXTENSION_NAME = "Python Tracing"
EXTENSION_DESC = "Use to trace every python call."
TRACE_FILE_NAME = "python_trace.log"


_trace_file = None
_trace_on = False
_trace_enabled = False


def set_trace_enabled(value: bool):
    """Enable tracing system."""
    global _trace_file
    if _trace_file is None and value:
        _trace_file = open(TRACE_FILE_NAME, "w")
    elif _trace_file is not None and not value:
        _trace_file = None


def clear_trace_log():
    """Clear tracing log."""
    global _trace_file
    enabled = _trace_file is not None
    set_trace_enabled(not enabled)
    set_trace_enabled(enabled)


def set_trace(value: bool):
    """Start/Stop trace."""
    global _trace_on
    _trace_on = value
    _refresh_trace()


@contextmanager
def trace():
    """Trace inside of context block.

    This function is a context manager.
    """

    set_trace(True)
    try:
        yield
    finally:
        set_trace(False)


def _refresh_trace():
    global _trace_on
    _set_trace_enabled(_trace_on)


def _set_trace_enabled(value: bool):
    global _trace_enabled, _trace_file
    if value == _trace_enabled:
        return
    if value:

        def trace_calls(frame, event, arg):
            global _trace_file
            if _trace_file is None or event != "call":
                return
            co = frame.f_code
            func_name = co.co_name
            func_line_no = frame.f_lineno
            func_filename = co.co_filename
            _trace_file.write(f"Call to {func_name} on line {func_line_no} of {func_filename}\n")
            _trace_file.flush()

        sys.settrace(trace_calls)
    else:
        sys.settrace(None)
    _trace_enabled = value
    if _trace_file is not None:
        _trace_file.write(f">>> Set trace enabled: {_trace_enabled}\n")
        _trace_file.flush()


class Extension:
    """
    Extension to trace python function calls into file.
    """

    def get_name(self):
        return EXTENSION_NAME

    def get_description(self):
        return EXTENSION_DESC

    def on_startup(self):
        self._window = omni.kit.ui.Window(EXTENSION_NAME, 300, 150)
        layout = self._window.layout

        # Trace Enabled
        self._toggle = layout.add_child(omni.kit.ui.CheckBox("Trace System Enabled"))
        self._toggle.set_on_changed_fn(lambda v: set_trace_enabled(v))

        # Toggle All
        self._toggle = layout.add_child(omni.kit.ui.CheckBox("Trace All"))
        self._toggle.set_on_changed_fn(lambda v: set_trace(v))

        # Clean Log
        self._clear = layout.add_child(omni.kit.ui.Button("Clear Log"))
        self._clear.set_clicked_fn(lambda *_: clear_trace_log())

        # Open File
        self._open = layout.add_child(omni.kit.ui.Button(TRACE_FILE_NAME))
        path = TRACE_FILE_NAME

        def on_open(_, path=path):
            import webbrowser

            webbrowser.open(path)

        self._open.set_clicked_fn(on_open)


def get_extension():
    return Extension()

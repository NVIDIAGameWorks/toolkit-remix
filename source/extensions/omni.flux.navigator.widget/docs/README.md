# Overview

This widget allows to navigate between widgets based on their position on the screen. It can be used in conjunction with


## Usage

You will need to register the widgets you want to navigate through before using this widget.

```python
from omni.ui as ui
from omni.flux.navigator.widget import NavigatorWidget

# A dummy widget dict. (Would normally be a dict of references to your widget's widgets)
widget_example_id = "example_id" # Using a UUID-4 here will guarantee unique IDs for the widgets
widget_example = ui.Rectangle()
widget_example_dict = { widget_example_id: widget_example }

# Set up the navigator
navigator = NavigatorWidget()  # Hold the widget in a variable or it will crash
navigator.register_widgets(widget_example_dict)

# Use the navigator. (Would usually be used in an input event handler)
navigator.go_right()
```

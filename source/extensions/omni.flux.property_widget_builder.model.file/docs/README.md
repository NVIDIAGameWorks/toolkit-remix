# Overview

This is the widget that let you build property widget(s) from disk file attributes.

You can show custom names for attributes. For example here, `translateY` is just `Y`:

![alt text](../data/images/preview.png)


There is a listener that will update the widget properties in real time.

## Usage

```python
import omni.client
import omni.ui as ui
from omni.flux.property_widget_builder.widget import PropertyWidget as _PropertyWidget

from omni.flux.property_widget_builder.model.file import get_file_listener_instance as _get_file_listener_instance
from omni.flux.property_widget_builder.model.file import FileModel as _FileModel
from omni.flux.property_widget_builder.model.file import FileDelegate as _FileDelegate
from omni.flux.property_widget_builder.model.file import FileAttributeItem as _FileAttributeItem

file_listener_instance = _get_file_listener_instance()

path = "/my_file.jpg"

items = []
for attr in [attr for attr in dir(omni.client.ListEntry) if not attr.startswith("_")]:
    items.append(_FileAttributeItem(path, attr, display_attr_name=attr.replace("_", " ").capitalize()))

model = _FileModel(path)
model.set_items(items)
delegate = _FileDelegate()
file_listener_instance.add_model_and_delegate(model, delegate)

with ui.Frame():
    widget = _PropertyWidget(model, delegate)
```

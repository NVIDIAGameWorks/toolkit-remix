# Overview

This is the widget that let you build property widget(s) from disk file attributes.

You can show custom names for attributes. For example here, `translateY` is just `Y`:

![alt text](../data/images/preview.png)


The file listener polls for metadata changes and updates changed attribute values without rebuilding property rows.
Cached metadata is cleared when a file becomes unreadable, its last model is removed, or the listener is destroyed.

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
file_listener_instance.add_model(model)

with ui.Frame():
    widget = _PropertyWidget(model, delegate)
```

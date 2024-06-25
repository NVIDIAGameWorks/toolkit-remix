# Overview

This is the widget that let you create a panel that shows all attributes of a USD prim(s)

![alt text](../data/images/preview.png)

## Usage

```python
from omni.flux.properties_pane.properties.usd.widget import PropertyWidget as _PropertyWidget

properties_create_ui = _PropertyWidget(self._context)  # hold the widget in a variable or it will crash
properties_create_ui.refresh(usd_paths)
```

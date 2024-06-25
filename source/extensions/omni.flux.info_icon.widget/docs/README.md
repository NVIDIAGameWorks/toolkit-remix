# Overview

This is the widget that let you create an icon that displays a message when hovered over

![alt text](../data/images/preview.png)

## Usage

```python
from omni.flux.info_icon.widget import InfoIconWidget

_info_icon = InfoIconWidget(message="This is a message that provides information")  # hold the widget in a variable or it will crash

...

# when done with object
_info_icon.destroy()
```

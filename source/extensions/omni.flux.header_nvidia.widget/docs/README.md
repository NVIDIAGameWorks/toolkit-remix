# Overview

This is the widget that let you create a header with the app name

![alt text](../data/images/preview.png)

## Usage

```python
from omni.flux.header_nvidia.widget import HeaderWidget

header_nvidia_widget = HeaderWidget()  # hold the widget in a variable or it will crash
```

## Implementation

### Logo
First you need to set your logo in your global style:
```python
import omni.ui as ui
style = ui.Style.get_instance()
current_dict = style.default
current_dict.update(
    {
        "Image::NvidiaShort": {"image_url": "Nvidia_logo.png", "color": 0xFFFFFFFF}
    }
)
style.default = current_dict
```

### App name
The header will show the name of the app automatically.

For this, you need to implement, as a setting in your Kit app, the app name, like:
```toml
[settings]
app.name = "Name of your app"
```

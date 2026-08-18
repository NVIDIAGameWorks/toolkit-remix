# omni.flux.property_widget_builder.model.native

Delegate and field builders for property widgets displaying native Python-typed data.

## Responsibilities

- Provides `NativeDelegate` for property widgets that work with non-USD, Python-typed items.
- Provides `NativeItem` as the explicit type contract consumed by native field builders.
- Provides `NATIVE_FIELD_BUILDERS` that dispatch to the correct widget based on `item.value_type`.
- Provides `NativeChoiceModel` for typed choices backed by the shared ComboBox delegate.
- Reuses the same checkbox, drag, string, file-picker, and ComboBox delegates as the Material and Object property panels.

## Non-Responsibilities

- Does not define product-specific properties; consumers provide `NativeItem` subclasses and value models.
- Does not handle USD-specific features such as overrides, layers, or metadata; use `model.usd` for that.
- Does not select editors from product-specific names or metadata aliases; dispatch uses the declared native type.

## Architecture

### Key Classes

- `NativeDelegate` extends `Delegate` and uses `NATIVE_FIELD_BUILDERS` by default.
- `NativeItem` requires an exact native `value_type`.
- `NativeChoiceModel` preserves typed choices while satisfying the native ComboBox item-model contract.
- `NATIVE_FIELD_BUILDERS` claims `NativeItem` values by exact Python type and uses the shared property delegates.

### Type Dispatch

Any `NativeItem` subclass is supported. Dispatch uses exact `value_type` matches; consumers set the Python type they
want rendered and may wrap the value model in `NativeChoiceModel` when the value has a fixed set of choices.

| `value_type` | Widget | Style |
|---|---|---|
| `bool` | `ui.CheckBox` | `PropertiesWidgetFieldBool` |
| `int` | `ui.IntDrag` | `PropertiesWidgetField` |
| `float` | `ui.FloatDrag` | `PropertiesWidgetField` |
| `str` | `ui.StringField` | `PropertiesWidgetField` |
| `pathlib.Path` | Shared file picker | `PropertiesWidgetField` |
| Any typed choices | Shared ComboBox | `PropertiesWidgetField` |

## Usage

```python
import pathlib

from omni.flux.property_widget_builder.model.native import NativeDelegate, NativeItem
from omni.flux.property_widget_builder.widget import Model, PropertyWidget


class ProductPropertyItem(NativeItem):
    @property
    def value_type(self) -> type:
        return pathlib.Path


model = Model()
model.set_items([ProductPropertyItem(...)])
delegate = NativeDelegate(right_aligned_labels=False)
widget = PropertyWidget(model=model, delegate=delegate)
```

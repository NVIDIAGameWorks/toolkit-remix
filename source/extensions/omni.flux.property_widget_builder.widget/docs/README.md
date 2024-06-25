# Overview

This is the base widget that let you build property widget(s) from any attributes (that come from USD, file, or anything...).

![alt text](../data/images/preview.png)

Because this is a base widget, by default, crating this widget will do nothing. You need to implement what the widget
has to show.

## Implementation

The widget uses multiple components:
- an item model class
- an item class
- a model class
- a delegate class

### Item model class

This is use a regular `ui.AbstractValueModel`. This item is the value or value of the name that your attribute has.

For example, if you have an attribute "translate" with a value "20", you will have 2 instances of the item model claas:
- one the show the value of the name: "translate"
- one the show the value of the value: "20"

This class can be subclassed to get the value of any data (name or value) (using a listener or not), like USD values, disk file values, etc etc

You can customize what you want to show using the `set_display_fn()` function.

For example, imagine the value represent some bytes, and the value is `4000`. But you want to display everything as kilobytes.
You can set a function with `set_display_fn()` that will divide the value by 1000 to show everything in kilobytes (`4`).
The underneath values will still be `4000`, but the UI will display `4`.

This feature is mainly used for attribute(s) that are read only. This is a "display" feature, not a "set" one.

### Item class

This is a regular `ui.AbstractItem`. This item has 2 properties:
- the name(s)
- the value(S)

Those 2 properties will be showed for each item into the property widget.

Each of those properties have to return a list of "item model class".

### Model class

This is a regular `ui.AbstractItemModel` that the `ui.TreeView` uses. It will hold all the items "item class".

### Delegate class

This is a regular `ui.AbstractItemDelegate`. The delegate will show each value of each item into 2 columns:
- name(s) in column 1
- value(s) in column 2

`_build_widget` has to be subclassed if you want to show your data.


## Implementation example(s)

Please check:
- `omni.flux.property_widget_builder.model.usd`
- `omni.flux.property_widget_builder.model.file`

For implementation examples.

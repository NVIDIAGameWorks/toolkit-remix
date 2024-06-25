# Overview

This widget allows users to view the history of selections.

![alt text](../data/images/preview.png)

## Implementation

The widget uses multiple components:
- an item class
- a model class
- a delegate class

### Item class

the `ItemBase` class inherits directly from `ui.AbstractItem` . It shows how a single item is to be defined and created.

- `SelectionHistoryItem`

These items are the structures that will be used in the delegate to display UI items on screen.

### Model class

This class inherits from `ui.AbstractItemModel` and must be inherited with abstract methods implemented.

The `ui.TreeView` uses the model class to populate the tree. The class holds all the items of type `SelectionHistoryItem` mentioned
in the "Item class" section.


### Delegate class

This class inherits from `ui.AbstractItemDelegate`. The delegate will define how the `ItemBase` items should be displayed in
terms of UI. The existing delegate can be overridden or replaced completely depending on your needs.

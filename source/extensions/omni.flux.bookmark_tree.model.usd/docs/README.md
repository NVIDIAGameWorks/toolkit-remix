# Overview

This model, in conjunction with the base widget `omni.flux.bookmark_tree.widget` allow users to create USD bookmark collections.

This model uses a USD Listener to update the UI in real-time based on changes applied to the USD Stage.

## Usage

```python
from omni.flux.bookmark_tree.model.usd import UsdBookmarkCollectionModel as _UsdBookmarkCollectionModel
from omni.flux.bookmark_tree.widget import BookmarkTreeWidget as _BookmarkTreeWidget
import omni.ui as ui

class TestWidget:
    def __init__(self, context_name: str):
        model = _UsdBookmarkCollectionModel(context_name)

        with ui.Frame():
            self._bookmark_tree_widget = _BookmarkTreeWidget(model=model)

        self._bookmark_tree_widget.show(True)
```

# Overview

This model, in conjunction with the base widget `omni.flux.selection_history_tree.widget` allow users to create USD Selection history.

This model uses a USD Listener to update the UI in real-time based on changes applied to the USD Stage.

## Usage

```python
from omni.flux.selection_history_tree.model.usd import UsdSelectionHistoryModel as _UsdSelectionHistoryModel
from omni.flux.selection_history_tree.widget import SelectionHistoryWidget as _SelectionHistoryWidget
import omni.ui as ui

class TestWidget:
    def __init__(self, context_name: str):
        model = _UsdSelectionHistoryModel(context_name)

        with ui.Frame():
            self._selectionHistoryWidget = _SelectionHistoryWidget(model=model)

        self._selectionHistoryWidget.show(True)

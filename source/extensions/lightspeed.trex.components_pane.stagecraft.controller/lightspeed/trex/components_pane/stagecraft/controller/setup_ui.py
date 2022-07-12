"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from lightspeed.trex.components_pane.stagecraft.models import create_all_items as _create_all_items
from omni.flux.tree_panel.widget import PanelOutlinerWidget as _PanelOutlinerWidget
from omni.flux.tree_panel.widget.tree.model import Model as _Model
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class SetupUI:
    def __init__(self):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {"_ui": None, "_items": None, "_model": None}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._items = _create_all_items()
        self._model = _Model()
        self._model.set_items(self._items)
        self._ui = _PanelOutlinerWidget(tree_model=self._model)  # hold or crash
        self._ui.set_title("Untitled workfile")

    def get_ui_widget(self):
        return self._ui

    def get_model(self):
        return self._model

    def destroy(self):
        _reset_default_attrs(self)

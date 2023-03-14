"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from pathlib import Path

import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.layer_types import LayerType
from lightspeed.trex.components_pane.stagecraft.models import create_all_items as _create_all_items
from omni.flux.tree_panel.widget import PanelOutlinerWidget as _PanelOutlinerWidget
from omni.flux.tree_panel.widget.tree.model import Model as _Model
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class SetupUI:

    DEFAULT_TITLE = "Untitled workfile"

    def __init__(self, context_name: str):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_ui": None,
            "_items": None,
            "_model": None,
            "_layer_manager": None,
            "_sub_stage_event": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context = omni.usd.get_context(context_name)
        self._layer_manager = _LayerManagerCore(context_name=context_name)

        self._sub_stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="StageChanged"
        )

        self._items = _create_all_items()
        self._model = _Model()
        self._model.set_items(self._items)
        self._ui = _PanelOutlinerWidget(tree_model=self._model)  # hold or crash
        self._ui.set_title(self.DEFAULT_TITLE)

    def __on_stage_event(self, event):
        if event.type in [
            int(omni.usd.StageEventType.CLOSED),
            int(omni.usd.StageEventType.OPENED),
            int(omni.usd.StageEventType.SAVED),
            int(omni.usd.StageEventType.ASSETS_LOADED),
        ]:
            self.refresh()

    def get_ui_widget(self):
        return self._ui

    def get_model(self):
        return self._model

    def refresh(self):
        capture_layer = self._layer_manager.get_layer(LayerType.capture)
        replacement_layer = self._layer_manager.get_layer(LayerType.replacement)
        if capture_layer and replacement_layer:
            for item in self._model.get_item_children(None):
                item.enabled = True
        else:
            # enable only the first one
            for i, item in enumerate(self._model.get_item_children(None)):
                item.enabled = i == 0

        # update the title
        stage_url = self._context.get_stage_url()
        stage = self._context.get_stage()
        root_layer = stage.GetRootLayer() if stage else None
        if stage_url and stage and root_layer and not root_layer.anonymous:
            self._ui.set_title(Path(stage_url).stem)
        else:
            self._ui.set_title(self.DEFAULT_TITLE)

    def destroy(self):
        _reset_default_attrs(self)

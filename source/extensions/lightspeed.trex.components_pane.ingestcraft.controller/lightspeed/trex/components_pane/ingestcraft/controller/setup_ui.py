"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""
from lightspeed.trex.components_pane.ingestcraft.models import create_all_items as _create_all_items
from omni.flux.tree_panel.widget import PanelOutlinerWidget as _PanelOutlinerWidget
from omni.flux.tree_panel.widget.tree.model import Model as _Model
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class ComponentPaneController:
    def __init__(self):
        """Nvidia IngestCraft Components Pane"""

        self._default_attr = {
            "_ui": None,
            "_items": None,
            "_model": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._items = _create_all_items()
        self._model = _Model()
        self._model.set_items(self._items)

        self._ui = _PanelOutlinerWidget(tree_model=self._model, show_title=False, show_menu_burger=False)
        self._ui.set_selection(self._model.get_item_children(None)[0])

    def get_ui_widget(self):
        return self._ui

    def get_model(self):
        return self._model

    def destroy(self):
        _reset_default_attrs(self)

"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from omni.graph.window.core import OmniGraphWindow

from .catalog_model import ComponentNodeTypeCatalogModel
from .graph_model import RemixLogicGraphModel
from .graph_widget import RemixLogicGraphWidget


class RemixLogicGraphWindow(OmniGraphWindow):
    def on_build_window(self):
        """Override the base widget type"""
        self._main_widget = RemixLogicGraphWidget(
            graph_model_class=RemixLogicGraphModel,
            catalog_model=ComponentNodeTypeCatalogModel(),
            filter_fn=self._filter_fn,
        )

        # Hack: Remove the Edit Graph button from the toolbar
        # (reasons: confusing with edit graph option, exposes omnigraph specific preference settings and
        # cleanup variables menu option)
        toolbar_items = self._main_widget._GraphEditorCoreWidget__toolbar_items  # noqa: SLF001
        toolbar_items = [i for i in toolbar_items if i["name"] != "Edit"]
        self._main_widget.set_toolbar_items(toolbar_items)

    def get_graph_widget(self) -> RemixLogicGraphWidget:
        """Get the graph widget"""
        return self._main_widget

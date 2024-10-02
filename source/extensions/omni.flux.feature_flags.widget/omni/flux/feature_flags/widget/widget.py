# noqa PLC0302
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
__all__ = ["FeatureFlagsWidget"]

from functools import partial

from omni import ui
from omni.flux.utils.common import reset_default_attrs

from .tree import FeatureFlagDelegate, FeatureFlagModel


class FeatureFlagsWidget:
    _HORIZONTAL_PADDING = ui.Pixel(8)
    _VERTICAL_PADDING = ui.Pixel(8)

    def __init__(self):
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._model = FeatureFlagModel()
        self._delegate = FeatureFlagDelegate()

        self._tree_view = None

        self._build_ui()

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_model": None,
            "_delegate": None,
            "_tree_view": None,
        }

    def show(self, value: bool):
        """
        A function to show or hide the widget.

        When `value` is `True`, the widget will be shown and the model listeners will be enabled.

        Args:
            value: `True` to show the widget, `False` to hide it.
        """
        self._model.enable_listeners(value)

    def _build_ui(self):
        with ui.HStack(spacing=self._HORIZONTAL_PADDING):
            ui.Spacer(height=0, width=0)
            with ui.VStack(spacing=self._VERTICAL_PADDING):
                ui.Spacer(height=0, width=0)
                ui.Label(
                    "Enable or Disable Feature Flags:",
                    height=0,
                    alignment=ui.Alignment.CENTER,
                    identifier="feature_flag_title",
                )

                with ui.ZStack():
                    ui.Rectangle(name="TreePanelBackground", id="feature_flag_background")
                    with ui.ScrollingFrame(name="PropertiesPaneSection", id="feature_flag_scrolling_frame"):
                        self._tree_view = ui.TreeView(
                            self._model,
                            delegate=self._delegate,
                            root_visible=False,
                            header_visible=True,
                            column_widths=[ui.Pixel(32), ui.Fraction(1)],
                        )

                with ui.HStack(spacing=self._HORIZONTAL_PADDING, height=0):
                    ui.Button(
                        "Enable All",
                        clicked_fn=partial(self._model.set_enabled_all, True),
                        identifier="feature_flag_enable",
                    )
                    ui.Button(
                        "Disable All",
                        clicked_fn=partial(self._model.set_enabled_all, False),
                        identifier="feature_flag_disable",
                    )
                ui.Spacer(height=0, width=0)
            ui.Spacer(height=0, width=0)

    def destroy(self):
        reset_default_attrs(self)

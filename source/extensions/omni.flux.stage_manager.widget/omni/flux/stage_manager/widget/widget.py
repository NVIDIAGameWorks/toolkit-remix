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

from asyncio import ensure_future
from functools import partial

import carb
from omni import ui, usd
from omni.flux.stage_manager.core import StageManagerCore as _StageManagerCore
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.kit import app


class StageManagerWidget:
    def __init__(
        self,
        core: _StageManagerCore | None = None,
        tab_height: int = 32,
        tab_padding: int = 8,
        active_style: str = "WorkspaceBackground",
        inactive_style: str = "TransparentBackground",
        **kwargs,
    ):
        """
        A configurable StageManager widget.

        Args:
            core: The StageManagerCore driving the widget
            tab_height: The height of the tabs built in the widget
            tab_padding: The padding around the text in the tabs
            active_style: The style to use for the currently selected tab.
                          Will also be the widget's interaction plugin background
            inactive_style: The style for unselected tabs
            kwargs: Args to pass to the top-level frame
        """
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._core = core or _StageManagerCore()
        self._tab_height = tab_height
        self._tab_padding = tab_padding
        self._active_style = active_style
        self._inactive_style = inactive_style
        self._kwargs = kwargs

        self._tab_backgrounds = {}
        self._tab_labels = {}

        self._interaction_frame = None
        self._active_interaction = -1

        self.__resize_task = None
        self.__select_tab_task = None

        self.build_ui()

    @property
    def default_attr(self) -> dict[str, None]:
        return {
            "_core": None,
            "_tab_height": None,
            "_tab_padding": None,
            "_active_style": None,
            "_inactive_style": None,
            "_kwargs": None,
            "_tab_backgrounds": None,
            "_tab_labels": None,
            "_interaction_frame": None,
            "_active_interaction": None,
        }

    def build_ui(self):
        with ui.Frame(raster_policy=ui.RasterPolicy.AUTO, **self._kwargs):
            # If no interactions are enabled, display a message
            enabled_interactions = [i for i in self._core.schema.interactions if i.enabled]
            if not enabled_interactions:
                with ui.ZStack():
                    ui.Rectangle(name=self._active_style)
                    ui.Label("No interactions enabled.", name="TreePanelTitleItemTitle", alignment=ui.Alignment.CENTER)
                return

            # Clear the cached dictionaries
            self._tab_backgrounds.clear()
            self._tab_labels.clear()

            # Build the widget
            with ui.ZStack():
                ui.Rectangle(name="TabBackground")
                with ui.VStack():
                    # Stack the tabs horizontally
                    with ui.HStack(height=0):
                        for index, interaction in enumerate(enabled_interactions):
                            with ui.ZStack(
                                width=0,
                                height=ui.Pixel(self._tab_height),
                                tooltip=interaction.tooltip,
                                mouse_released_fn=partial(self.select_tab, index),
                            ):
                                # Cache the tab widgets
                                self._tab_backgrounds[hash(interaction)] = ui.Rectangle(name=self._inactive_style)
                                with ui.HStack():
                                    ui.Spacer(height=0)
                                    self._tab_labels[hash(interaction)] = ui.Label(
                                        interaction.display_name,
                                        width=0,
                                        name="PropertiesWidgetLabel",
                                    )
                                    ui.Spacer(height=0)
                        ui.Spacer(height=0)
                        ui.Label("Experimental Feature", name="ExperimentalFeatureLabel", width=0)
                        ui.Spacer(width=ui.Pixel(16), height=0)

                    with ui.ZStack():
                        ui.Rectangle(name=self._active_style)
                        self._interaction_frame = ui.Frame()

        # Set the first tab as active
        self.select_tab(0)
        self.resize_tabs()

    def resize_tabs(self):
        """
        Fire and forget the `_resize_tabs_deferred` asynchronous method
        """
        if self.__resize_task:
            self.__resize_task.cancel()
        self.__resize_task = ensure_future(self._resize_tabs_deferred())

    def select_tab(self, index: int, *args):
        """
        Fire and forget the `_select_tab_deferred` asynchronous method
        """
        if self.__select_tab_task:
            self.__select_tab_task.cancel()
        self.__select_tab_task = ensure_future(self._select_tab_deferred(index, *args))

    @usd.handle_exception
    async def _resize_tabs_deferred(self):
        """
        Wait 1 frame for the widget to be drawn on screen, then resize all the tabs to be the same size as the largest
        tab rendered.
        """
        await app.get_app().next_update_async()

        if not self._tab_backgrounds:
            return

        widest_label = max(w.computed_width for w in self._tab_labels.values())
        tab_width = (ui.Workspace.get_dpi_scale() * widest_label) + self._tab_padding

        for tab in self._tab_backgrounds.values():
            tab.width = ui.Pixel(tab_width)

    @usd.handle_exception
    async def _select_tab_deferred(self, index: int, *args):
        """
        Set a given tab to be active

        Args:
            index: The interaction index to set active
            *args: 0 -> x
                   1 -> y
                   2 -> button
                   3 -> modifier
        """
        # Only trigger on button == 0 (Left Click) if coming from mouse released event
        if len(args) == 4 and args[2] != 0:
            return

        # Quick return if the active interaction is the selected tab
        if self._active_interaction == index:
            return
        self._active_interaction = index

        # Reset the widget to the original state
        for tab in self._tab_backgrounds.values():
            tab.name = self._inactive_style

        enabled_interactions = [i for i in self._core.schema.interactions if i.enabled]
        if index >= len(enabled_interactions):
            carb.log_warn("An invalid tab was selected.")
            return

        interaction = enabled_interactions[index]

        self._tab_backgrounds[hash(interaction)].name = self._active_style

        self._interaction_frame.clear()
        with self._interaction_frame:
            interaction.build_ui()

        # Make sure the interaction is visible before making it active
        for enabled_interaction in enabled_interactions:
            enabled_interaction.set_active(enabled_interaction == interaction)

    def destroy(self):
        if self.__select_tab_task:
            self.__select_tab_task.cancel()
            self.__select_tab_task = None

        if self.__resize_task:
            self.__resize_task.cancel()
            self.__resize_task = None

        if self._core:
            for interaction in self._core.schema.interactions:
                interaction.set_active(False)

        _reset_default_attrs(self)

"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
from enum import Enum

import omni.appwindow
import omni.kit.app
import omni.ui as ui
import omni.usd
from lightspeed.trex.components_pane.ingestcraft.controller import ComponentPaneController as _ComponentPaneController
from lightspeed.trex.contexts import get_instance as trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.layout.shared import SetupUI as TrexLayout
from lightspeed.trex.properties_pane.ingestcraft.widget import SetupUI as _PropertiesPane
from lightspeed.trex.utils.common import ignore_function_decorator as _ignore_function_decorator
from lightspeed.trex.viewports.shared.widget import SetupUI as ViewportUI


class Pages(Enum):
    WORKSPACE_PAGE = "WorkspacePage"


class SetupUI(TrexLayout):
    WIDTH_COMPONENT_PANEL = 256
    WIDTH_PROPERTY_PANEL = 440

    def __init__(self, ext_id):
        super().__init__(ext_id)
        self._context_name = TrexContexts.INGEST_CRAFT.value
        self._context = trex_contexts_instance().get_context(TrexContexts.INGEST_CRAFT)

    @property
    def default_attr(self):
        default_attr = super().default_attr
        default_attr.update(
            {
                "_frame_workspace": None,
                "_viewport": None,
                "_properties_pane": None,
                "_property_panel_frame": None,
                "_splitter_property_viewport": None,
                "_sub_stage_event": None,
                "_last_property_viewport_splitter_x": None,
                "_components_pane_tree_selection_changed": None,
            }
        )
        return default_attr

    @property
    def button_name(self) -> str:
        return "Ingest"

    @property
    def button_priority(self) -> int:
        return 15

    def _create_layout(self):
        self._frame_workspace = ui.Frame(name=Pages.WORKSPACE_PAGE.value, visible=True)
        with self._frame_workspace:
            with ui.HStack():
                with ui.ZStack(width=0):
                    with ui.HStack():
                        with ui.Frame(width=ui.Pixel(self.WIDTH_COMPONENT_PANEL)):
                            self._components_pane = _ComponentPaneController()
                        self._property_panel_frame = ui.Frame(width=ui.Pixel(self.WIDTH_PROPERTY_PANEL))
                        with self._property_panel_frame:
                            self._properties_pane = _PropertiesPane(self._context_name)
                    self._splitter_property_viewport = ui.Placer(
                        draggable=True,
                        offset_x=ui.Pixel(self.WIDTH_COMPONENT_PANEL + self.WIDTH_PROPERTY_PANEL),
                        drag_axis=ui.Axis.X,
                        width=50,
                        offset_x_changed_fn=self._on_property_viewport_splitter_change,
                    )
                    with self._splitter_property_viewport:
                        with ui.Frame(separate_window=True, width=ui.Pixel(12)):  # to keep the Z depth order
                            with ui.ZStack():
                                ui.Rectangle(name="WorkspaceBackground")
                                with ui.ScrollingFrame(
                                    name="TreePanelBackground",
                                    vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                                    scroll_y_max=0,
                                ):
                                    with ui.VStack():
                                        for _ in range(3):
                                            ui.Image(
                                                "",
                                                name="TreePanelLinesBackground",
                                                fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                                height=ui.Pixel(256),
                                                width=ui.Pixel(256),
                                            )
                                with ui.Frame(separate_window=True):
                                    ui.Rectangle(name="TreePanelBackground")
                with ui.Frame(separate_window=False):
                    self._viewport = ViewportUI(self._context_name)

        # connect the component pane to the property pane
        self._components_pane_tree_selection_changed = (
            self._components_pane.get_ui_widget().subscribe_tree_selection_changed(
                self._on_components_pane_tree_selection_changed
            )
        )
        # make sure the right pane is showing
        self._on_components_pane_tree_selection_changed(self._components_pane.get_ui_widget().get_selection())

    @_ignore_function_decorator(attrs=["_ignore_property_viewport_splitter_change"])
    def _on_property_viewport_splitter_change(self, x):
        if x.value <= self.WIDTH_COMPONENT_PANEL + self.WIDTH_PROPERTY_PANEL:
            self._splitter_property_viewport.offset_x = self.WIDTH_COMPONENT_PANEL + self.WIDTH_PROPERTY_PANEL
        if (
            self._last_property_viewport_splitter_x is not None
            and self._splitter_property_viewport.offset_x.value >= self._last_property_viewport_splitter_x.value
            and self._frame_workspace.computed_width + 8 > omni.appwindow.get_default_app_window().get_width()
        ):
            self._splitter_property_viewport.offset_x = self._last_property_viewport_splitter_x
            return
        asyncio.ensure_future(self.__deferred_on_property_viewport_splitter_change(x))

    @omni.usd.handle_exception
    async def __deferred_on_property_viewport_splitter_change(self, x):
        await omni.kit.app.get_app_interface().next_update_async()
        if x.value < self.WIDTH_COMPONENT_PANEL + self.WIDTH_PROPERTY_PANEL:
            x = ui.Pixel(self.WIDTH_COMPONENT_PANEL + self.WIDTH_PROPERTY_PANEL)
        self._property_panel_frame.width = ui.Pixel(x.value - self.WIDTH_COMPONENT_PANEL)
        self._last_property_viewport_splitter_x = x

    def _on_components_pane_tree_selection_changed(self, selection):
        self._property_panel_frame.visible = bool(selection)
        offset = 0
        if bool(selection) != self._splitter_property_viewport.visible:
            offset = 1 if bool(selection) else -1
        self._splitter_property_viewport.visible = bool(selection)
        # force refresh
        self._splitter_property_viewport.offset_x = self._splitter_property_viewport.offset_x + offset
        if not selection:
            self._properties_pane.show_panel(forced_value=False)
            return
        self._properties_pane.show_panel(title=selection[0].title)

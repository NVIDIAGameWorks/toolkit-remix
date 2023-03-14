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
from lightspeed.trex.contexts import get_instance as trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.layout.shared import SetupUI as TrexLayout
from lightspeed.trex.properties_pane.shared.asset_validation.widget import AssetValidationPane as _AssetValidationPane
from lightspeed.trex.utils.common import ignore_function_decorator as _ignore_function_decorator
from lightspeed.trex.viewports.shared.widget import SetupUI as ViewportUI


class Pages(Enum):
    WORKSPACE_PAGE = "WorkspacePage"


class SetupUI(TrexLayout):
    WIDTH_PROPERTY_PANEL = 496

    def __init__(self, ext_id):
        super().__init__(ext_id)
        self._context_name = TrexContexts.INGEST_CRAFT.value
        self._context = trex_contexts_instance().get_context(TrexContexts.INGEST_CRAFT)
        self._sub_stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="StageChanged"
        )

    def __on_stage_event(self, event):
        if event.type in [
            int(omni.usd.StageEventType.CLOSED),
            int(omni.usd.StageEventType.OPENED),
            int(omni.usd.StageEventType.SAVED),
        ]:
            pass

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
        return "IngestCraft (WIP)"

    @property
    def button_priority(self) -> int:
        return 15

    def _create_layout(self):
        self._frame_workspace = ui.Frame(name=Pages.WORKSPACE_PAGE.value, visible=True)
        with self._frame_workspace:
            with ui.HStack():
                with ui.ZStack(width=0):
                    with ui.ZStack():
                        ui.Rectangle(name="WorkspaceBackground")
                        self._property_panel_frame = ui.Frame(visible=True, width=ui.Pixel(self.WIDTH_PROPERTY_PANEL))
                        with self._property_panel_frame:
                            self._properties_pane = _AssetValidationPane(self._context_name)
                    self._splitter_property_viewport = ui.Placer(
                        draggable=True,
                        offset_x=ui.Pixel(self.WIDTH_PROPERTY_PANEL),
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

    @_ignore_function_decorator(attrs=["_ignore_property_viewport_splitter_change"])
    def _on_property_viewport_splitter_change(self, x):
        if x.value <= self.WIDTH_PROPERTY_PANEL:
            self._splitter_property_viewport.offset_x = self.WIDTH_PROPERTY_PANEL
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
        if x.value < 0:
            x = 0
        self._property_panel_frame.width = ui.Pixel(x)
        self._last_property_viewport_splitter_x = x

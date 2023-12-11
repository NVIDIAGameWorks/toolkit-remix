"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import abc
import asyncio
import functools
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

import carb.events
import omni.appwindow
import omni.kit.app
import omni.ui as ui
import omni.usd
from lightspeed.trex.contexts import get_instance as trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.layout.shared.base import SetupUI as _BaseLayout
from lightspeed.trex.stage_view.shared.widget import SetupUI as _StageViewWidget
from lightspeed.trex.viewports.shared.widget import create_instance as _create_viewport_instance
from omni.flux.tabbed.widget import SetupUI as _TabbedFrame
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.flux.validator.mass.queue.widget import Actions as _MassQueueTreeActions
from omni.flux.validator.mass.widget import ValidatorMassWidget as _ValidatorMassWidget

if TYPE_CHECKING:
    from omni.flux.tabbed.widget.tab_tree.model import Item as _TabbedItem
    from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
    from omni.flux.validator.mass.core import Item as _MassCoreItem


class Pages(Enum):
    WORKSPACE_PAGE = "WorkspacePage"


class SetupUI(_BaseLayout):
    FRACTION_WIDTH_MASS_INGEST = 70
    WIDTH_PROPERTY_WIDGET = 400
    MIN_WIDTH_MASS_INGEST = 400
    MIN_WIDTH_VIEWPORT = 200
    WIDTH_TAB_LABEL_PROPERTY = 40

    _VALIDATION_TAB_NAME = "Validation"
    _STAGE_VIEW_TAB_NAME = "Stage View"

    def __init__(self, ext_id, schema_paths: List[str], context: TrexContexts = ""):
        super().__init__(ext_id)

        self._schema_paths = schema_paths
        self._context_name = context.value
        self._context = trex_contexts_instance().get_context(context)

        self._sub_mass_cores_started = []
        self._sub_mass_cores_finished = []

        self._mass_cores_are_running = {}

        self.__last_splitter_property_viewport_width = None
        self.__last_show_viewport_item = None
        self.__frame_property_widget_visibility = False
        self.__mass_frame_widget_visibility = True

        appwindow_stream = omni.appwindow.get_default_app_window().get_window_resize_event_stream()
        self._subscription_app_window_size_changed = appwindow_stream.create_subscription_to_pop(
            self._on_app_window_size_changed, name="On app window resized", order=0
        )

    @property
    def default_attr(self):
        default_attr = super().default_attr
        default_attr.update(
            {
                "_context_name": None,
                "_context": None,
                "_sub_mass_cores_started": None,
                "_sub_mass_cores_finished": None,
                "_mass_cores_are_running": None,
                "_subscription_app_window_size_changed": None,
                "_frame_workspace": None,
                "_mass_ingest_stack": None,
                "_mass_ingest_widget_frame": None,
                "_mass_ingest_widget": None,
                "_sub_mass_core_added": None,
                "_sub_mass_queue_action_pressed": None,
                "_sub_mass_tab_toggle": None,
                "_splitter_property_viewport": None,
                "_splitter_viewport_highlight": None,
                "_frame_property_widget": None,
                "_properties_panel": None,
                "_sub_tab_toggle_property": None,
                "_frame_viewport": None,
                "_viewport": None,
                "_stage_view_widget": None,
            }
        )
        return default_attr

    @property
    @abc.abstractmethod
    def button_name(self) -> str:
        return ""

    @property
    @abc.abstractmethod
    def button_priority(self) -> int:
        return 0

    def _create_layout(self):
        self._frame_workspace = ui.Frame(name=Pages.WORKSPACE_PAGE.value, visible=True)
        with self._frame_workspace:
            with ui.HStack():
                # self._mass_ingest_stack = ui.ZStack(width=ui.Percent(self.PERCENT_WIDTH_MASS_INGEST))
                self._mass_ingest_stack = ui.ZStack(width=ui.Fraction(self.FRACTION_WIDTH_MASS_INGEST))
                with self._mass_ingest_stack:
                    with ui.HStack():
                        self._mass_ingest_widget_frame = ui.Frame()
                        with self._mass_ingest_widget_frame:
                            self._mass_ingest_widget = _ValidatorMassWidget(
                                schema_paths=self._schema_paths,
                                use_global_style=True,
                            )
                            self._sub_mass_core_added = self._mass_ingest_widget.core.subscribe_core_added(
                                self._on_mass_ingest_core_added
                            )
                            self._sub_mass_queue_action_pressed = (
                                self._mass_ingest_widget.subscribe_mass_queue_action_pressed(
                                    self._on_mass_queue_action_pressed
                                )
                            )
                            self._sub_mass_tab_toggle = self._mass_ingest_widget.subscribe_tab_toggled(
                                self._on_tab_toggle_mass
                            )
                        ui.Spacer(width=ui.Pixel(12), height=0)

                    self._splitter_property_viewport = ui.Placer(
                        draggable=True,
                        drag_axis=ui.Axis.X,
                        offset_x_changed_fn=self._on_property_viewport_splitter_change,
                    )
                    asyncio.ensure_future(self.__init_splitter_property_viewport_offset())
                    with self._splitter_property_viewport:
                        with ui.ZStack(width=ui.Pixel(12), opaque_for_mouse_events=True):
                            ui.Rectangle(name="WorkspaceBackground")
                            with ui.VStack():
                                for _ in range(3):
                                    ui.Image(
                                        "",
                                        name="TreePanelLinesBackground",
                                        fill_policy=ui.FillPolicy.PRESERVE_ASPECT_CROP,
                                        width=ui.Pixel(12),
                                    )

                            self._splitter_viewport_highlight = ui.Rectangle(name="TreePanelBackgroundSplitter")
                self._frame_property_widget = ui.Frame(width=ui.Fraction(100 - self.FRACTION_WIDTH_MASS_INGEST))
                with self._frame_property_widget:
                    self._properties_panel = _TabbedFrame(
                        horizontal=False,
                        size_tab_label=(ui.Pixel(self.WIDTH_TAB_LABEL_PROPERTY), ui.Pixel(100)),
                        disable_tab_toggle=False,
                        hidden_by_default=True,
                    )
                    self._sub_tab_toggle_property = self._properties_panel.subscribe_tab_toggled(
                        self._on_tab_toggle_property
                    )
                self._frame_viewport = ui.Frame(separate_window=False, visible=False, width=ui.Fraction(1))
                with self._frame_viewport:
                    self._viewport = _create_viewport_instance(self._context_name)

        self._properties_panel.add([self._VALIDATION_TAB_NAME, self._STAGE_VIEW_TAB_NAME])
        self._mass_ingest_widget.set_validator_widget_root_frame(
            self._properties_panel.get_frame(self._VALIDATION_TAB_NAME)
        )

        with self._properties_panel.get_frame(self._STAGE_VIEW_TAB_NAME):
            with ui.HStack():
                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(8))
                    with ui.ZStack():
                        ui.Rectangle(name="BackgroundWithBorder")
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            with ui.HStack():
                                ui.Spacer(width=ui.Pixel(8))
                                self._stage_view_widget = _StageViewWidget(usd_context_name=self._context_name)
                                ui.Spacer(width=ui.Pixel(8))
                            ui.Spacer(height=ui.Pixel(8))
                    ui.Spacer(height=ui.Pixel(8))
                ui.Spacer(width=ui.Pixel(8))

        self._properties_panel.selection = [self._VALIDATION_TAB_NAME]

        # by default, we don't want to show the validation/stage view panel
        self._properties_panel.force_toggle(self._properties_panel.selection[0], False)
        asyncio.ensure_future(self.__toggle_mass_ingest())

    @omni.usd.handle_exception
    async def __toggle_mass_ingest(self):
        time_out = 20
        i = 0
        while not self._mass_ingest_widget.tab_selection:
            await omni.kit.app.get_app().next_update_async()
            i += 1
            if i == time_out:
                return
        self._mass_ingest_widget.force_toggle(self._mass_ingest_widget.tab_selection[0], True)

    def _on_tab_toggle_property(self, item: "_TabbedItem", visible: bool):
        # if mass + property + not viewport is toggle to false, we skip
        self.__frame_property_widget_visibility = visible
        if not visible and not self._splitter_viewport_highlight.visible and not self._frame_viewport.visible:
            return
        if not self._frame_viewport.visible:
            self._splitter_viewport_highlight.enabled = visible
            self._splitter_property_viewport.draggable = visible
        self.__set_frame_property_widget_width()

    def _on_tab_toggle_mass(self, item: "_TabbedItem", visible: bool):
        self.__mass_frame_widget_visibility = visible
        self._splitter_viewport_highlight.visible = visible
        value = visible
        if self.__frame_property_widget_visibility or (self._frame_viewport.visible and visible):
            value = True
        if not self._frame_viewport.visible and not self.__frame_property_widget_visibility:
            value = False
        self._splitter_viewport_highlight.enabled = value
        if visible:
            asyncio.ensure_future(self.__deferred_mass_computed_content_size_changed())
        else:
            self._splitter_property_viewport.offset_x = 0
            if not self._frame_viewport.visible and not self.__frame_property_widget_visibility:
                self._frame_property_widget.width = ui.Fraction(100 - self.FRACTION_WIDTH_MASS_INGEST)

    @_ignore_function_decorator(attrs=["_ignore_set_frame_property_widget_width"])
    def __set_frame_property_widget_width(self):
        if self._frame_viewport is None:
            return
        if self._frame_viewport.visible:
            if not self.__frame_property_widget_visibility:
                value = 50
                self._frame_property_widget.width = ui.Fraction(1)
                self._frame_viewport.width = ui.Fraction(value - 1)
                if self.__mass_frame_widget_visibility:
                    self._mass_ingest_stack.width = ui.Fraction(value)
                    self._splitter_property_viewport.offset_x = self._frame_workspace.computed_width / 100 * value
            else:
                self._frame_viewport.width = ui.Fraction(33)
                self._frame_property_widget.width = ui.Pixel(self.WIDTH_PROPERTY_WIDGET)
                if self.__mass_frame_widget_visibility:
                    self._mass_ingest_stack.width = ui.Fraction(40)
                    self._splitter_property_viewport.offset_x = self._frame_workspace.computed_width / 100 * 40
        else:
            if not self.__frame_property_widget_visibility:
                self._frame_property_widget.width = ui.Percent(1)
                self._mass_ingest_stack.width = ui.Fraction(self.FRACTION_WIDTH_MASS_INGEST)
                app_window = omni.appwindow.get_default_app_window()
                size = app_window.get_size()
                if self._frame_workspace.computed_width != 0:
                    self._splitter_property_viewport.offset_x = size[0] - 16 - self.WIDTH_TAB_LABEL_PROPERTY
            elif self.__mass_frame_widget_visibility:
                self._frame_property_widget.width = ui.Fraction(100 - self.FRACTION_WIDTH_MASS_INGEST)
                self._splitter_property_viewport.offset_x = (
                    self._frame_workspace.computed_width / 100 * self.FRACTION_WIDTH_MASS_INGEST
                )

    def _on_mass_queue_action_pressed(self, item: "_MassCoreItem", action_name: str, **kwargs):
        if action_name == "show_in_viewport":
            if self.__last_show_viewport_item == item or self.__last_show_viewport_item is None:
                value = not self._frame_viewport.visible
                self._frame_viewport.visible = value
                self._splitter_viewport_highlight.enabled = any(
                    [self.__frame_property_widget_visibility, self._frame_viewport.visible]
                )
                self._splitter_property_viewport.draggable = any(
                    [self.__frame_property_widget_visibility, self._frame_viewport.visible]
                )
                self.__set_frame_property_widget_width()
            self.__last_show_viewport_item = item
        elif action_name == _MassQueueTreeActions.SHOW_VALIDATION.value:
            self._properties_panel.selection = [self._VALIDATION_TAB_NAME]
            self._properties_panel.force_toggle(
                self._properties_panel.selection[0], kwargs.get("show_validation_checked", False)
            )

    def _on_mass_ingest_core_added(self, core: "_ManagerCore"):
        self._sub_mass_cores_started.append(
            core.subscribe_run_started(functools.partial(self._on_mass_cores_started, core))
        )
        self._sub_mass_cores_finished.append(
            core.subscribe_run_finished(functools.partial(self._on_mass_cores_finished, core))
        )

    def _on_mass_cores_started(self, core: "_ManagerCore"):
        if self._viewport:
            self._viewport.set_active(False)
        self._stage_view_widget.enable_context_event(False)
        self._mass_cores_are_running[id(core)] = True

    def _on_mass_cores_finished(self, core: "_ManagerCore", _finished: bool, message: Optional[str] = None):
        self._mass_cores_are_running[id(core)] = False
        update_viewport = not any(self._mass_cores_are_running.values())
        if update_viewport:
            if self._viewport:
                self._viewport.set_active(True)
            self._stage_view_widget.enable_context_event(True)

    def _on_app_window_size_changed(self, event: carb.events.IEvent):
        self.__set_frame_property_widget_width()

    @omni.usd.handle_exception
    async def __init_splitter_property_viewport_offset(self):
        for _ in range(3):
            await omni.kit.app.get_app_interface().next_update_async()
        if self._mass_ingest_widget_frame is None:
            return
        self._splitter_property_viewport.offset_x = self._mass_ingest_widget_frame.computed_width

    @omni.usd.handle_exception
    async def __deferred_mass_computed_content_size_changed(self):
        await omni.kit.app.get_app_interface().next_update_async()
        if not self._frame_property_widget:
            return
        if not self.__frame_property_widget_visibility:
            self._frame_property_widget.width = ui.Percent(1)
            if not self._frame_viewport.visible:
                self._mass_ingest_stack.width = ui.Fraction(self.FRACTION_WIDTH_MASS_INGEST)
                self._splitter_property_viewport.offset_x = (
                    self._frame_workspace.computed_width - self._frame_property_widget.computed_width
                )
            else:
                self._splitter_property_viewport.offset_x = self._frame_workspace.computed_width / 2
        else:
            if self.__last_splitter_property_viewport_width is not None:
                self._splitter_property_viewport.offset_x = self.__last_splitter_property_viewport_width
            else:
                self._splitter_property_viewport.offset_x = (
                    self._frame_workspace.computed_width / 100 * self.FRACTION_WIDTH_MASS_INGEST
                )
        self.__last_splitter_property_viewport_width = self._splitter_property_viewport.offset_x.value

    @_ignore_function_decorator(attrs=["_ignore_property_viewport_splitter_change"])
    def _on_property_viewport_splitter_change(self, x):
        if x.value < self._mass_ingest_stack.computed_width:
            self._mass_ingest_stack.width = ui.Percent(1)
        asyncio.ensure_future(self.__deferred_on_property_viewport_splitter_change(x))

    @omni.usd.handle_exception
    async def __deferred_on_property_viewport_splitter_change(self, x):
        await omni.kit.app.get_app_interface().next_update_async()
        if self._mass_ingest_widget_frame is None:
            return

        if (
            x.value < self._mass_ingest_widget_frame.computed_width
            or self._mass_ingest_widget_frame.computed_width == self._mass_ingest_widget.SCHEMA_TREE_WIDTH
        ):
            self._splitter_property_viewport.offset_x = self._mass_ingest_widget_frame.computed_width
        elif (
            x.value > self._frame_workspace.computed_width / 100 * self.FRACTION_WIDTH_MASS_INGEST
            and self.__frame_property_widget_visibility
        ):
            self._splitter_property_viewport.offset_x = (
                self._frame_workspace.computed_width / 100 * self.FRACTION_WIDTH_MASS_INGEST
            )
        if self._splitter_viewport_highlight.visible:
            self.__last_splitter_property_viewport_width = self._splitter_property_viewport.offset_x.value

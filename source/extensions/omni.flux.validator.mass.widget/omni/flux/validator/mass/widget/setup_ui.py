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

import asyncio
import traceback
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

import carb
import omni.ui as ui
import omni.usd
from omni.flux.info_icon.widget import InfoIconWidget as _InfoIconWidget
from omni.flux.tabbed.widget import SetupUI as _TabbedFrame
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.validator.mass.core import Executors as _MassExecutors
from omni.flux.validator.mass.core import ManagerMassCore as _ManagerMassCore
from omni.flux.validator.mass.core.executors import CurrentProcessExecutor as _CurrentProcessExecutor
from omni.flux.validator.mass.core.executors import ExternalProcessExecutor as _ExternalProcessExecutor
from omni.flux.validator.mass.queue.widget import Actions as _MassQueueTreeActions
from omni.flux.validator.mass.queue.widget import MassQueueTreeWidget as _MassQueueTreeWidget
from omni.flux.validator.mass.queue.widget.tree.delegate import Delegate as _Delegate
from omni.flux.validator.mass.queue.widget.tree.model import Model as _Model
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager
from pydantic import ValidationError

if TYPE_CHECKING:
    from omni.flux.tabbed.widget.tab_tree.model import Item as _TabbedItem
    from omni.flux.validator.manager.core import ManagerCore as _ManagerCore
    from omni.flux.validator.mass.core import Item as _Item
    from omni.flux.validator.mass.queue.widget import Item as _MassQueueItem
    from omni.flux.validator.mass.queue.widget import Model as _MassQueueModel


_SETTINGS_DISABLE_NOTIFICATIONS = "/exts/omni.kit.notification_manager/disable_notifications"


@contextmanager
def disable_viewport_notifications():
    """
    Disable viewport notifications temporarily
    """
    carb.settings.get_settings().set(_SETTINGS_DISABLE_NOTIFICATIONS, True)
    try:
        yield
    finally:
        carb.settings.get_settings().set(_SETTINGS_DISABLE_NOTIFICATIONS, False)


class ValidatorMassWidget:
    def __init__(
        self,
        schema_paths: List[str] = None,
        use_global_style: bool = False,
        style: Dict[str, Dict[str, Any]] = None,
        validator_widget_root_frame: ui.Widget = None,
        width: ui.Length = None,
    ):
        """
        Create a mass validator widget

        Args:
        Args:
            schema_paths: list of json file to use as schema
            use_global_style: use the global style or the local one
            style: UI style to use
            validator_widget_root_frame: frame to use if we want to show the validation widget of a job
        """

        self._default_attr = {
            "_manager_cores": None,
            "_style": None,
            "_schema_tree_view": None,
            "_sub_on_item_changed": None,
            "_sub_on_mass_cook_template": None,
            "_pages": None,
            "_mass_queue_widget": None,
            "_sub_mass_queue_items_changed": None,
            "_all_validator_widgets": None,
            "_sub_show_validation_widgets": None,
            "_validator_widget_root_frame": None,
            "_current_validation_widget_item": None,
            "_root_main_frame": None,
            "_sub_item_mouse_pressed": None,
            "_schema_tree_view_selection_changed": None,
            "_schema_tree_view_tab_toggled": None,
            "_mass_queue_frame": None,
            "_executors_cb": None,
            "_executor_container": None,
            "_queue_tree_model": None,
            "_queue_tree_delegate": None,
            "_current_process_executor": None,
            "_external_process_executor": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._use_global_style = use_global_style
        self._current_validation_widget_item = None
        self._validator_widget_root_frame = validator_widget_root_frame
        self._all_validator_widgets = {}
        self._sub_show_validation_widgets = {}
        self._mass_queue_frame = {}
        self._core = _ManagerMassCore(schema_paths=schema_paths)
        self._sub_on_item_changed = self._core.schema_model.subscribe_item_changed_fn(self._on_item_changed)
        self._sub_on_mass_cook_template = self._core.schema_model.subscribe_mass_cook_template(
            self._on_mass_cook_template
        )

        self._style = None
        self._pages = {}
        if not use_global_style:
            from .style import style as _local_style  # or doc will not build

            self._style = style or _local_style
        else:
            self._style = ui.Style.get_instance().default
        self.__root_frame = ui.Frame(style=self._style)
        if width is not None:
            self.__root_frame.width = width

        self._queue_tree_model = _Model()
        self._queue_tree_delegate = _Delegate(use_global_style=self._use_global_style, style=self._style)

        self._current_process_executor = _CurrentProcessExecutor()
        self._external_process_executor = _ExternalProcessExecutor()

        self.__on_mass_queue_action_pressed = _Event()
        self.__on_schema_tab_toggled = _Event()
        self.__on_schema_selection_changed = _Event()

        self._create_ui()

    def subscribe_mass_queue_action_pressed(self, callback: Callable[["_Item", str], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_mass_queue_action_pressed, callback)

    def _selection_changed(self, item: "_Item"):
        """Call the event object that has the list of functions"""
        self.__on_schema_selection_changed(item)

    def subscribe_selection_changed(self, function: Callable[["_Item"], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the selection of the tree change
        """
        return _EventSubscription(self.__on_schema_selection_changed, function)

    def _tab_toggled(self, item: "_TabbedItem", visible: bool):
        """Call the event object that has the list of functions"""
        # fraction will let the widget to not oversize to the right
        self.__root_frame.width = ui.Fraction(1) if visible else ui.Percent(0)
        self.__on_schema_tab_toggled(item, visible)

    def subscribe_tab_toggled(self, function: Callable[["_Item", bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the selection of the tree change
        """
        return _EventSubscription(self.__on_schema_tab_toggled, function)

    def set_validator_widget_root_frame(self, value: ui.Frame):
        """
        Set the frame to use to show the validation widget of a job

        Args:
            value: the frame to use
        """
        if self._validator_widget_root_frame:
            self._validator_widget_root_frame.clear()
        self._validator_widget_root_frame = value

    @property
    def core(self):
        """Mass Validation core"""
        return self._core

    def _on_item_changed(self, items):
        # we pre-build the ui of ZStack
        asyncio.ensure_future(self._build_mass_ui_plugin())

    def force_toggle(self, item: "_Item", value: bool):
        """Toggle or not a tab"""
        self._schema_tree_view.force_toggle(item, value)

    @property
    def tab_selection(self):
        """Current selected tab(s)"""
        return self._schema_tree_view.selection

    def _on_schema_tab_toggled(self, item: "_TabbedItem", visible: bool):
        self._tab_toggled(item, visible)

    def _on_schema_selection_changed(self, _item: "_TabbedItem"):
        for item, (page, _was_built, frame_build) in self._pages.items():
            value = (
                item.title == self._schema_tree_view.selection[0].title if self._schema_tree_view.selection else None
            )
            page.visible = value
            frame_build.enabled = value
            if value:
                with self._mass_queue_frame[item]:
                    self._create_work_ui()

        self._selection_changed(self._schema_tree_view.selection[0])

    @omni.usd.handle_exception
    async def _build_mass_ui_plugin(self):
        # build the UI of the context plugin
        self._pages = {}
        self._mass_queue_frame = {}
        items = self._core.schema_model.get_item_children(None)
        for i, item in enumerate(items):
            with self._schema_tree_view.get_frame(item.title):
                frame = ui.Frame(visible=i == 0)
                with frame:
                    with ui.VStack():
                        ui.Spacer(height=ui.Pixel(16))
                        with ui.HStack(height=0):
                            with ui.ZStack():
                                ui.Rectangle(name="BackgroundWithBorder")
                                with ui.VStack():
                                    ui.Spacer(height=ui.Pixel(8))
                                    with ui.HStack():
                                        ui.Spacer(width=ui.Pixel(8), height=0)
                                        frame_build = ui.Frame(height=0)
                                        with frame_build:
                                            was_built = await item.build_ui()
                                        ui.Spacer(width=ui.Pixel(8), height=0)
                                    ui.Spacer(height=ui.Pixel(8))
                            ui.Spacer(width=ui.Pixel(8), height=0)

                        self._mass_queue_frame[item] = ui.Frame()

                self._pages[item] = (frame, was_built, frame_build)

        # here or we will have a style/refresh bug. Do not move above.
        if items and self._mass_queue_widget is None:
            with self._mass_queue_frame[items[0]]:
                self._create_work_ui()

    def add_and_run_all(self):
        """Add and run the Mass Validation"""
        asyncio.ensure_future(self._add_and_run_all())

    def __show_invalid_dialog(self):
        message = "Some inputs are not valid. Please delete/fix them before continuing"
        PromptManager.post_simple_prompt("An Error Occurred", message, ok_button_info=PromptButtonInfo("Okay", None))

    @omni.usd.handle_exception
    async def _add_and_run_all(self):
        with disable_viewport_notifications():
            for item, (page, _, _) in self._pages.items():
                # work only on the visible item
                if page.visible:
                    if not all(item.model.is_ready_to_run().values()):
                        self.__show_invalid_dialog()
                        return
                    try:
                        result: List[Dict[Any, Any]] = await item.cook_template_no_exception()
                    except ValidationError as e:
                        carb.log_error("Exception when async cook_template_no_exception()")
                        carb.log_error(f"{e}")
                        carb.log_error(f"{traceback.format_exc()}")
                        self.__show_invalid_dialog()
                        return
                    result_run: List[Tuple["_ManagerCore", asyncio.Future]] = await self._core.create_tasks(
                        self._executors_cb.model.get_item_value_model().get_value_as_int(),
                        result,
                        custom_executors=(self._current_process_executor, self._external_process_executor),
                        standalone=False,
                        queue_id=self._mass_queue_widget.get_queue_id(),
                    )
                    for core, _task in result_run:
                        self._mass_queue_widget.add_items([core])
                    break

    def _on_mass_queue_action_pressed(self, item: "_Item", action_name: str, **kwargs):
        if action_name == _MassQueueTreeActions.SHOW_VALIDATION.value:
            if self._current_validation_widget_item is not None and id(self._current_validation_widget_item) == id(
                item
            ):
                # toggle
                frame_visibility = bool(kwargs["force_show_frame"])
                self._current_validation_widget_item = None
            else:
                frame_visibility = True
                self._current_validation_widget_item = item

            self._validator_widget_frame.clear()
            if self._validator_widget_root_frame:  # if we have a custom root frame, we use it
                self._validator_widget_root_frame.clear()
                with self._validator_widget_root_frame:
                    # re root the frame
                    self._validator_widget_frame = ui.Frame()
                    frame = self._validator_widget_frame
            else:
                frame = self._validator_widget_frame
            frame.visible = frame_visibility
            with frame:
                with ui.ZStack():
                    ui.Rectangle(name="WorkspaceBackground")
                    with ui.ScrollingFrame(
                        name="PropertiesPaneSection",
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                    ):
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            with ui.HStack():
                                ui.Spacer(width=ui.Pixel(8))
                                item.build_validation_widget_ui(use_global_style=True)
                            ui.Spacer(height=ui.Pixel(8))
        self.__on_mass_queue_action_pressed(item, action_name, **kwargs)

    def _on_mass_queue_items_changed(self, model: "_MassQueueModel", items: List["_MassQueueItem"]):
        all_items = model.get_item_children(None)
        for item in all_items:
            if id(item) in self._sub_show_validation_widgets:
                continue
            self._sub_show_validation_widgets[id(item)] = item.subscribe_mass_queue_action_pressed(
                self._on_mass_queue_action_pressed
            )

    def _on_mass_cook_template(self, success: bool, message: str, _: Any):
        if success:
            return
        PromptManager.post_simple_prompt("An Error Occurred", message, ok_button_info=PromptButtonInfo("Okay", None))

    def _create_ui(self):
        with self.__root_frame:
            with ui.HStack():
                with ui.ZStack():
                    ui.Rectangle(name="WorkspaceBackground")
                    with ui.ScrollingFrame(
                        name="TreePanelBackground",
                        vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
                        scroll_y_max=0,
                    ):
                        with ui.VStack():
                            for _ in range(5):
                                ui.Image(
                                    "",
                                    name="TreePanelLinesBackground",
                                    fill_policy=ui.FillPolicy.PRESERVE_ASPECT_FIT,
                                    height=ui.Pixel(256),
                                    width=ui.Pixel(256),
                                )
                    with ui.Frame(separate_window=True):  # to keep the Z depth order
                        with ui.HStack():
                            with ui.ZStack(content_clipping=True):
                                ui.Rectangle(name="DarkBackgroound")

                                self._schema_tree_view = _TabbedFrame(
                                    horizontal=False,
                                    size_tab_label=(ui.Percent(100), ui.Pixel(100)),
                                    disable_tab_toggle=False,
                                )
                                self._schema_tree_view.add(
                                    [item.title for item in self._core.schema_model.get_item_children(None)]
                                )
                                self._schema_tree_view_tab_toggled = self._schema_tree_view.subscribe_tab_toggled(
                                    self._on_schema_tab_toggled
                                )
                                self._schema_tree_view_selection_changed = (
                                    self._schema_tree_view.subscribe_selection_changed(
                                        self._on_schema_selection_changed
                                    )
                                )
        self._on_item_changed([])

    def _create_work_ui(self):
        self._root_main_frame = ui.Frame(style=self._style)
        with self._root_main_frame:
            with ui.HStack():
                with ui.ZStack():
                    ui.Rectangle(name="WorkspaceBackground")
                    with ui.HStack():
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            with ui.HStack(height=ui.Pixel(24)):
                                with ui.HStack(width=ui.Percent(50)):
                                    ui.Spacer()
                                    ui.Button(
                                        "Add to Queue",
                                        clicked_fn=self.add_and_run_all,
                                        identifier="AddToQueue",
                                        width=ui.Pixel(140),
                                    )
                                with ui.HStack(width=ui.Percent(50), spacing=ui.Pixel(8)):
                                    ui.Spacer()
                                    ui.Label("Execute In: ", width=0)
                                    self._executors_cb = ui.ComboBox(
                                        1,
                                        *_MassExecutors.get_names(),
                                        width=ui.Pixel(150),
                                        identifier="executors_combo_box",
                                    )
                                    self._executors_cb.model.add_item_changed_fn(self._update_executor_container)

                                    self._executor_container = ui.HStack(width=0)
                                    with self._executor_container:
                                        ui.Spacer()
                                        self._external_process_executor.create_ui()
                                        ui.Spacer()

                                    with ui.VStack(width=0):
                                        ui.Spacer()
                                        self._normals_type_info_icon = _InfoIconWidget(
                                            message=(
                                                "Specify how the ingestion process should run.\n"
                                                "It is not recommended to change this setting unless "
                                                "you are an expert user and understand its effects.\n\n"
                                                "Options:\n"
                                                "- External Process: Run the ingestion in external process(es) "
                                                "(recommended for running multiple ingestions at once)\n"
                                                "- Current Process: Run the ingestion asynchronously on the main thread"
                                            )
                                        )
                                        ui.Spacer()
                                    ui.Spacer(width=ui.Pixel(0))
                            ui.Spacer(height=ui.Pixel(8))
                            with ui.ZStack():
                                ui.Rectangle(name="BackgroundWithBorder")
                                with ui.VStack():
                                    ui.Spacer(height=ui.Pixel(8))
                                    with ui.HStack():
                                        ui.Spacer(width=ui.Pixel(8))
                                        with ui.VStack():
                                            ui.Label("Queue", name="PropertiesPaneSectionTitle", height=0)
                                            ui.Spacer(height=ui.Pixel(8))
                                            self._mass_queue_widget = _MassQueueTreeWidget(
                                                tree_model=self._queue_tree_model,
                                                tree_delegate=self._queue_tree_delegate,
                                                use_global_style=self._use_global_style,
                                                style=self._style,
                                            )
                                            self._sub_mass_queue_items_changed = (
                                                self._mass_queue_widget.subscribe_item_changed(
                                                    self._on_mass_queue_items_changed
                                                )
                                            )
                                        ui.Spacer(width=ui.Pixel(8))
                                    ui.Spacer(height=ui.Pixel(8))
                            ui.Spacer(height=ui.Pixel(8))
                        ui.Spacer(width=ui.Pixel(8))

                self._validator_widget_frame = ui.Frame(visible=False, identifier="ValidationWidgetFrame")

    def _update_executor_container(self, *_):
        with self._executor_container:
            # For the Process executor, show the processor count dropdown; Show nothing for the current process executor
            current_executor = self._executors_cb.model.get_item_value_model().get_value_as_int()
            if current_executor == 1:  # external executor
                self._external_process_executor.create_ui()
            else:  # current executor (async)
                self._executor_container.clear()

    def show(self, value: bool):
        for plugin in self._core.schema_model.get_item_children(None):
            plugin.show(value)
        if self._mass_queue_widget:
            self._mass_queue_widget.show(value)

    def destroy(self):
        self.__root_frame.clear()
        self.__root_frame = None
        _reset_default_attrs(self)

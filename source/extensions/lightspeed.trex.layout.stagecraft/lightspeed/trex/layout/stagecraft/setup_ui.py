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
import os
import subprocess
import typing
from enum import Enum
from functools import partial
from pathlib import Path

import carb.events
import omni.appwindow
import omni.kit.app
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import (
    READ_USD_FILE_EXTENSIONS_OPTIONS,
    REMIX_LAUNCHER_PATH,
    REMIX_SAMPLE_PATH,
    GlobalEventNames,
)
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.trex.components_pane.stagecraft.controller import SetupUI as ComponentsPaneSetupUI
from lightspeed.trex.components_pane.stagecraft.models import EnumItems as ComponentsEnumItems
from lightspeed.trex.contexts import get_instance as trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.home.widget import HomePageWidget as _HomePageWidget
from lightspeed.trex.layout.shared.base import SetupUI as TrexLayout
from lightspeed.trex.menu.workfile import get_instance as get_burger_menu_instance
from lightspeed.trex.properties_pane.stagecraft.widget import SetupUI as PropertyPanelUI
from lightspeed.trex.recent_projects.core import RecentProjectsCore as _RecentProjectsCore
from lightspeed.trex.stage_manager.widget import StageManagerWidget as _StageManagerWidget
from lightspeed.trex.utils.common.dialog_utils import delete_dialogs as _delete_dialogs
from lightspeed.trex.utils.common.file_utils import (
    is_usd_file_path_valid_for_filepicker as _is_usd_file_path_valid_for_filepicker,
)
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from lightspeed.trex.viewports.shared.widget import create_instance as _create_viewport_instance
from omni.flux.feature_flags.core import FeatureFlagsCore as _FeatureFlagsCore
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.widget.file_pickers.file_picker import destroy_file_picker as _destroy_file_picker
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker
from omni.flux.utils.widget.hover import hover_helper as _hover_helper

if typing.TYPE_CHECKING:
    from pxr import Usd


class Pages(Enum):
    HOME_PAGE = "HomePage"
    WORKSPACE_PAGE = "WorkspacePage"


class SetupUI(TrexLayout):
    """Stagecraft Layout"""

    HEIGHT_STAGE_MANAGER_SPLITTER = 12
    HEIGHT_STAGE_MANAGER_PANEL = 400
    MIN_HEIGHT_STAGE_MANAGER_PANEL = 100
    WIDTH_COMPONENT_PANEL = 256
    WIDTH_PROPERTY_PANEL = 600
    MIN_WIDTH_PROPERTY_PANEL = 375

    def __init__(self, ext_id):
        super().__init__(ext_id)

        self._feature_flags_core = _FeatureFlagsCore()

        self._all_frames = []
        self.__enable_items_task = None
        self.__update_recent_items_task = None
        appwindow_stream = omni.appwindow.get_default_app_window().get_window_resize_event_stream()
        self._subcription_app_window_size_changed = appwindow_stream.create_subscription_to_pop(
            self._on_app_window_size_changed, name="On app window resized", order=0
        )

        self._context_name = TrexContexts.STAGE_CRAFT.value
        self._context = trex_contexts_instance().get_usd_context(TrexContexts.STAGE_CRAFT)
        self._layer_manager = _LayerManagerCore(context_name=self._context_name)
        self._sub_stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="StageChanged"
        )

        self._recent_saved_file = _RecentProjectsCore()

        self.__current_page = None

        self._header_refreshed_task = self._header_navigator.subscribe_header_refreshed(self._on_header_refreshed)
        self._on_new_work_file_clicked = _Event()
        self._on_open_work_file_clicked = _Event()
        self._on_load_work_file = _Event()
        self._on_resume_work_file_clicked = _Event()
        self.__on_import_capture_layer = _Event()

        # TODO Feature OM-45888 - File Picker will appear behind the wizard modal
        event_manager = _get_event_manager_instance()
        event_manager.register_global_custom_event(GlobalEventNames.PAGE_CHANGED.value)
        self._page_changed_sub = event_manager.subscribe_global_custom_event(
            GlobalEventNames.PAGE_CHANGED.value, _destroy_file_picker
        )
        self._page_changed_dialog_sub = event_manager.subscribe_global_custom_event(
            GlobalEventNames.PAGE_CHANGED.value, _delete_dialogs
        )

    def enable_welcome_resume_item(self) -> bool:
        current_stage = self._context.get_stage()
        if current_stage:
            # enable when a stage from disk is opened
            if not bool(current_stage.GetRootLayer().anonymous):
                return True
            # check if the custom data is here
            root_layer = current_stage.GetRootLayer()
            if root_layer:
                return bool(self._layer_manager.get_custom_data_layer_type(root_layer))
        return False

    def __on_stage_event(self, event):
        if event.type in [
            int(omni.usd.StageEventType.CLOSED),
            int(omni.usd.StageEventType.OPENED),
            int(omni.usd.StageEventType.SAVED),
        ]:
            if self.__enable_items_task:
                self.__enable_items_task.cancel()
            self.__enable_items_task = asyncio.ensure_future(self.__deferred_enable_items())

            if self._components_pane:
                self._components_pane.refresh()

    @omni.usd.handle_exception
    async def __deferred_enable_items(self):
        stage = self._context.get_stage()
        while (
            self._context.get_stage_state() in [omni.usd.StageState.OPENING, omni.usd.StageState.CLOSING]
        ) or not stage:
            await asyncio.sleep(0.1)
        await omni.kit.app.get_app_interface().next_update_async()
        if self._home_page:
            self._home_page.set_resume_enabled(self.enable_welcome_resume_item())

    def _import_replacement_layer(self, path, use_existing_layer):
        """Call the event object that has the list of functions"""
        self.__on_import_capture_layer(path, use_existing_layer)
        self._components_pane.refresh()

    def subscribe_import_replacement_layer(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_import_capture_layer, function)

    def _load_work_file(self, path):
        """Call the event object that has the list of functions"""
        if not Path(path).exists():
            _TrexMessageDialog(
                "The selected project does not exist at the given location.",
                title="Invalid Selected Project",
                disable_cancel_button=True,
            )
            self._refresh_recent_items()
            return

        self._on_load_work_file(path)
        self.show_page(Pages.WORKSPACE_PAGE)

    def _on_open_from_storage_pad_clicked(self, _x, _y, b, _m):
        """Called when we click on the 'open from storage' from the welcome pad"""
        if b != 0:
            return
        _open_file_picker(
            "Workfile picker",
            self._load_work_file,
            lambda *args: None,
            file_extension_options=READ_USD_FILE_EXTENSIONS_OPTIONS,
            validate_selection=_is_usd_file_path_valid_for_filepicker,
            validation_failed_callback=self.__show_error_not_usd_file,
        )

    def __show_error_not_usd_file(self, dirname: str, filename: str):
        _TrexMessageDialog(
            message=f"{dirname}/{filename} is not a USD file",
            disable_cancel_button=True,
        )

    def subscribe_load_work_file(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self._on_load_work_file, function)

    def _launch_game_with_remix(self):
        def execute_launcher(filename: str):
            file_url = OmniUrl(filename)
            launcher_url = OmniUrl(carb.tokens.get_tokens_interface().resolve(REMIX_LAUNCHER_PATH))
            command = [str(launcher_url), "-w", file_url.parent_url, str(file_url)]
            # Start the sub-process
            subprocess.Popen(  # noqa PLR1732
                command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, cwd=launcher_url.parent_url
            )

        _open_file_picker(
            "Select a game executable",
            execute_launcher,
            lambda *_: None,
            apply_button_label="Select Game",
            current_file=carb.tokens.get_tokens_interface().resolve(REMIX_SAMPLE_PATH),
            file_extension_options=[("*.exe", "Executable Files")],
        )

    def _new_work_file_clicked(self):
        """Call the event object that has the list of functions"""
        self._on_new_work_file_clicked()

    def subscribe_new_work_file_clicked(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self._on_new_work_file_clicked, fn)

    def _open_work_file_clicked(self):
        """Call the event object that has the list of functions"""
        self._on_open_work_file_clicked()

    def subscribe_open_work_file_clicked(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self._on_open_work_file_clicked, fn)

    def _resume_work_file_clicked(self):
        self.show_page(Pages.WORKSPACE_PAGE)
        self._on_resume_work_file_clicked()
        if not self._components_pane.get_ui_widget().get_selection():
            self._components_pane.get_ui_widget().set_selection(
                self._components_pane.get_model().get_item_children(None)[0]
            )
        self._components_pane.refresh()

    def subscribe_resume_work_file_clicked(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self._on_resume_work_file_clicked, fn)

    def _remove_project_from_recent(self, paths: list[str]):
        for path in paths:
            self._recent_saved_file.remove_path_from_recent_file(path)
        self._refresh_recent_items()

    @property
    def default_attr(self):
        default_attr = super().default_attr
        default_attr.update(
            {
                "_feature_flags_core": None,
                "_subcription_app_window_size_changed": None,
                "_welcome_pads_recent_model": None,
                "_frame_home_page": None,
                "_home_page": None,
                "_sub_new_project_clicked": None,
                "_sub_open_project_clicked": None,
                "_sub_resume_clicked": None,
                "_sub_remove_from_recent_clicked": None,
                "_sub_load_project_clicked": None,
                "_frame_workspace": None,
                "_feature_flags_changed_subs": None,
                "_header_refreshed_task": None,
                "_viewport": None,
                "_stage_manager_frame": None,
                "_stage_manager": None,
                "_components_pane": None,
                "_properties_pane": None,
                "_components_pane_tree_selection_changed": None,
                "_property_panel_frame": None,
                "_all_frames": None,
                "_splitter_property_viewport": None,
                "_splitter_stage_manager": None,
                "_sub_import_replacement_layer": None,
                "_welcome_resume_item": None,
                "_sub_menu_burger_pressed": None,
                "_recent_saved_file": None,
                "_welcome_pad_widget_recent": None,
                "_sub_stage_event": None,
                "_layer_manager": None,
                "_last_property_viewport_splitter_x": None,
                "_sub_frame_prim_selection_panel": None,
                "_sub_go_to_ingest": None,
            }
        )
        return default_attr

    @property
    def button_name(self) -> str:
        return "Modding"

    @property
    def context(self) -> TrexContexts:
        return TrexContexts.STAGE_CRAFT

    @property
    def button_priority(self) -> int:
        return 10

    @omni.usd.handle_exception
    async def __resize_stage_manager_deferred(self):
        if not self._splitter_stage_manager:
            return

        await omni.kit.app.get_app_interface().next_update_async()
        if self._frame_workspace.computed_height <= 0:
            return

        if self._stage_manager_frame is not None and self._stage_manager_frame.computed_height > 0:
            stage_manager_height = self._stage_manager_frame.computed_height
        else:
            stage_manager_height = self.HEIGHT_STAGE_MANAGER_PANEL

        self._set_stage_manager_splitter_offset(ui.Pixel(self._frame_workspace.computed_height - stage_manager_height))

    def _on_app_window_size_changed(self, event: carb.events.IEvent):
        asyncio.ensure_future(self.__resize_stage_manager_deferred())

    def show_page(self, page: Pages):
        # TODO Feature OM-45888 - File Picker will appear behind the wizard modal
        if page != self.__current_page:
            _get_event_manager_instance().call_global_custom_event(GlobalEventNames.PAGE_CHANGED.value)

        for frame in self._all_frames:
            if frame.name == page.value:
                frame.visible = True
                match frame.name:
                    case Pages.WORKSPACE_PAGE.value:
                        if self._stage_manager is not None:
                            self._stage_manager.resize_tabs()
                        self._components_pane.get_ui_widget().set_selection(
                            self._components_pane.get_model().get_item_children(None)[0]
                        )
            else:
                frame.visible = False
        self.__current_page = page
        self._on_header_refreshed()

    def current_page(self):
        return self.__current_page

    def _on_header_refreshed(self):
        self._header_navigator.show_logo_and_title(self.__current_page == Pages.WORKSPACE_PAGE)

    def _create_layout(self):
        with ui.ZStack():
            self._frame_home_page = ui.Frame(name=Pages.HOME_PAGE.value)
            self._all_frames.append(self._frame_home_page)
            with self._frame_home_page:
                self._home_page = _HomePageWidget()
                self._sub_resume_clicked = self._home_page.subscribe_resume_clicked(self._resume_work_file_clicked)
                self._sub_new_project_clicked = self._home_page.subscribe_new_project_clicked(
                    self._new_work_file_clicked
                )
                self._sub_open_project_clicked = self._home_page.subscribe_open_project_clicked(
                    self._open_work_file_clicked
                )
                self._sub_remove_from_recent_clicked = self._home_page.subscribe_remove_from_recent_clicked(
                    self._remove_project_from_recent
                )
                self._sub_load_project_clicked = self._home_page.subscribe_load_project_clicked(self._load_work_file)

            self._frame_workspace = ui.Frame(
                name=Pages.WORKSPACE_PAGE.value,
                visible=False,
            )

            self._all_frames.append(self._frame_workspace)
            with self._frame_workspace:
                with ui.HStack():
                    with ui.ZStack(width=0):
                        with ui.HStack():
                            with ui.Frame(width=ui.Pixel(self.WIDTH_COMPONENT_PANEL)):
                                self._components_pane = ComponentsPaneSetupUI(self._context_name)
                            self._property_panel_frame = ui.Frame(
                                visible=False, width=ui.Pixel(self.WIDTH_PROPERTY_PANEL)
                            )
                            with self._property_panel_frame:
                                self._properties_pane = PropertyPanelUI(self._context_name)
                                # hidden by default
                                self._properties_pane.show_panel(forced_value=False)
                        self._splitter_property_viewport = ui.Placer(
                            draggable=True,
                            offset_x=ui.Pixel(self.WIDTH_COMPONENT_PANEL + self.WIDTH_PROPERTY_PANEL),
                            drag_axis=ui.Axis.X,
                            width=50,
                            offset_x_changed_fn=self._on_property_viewport_splitter_change,
                        )
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

                                splitter = ui.Rectangle(name="TreePanelBackgroundSplitter")
                                _hover_helper(splitter)
                    with ui.ZStack():
                        with ui.VStack():
                            self._viewport = _create_viewport_instance(self._context_name)
                            stage_manager_frame = ui.Frame(build_fn=self._build_stage_manager, height=0)
                        stage_manager_splitter_frame = ui.Frame(build_fn=self._build_stage_manager_splitter, height=0)

        def rebuild_stage_manager():
            # Clear the existing UI in case the feature flag is disabled
            stage_manager_frame.clear()
            stage_manager_splitter_frame.clear()

            # Destroy the stage manager to disable listeners
            if self._stage_manager:
                self._stage_manager.destroy()

            # Rebuild the UI if required
            stage_manager_frame.rebuild()
            stage_manager_splitter_frame.rebuild()

        # Rebuild feature-flag-gated UI when feature flags change
        self._feature_flags_changed_subs = self._feature_flags_core.subscribe_feature_flags_changed(
            lambda *_: rebuild_stage_manager()
        )

        # subscribe to the burger menu
        self._sub_menu_burger_pressed = self._components_pane.get_ui_widget().menu_burger_widget.set_mouse_pressed_fn(
            lambda x, y, b, m: self._on_menu_burger_mouse_pressed(b)
        )

        # connect the component pane back arrow
        components_pane_widget = self._components_pane.get_ui_widget()
        components_pane_widget.arrow_back_title_widget.set_mouse_pressed_fn(
            lambda x, y, b, m: self._on_back_arrow_pressed()
        )

        # connect the component pane to the property pane
        self._components_pane_tree_selection_changed = components_pane_widget.subscribe_tree_selection_changed(
            self._on_components_pane_tree_selection_changed
        )

        # connect the property pane with the component pane
        self._sub_import_replacement_layer = self._properties_pane.get_frame(
            ComponentsEnumItems.MOD_SETUP
        ).subscribe_import_replacement_layer(self._import_replacement_layer)

        # connect the property selection pane with the viewport
        self._sub_frame_prim_selection_panel = self._properties_pane.get_frame(
            ComponentsEnumItems.ASSET_REPLACEMENTS
        ).selection_tree_widget.subscribe_frame_prim(self._frame_prim)

        # connect the go to ingest event
        self._sub_go_to_ingest = self._properties_pane.get_frame(
            ComponentsEnumItems.ASSET_REPLACEMENTS
        ).subscribe_go_to_ingest_tab(partial(self.show_layout_by_name, "Ingestion"))

        self._refresh_recent_items()

    def show(self, value: bool):
        pass

    def _build_stage_manager(self):
        if not self._feature_flags_core.is_enabled("stage_manager"):
            return

        with ui.VStack():
            ui.Spacer(height=ui.Pixel(self.HEIGHT_STAGE_MANAGER_SPLITTER))

            self._stage_manager_frame = ui.ZStack(
                height=ui.Pixel(self.HEIGHT_STAGE_MANAGER_PANEL), content_clipping=True
            )
            with self._stage_manager_frame:
                self._stage_manager = _StageManagerWidget()

    def _build_stage_manager_splitter(self):
        if not self._feature_flags_core.is_enabled("stage_manager"):
            return

        self._splitter_stage_manager = ui.Placer(
            draggable=True,
            offset_y=0,
            drag_axis=ui.Axis.Y,
            height=ui.Pixel(self.HEIGHT_STAGE_MANAGER_SPLITTER),
            offset_y_changed_fn=self._set_stage_manager_splitter_offset,
        )

        with self._splitter_stage_manager:
            with ui.ZStack(opaque_for_mouse_events=True):
                ui.Rectangle(name="WorkspaceBackground")
                with ui.HStack():
                    for _ in range(3):
                        ui.Image(
                            "",
                            name="TreePanelLinesBackground",
                            fill_policy=ui.FillPolicy.PRESERVE_ASPECT_CROP,
                            height=ui.Pixel(12),
                        )

                splitter = ui.Rectangle(name="TreePanelBackgroundSplitter")
                _hover_helper(splitter)

        asyncio.ensure_future(self.__resize_stage_manager_deferred())

    def _frame_prim(self, prim: "Usd.Prim"):
        if prim and prim.IsValid():
            self._viewport.frame_viewport_selection(selection=[str(prim.GetPath())])

    def _on_back_arrow_pressed(self):
        self.show_page(Pages.HOME_PAGE)
        self._refresh_recent_items()

    def _refresh_recent_items(self):
        if self.__update_recent_items_task:
            self.__update_recent_items_task.cancel()
        self.__update_recent_items_task = asyncio.ensure_future(self._refresh_recent_items_deferred())

    @omni.usd.handle_exception
    async def _refresh_recent_items_deferred(self):
        if not self._home_page:
            return

        items = []
        for path, _ in self._recent_saved_file.get_recent_file_data().items():
            title = os.path.basename(path)
            details = {"Path": path}
            details.update(self._recent_saved_file.get_path_detail(path))
            data = await self._recent_saved_file.find_thumbnail_async(path)
            if data is None:
                continue
            _, thumbnail = data
            items.append((title, thumbnail, details))

        self._home_page.set_recent_items(items)

    def _on_menu_burger_mouse_pressed(self, button):
        if button != 0:
            return
        get_burger_menu_instance().show_at(
            self._components_pane.get_ui_widget().menu_burger_widget.screen_position_x,
            self._components_pane.get_ui_widget().menu_burger_widget.screen_position_y
            + self._components_pane.get_ui_widget().menu_burger_widget.computed_height
            + ui.Pixel(8),
        )

    def subscribe_import_capture_layer(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return self._properties_pane.get_frame(ComponentsEnumItems.MOD_SETUP).subscribe_import_capture_layer(function)

    def _set_stage_manager_splitter_offset(self, y):
        min_offset = 0
        max_offset = (
            self._frame_workspace.computed_height
            - self.MIN_HEIGHT_STAGE_MANAGER_PANEL
            - self.HEIGHT_STAGE_MANAGER_SPLITTER
        )

        clamped_offset = ui.Pixel(min(max(y.value, min_offset), max(max_offset, min_offset)))
        self._splitter_stage_manager.offset_y = clamped_offset

        self._stage_manager_frame.height = ui.Pixel(
            self._frame_workspace.computed_height - clamped_offset - self.HEIGHT_STAGE_MANAGER_SPLITTER
        )

    @_ignore_function_decorator(attrs=["_ignore_property_viewport_splitter_change"])
    def _on_property_viewport_splitter_change(self, x):
        if x.value <= self.WIDTH_COMPONENT_PANEL + self.MIN_WIDTH_PROPERTY_PANEL:
            self._splitter_property_viewport.offset_x = self.WIDTH_COMPONENT_PANEL + self.MIN_WIDTH_PROPERTY_PANEL
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
        if x.value < self.WIDTH_COMPONENT_PANEL + self.MIN_WIDTH_PROPERTY_PANEL:
            x = ui.Pixel(self.WIDTH_COMPONENT_PANEL + self.MIN_WIDTH_PROPERTY_PANEL)
        self._property_panel_frame.width = ui.Pixel(x - self.WIDTH_COMPONENT_PANEL)
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

    def destroy(self):
        if self._feature_flags_changed_subs:
            self._feature_flags_core.unsubscribe_feature_flags_changed(self._feature_flags_changed_subs)

        if self.__enable_items_task:
            self.__enable_items_task.cancel()
        self.__enable_items_task = None

        if self.__update_recent_items_task:
            self.__update_recent_items_task.cancel()
        self.__update_recent_items_task = None

        super().destroy()

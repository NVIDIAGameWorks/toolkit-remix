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
import os
import typing
from enum import Enum
from functools import partial

import carb.events
import omni.appwindow
import omni.kit.app
import omni.ui as ui
import omni.usd
from lightspeed.common.constants import READ_USD_FILE_EXTENSIONS_OPTIONS
from lightspeed.event.save_recent.recent_saved_file_utils import RecentSavedFile as _RecentSavedFile
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.trex.components_pane.stagecraft.controller import SetupUI as ComponentsPaneSetupUI
from lightspeed.trex.components_pane.stagecraft.models import EnumItems as ComponentsEnumItems
from lightspeed.trex.contexts import get_instance as trex_contexts_instance
from lightspeed.trex.contexts.setup import Contexts as TrexContexts
from lightspeed.trex.footer.stagecraft.models import StageCraftFooterModel
from lightspeed.trex.layout.shared import SetupUI as TrexLayout
from lightspeed.trex.menu.workfile import get_instance as get_burger_menu_instance
from lightspeed.trex.properties_pane.stagecraft.widget import SetupUI as PropertyPanelUI
from lightspeed.trex.utils.common import ignore_function_decorator as _ignore_function_decorator
from lightspeed.trex.viewports.shared.widget import SetupUI as ViewportUI
from lightspeed.trex.welcome_pads.stagecraft.models import NewWorkFileItem, RecentWorkFileItem, ResumeWorkFileItem
from omni.flux.footer.widget import FooterWidget
from omni.flux.header_nvidia.widget import HeaderWidget
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.widget.color import color_to_hex
from omni.flux.utils.widget.file_pickers.file_picker import open_file_picker as _open_file_picker
from omni.flux.utils.widget.resources import get_background_images
from omni.flux.utils.widget.resources import get_icons as _get_icons
from omni.flux.welcome_pad.widget import WelcomePadWidget
from omni.flux.welcome_pad.widget.model import Model as WelcomePadModel

if typing.TYPE_CHECKING:
    from pxr import Usd


class Pages(Enum):
    HOME_PAGE = "HomePage"
    WORKSPACE_PAGE = "WorkspacePage"


class SetupUI(TrexLayout):
    WIDTH_COMPONENT_PANEL = 256
    WIDTH_PROPERTY_PANEL = 400

    def __init__(self, ext_id):
        super().__init__(ext_id)

        self._welcome_pad_widgets = []
        self._all_frames = []
        self._background_images = []
        self.__background_switcher_task = None
        self.__enable_items_task = None
        appwindow_stream = omni.appwindow.get_default_app_window().get_window_resize_event_stream()
        self._subcription_app_window_size_changed = appwindow_stream.create_subscription_to_pop(
            self._on_app_window_size_changed, name="On app window resized", order=0
        )

        self._context_name = TrexContexts.STAGE_CRAFT.value
        self._context = trex_contexts_instance().get_context(TrexContexts.STAGE_CRAFT)
        self._layer_manager = _LayerManagerCore(context_name=self._context_name)
        self._sub_stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="StageChanged"
        )

        self._welcome_pads_new_model = WelcomePadModel()
        self._welcome_resume_item = ResumeWorkFileItem(self._resume_work_file_clicked)
        self._welcome_resume_item.enabled = self.enable_welcome_resume_item()
        self._welcome_pads_new_model.add_items(
            [NewWorkFileItem(self._new_work_file_clicked), self._welcome_resume_item]
        )

        self._recent_saved_file = _RecentSavedFile()
        self._welcome_pads_recent_model = WelcomePadModel()
        self._welcome_pads_recent_model.set_list_limit(20)

        self.__current_page = None

        self._header_refreshed_task = self._header_navigator.subscribe_header_refreshed(self._on_header_refreshed)
        self._on_new_work_file_clicked = _Event()
        self._on_open_work_file = _Event()
        self._on_resume_work_file_clicked = _Event()
        self.__on_import_capture_layer = _Event()
        self.__on_ctrl_s = _Event()
        self.__on_ctrl_shift_s = _Event()
        self.__on_ctrl_y = _Event()
        self.__on_ctrl_z = _Event()

    def subscribe_ctrl_s_released(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_ctrl_s, fn)

    def subscribe_ctrl_shift_s_released(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_ctrl_shift_s, fn)

    def subscribe_ctrl_z_released(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_ctrl_z, fn)

    def subscribe_ctrl_y_released(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self.__on_ctrl_y, fn)

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
            self._components_pane.refresh()

    @omni.usd.handle_exception
    async def __deferred_enable_items(self):
        stage = self._context.get_stage()
        while (
            self._context.get_stage_state() in [omni.usd.StageState.OPENING, omni.usd.StageState.CLOSING]
        ) or not stage:
            await asyncio.sleep(0.1)
        await omni.kit.app.get_app_interface().next_update_async()
        self._welcome_pads_new_model.enable_items([self._welcome_resume_item], self.enable_welcome_resume_item())

    def _import_replacement_layer(self, path, use_existing_layer):
        """Call the event object that has the list of functions"""
        self.__on_import_capture_layer(path, use_existing_layer)
        self._components_pane.refresh()

    def subscribe_import_replacement_layer(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_import_capture_layer, function)

    def _open_work_file(self, path):
        """Call the event object that has the list of functions"""
        self._on_open_work_file(path)
        self.show_page(Pages.WORKSPACE_PAGE)
        # select the first component
        self._components_pane.get_ui_widget().set_selection(
            self._components_pane.get_model().get_item_children(None)[0]
        )

    def _on_open_from_storage_pad_clicked(self, _x, _y, b, _m):
        """Called when we click on the 'open from storage' from the welcome pad"""
        if b != 0:
            return
        _open_file_picker(
            "Workfile picker",
            self._open_work_file,
            lambda *args: None,
            file_extension_options=READ_USD_FILE_EXTENSIONS_OPTIONS,
        )

    def subscribe_open_work_file(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self._on_open_work_file, function)

    def _new_work_file_clicked(self):
        """Call the event object that has the list of functions"""
        self.show_page(Pages.WORKSPACE_PAGE)
        # select the first component
        self._components_pane.get_ui_widget().set_selection(
            self._components_pane.get_model().get_item_children(None)[0]
        )
        self._on_new_work_file_clicked()

    def subscribe_new_work_file_clicked(self, fn):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when we click on a tool (change of the selected tool)
        """
        return _EventSubscription(self._on_new_work_file_clicked, fn)

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

    @property
    def default_attr(self):
        default_attr = super().default_attr
        default_attr.update(
            {
                "_header_nvidia_widget": None,
                "_welcome_pad_widgets": None,
                "_subcription_app_window_size_changed": None,
                "_welcome_pads_new_model": None,
                "_welcome_pads_recent_model": None,
                "_frame_home_page": None,
                "_frame_workspace": None,
                "_header_refreshed_task": None,
                "_viewport": None,
                "_home_footer": None,
                "_components_pane": None,
                "_properties_pane": None,
                "_components_pane_tree_selection_changed": None,
                "_property_panel_frame": None,
                "_all_frames": None,
                "_background_images": None,
                "_splitter_property_viewport": None,
                "_sub_import_replacement_layer": None,
                "_welcome_resume_item": None,
                "_sub_menu_burger_pressed": None,
                "_recent_saved_file": None,
                "_welcome_pad_widget_recent": None,
                "_sub_stage_event": None,
                "_layer_manager": None,
                "_last_property_viewport_splitter_x": None,
                "_sub_frame_prim_selection_panel": None,
            }
        )
        return default_attr

    @property
    def button_name(self) -> str:
        return "StageCraft"

    @property
    def button_priority(self) -> int:
        return 10

    def __refresh_welcome_pad_tree(self):
        for pad in self._welcome_pad_widgets:
            pad.resize_tree_content()

    def _on_app_window_size_changed(self, event: carb.events.IEvent):
        self.__refresh_welcome_pad_tree()

    def _on_button_clicked(self, x, y, b, m):  # noqa PLC0103
        super()._on_button_clicked(x, y, b, m)
        self.__refresh_welcome_pad_tree()

    def show_page(self, page: Pages):
        for frame in self._all_frames:
            frame.visible = frame.name == page.value
        self.__current_page = page
        self._on_header_refreshed()
        self.__refresh_welcome_pad_tree()

    def _on_header_refreshed(self):
        self._header_navigator.show_logo_and_title(self.__current_page == Pages.WORKSPACE_PAGE)

    @omni.usd.handle_exception
    async def __background_switcher(self):
        """Switch background smoothly
        The idea is to start from bottom of the list to top (for Z order)
        """

        @omni.usd.handle_exception
        async def blend(current_one, next_one):
            speed = 200
            alpha = 255.0
            for speed_i in range(speed):
                await omni.kit.app.get_app_interface().next_update_async()
                alpha_down = alpha - ((alpha / (speed - 1)) * speed_i)
                alpha_up = (alpha / (speed - 1)) * speed_i
                current_one.set_style({"Image": {"color": color_to_hex((1.0, 1.0, 1.0, alpha_down / 255))}})
                next_one.set_style({"Image": {"color": color_to_hex((1.0, 1.0, 1.0, alpha_up / 255))}})

        i = 0
        while True:
            next_widget = None
            current_widget = None
            background_images = list(reversed(self._background_images))
            for image_i, image in enumerate(background_images):
                image.visible = image_i == i
                if image_i == i:
                    current_widget = image
                    current_widget.set_style({"Image": {"color": 0xFFFFFFFF}})
                    if image == background_images[-1]:
                        next_widget = background_images[0]
                    else:
                        next_widget = background_images[image_i + 1]
                    next_widget.set_style({"Image": {"color": 0x00FFFFFF}})
            if next_widget is None or current_widget is None:
                return
            await asyncio.sleep(5)
            next_widget.visible = True
            await blend(current_widget, next_widget)

            if self._background_images is None:
                return  # reload
            i += 1
            if i == len(self._background_images) - 1:
                i = 0

    def _create_layout(self):
        self._welcome_pad_widgets = []
        with ui.ZStack():
            self._frame_home_page = ui.Frame(name=Pages.HOME_PAGE.value)
            self._all_frames.append(self._frame_home_page)
            with self._frame_home_page:
                with ui.ZStack():
                    # create background image
                    background_image_paths = get_background_images()
                    if background_image_paths:
                        # the first image is the same than the last one! To be able to switch smoothly
                        self._background_images.append(
                            ui.Image(background_image_paths[-1], fill_policy=ui.FillPolicy.PRESERVE_ASPECT_CROP)
                        )
                        for background_image_path in background_image_paths:
                            image = ui.Image(background_image_path, fill_policy=ui.FillPolicy.PRESERVE_ASPECT_CROP)
                            self._background_images.append(image)
                    with ui.VStack():
                        self._header_nvidia_widget = HeaderWidget()  # hold or it will crash
                        with ui.HStack():
                            ui.Spacer()  # flexible
                            with ui.VStack(width=ui.Pixel(480)):
                                ui.Spacer(height=ui.Pixel(48))
                                self._welcome_pad_widgets.append(
                                    WelcomePadWidget(
                                        model=self._welcome_pads_new_model,
                                        show_footer=False,
                                        title="PROJECT SETUP",
                                        auto_resize_list=False,
                                    )
                                )  # hold or crash
                            ui.Spacer(width=ui.Pixel(64))
                            with ui.VStack(width=ui.Pixel(480)):
                                ui.Spacer(height=ui.Pixel(48))
                                self._welcome_pad_widget_recent = WelcomePadWidget(
                                    model=self._welcome_pads_recent_model,
                                    title="RECENTLY OPENED",
                                    show_footer=False,
                                    auto_resize_list=False,
                                    word_wrap_description=False,
                                )  # hold or crash
                                self._welcome_pad_widgets.append(self._welcome_pad_widget_recent)
                            ui.Spacer(width=ui.Pixel(64))
                            with ui.VStack(width=ui.Pixel(480)):
                                ui.Spacer(height=ui.Pixel(48))
                                self._welcome_pad_widgets.append(
                                    WelcomePadWidget(title="WHAT'S NEW", create_demo_items=False)
                                )  # hold or crash

                            ui.Spacer()  # flexible
                        self._home_footer = FooterWidget(model=StageCraftFooterModel, height=ui.Pixel(144))

            self._frame_workspace = ui.Frame(
                name=Pages.WORKSPACE_PAGE.value,
                visible=False,
                key_pressed_fn=self._on_frame_workspace_key_pressed,
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

        if self.__background_switcher_task:
            self.__background_switcher_task.cancel()
        self.__background_switcher_task = asyncio.ensure_future(self.__background_switcher())

        self._refresh_welcome_pads_recent_model()

    def _frame_prim(self, prim: "Usd.Prim"):
        if prim and prim.IsValid():
            self._viewport.frame_viewport_selection(selection=[str(prim.GetPath())])

    def _on_frame_workspace_key_pressed(self, key, modifiers, is_down):
        if (
            key == int(carb.input.KeyboardInput.Z)
            and modifiers == carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL
            and not is_down
        ):
            self.__on_ctrl_z()
        elif (
            key == int(carb.input.KeyboardInput.Y)
            and modifiers == carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL
            and not is_down
        ):
            self.__on_ctrl_y()
        elif (
            key == int(carb.input.KeyboardInput.S)
            and modifiers == carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL
            and not is_down
        ):
            self.__on_ctrl_s()
        elif (
            key == int(carb.input.KeyboardInput.S)
            and modifiers == carb.input.KEYBOARD_MODIFIER_FLAG_CONTROL + carb.input.KEYBOARD_MODIFIER_FLAG_SHIFT
            and not is_down
        ):
            self.__on_ctrl_shift_s()

    def _on_back_arrow_pressed(self):
        self.show_page(Pages.HOME_PAGE)
        self._refresh_welcome_pads_recent_model()

    def _refresh_welcome_pads_recent_model(self):
        @omni.usd.handle_exception
        async def _update_images(_path):
            _, thumbnail = await self._recent_saved_file.find_thumbnail_async(_path)
            if thumbnail is None:
                return
            await omni.kit.app.get_app().next_update_async()
            if not self._welcome_pad_widget_recent or not self._welcome_pad_widget_recent.delegate:
                return
            images_widgets = self._welcome_pad_widget_recent.delegate.get_image_widgets()
            _title = os.path.basename(_path)
            if _title in images_widgets:
                images_widgets[_title].source_url = thumbnail

        def _get_image(_path):
            asyncio.ensure_future(_update_images(_path))
            return _get_icons("new_workfile")  # default image or it will always show the default image from style

        items = []
        for path, _ in self._recent_saved_file.get_recent_file_data().items():
            title = os.path.basename(path)
            details = {"Path": path}
            details.update(self._recent_saved_file.get_path_detail(path))
            items.append(
                RecentWorkFileItem(title, details, partial(_get_image, path), partial(self._open_work_file, path))
            )
        self._welcome_pads_recent_model.set_items(reversed(items))

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
        if x.value < 0:
            x = 0
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
        if self.__enable_items_task:
            self.__enable_items_task.cancel()
        self.__enable_items_task = None
        if self.__background_switcher_task:
            self.__background_switcher_task.cancel()
        self.__background_switcher_task = None
        super().destroy()

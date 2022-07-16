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
import functools
import os

import omni.appwindow
import omni.client
import omni.ui as ui
import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.layer_types import LayerType
from lightspeed.trex.capture.core.shared import Setup as CaptureCoreSetup
from lightspeed.trex.replacement.core.shared import Setup as ReplacementCoreSetup
from lightspeed.trex.utils.widget import TrexMessageDialog
from lightspeed.trex.utils.widget import create_widget_with_pattern as _create_widget_with_pattern
from omni.flux.property_widget_builder.model.file import FileAttributeItem as _FileAttributeItem
from omni.flux.property_widget_builder.model.file import FileDelegate as _FileDelegate
from omni.flux.property_widget_builder.model.file import FileModel as _FileModel
from omni.flux.property_widget_builder.model.file import get_file_listener_instance as _get_file_listener_instance
from omni.flux.property_widget_builder.widget import PropertyWidget as _PropertyWidget
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.collapsable_frame import PropertyCollapsableFrameWithInfoPopup
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font
from omni.flux.utils.widget.resources import get_fonts as _get_fonts

from .capture_dir_picker import open_directory_picker
from .capture_tree.delegate import Delegate as CaptureTreeDelegate
from .capture_tree.model import ListModel as CaptureTreeModel
from .mod_file_picker import open_file_picker
from .mod_file_picker_create import open_file_picker_create


class ModSetupPane:

    DEFAULT_CAPTURE_TREE_FRAME_HEIGHT = 200
    SIZE_PERCENT_MANIPULATOR_WIDTH = 50

    def __init__(self, context: omni.usd.UsdContext):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_capture_detail_property_widget": None,
            "_capture_details_collapsable_frame": None,
            "_capture_details_delegate": None,
            "_capture_details_frame": None,
            "_capture_details_model": None,
            "_capture_details_scroll_frame": None,
            "_capture_dir_field": None,
            "_capture_directory_provider": None,
            "_capture_file_collapsable_frame": None,
            "_capture_manip_frame": None,
            "_capture_manipulator_frame": None,
            "_capture_slide_placer": None,
            "_capture_slider_manip": None,
            "_capture_tree_delegate": None,
            "_capture_tree_hovered_task": None,
            "_capture_tree_model": None,
            "_capture_tree_view": None,
            "_capture_tree_view_window": None,
            "_context": None,
            "_last_capture_tree_view_window_selection": None,
            "_overlay_capture_label": None,
            "_root_frame": None,
            "_tree_capture_scroll_frame": None,
            "_window_capture_tree": None,
            "_game_icon_hovered_task": None,
            "_mod_file_collapsable_frame": None,
            "_mod_file_details_collapsable_frame": None,
            "_mod_file_frame": None,
            "_mod_file_details_frame": None,
            "_mod_file_label_path": None,
            "_mod_file_field": None,
            "_core_capture": None,
            "_core_replacement": None,
            "_mod_details_model": None,
            "_mod_details_delegate": None,
            "_mod_detail_property_widget": None,
            "_sub_stage_event": None,
            "_layer_manager": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context = context
        self._layer_manager = _LayerManagerCore(context=self._context)
        self.__import_existing_mod_file = True
        self._capture_tree_hovered_task = False
        self._game_icon_hovered_task = None
        self.__ignore_capture_tree_selection_changed = False
        self.__ignore_capture_tree_hovered = False
        self._capture_tree_model = CaptureTreeModel()
        self._capture_tree_delegate = CaptureTreeDelegate()
        self._capture_tree_delegate_window = CaptureTreeDelegate()
        self.__capture_field_is_editing = False
        self._core_capture = CaptureCoreSetup(context)
        self._core_replacement = ReplacementCoreSetup(context)

        self._sub_stage_event = self._context.get_stage_event_stream().create_subscription_to_pop(
            self.__on_stage_event, name="StageChanged"
        )

        self.__file_listener_instance = _get_file_listener_instance()

        self.__on_select_vehicle_pressed_event = _Event()
        self.__on_import_capture_layer = _Event()
        self.__on_import_replacement_layer = _Event()

        self.__update_default_style()
        self.__create_ui()

    def __on_stage_event(self, event):
        if event.type in [
            int(omni.usd.StageEventType.CLOSED),
            int(omni.usd.StageEventType.OPENED),
            int(omni.usd.StageEventType.ASSETS_LOADED),
        ]:
            if not self._capture_tree_view_window:
                return
            capture_layer = self._layer_manager.get_layer(LayerType.capture)
            if capture_layer is not None:
                for item in self._capture_tree_model.get_item_children(None):
                    if omni.client.normalize_url(item.path) == omni.client.normalize_url(capture_layer.realPath):
                        self._capture_tree_view_window.selection = [item]
                        return
            self._capture_tree_view_window.selection = []

            replacement_layer = self._layer_manager.get_layer(LayerType.replacement)
            if replacement_layer is not None:
                self._mod_file_field.model.set_value(omni.client.normalize_url(replacement_layer.realPath))
            else:
                self._mod_file_field.model.set_value("...")

    def __update_default_style(self):
        """
        This widget generate image from text. It needs to read keys from a the global style.
        If those keys doesn't exist, we add them here (or it will crash). With this, the widget will work even without
        global style that sets those keys
        """
        style = ui.Style.get_instance()
        current_dict = style.default
        if "ImageWithProvider::PropertiesPaneSectionTitle" not in current_dict:
            current_dict["ImageWithProvider::PropertiesPaneSectionTitle"] = {
                "color": 0xB3FFFFFF,
                "font_size": 13,
                "image_url": _get_fonts("Barlow-Bold"),
            }
        style.default = current_dict

    def _import_capture_layer(self, path):
        def on_okay_clicked(dialog: TrexMessageDialog):
            dialog.hide()
            self.__on_import_capture_layer(path)
            self.refresh_capture_detail_panel()
            self._last_capture_tree_view_window_selection = self._capture_tree_view_window.selection

        def on_cancel_clicked(dialog: TrexMessageDialog):
            dialog.hide()
            self.__ignore_capture_tree_selection_changed = True
            self._capture_tree_view_window.selection = (
                []
                if self._last_capture_tree_view_window_selection is None
                else self._last_capture_tree_view_window_selection
            )
            self.__ignore_capture_tree_selection_changed = False

        message = f"Are you sure you want to load this capture layer?\n{path}"

        dialog = TrexMessageDialog(
            width=600,
            message=message,
            ok_handler=on_okay_clicked,
            cancel_handler=on_cancel_clicked,
            ok_label="Yes",
            disable_cancel_button=False,
        )
        dialog.show()

    def subscribe_import_capture_layer(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_import_capture_layer, function)

    def subscribe_import_replacement_layer(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_import_replacement_layer, function)

    def _select_vehicle_pressed(self):
        """Call the event object that has the list of functions"""
        self.__on_select_vehicle_pressed_event()

    def subscribe_select_vehicle_pressed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_select_vehicle_pressed_event, function)

    def __create_capture_tree_window(self):
        flags = ui.WINDOW_FLAGS_NO_COLLAPSE
        flags |= ui.WINDOW_FLAGS_NO_CLOSE
        flags |= ui.WINDOW_FLAGS_NO_MOVE
        flags |= ui.WINDOW_FLAGS_NO_RESIZE
        flags |= ui.WINDOW_FLAGS_NO_DOCKING
        flags |= ui.WINDOW_FLAGS_NO_BACKGROUND
        flags |= ui.WINDOW_FLAGS_NO_TITLE_BAR
        # flags |= ui.WINDOW_FLAGS_MODAL  # OM-49102

        self._window_capture_tree = ui.Window(
            "Capture tree window",
            width=self._tree_capture_scroll_frame.computed_width,
            height=self._tree_capture_scroll_frame.computed_height,
            visible=False,
            flags=flags,
        )
        self._window_capture_tree.frame.set_mouse_hovered_fn(self._on_capture_tree_hovered)
        with self._window_capture_tree.frame:
            with ui.ScrollingFrame(
                name="PropertiesPaneSection",
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                with ui.ZStack():
                    ui.Rectangle(name="PropertiesPaneSectionWindowCaptureBackground")
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))
                            self._capture_tree_view_window = ui.TreeView(
                                self._capture_tree_model,
                                delegate=self._capture_tree_delegate_window,
                                root_visible=False,
                                header_visible=False,
                                columns_resizable=False,
                                name="PropertiesPaneSectionCapture",
                                selection_changed_fn=self._on_capture_tree_selection_changed,
                            )
                            ui.Spacer(height=ui.Pixel(8))
                        ui.Spacer(width=ui.Pixel(8))
        self._window_capture_tree.frame.set_computed_content_size_changed_fn(
            functools.partial(
                self._resize_capture_tree_columns, self._capture_tree_view_window, self._window_capture_tree.frame
            )
        )

        self._window_capture_tree.frame.set_build_fn(
            functools.partial(
                self._resize_capture_tree_columns, self._capture_tree_view_window, self._window_capture_tree.frame
            )
        )

    def __create_ui(self):
        self._root_frame = ui.Frame()
        with self._root_frame:
            with ui.ScrollingFrame(
                name="PropertiesPaneSection",
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(56))

                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8), height=ui.Pixel(0))
                        with ui.VStack():
                            ui.Spacer(height=ui.Pixel(8))

                            self._capture_file_collapsable_frame = PropertyCollapsableFrameWithInfoPopup(
                                "CAPTURE FILE",
                                info_text=(
                                    "The capture file loads the captured scene from the game.\n"
                                    "This will be used as the base scene for modifications created in the system."
                                ),
                            )
                            with self._capture_file_collapsable_frame:
                                with ui.VStack():
                                    ui.Spacer(height=ui.Pixel(8))
                                    with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                                        with ui.HStack(width=ui.Percent(40)):
                                            ui.Spacer()
                                            with ui.VStack(width=0):
                                                ui.Spacer()
                                                self._capture_directory_provider, _, _ = _create_label_with_font(
                                                    "Capture ", "PropertiesWidgetLabel", remove_offset=False
                                                )
                                                ui.Spacer()
                                        with ui.HStack():
                                            ui.Spacer(width=ui.Pixel(4))
                                            with ui.ZStack():
                                                self._capture_dir_field = ui.StringField(
                                                    height=ui.Pixel(18), name="USDPropertiesWidgetValue"
                                                )
                                                with ui.HStack():
                                                    ui.Spacer(width=ui.Pixel(8))
                                                    with ui.Frame(width=ui.Pixel(134), horizontal_clipping=True):
                                                        self._overlay_capture_label = ui.Label(
                                                            "Capture directory path...",
                                                            name="USDPropertiesWidgetValueOverlay",
                                                            width=0,
                                                        )
                                                self._capture_dir_field.model.add_begin_edit_fn(
                                                    self._on_capture_dir_field_begin
                                                )
                                                self._capture_dir_field.model.add_end_edit_fn(
                                                    self._on_capture_dir_field_end
                                                )
                                                self._capture_dir_field.model.add_value_changed_fn(
                                                    self._on_capture_dir_field_changed
                                                )
                                            ui.Spacer(width=ui.Pixel(8))
                                            with ui.VStack(width=ui.Pixel(20)):
                                                ui.Spacer()
                                                ui.Image(
                                                    "",
                                                    name="OpenFolder",
                                                    height=ui.Pixel(20),
                                                    mouse_pressed_fn=lambda x, y, b, m: self._on_capture_dir_pressed(b),
                                                )
                                                ui.Spacer()

                                    self._capture_manipulator_frame = ui.Frame(visible=False)
                                    with self._capture_manipulator_frame:
                                        with ui.VStack():
                                            ui.Spacer(height=ui.Pixel(8))
                                            ui.Line(name="PropertiesPaneSectionTitle", height=0)
                                            ui.Spacer(height=ui.Pixel(8))
                                            size_manipulator_height = 4
                                            with ui.Frame():
                                                with ui.ZStack():
                                                    with ui.VStack():
                                                        self._tree_capture_scroll_frame = ui.ScrollingFrame(
                                                            name="PropertiesPaneSection",
                                                            # height=ui.Pixel(self.DEFAULT_CAPTURE_TREE_FRAME_HEIGHT),
                                                            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,  # noqa E501
                                                        )
                                                        with self._tree_capture_scroll_frame:
                                                            self._capture_tree_view = ui.TreeView(
                                                                self._capture_tree_model,
                                                                delegate=self._capture_tree_delegate,
                                                                root_visible=False,
                                                                header_visible=False,
                                                                columns_resizable=False,
                                                                mouse_hovered_fn=self._on_capture_tree_hovered,
                                                            )
                                                        self._tree_capture_scroll_frame.set_build_fn(
                                                            functools.partial(
                                                                self._resize_capture_tree_columns,
                                                                self._capture_tree_view,
                                                                self._tree_capture_scroll_frame,
                                                            )
                                                        )
                                                        self._tree_capture_scroll_frame.set_computed_content_size_changed_fn(  # noqa E501
                                                            functools.partial(
                                                                self._resize_capture_tree_columns,
                                                                self._capture_tree_view,
                                                                self._tree_capture_scroll_frame,
                                                            )
                                                        )
                                                        ui.Spacer(height=ui.Pixel(8))
                                                        ui.Line(name="PropertiesPaneSectionTitle")
                                                        ui.Spacer(height=ui.Pixel(8))
                                                        ui.Spacer(height=size_manipulator_height)

                                                    with ui.VStack():
                                                        ui.Spacer()
                                                        self._capture_manip_frame = ui.Frame(
                                                            height=size_manipulator_height
                                                        )
                                                        with self._capture_manip_frame:
                                                            self._capture_slide_placer = ui.Placer(
                                                                draggable=True,
                                                                height=size_manipulator_height,
                                                                offset_x_changed_fn=self._on_capture_slide_x_changed,
                                                                offset_y_changed_fn=functools.partial(
                                                                    self._on_capture_slide_y_changed,
                                                                    size_manipulator_height,
                                                                ),
                                                            )
                                                            # Body
                                                            with self._capture_slide_placer:
                                                                self._capture_slider_manip = ui.Rectangle(
                                                                    width=ui.Percent(
                                                                        self.SIZE_PERCENT_MANIPULATOR_WIDTH
                                                                    ),
                                                                    name="PropertiesPaneSectionCaptureTreeManipulator",
                                                                )
                            ui.Spacer(height=ui.Pixel(16))

                            self._capture_details_collapsable_frame = PropertyCollapsableFrameWithInfoPopup(
                                "CAPTURE DETAILS",
                                info_text="Details from the capture layer file loaded in this stage",
                                collapsed=True,
                                enabled=False,
                            )
                            with self._capture_details_collapsable_frame:
                                self._capture_details_frame = ui.Frame()

                            ui.Spacer(height=ui.Pixel(16))
                            self._mod_file_collapsable_frame = PropertyCollapsableFrameWithInfoPopup(
                                "MOD FILE",
                                info_text=(
                                    "The mod file modify the capture file above.\n"
                                    "This will be used as a layer over the capture file.\n"
                                    "You can load an existing mod file or create a new one.\n"
                                    "Each time that you create/load a mod file, it will replace the existing one in the"
                                    " stage."
                                ),
                                enabled=False,
                            )
                            with self._mod_file_collapsable_frame:
                                with ui.VStack(spacing=ui.Pixel(8)):
                                    with ui.HStack():
                                        _create_widget_with_pattern(
                                            functools.partial(
                                                ui.Button,
                                                "Load existing mod file",
                                                name="NoBackground",
                                                clicked_fn=self._on_load_existing_mod,
                                            ),
                                            "BackgroundButton",
                                            height=ui.Pixel(24),
                                            background_margin=(2, 2),
                                        )

                                        ui.Spacer(width=ui.Pixel(8))

                                        _create_widget_with_pattern(
                                            functools.partial(
                                                ui.Button,
                                                "Create a new mod file",
                                                name="NoBackground",
                                                clicked_fn=self._on_create_mod,
                                            ),
                                            "BackgroundButton",
                                            height=ui.Pixel(24),
                                            background_margin=(2, 2),
                                        )

                                    self._mod_file_frame = ui.Frame()
                                    with self._mod_file_frame:
                                        with ui.HStack():
                                            with ui.HStack(width=ui.Percent(40)):
                                                ui.Spacer()
                                                with ui.VStack(width=0):
                                                    ui.Spacer()
                                                    self._mod_file_label_path, _, _ = _create_label_with_font(
                                                        "Current path", "PropertiesWidgetLabel", remove_offset=False
                                                    )
                                                    ui.Spacer()
                                                ui.Spacer(width=ui.Pixel(8))
                                            with ui.HStack():
                                                ui.Spacer(width=ui.Pixel(8))
                                                self._mod_file_field = ui.StringField(read_only=True, height=0)
                                                self._mod_file_field.model.set_value("...")
                                                self._mod_file_field.model.add_value_changed_fn(
                                                    self._on_mod_file_field_changed
                                                )

                            ui.Spacer(height=ui.Pixel(16))

                            self._mod_file_details_collapsable_frame = PropertyCollapsableFrameWithInfoPopup(
                                "MOD DETAILS",
                                info_text="Details from the mod layer file loaded in this stage",
                                collapsed=True,
                                enabled=False,
                            )
                            with self._mod_file_details_collapsable_frame:
                                self._mod_file_details_frame = ui.Frame()

                        # ui.Spacer(width=ui.Pixel(16), height=ui.Pixel(0))  # no need for spacer, scrollframe does it

                    ui.Spacer()

    def _on_load_existing_mod(self):
        value = self._mod_file_field.model.get_value_as_string()
        current_file = value if value.strip() else None
        if current_file:
            result, entry = omni.client.stat(current_file)
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.READABLE_FILE:
                current_file = None
        self.__import_existing_mod_file = True
        open_file_picker(self.set_mod_file_field, lambda *args: None, current_file=current_file)

    def set_mod_file_field(self, path):
        self._mod_file_field.model.set_value(path)

    def _on_create_mod(self):
        value = self._mod_file_field.model.get_value_as_string()
        current_file = value if value.strip() else None
        if current_file:
            result, entry = omni.client.stat(current_file)
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.READABLE_FILE:
                current_file = None
        self.__import_existing_mod_file = False
        open_file_picker_create(self.set_mod_file_field, lambda *args: None, current_file=current_file)

    def _enable_panels(self):
        value = bool(self._core_capture.get_layer())
        if not value:
            self._capture_file_collapsable_frame.root.collapsed = False
            self._capture_details_collapsable_frame.root.collapsed = True
            self._mod_file_collapsable_frame.root.collapsed = False
            self._mod_file_details_collapsable_frame.root.collapsed = True
        self._capture_details_collapsable_frame.enabled = value
        self._mod_file_collapsable_frame.enabled = value
        self._mod_file_details_collapsable_frame.enabled = value

    def refresh_mod_detail_panel(self):
        if not self._root_frame.visible:
            return
        self._mod_file_details_frame.clear()
        value = self._mod_file_field.model.get_value_as_string()
        current_file = value if value.strip() else None
        if not current_file or not self._core_replacement.is_path_valid(current_file):
            return
        self._destroy_mod_properties()

        items = []
        for attr in [attr for attr in dir(omni.client.ListEntry) if not attr.startswith("_")]:
            items.append(_FileAttributeItem(current_file, attr, display_attr_name=attr.replace("_", " ").capitalize()))

        self._mod_details_model = _FileModel(current_file)
        self._mod_details_model.set_items(items)
        self._mod_details_delegate = _FileDelegate()
        self.__file_listener_instance.add_model_and_delegate(self._mod_details_model, self._mod_details_delegate)

        with self._mod_file_details_frame:
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(8))
                self._mod_detail_property_widget = _PropertyWidget(self._mod_details_model, self._mod_details_delegate)

    def refresh_capture_detail_panel(self):
        """
        Refresh the panel with the given paths
        """
        min_game_icon_size = 48
        max_game_icon_size = 96

        def set_game_icon(widget, image_path):
            widget.source_url = image_path

        @omni.usd.handle_exception
        async def deferred_on_game_icon_hovered(widget, hovered):
            current_size = widget.computed_width
            final_size = current_size
            if hovered:
                while final_size <= max_game_icon_size:
                    await asyncio.sleep(0.04)
                    final_size += 10
                    widget.width = ui.Pixel(final_size)
                    widget.height = ui.Pixel(final_size)
            else:
                while final_size >= min_game_icon_size:
                    await asyncio.sleep(0.04)
                    final_size -= 10
                    widget.width = ui.Pixel(final_size)
                    widget.height = ui.Pixel(final_size)

        def on_game_icon_hovered(widget, hovered):
            if self._game_icon_hovered_task:
                self._game_icon_hovered_task.cancel()
            self._game_icon_hovered_task = asyncio.ensure_future(deferred_on_game_icon_hovered(widget, hovered))

        if not self._root_frame.visible:
            return
        self._capture_details_frame.clear()

        self._enable_panels()

        value = self._capture_dir_field.model.get_value_as_string()
        current_directory = value if value.strip() else None
        if not current_directory:
            return
        self._destroy_capture_properties()

        selection = self._capture_tree_view_window.selection
        if not selection:
            return
        capture_path = selection[0].path

        items = []
        for attr in [attr for attr in dir(omni.client.ListEntry) if not attr.startswith("_")]:
            items.append(_FileAttributeItem(capture_path, attr, display_attr_name=attr.replace("_", " ").capitalize()))

        self._capture_details_model = _FileModel(capture_path)
        self._capture_details_model.set_items(items)
        self._capture_details_delegate = _FileDelegate()
        self.__file_listener_instance.add_model_and_delegate(
            self._capture_details_model, self._capture_details_delegate
        )

        with self._capture_details_frame:
            with ui.VStack():
                ui.Spacer(height=ui.Pixel(8))
                with ui.HStack(height=ui.Pixel(min_game_icon_size)):
                    with ui.HStack(width=ui.Percent(40)):
                        ui.Spacer()
                        game_icon_widget = ui.Image("", width=ui.Pixel(min_game_icon_size))
                        asyncio.ensure_future(
                            self._core_capture.deferred_get_upscaled_game_icon_from_folder(
                                os.path.dirname(capture_path), functools.partial(set_game_icon, game_icon_widget)
                            )
                        )
                        game_icon_widget.set_mouse_hovered_fn(functools.partial(on_game_icon_hovered, game_icon_widget))
                    with ui.VStack():
                        ui.Spacer()
                        with ui.HStack():
                            ui.Spacer(width=ui.Pixel(8), height=0)
                            game_name = self._core_capture.get_game_name(capture_path)
                            ui.StringField(read_only=True, height=0).model.set_value(game_name)
                        ui.Spacer()
                ui.Spacer(height=ui.Pixel(8))
                self._capture_detail_property_widget = _PropertyWidget(
                    self._capture_details_model, self._capture_details_delegate
                )

    def _on_capture_tree_selection_changed(self, items):
        if self.__ignore_capture_tree_selection_changed:
            return
        if len(items) > 1:
            self._capture_tree_view_window.selection = [items[0]]
        self._capture_tree_view.selection = self._capture_tree_view_window.selection
        if self._capture_tree_view_window.selection:
            self._import_capture_layer(items[0].path)
        else:
            self.refresh_capture_detail_panel()

    def _on_capture_tree_hovered(self, hovered):
        if self._window_capture_tree is None:
            self.__create_capture_tree_window()
        if self.__ignore_capture_tree_hovered:
            return
        if self._capture_tree_hovered_task:
            self._capture_tree_hovered_task.cancel()
        self._capture_tree_hovered_task = asyncio.ensure_future(self.__deferred_on_capture_tree_hovered(hovered))

    @omni.usd.handle_exception
    async def __deferred_on_capture_tree_hovered(self, hovered):
        await omni.kit.app.get_app_interface().next_update_async()
        item_path_scroll_frames = self._capture_tree_delegate.get_path_scroll_frames()
        if not item_path_scroll_frames:
            return
        self._window_capture_tree.position_x = self._tree_capture_scroll_frame.screen_position_x - 12
        self._window_capture_tree.position_y = self._tree_capture_scroll_frame.screen_position_y - 12
        if hovered and not self._window_capture_tree.visible:
            self.__ignore_capture_tree_hovered = True
            self._window_capture_tree.visible = hovered
            app_window = omni.appwindow.get_default_app_window()
            size = app_window.get_size()

            rows_size = (
                len(self._capture_tree_model.get_item_children(None))
                * self._capture_tree_delegate.DEFAULT_IMAGE_ICON_SIZE
            )
            final_value_h = rows_size + 40
            if final_value_h > size[1] - self._tree_capture_scroll_frame.screen_position_y - 8:
                final_value_h = size[1] - self._tree_capture_scroll_frame.screen_position_y - 8
            self._window_capture_tree.height = ui.Pixel(final_value_h + 8)
            self._window_capture_tree.width = ui.Pixel(self._tree_capture_scroll_frame.computed_width + 24)
            for _ in range(2):  # 2 frame to have the scroll frame appear
                await omni.kit.app.get_app().next_update_async()  # wait the window to appear
            item_path_scroll_frames = self._capture_tree_delegate_window.get_path_scroll_frames()
            value = max(frame.scroll_x_max for frame in item_path_scroll_frames.values())
            if value != 0:  # no scroll max = we see everything
                final_value_w = self._window_capture_tree.width + value
                if final_value_w > size[0] - self._tree_capture_scroll_frame.screen_position_x - 8:
                    final_value_w = size[0] - self._tree_capture_scroll_frame.screen_position_x - 8
                self._window_capture_tree.width = ui.Pixel(final_value_w + 16)
            self.__ignore_capture_tree_hovered = False
        elif (
            self._window_capture_tree.visible
            and not self._capture_tree_delegate_window.get_window_bigger_image().visible
        ):
            self._window_capture_tree.visible = hovered

    def _resize_capture_tree_columns(self, tree_view, frame):
        tree_view.column_widths = [
            ui.Percent(100),
        ]

    def _on_capture_slide_x_changed(self, x):
        size_manip = self._capture_manip_frame.computed_width / 100 * self.SIZE_PERCENT_MANIPULATOR_WIDTH
        if x.value < 0:
            self._capture_slide_placer.offset_x = 0
        elif x.value > self._capture_manip_frame.computed_width - size_manip:
            self._capture_slide_placer.offset_x = self._capture_manip_frame.computed_width - size_manip

        item_path_scroll_frames = self._capture_tree_delegate.get_path_scroll_frames()
        if item_path_scroll_frames:
            max_frame_scroll_x = max(frame.scroll_x_max for frame in item_path_scroll_frames.values())
            value = (max_frame_scroll_x / (self._capture_manip_frame.computed_width - size_manip)) * x
            for frame in item_path_scroll_frames.values():
                frame.scroll_x = value

    def _on_capture_slide_y_changed(self, size_manip, y):
        if y.value < 0:
            self._capture_slide_placer.offset_y = 0
        self._tree_capture_scroll_frame.height = ui.Pixel(self.DEFAULT_CAPTURE_TREE_FRAME_HEIGHT + y.value)

    def _on_capture_dir_pressed(self, button):
        if button != 0:
            return
        value = self._capture_dir_field.model.get_value_as_string()
        current_directory = value if value.strip() else None
        if current_directory:
            result, entry = omni.client.stat(current_directory)
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                current_directory = None
        open_directory_picker(self.set_capture_dir_field, lambda *args: None, current_directory=current_directory)

    def set_capture_dir_field(self, path):
        self._capture_dir_field.model.set_value(path)

    def _on_capture_dir_field_begin(self, model):
        self.__capture_field_is_editing = True

    def _on_capture_dir_field_end(self, model):
        self.__capture_field_is_editing = False
        self._on_capture_dir_field_changed(model)

    def _on_capture_dir_field_changed(self, model):
        path = model.get_value_as_string()
        self._overlay_capture_label.visible = not bool(path.strip())
        if self.__capture_field_is_editing:
            return
        if not self._core_capture.is_path_valid(path):
            return
        self._core_capture.set_directory(path)
        self._capture_tree_model.refresh(
            [(path, self._core_capture.get_capture_image(path)) for path in self._core_capture.capture_files]
        )
        if not self._capture_manipulator_frame.visible:
            self._capture_manipulator_frame.visible = True
            self._tree_capture_scroll_frame.height = ui.Pixel(self.DEFAULT_CAPTURE_TREE_FRAME_HEIGHT)

    def _on_mod_file_field_changed(self, model):
        path = model.get_value_as_string()
        self.refresh_mod_detail_panel()
        if not self._core_replacement.is_path_valid(path):
            return
        self.__on_import_replacement_layer(path, self.__import_existing_mod_file)

    def _destroy_capture_properties(self):
        if self.__file_listener_instance and self._capture_details_model and self._capture_details_delegate:
            self.__file_listener_instance.remove_model_and_delegate(
                self._capture_details_model, self._capture_details_delegate
            )

    def _destroy_mod_properties(self):
        if self.__file_listener_instance and self._mod_details_model and self._mod_details_delegate:
            self.__file_listener_instance.remove_model_and_delegate(self._mod_details_model, self._mod_details_delegate)

    def show(self, value):
        self._root_frame.visible = value
        if value:
            self.refresh_capture_detail_panel()
            self.refresh_mod_detail_panel()
        else:
            self._destroy_mod_properties()
            self._destroy_capture_properties()

    def destroy(self):
        if self._capture_tree_hovered_task:
            self._capture_tree_hovered_task.cancel()
        self._destroy_mod_properties()
        self._destroy_capture_properties()
        _reset_default_attrs(self)
        self.__file_listener_instance = None

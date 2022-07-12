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

import omni.appwindow
import omni.client
import omni.ui as ui
import omni.usd
from lightspeed.trex.capture.core.shared import Setup as CaptureCoreSetup
from omni.flux.property_widget_builder.model.file import FileAttributeItem as _FileAttributeItem
from omni.flux.property_widget_builder.model.file import FileDelegate as _FileDelegate
from omni.flux.property_widget_builder.model.file import FileModel as _FileModel
from omni.flux.property_widget_builder.model.file import get_file_listener_instance as _get_file_listener_instance
from omni.flux.property_widget_builder.widget import PropertiesWidget as _PropertiesWidget
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.widget.collapsable_frame import PropertyCollapsableFrameWithInfoPopup
from omni.flux.utils.widget.label import create_label_with_font as _create_label_with_font
from omni.flux.utils.widget.resources import get_fonts as _get_fonts
from omni.kit.window.popup_dialog import MessageDialog

from .capture_dir_picker import open_directory_picker
from .capture_tree.delegate import Delegate as CaptureTreeDelegate
from .capture_tree.model import ListModel as CaptureTreeModel


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
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context = context
        self._capture_tree_hovered_task = False
        self.__ignore_capture_tree_selection_changed = False
        self.__ignore_capture_tree_hovered = False
        self._capture_tree_model = CaptureTreeModel()
        self._capture_tree_delegate = CaptureTreeDelegate()
        self._capture_tree_delegate_window = CaptureTreeDelegate()
        self.__capture_field_is_editing = False
        self._core_capture = CaptureCoreSetup(context)

        self.__file_listener_instance = _get_file_listener_instance()

        self.__on_select_vehicle_pressed_event = _Event()
        self.__on_import_capture_layer = _Event()

        self.__update_default_style()
        self.__create_ui()

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
        def on_okay_clicked(dialog: MessageDialog):
            dialog.hide()
            self.__on_import_capture_layer(path)
            self.refresh_capture_detail_panel()
            self._last_capture_tree_view_window_selection = self._capture_tree_view_window.selection

        def on_cancel_clicked(dialog: MessageDialog):
            dialog.hide()
            self.__ignore_capture_tree_selection_changed = True
            self._capture_tree_view_window.selection = (
                []
                if self._last_capture_tree_view_window_selection is None
                else self._last_capture_tree_view_window_selection
            )
            self.__ignore_capture_tree_selection_changed = False

        message = f"Are you sure you want to load this capture layer?\n{path}"

        dialog = MessageDialog(
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
                                                    "Capture directory", "PropertiesWidgetLabel", remove_offset=False
                                                )
                                                ui.Spacer()
                                            ui.Spacer(width=ui.Pixel(8))
                                        with ui.HStack(width=ui.Percent(60), spacing=ui.Pixel(8)):
                                            with ui.ZStack():
                                                self._capture_dir_field = ui.StringField(
                                                    height=ui.Pixel(18), name="USDPropertiesWidgetValue"
                                                )
                                                with ui.HStack():
                                                    ui.Spacer(width=ui.Pixel(8))
                                                    self._overlay_capture_label = ui.Label(
                                                        "Capture directory path...",
                                                        name="USDPropertiesWidgetValueOverlay",
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
                                            with ui.VStack(width=ui.Pixel(20)):
                                                ui.Spacer()
                                                ui.Image(
                                                    "",
                                                    name="OpenFolder",
                                                    height=ui.Pixel(20),
                                                    mouse_pressed_fn=lambda x, y, b, m: self._on_capture_dir_pressed(b),
                                                )
                                                ui.Spacer()

                                    ui.Spacer(height=ui.Pixel(8))
                                    ui.Line(name="PropertiesPaneSectionTitle", height=0)
                                    ui.Spacer(height=ui.Pixel(8))
                                    size_manipulator_height = 4
                                    with ui.Frame():
                                        with ui.ZStack():
                                            with ui.VStack():
                                                self._tree_capture_scroll_frame = ui.ScrollingFrame(
                                                    name="PropertiesPaneSection",
                                                    height=ui.Pixel(self.DEFAULT_CAPTURE_TREE_FRAME_HEIGHT),
                                                    horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
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
                                                self._tree_capture_scroll_frame.set_computed_content_size_changed_fn(
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
                                                    height=size_manipulator_height,
                                                )
                                                with self._capture_manip_frame:
                                                    self._capture_slide_placer = ui.Placer(
                                                        draggable=True,
                                                        height=size_manipulator_height,
                                                        offset_x_changed_fn=self._on_capture_slide_x_changed,
                                                        offset_y_changed_fn=functools.partial(
                                                            self._on_capture_slide_y_changed, size_manipulator_height
                                                        ),
                                                    )
                                                    # Body
                                                    with self._capture_slide_placer:
                                                        self._capture_slider_manip = ui.Rectangle(
                                                            width=ui.Percent(self.SIZE_PERCENT_MANIPULATOR_WIDTH),
                                                            name="PropertiesPaneSectionCaptureTreeManipulator",
                                                        )
                            ui.Spacer(height=ui.Pixel(16))

                            self._capture_details_collapsable_frame = PropertyCollapsableFrameWithInfoPopup(
                                "CAPTURE DETAILS", info_text="Details from the capture layer file loaded in this stage"
                            )
                            with self._capture_details_collapsable_frame:
                                self._capture_details_frame = ui.Frame()
                        ui.Spacer(width=ui.Pixel(16), height=ui.Pixel(0))
                    ui.Spacer()

    def refresh_capture_detail_panel(self):
        """
        Refresh the panel with the given paths
        """

        if not self._root_frame.visible:
            return
        self._capture_details_frame.clear()

        value = self._capture_dir_field.model.get_value_as_string()
        current_directory = value if value.strip() else None
        if not current_directory:
            return
        self._destroy_properties()

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
            self._capture_detail_property_widget = _PropertiesWidget(
                self._capture_details_model, self._capture_details_delegate
            )

    def _on_capture_tree_selection_changed(self, items):
        if self.__ignore_capture_tree_selection_changed:
            return
        if len(items) > 1:
            self._capture_tree_view_window.selection = [items[0]]
        if self._capture_tree_view_window.selection:
            self._import_capture_layer(items[0].path)

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
        if not path or not path.strip():
            return
        if self.__capture_field_is_editing:
            return
        self._core_capture.set_directory(path)
        self._capture_tree_model.refresh(
            [(path, self._core_capture.get_capture_image(path)) for path in self._core_capture.capture_files]
        )

    def _destroy_properties(self):
        if self.__file_listener_instance and self._capture_details_model and self._capture_details_delegate:
            self.__file_listener_instance.remove_model_and_delegate(
                self._capture_details_model, self._capture_details_delegate
            )

    def show(self, value):
        self._root_frame.visible = value
        if value:
            self.refresh_capture_detail_panel()
        else:
            self._destroy_properties()

    def destroy(self):
        if self._capture_tree_hovered_task:
            self._capture_tree_hovered_task.cancel()
        self._destroy_properties()
        _reset_default_attrs(self)
        self.__file_listener_instance = None

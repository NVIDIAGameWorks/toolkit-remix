"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import os

import carb
import omni
import omni.client
import omni.ext
import omni.kit.menu.utils as omni_utils
import omni.kit.window.content_browser as content
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from lightspeed.progress_popup.window import ProgressPopup
from omni import ui
from omni.kit.menu.utils import MenuItemDescription
from omni.kit.tool.collect.icons import Icons

from .exporter import LightspeedExporterCore
from .usd_file_picker import open_file_picker


class LightspeedExporterUI:
    def __init__(self):
        self.__default_attr = {
            "_window": None,
            "_folder_exsit_popup": None,
            "_progress_popup": None,
            "_exportion_path_field": None,
            "_core": None,
            "_layer_manager": None,
            "_subscription_progress_changed": None,
            "_subscription_progress_text_changed": None,
            "_subscription_finish_export": None,
        }
        for attr, value in self.__default_attr.items():
            setattr(self, attr, value)

        self._layer_manager = LayerManagerCore()
        self._core = LightspeedExporterCore()
        self._subscription_progress_changed = self._core.subscribe_progress_changed(self._on_progress_changed)
        self._subscription_progress_text_changed = self._core.subscribe_progress_text_changed(
            self._on_progress_text_changed
        )
        self._subscription_finish_export = self._core.subscribe_finish_export(self._on_finish_export)

        self._window = None
        self._folder_exsit_popup = None
        self._exportion_path_field = None
        self._progress_popup = None

        self.__create_save_menu()

    def _on_progress_changed(self, progress: float):
        self._progress_popup.progress = progress

    def _on_progress_text_changed(self, text: str):
        self._progress_popup.status_text = text

    def _on_finish_export(self):
        content_window = content.get_content_window()
        content_window.refresh_current_directory()
        self._progress_popup.hide()

    def __create_save_menu(self):
        """Create the menu to Save scenario"""
        self._tools_manager_menus = [
            MenuItemDescription(
                name="Export to Lightspeed Runtime", onclick_fn=self.__clicked, glyph="none.svg", appear_after="Save"
            )
        ]
        omni_utils.add_menu_items(self._tools_manager_menus, "File")

    def __clicked(self):

        replacement_layer = self._layer_manager.get_layer(LayerType.replacement)
        if replacement_layer is None:
            carb.log_error("Can't find the replacement layer in the stage")
            return

        self._window = omni.ui.Window(
            "Export Options", visible=True, height=0, dockPreference=ui.DockPreference.DISABLED
        )
        self._window.flags = (
            ui.WINDOW_FLAGS_NO_COLLAPSE
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_MOVE
        )

        self._window.flags = self._window.flags | ui.WINDOW_FLAGS_MODAL

        style = {
            "Rectangle::hovering": {"background_color": 0x0, "border_radius": 2, "margin": 0, "padding": 0},
            "Rectangle::hovering:hovered": {"background_color": 0xFF9E9E9E},
            "Button.Image::folder": {"image_url": Icons().get("folder")},
            "Button.Image::folder:checked": {"image_url": Icons().get("folder")},
            "Button::folder": {"background_color": 0x0, "margin": 0},
            "Button::folder:checked": {"background_color": 0x0, "margin": 0},
            "Button::folder:pressed": {"background_color": 0x0, "margin": 0},
            "Button::folder:hovered": {"background_color": 0x0, "margin": 0},
            "Label::ExportWarningLayer": {"color": 0xFF00B4F5},
        }

        with self._window.frame:
            with ui.VStack(height=0, style=style):
                ui.Spacer(height=20)
                with ui.HStack(height=0):
                    ui.Spacer(width=40)
                    ui.Label("Export folder path", width=0)
                    ui.Spacer(width=5)
                    with ui.VStack(height=0):
                        ui.Spacer(height=4)
                        self._exportion_path_field = ui.StringField(height=20, width=ui.Fraction(1))
                        default_path = self._core.get_default_export_path(create_if_not_exist=True)
                        if default_path:
                            self._exportion_path_field.model.set_value(default_path)
                        ui.Spacer(height=4)
                    with ui.VStack(height=0, width=0):
                        ui.Spacer(height=4)
                        with ui.ZStack(width=20, height=20):
                            ui.Rectangle(name="hovering")
                            button = ui.Button(name="folder", width=24, height=24)
                            button.set_tooltip("Choose folder")
                            button.set_clicked_fn(lambda: self._show_file_picker())
                        ui.Spacer(height=4)
                    ui.Spacer(width=2)
                    ui.Spacer(width=40)
                ui.Spacer(height=10)
                ui.Label(
                    f'Only data from the layer "{os.path.basename(replacement_layer.realPath)}" will be exported',
                    alignment=ui.Alignment.CENTER,
                    name="ExportWarningLayer",
                )
                ui.Spacer(height=10)
                with ui.HStack(height=0):
                    ui.Spacer()
                    self._export_button = ui.Button("Export", width=60, height=0)
                    self._export_button.set_clicked_fn(self._on_export_button_clicked)
                    self._cancel_button = ui.Button("Cancel", width=60, height=0)
                    self._cancel_button.set_clicked_fn(self._on_cancel_button_clicked)
                    ui.Spacer()
                ui.Spacer(height=20)

    def _on_export_button_clicked(self):
        export_dir = self._exportion_path_field.model.get_value_as_string()
        if not self._core.check_export_path(export_dir):
            return
        self._show_progress_popup()
        self._core.export(export_dir)

        self._window.visible = False

    def _on_cancel_button_clicked(self):
        self._window.visible = False

    def _select_picked_folder_callback(self, path):
        self._exportion_path_field.model.set_value(path)
        self._window.visible = True

    def _cancel_picked_folder_callback(self):
        self._window.visible = True

    def _show_file_picker(self):
        self._window.visible = False
        path = self._exportion_path_field.model.get_value_as_string()
        current_directory = path if path else None
        open_file_picker(self._select_picked_folder_callback, lambda *args: None, current_directory=current_directory)

    def _show_progress_popup(self):
        if not self._progress_popup:
            self._progress_popup = ProgressPopup("Exporting")
            self._progress_popup.set_cancel_fn(self._core.cancel)
        self._progress_popup.progress = 0
        self._progress_popup.show()

    def destroy(self):
        omni_utils.remove_menu_items(self._tools_manager_menus, "File")
        for attr, value in self.__default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()
                del m_attr
                setattr(self, attr, value)

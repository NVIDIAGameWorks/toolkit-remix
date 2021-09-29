import os
import omni
import carb
import time
import asyncio
import weakref
import numpy as np
from pxr import Gf
from pxr import UsdGeom

from omni import ui
import omni.ext
import omni.kit.window.content_browser as content
import omni.kit.menu.utils as omni_utils

from omni.kit.tool.collect.collector import Collector
from omni.kit.tool.collect.icons import Icons
from omni.kit.tool.collect.filebrowser import FileBrowserSelectionType, FileBrowserMode
from omni.kit.tool.collect.file_picker import FilePicker
from omni.kit.tool.collect.progress_popup import ProgressPopup
from omni.kit.menu.utils import MenuItemDescription
from omni.kit.window.file import DialogOptions


class LightspeedExporterExtension(omni.ext.IExt):
    def __init__(self, export_button_fn=None, cancel_button_fn=None):
        self._export_button_fn = export_button_fn
        self._cancel_button_fn = cancel_button_fn
        self._file_picker = None
        self._folder_exsit_popup = None
        self._exportion_path_field = None
        self._progress_popup = None

    def set_export_fn(self, export_fn):
        self._export_button_fn = export_fn

    def set_cancel_fn(self, cancel_fn):
        self._cancel_button_fn = cancel_fn

    def on_startup(self, ext_id):
        self.__create_save_menu()
        self.set_export_fn(self._start_exporting)

    def __create_save_menu(self):
        """Create the menu to Save scenario"""
        self._tools_manager_menus = [
            MenuItemDescription(
                name="Export to Lightspeed Runtime", onclick_fn=self.__clicked, glyph="none.svg", appear_after="Save"
            )
        ]
        omni_utils.add_menu_items(self._tools_manager_menus, "File")

    def __clicked(self):
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
        }

        with self._window.frame:
            with ui.VStack(height=0, style=style):
                ui.Spacer(height=20)
                with ui.HStack(height=0):
                    ui.Spacer(width=40)
                    ui.Label("Export Path", width=0)
                    ui.Spacer(width=5)
                    with ui.VStack(height=0):
                        ui.Spacer(height=4)
                        self._exportion_path_field = ui.StringField(height=20, width=ui.Fraction(1))
                        ui.Spacer(height=4)
                    with ui.VStack(height=0, width=0):
                        ui.Spacer(height=4)
                        with ui.ZStack(width=20, height=20):
                            ui.Rectangle(name="hovering")
                            button = ui.Button(name="folder", width=24, height=24)
                        button.set_tooltip("Choose folder")
                        ui.Spacer(height=4)
                    ui.Spacer(width=2)
                    button.set_clicked_fn(lambda: self._show_file_picker())
                    ui.Spacer(width=40)
                ui.Spacer(height=10)
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
        if self._export_button_fn:
            export_dir = self._exportion_path_field.model.get_value_as_string()
            self._export_button_fn(export_dir)

        self._window.visible = False

    def _on_cancel_button_clicked(self):
        if self._cancel_button_fn:
            self._cancel_button_fn()

        self._window.visible = False

    def _select_picked_folder_callback(self, path):
        self._exportion_path_field.model.set_value(path)
        self._window.visible = True

    def _cancel_picked_folder_callback(self):
        self._window.visible = True

    def _show_file_picker(self):
        self._window.visible = False
        if not self._file_picker:
            mode = FileBrowserMode.SAVE
            file_type = FileBrowserSelectionType.DIRECTORY_ONLY
            filters = [(".*", "All Files (*.*)")]
            self._file_picker = FilePicker(
                "Select export Destination", mode=mode, file_type=file_type, filter_options=filters
            )
            self._file_picker.set_file_selected_fn(self._select_picked_folder_callback)
            self._file_picker.set_cancel_fn(self._cancel_picked_folder_callback)

        path = self._exportion_path_field.model.get_value_as_string()
        if path.endswith("/"):
            path = path[:-1]
        dir_name = os.path.dirname(path)
        folder_name = os.path.basename(path)
        self._file_picker.show(dir_name, folder_name)

    def _start_exporting(self, export_folder):
        self._show_progress_popup()

        # Save the current stage
        omni.kit.window.file.save(dialog_options=DialogOptions.HIDE)

        # Get current stage path
        usd_path = omni.usd.get_context().get_stage_url()

        self._progress_popup.status_text = f"Analyzing USD {os.path.basename(usd_path)}..."
        collector = Collector(usd_path, export_folder, False, True, False)

        collector_weakref = weakref.ref(collector)

        def on_cancel():
            carb.log_info("Cancel export...")
            if not collector_weakref():
                return

            collector_weakref().cancel()

        self._progress_popup.set_cancel_fn(on_cancel)

        def progress_callback(step, total):
            self._progress_popup.status_text = f"Collecting USD {os.path.basename(usd_path)}..."
            if total != 0:
                self._progress_popup.progress = float(step) / total
            else:
                self._progress_popup.progress = 0.0

        def finish_callback():
            self._progress_popup.hide()
            self._refresh_current_directory()
            # now process/optimize geo for game
            file_path = export_folder
            if not file_path.endswith("/"):
                file_path += "/"
            file_path += os.path.basename(usd_path)
            self._process_exported_usd(file_path)
            #reopen original stage
            omni.usd.get_context().open_stage(usd_path)

        asyncio.ensure_future(collector.collect(progress_callback, finish_callback))

    def _show_progress_popup(self):
        if not self._progress_popup:
            self._progress_popup = ProgressPopup("Exporting")
        self._progress_popup.progress = 0
        self._progress_popup.show()

    def _refresh_current_directory(self):
        content_window = content.get_content_window()
        content_window.refresh_current_directory()

    def _process_geometry(self, prim):
        # get the primvars API of the prim
        gp_pv = UsdGeom.PrimvarsAPI(prim)
        # get the mesh from the Prim
        mesh = UsdGeom.Mesh(prim)
        # get vertex counts (by face) attribute
        face_vertex_count = mesh.GetFaceVertexCountsAttr()
        # get the value of the vertex counts attribute
        face_vertex_count_value = face_vertex_count.Get()
        # get the vertex indices attribute
        face_vertex_indices = mesh.GetFaceVertexIndicesAttr()
        # get the value of the vertex indices attribute
        face_vertex_indices_value = face_vertex_indices.Get()
        # get the primvars attribute of the UVs
        st_prim_var = gp_pv.GetPrimvar("st")
        # Get interpolation
        inter_st_prim_var = st_prim_var.GetInterpolation()
        # get the indices attribute of st_prim_var
        st_indices_prim_var = st_prim_var.GetIndicesAttr()
        # get the value (position) of the UVs
        st_value = st_prim_var.Get()
        # get the indices value of the UVs
        st_indices_value = st_indices_prim_var.Get()

        # get rid of pesky indexed UVs
        st_prim_var.Set(st_prim_var.ComputeFlattened())
        prim.RemoveProperty(st_indices_prim_var.GetName())

        #TODO: Triangulate non-3 faceCounts
        #TODO: Expand vertex data to "Vertex" interpolation

    def _process_exported_usd(self, file_path):
        carb.log_info("Processing: " + file_path)

        success = omni.usd.get_context().open_stage(file_path)
        if not success:
            return

        stage = omni.usd.get_context().get_stage()

        all_geos = [prim_ref for prim_ref in stage.Traverse() if UsdGeom.Mesh(prim_ref)]
        for geo_prim in all_geos:
            self._process_geometry(geo_prim)

        omni.usd.get_context().save_stage()
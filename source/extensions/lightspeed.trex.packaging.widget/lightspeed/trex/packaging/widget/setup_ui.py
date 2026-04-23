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

from asyncio import ensure_future
from functools import partial

import carb.settings
import omni.kit.window.file
import omni.ui as ui
import omni.usd
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.mod_packaging_details.widget import ModPackagingDetailsWidget as _ModPackagingDetailsWidget
from lightspeed.trex.mod_packaging_layers.widget import ModPackagingLayersWidget as _ModPackagingLayersWidget
from lightspeed.trex.mod_packaging_output.widget import ModPackagingOutputWidget as _ModPackagingOutputWidget
from omni.flux.asset_importer.core.data_models import UsdExtensions as _UsdExtensions
from lightspeed.trex.packaging.core.enum import MOD_PACKAGING_MODE_UI_OPTIONS as _MOD_PACKAGING_MODE_UI_OPTIONS
from lightspeed.trex.packaging.core.enum import (
    MOD_PACKAGING_OUTPUT_FORMAT_UI_OPTIONS as _MOD_PACKAGING_OUTPUT_FORMAT_UI_OPTIONS,
)
from lightspeed.trex.packaging.core.enum import ModPackagingMode as _ModPackagingMode
from lightspeed.trex.packaging.core.enum import get_packaging_mode_description as _get_packaging_mode_description
from lightspeed.trex.packaging.core.enum import (
    get_packaging_output_format_description as _get_packaging_output_format_description,
)
from lightspeed.trex.packaging.core.packaging import PackagingCore as _PackagingCore
from lightspeed.trex.packaging.window import PackagingErrorWindow as _PackagingErrorWindow
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from lightspeed.trex.utils.widget import WorkspaceWidget as _WorkspaceWidget
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.dialog import ErrorPopup as _ErrorPopup
from omni.flux.utils.dialog import ProgressPopup as _ProgressPopup
from omni.flux.utils.widget.collapsable_frame import (
    PropertyCollapsableFrameWithInfoPopup as _PropertyCollapsableFrameWithInfoPopup,
)
from omni.kit.usd.collect.omni_client_wrapper import OmniClientWrapper as _OmniClientWrapper

_SETTINGS_PACKAGING_MODE = "/persistent/exts/lightspeed.trex.packaging.widget/packaging_mode"
_SETTINGS_OUTPUT_FORMAT = "/persistent/exts/lightspeed.trex.packaging.widget/output_format"
_PRESERVE_OUTPUT_FORMAT_SETTING_VALUE = "preserve"


class PackagingPane(_WorkspaceWidget):
    _MOD_PACKAGING_CONTEXT = "ModPackaging"

    def __init__(self, context_name: str = ""):
        """Nvidia StageCraft Mod Packaging Pane"""
        super().__init__()

        self._default_attr = {
            "_context_name": None,
            "_context": None,
            "_settings": None,
            "_packaging_core": None,
            "_packaging_progress_sub": None,
            "_packaging_completed_sub": None,
            "_packaging_errors_resolved_sub": None,
            "_output_valid": None,
            "_layers_valid": None,
            "_progress_popup": None,
            "_packaging_window": None,
            "root_widget": None,
            "_package_details_collapsable_frame": None,
            "_package_details_widget": None,
            "_package_output_collapsable_frame": None,
            "_package_output_widget": None,
            "_package_output_valid_sub": None,
            "_package_layers_collapsable_frame": None,
            "_package_layers_widget": None,
            "_package_mode_collapsable_frame": None,
            "_packaging_mode_combo": None,
            "_packaging_mode_changed_sub": None,
            "_packaging_output_format_combo": None,
            "_packaging_output_format_changed_sub": None,
            "_export_button": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = omni.usd.get_context(self._context_name)
        self._settings = carb.settings.get_settings()
        self._packaging_core = _PackagingCore()
        self._layer_manager = _LayerManagerCore(self._context_name)

        # Subscriptions created/destroyed in show() based on visibility
        self._packaging_progress_sub = None
        self._packaging_completed_sub = None
        self._packaging_errors_resolved_sub = None

        self._output_valid = False
        self._layers_valid = False

        self._progress_popup = None
        self._packaging_window = None

        self.__create_ui()

    def __create_ui(self):
        self.root_widget = ui.Frame()
        with self.root_widget:
            with ui.ScrollingFrame(
                name="Background_GREY_50",
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(5))
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(5))
                        with ui.VStack(style={"margin": 0}):
                            self._package_details_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "MOD DETAILS",
                                info_text="The packaged mod name and any additional details about the mod.",
                                collapsed=False,
                            )
                            with self._package_details_collapsable_frame:
                                self._package_details_widget = _ModPackagingDetailsWidget(self._context_name)

                            ui.Spacer(height=ui.Pixel(16))

                            self._package_output_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "OUTPUT DIRECTORY",
                                info_text=(
                                    "The package output directory is the path where the collected assets will be "
                                    "copied to."
                                ),
                                collapsed=False,
                            )
                            with self._package_output_collapsable_frame:
                                self._package_output_widget = _ModPackagingOutputWidget(self._context_name)
                                self._package_output_valid_sub = (
                                    self._package_output_widget.subscribe_output_validity_changed(
                                        self._update_output_valid
                                    )
                                )

                            ui.Spacer(height=ui.Pixel(16))

                            self._package_layers_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "SELECTED LAYERS",
                                info_text=(
                                    "A list of layers available for packaging.\n"
                                    "The dependencies of the selected layers will be collected so the mod can be "
                                    "packaged in an atomic way.\n\n"
                                    "- Only the layers you have edited should be selected.\n"
                                    "- Any dependencies should be packaged independently.\n"
                                ),
                                collapsed=False,
                            )
                            with self._package_layers_collapsable_frame:
                                self._package_layers_widget = _ModPackagingLayersWidget(self._context_name)
                                self._package_layers_valid_sub = (
                                    self._package_layers_widget.subscribe_layers_validity_changed(
                                        self._update_layers_valid
                                    )
                                )

                            ui.Spacer(height=ui.Pixel(16))

                            self._package_mode_collapsable_frame = _PropertyCollapsableFrameWithInfoPopup(
                                "PACKAGING OPTIONS",
                                info_text=self._get_packaging_options_tooltip(),
                                collapsed=False,
                            )
                            with self._package_mode_collapsable_frame:
                                with ui.VStack(height=0):
                                    row_height = ui.Pixel(24)
                                    ui.Spacer(height=ui.Pixel(8))
                                    with ui.HStack(height=0, spacing=ui.Pixel(8)):
                                        with ui.VStack(width=0, height=0, spacing=ui.Pixel(8)):
                                            with ui.HStack(height=row_height, alignment=ui.Alignment.RIGHT_CENTER):
                                                ui.Label("Mode", width=0, alignment=ui.Alignment.RIGHT_CENTER)
                                            with ui.HStack(height=row_height, alignment=ui.Alignment.RIGHT_CENTER):
                                                ui.Label(
                                                    "Output Extension", width=0, alignment=ui.Alignment.RIGHT_CENTER
                                                )
                                        with ui.VStack(height=0, spacing=ui.Pixel(8)):
                                            with ui.HStack(height=row_height):
                                                self._packaging_mode_combo = ui.ComboBox(
                                                    self._get_default_packaging_mode_index(),
                                                    *[label for _, label in _MOD_PACKAGING_MODE_UI_OPTIONS],
                                                    identifier="packaging_mode_combo",
                                                )
                                                self._packaging_mode_changed_sub = self._packaging_mode_combo.model.get_item_value_model().subscribe_value_changed_fn(
                                                    self._on_packaging_mode_changed
                                                )
                                            with ui.HStack(height=row_height):
                                                self._packaging_output_format_combo = ui.ComboBox(
                                                    self._get_default_packaging_output_format_index(),
                                                    *[label for _, label in _MOD_PACKAGING_OUTPUT_FORMAT_UI_OPTIONS],
                                                    identifier="packaging_output_format_combo",
                                                )
                                                self._packaging_output_format_changed_sub = self._packaging_output_format_combo.model.get_item_value_model().subscribe_value_changed_fn(
                                                    self._on_packaging_output_format_changed
                                                )

                            ui.Spacer(height=ui.Pixel(16))

                            self._export_button = ui.Button(
                                "Package", clicked_fn=self._on_package_pressed, height=ui.Pixel(32)
                            )

                            ui.Spacer(height=ui.Pixel(16))
                        ui.Spacer(width=ui.Pixel(5))
                    ui.Spacer(height=ui.Pixel(5))

    def show(self, visible: bool):
        super().show(visible)
        self.root_widget.visible = visible
        self._package_details_widget.show(visible)
        self._package_output_widget.show(visible)
        self._package_layers_widget.show(visible)

        if visible:
            # Create subscriptions when window becomes visible
            if not self._packaging_progress_sub:
                self._packaging_progress_sub = self._packaging_core.subscribe_packaging_progress(
                    self._on_packaging_progress
                )
            if not self._packaging_completed_sub:
                self._packaging_completed_sub = self._packaging_core.subscribe_packaging_completed(
                    lambda e, f, c: ensure_future(self._on_packaging_completed(e, f, c))
                )
        else:
            # Destroy subscriptions when window becomes invisible
            self._packaging_progress_sub = None
            self._packaging_completed_sub = None

    def _update_output_valid(self, is_valid: bool):
        self._output_valid = is_valid
        self._update_export_button_state()

    def _update_layers_valid(self, is_valid: bool):
        self._layers_valid = is_valid
        self._update_export_button_state()

    def _update_export_button_state(self):
        self._export_button.enabled = self._output_valid and self._layers_valid
        self._export_button.tooltip = ""
        if not self._output_valid:
            self._export_button.tooltip += "The selected output directory is invalid.\n"
        if not self._layers_valid:
            self._export_button.tooltip += "The current layer selection is invalid.\n"

    def _on_package_pressed(self, silent: bool = False, ignored_errors: list[tuple[str, str, str]] = None):
        output_url = _OmniUrl(self._package_output_widget.output_path)

        @omni.usd.handle_exception
        async def delete_existing_output_directory() -> bool:
            try:
                await _OmniClientWrapper.delete(str(output_url))
            except Exception as e:  # noqa: BLE001
                ensure_future(
                    self._on_packaging_completed(
                        [f"Unable to delete the existing package output directory: {e}"], [], False
                    )
                )
                return False

            self._package_output_widget.refresh_output_directory_state()
            return True

        @omni.usd.handle_exception
        async def package(success, error, delete_existing_output: bool = False):
            await omni.kit.app.get_app().next_update_async()
            if success:
                if delete_existing_output and not await delete_existing_output_directory():
                    return
                self._packaging_core.package(
                    {
                        "context_name": self._MOD_PACKAGING_CONTEXT,
                        "mod_layer_paths": [
                            layer.realPath for layer in self._layer_manager.get_layers_of_type(_LayerType.replacement)
                        ],
                        "selected_layer_paths": self._package_layers_widget.packaged_layers,
                        "output_directory": self._package_output_widget.output_path,
                        "packaging_mode": self._get_selected_packaging_mode(),
                        "output_format": self._get_selected_packaging_output_format(),
                        "mod_name": self._package_details_widget.mod_name,
                        "mod_version": self._package_details_widget.mod_version,
                        "mod_details": self._package_details_widget.mod_details,
                        "ignored_errors": ignored_errors,
                    }
                )
            else:
                ensure_future(self._on_packaging_completed([error], [], False))

        def start_packaging(should_save: bool, delete_existing_output: bool):
            if should_save:
                omni.kit.window.file.save(
                    on_save_done=lambda s, e: ensure_future(package(s, e, delete_existing_output))
                )
            else:
                ensure_future(package(True, "", delete_existing_output))

        @omni.usd.handle_exception
        async def validate_pending_edits(delete_existing_output: bool):
            # Wait for the previous popup to be hidden to center the following message dialog
            await omni.kit.app.get_app().next_update_async()

            if not silent and self._context and self._context.has_pending_edit():
                _TrexMessageDialog(
                    message="There are some pending edits in your current stage. "
                    "All unsaved changes will be lost after packaging is started.\n\n"
                    "Do you want to save your changes before packaging the mod?",
                    ok_label="Save",
                    middle_label="Discard",
                    cancel_label="Cancel",
                    disable_middle_button=False,
                    ok_handler=partial(start_packaging, True, delete_existing_output),
                    middle_handler=partial(start_packaging, False, delete_existing_output),
                )
            else:
                start_packaging(False, delete_existing_output)

        if not silent and output_url.exists and list(output_url.iterdir()):
            _TrexMessageDialog(
                message="The output directory is not empty.\n\n"
                "Would you like to delete the directory content or cancel the packaging process?",
                ok_handler=lambda: ensure_future(validate_pending_edits(True)),
                ok_label="Delete",
            )
        else:
            ensure_future(validate_pending_edits(False))

    def _get_selected_packaging_mode(self) -> _ModPackagingMode:
        index = self._packaging_mode_combo.model.get_item_value_model().as_int
        return _MOD_PACKAGING_MODE_UI_OPTIONS[index][0]

    def _get_selected_packaging_output_format(self) -> _UsdExtensions | None:
        index = self._packaging_output_format_combo.model.get_item_value_model().as_int
        return _MOD_PACKAGING_OUTPUT_FORMAT_UI_OPTIONS[index][0]

    def _get_persisted_packaging_mode(self) -> _ModPackagingMode:
        persisted_mode = self._settings.get(_SETTINGS_PACKAGING_MODE)
        try:
            return _ModPackagingMode(persisted_mode)
        except (TypeError, ValueError):
            return _ModPackagingMode.FLATTEN

    def _get_persisted_packaging_output_format(self) -> _UsdExtensions | None:
        persisted_output_format = self._settings.get(_SETTINGS_OUTPUT_FORMAT)
        if persisted_output_format == _PRESERVE_OUTPUT_FORMAT_SETTING_VALUE:
            return None
        try:
            return _UsdExtensions(persisted_output_format)
        except (TypeError, ValueError):
            return _UsdExtensions.USD

    def _on_packaging_mode_changed(self, _value_model):
        self._settings.set(_SETTINGS_PACKAGING_MODE, self._get_selected_packaging_mode().value)

    def _on_packaging_output_format_changed(self, _value_model):
        selected_output_format = self._get_selected_packaging_output_format()
        persisted_output_format = (
            _PRESERVE_OUTPUT_FORMAT_SETTING_VALUE if selected_output_format is None else selected_output_format.value
        )
        self._settings.set(_SETTINGS_OUTPUT_FORMAT, persisted_output_format)

    def _get_default_packaging_mode_index(self) -> int:
        persisted_mode = self._get_persisted_packaging_mode()
        for index, (mode_value, _) in enumerate(_MOD_PACKAGING_MODE_UI_OPTIONS):
            if mode_value == persisted_mode:
                return index
        return 0

    def _get_default_packaging_output_format_index(self) -> int:
        persisted_output_format = self._get_persisted_packaging_output_format()
        for index, (format_value, _) in enumerate(_MOD_PACKAGING_OUTPUT_FORMAT_UI_OPTIONS):
            if format_value == persisted_output_format:
                return index
        return 0

    @classmethod
    def _get_packaging_options_tooltip(cls) -> str:
        packaging_mode_lines = "\n".join(
            f"- {label}: {_get_packaging_mode_description(mode_value)}"
            for mode_value, label in _MOD_PACKAGING_MODE_UI_OPTIONS
        )
        output_format_lines = "\n".join(
            f"- {label}: {_get_packaging_output_format_description(format_value)}"
            for format_value, label in _MOD_PACKAGING_OUTPUT_FORMAT_UI_OPTIONS
        )
        return (
            "Choose how dependencies are handled during packaging and which extension the packaged root layer should use.\n\n"
            f"Packaging mode:\n{packaging_mode_lines}\n\n"
            f"Output Extension:\n{output_format_lines}"
        )

    def _on_packaging_progress(self, current: int, total: int, status: str):
        """Packaging progress callback - subscription destroyed when window invisible."""
        if not self._progress_popup:
            self._progress_popup = _ProgressPopup(title="Packaging Mod")
            self._progress_popup.set_cancel_fn(self._packaging_core.cancel)

        if not self._progress_popup.is_visible():
            self._progress_popup.show()

        if self._progress_popup.get_status_text != status:
            self._progress_popup.set_status_text(status)

        self._progress_popup.set_progress(current / total if total > 0 else 0)

    @omni.usd.handle_exception
    async def _on_packaging_completed(
        self, errors: list[str], failed_assets: list[tuple[str, str, str]], was_cancelled: bool
    ):
        if self._progress_popup:
            self._progress_popup.hide()
            self._progress_popup = None

        # Wait for the progress popup to be hidden to center the following message dialog
        await omni.kit.app.get_app().next_update_async()

        self._packaging_errors_resolved_sub = None

        if errors:
            error_popup = _ErrorPopup(
                "Mod Packaging Error",
                "Some errors occurred while packaging the mod.",
                "- " + "\n- ".join([str(e) for e in errors]),
                window_size=(800, 400),
            )
            error_popup.show()
        elif failed_assets:
            self._packaging_window = _PackagingErrorWindow(failed_assets, context_name=self._context_name)
            self._packaging_errors_resolved_sub = self._packaging_window.subscribe_actions_applied(
                lambda ignored_errors: ensure_future(self._retry_packaging(ignored_errors))
            )
        else:
            if not was_cancelled:
                self._package_output_widget.refresh_output_directory_state()
                self._package_output_widget.open_output_path()

            message = (
                "The mod packaging process was cancelled." if was_cancelled else "The mod was successfully packaged."
            )
            title = "Mod Packaging Cancelled" if was_cancelled else "Mod Packaging Successful"
            _TrexMessageDialog(message, title, disable_cancel_button=True)

    @omni.usd.handle_exception
    async def _retry_packaging(self, ignored_errors: list[tuple[str, str, str]]):
        # Wait 1 frame to make sure the dialogs are centered
        await omni.kit.app.get_app().next_update_async()

        self._on_package_pressed(silent=True, ignored_errors=ignored_errors)

    def destroy(self):
        _reset_default_attrs(self)

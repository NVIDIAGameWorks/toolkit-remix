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
from typing import List, Tuple

import omni.appwindow
import omni.kit.window.file
import omni.ui as ui
import omni.usd
from lightspeed.error_popup.window import ErrorPopup as _ErrorPopup
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManagerCore
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.progress_popup.window import ProgressPopup as _ProgressPopup
from lightspeed.trex.mod_packaging_details.widget import ModPackagingDetailsWidget as _ModPackagingDetailsWidget
from lightspeed.trex.mod_packaging_layers.widget import ModPackagingLayersWidget as _ModPackagingLayersWidget
from lightspeed.trex.mod_packaging_output.widget import ModPackagingOutputWidget as _ModPackagingOutputWidget
from lightspeed.trex.packaging.core import PackagingCore as _PackagingCore
from lightspeed.trex.packaging.window import PackagingErrorWindow as _PackagingErrorWindow
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.widget.collapsable_frame import (
    PropertyCollapsableFrameWithInfoPopup as _PropertyCollapsableFrameWithInfoPopup,
)


class ModPackagingPane:
    _MOD_PACKAGING_CONTEXT = "ModPackaging"

    def __init__(self, context_name: str = ""):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_context_name": None,
            "_context": None,
            "_packaging_core": None,
            "_packaging_progress_sub": None,
            "_packaging_completed_sub": None,
            "_packaging_errors_resolved_sub": None,
            "_output_valid": None,
            "_layers_valid": None,
            "_progress_popup": None,
            "_packaging_window": None,
            "_root_frame": None,
            "_package_details_collapsable_frame": None,
            "_package_details_widget": None,
            "_package_output_collapsable_frame": None,
            "_package_output_widget": None,
            "_package_output_valid_sub": None,
            "_package_layers_collapsable_frame": None,
            "_package_layers_widget": None,
            "_redirect_checkbox": None,
            "_export_button": None,
            "_tooltip_window": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._context_name = context_name
        self._context = omni.usd.get_context(self._context_name)
        self._packaging_core = _PackagingCore()
        self._layer_manager = _LayerManagerCore(self._context_name)

        self._packaging_progress_sub = self._packaging_core.subscribe_packaging_progress(self._on_packaging_progress)
        self._packaging_completed_sub = self._packaging_core.subscribe_packaging_completed(
            lambda e, f, c: ensure_future(self._on_packaging_completed(e, f, c))
        )

        self._packaging_errors_resolved_sub = None

        self._output_valid = False
        self._layers_valid = False

        self._progress_popup = None
        self._packaging_window = None

        self.__info_hovered_task = None
        self.__exit_task = False

        self.__create_ui()

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
                        with ui.VStack():
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

                            with ui.HStack(height=0):
                                self._redirect_checkbox = ui.CheckBox(width=0)
                                ui.Spacer(width=ui.Pixel(8))
                                ui.Label("Redirect external mod dependencies", width=0)
                                ui.Spacer()
                                info_image = ui.Image(
                                    name="PropertiesPaneSectionInfo",
                                    width=ui.Pixel(16),
                                    height=ui.Pixel(16),
                                )

                            self._redirect_checkbox.model.set_value(True)
                            info_image.set_mouse_hovered_fn(
                                partial(
                                    self.__on_info_hovered,
                                    info_image,
                                    "Whether the reference dependencies taken from external mods should be redirected\n"  # noqa E501
                                    "or copied in this mod's package during the packaging process.\n\n"
                                    "- Redirecting will allow the mod to use the installed mod's dependencies so updating\n"  # noqa E501
                                    "   a dependency will be as simple as to install the updated dependency.\n"
                                    "- Copying will make sure the mod is completely standalone so no other mods need\n"  # noqa E501
                                    "   to be installed for this mod to be loaded successfully.",
                                )
                            )

                            ui.Spacer(height=ui.Pixel(16))

                            self._export_button = ui.Button(
                                "Package", clicked_fn=self._on_package_pressed, height=ui.Pixel(32)
                            )

                            ui.Spacer(height=ui.Pixel(16))
                        ui.Spacer(width=ui.Pixel(16))

    def show(self, value):
        self._root_frame.visible = value
        self._package_details_widget.show(value)
        self._package_output_widget.show(value)
        self._package_layers_widget.show(value)

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

    def _on_package_pressed(self, silent: bool = False, ignored_errors: List[Tuple[str, str, str]] = None):
        @omni.usd.handle_exception
        async def package(success, error):
            await omni.kit.app.get_app().next_update_async()
            if success:
                self._packaging_core.package(
                    {
                        "context_name": self._MOD_PACKAGING_CONTEXT,
                        "mod_layer_paths": [
                            layer.realPath for layer in self._layer_manager.get_layers(_LayerType.replacement)
                        ],
                        "selected_layer_paths": self._package_layers_widget.packaged_layers,
                        "output_directory": self._package_output_widget.output_path,
                        "redirect_external_dependencies": self._redirect_checkbox.model.get_value_as_bool(),
                        "mod_name": self._package_details_widget.mod_name,
                        "mod_version": self._package_details_widget.mod_version,
                        "mod_details": self._package_details_widget.mod_details,
                        "ignored_errors": ignored_errors,
                    }
                )
            else:
                ensure_future(self._on_packaging_completed([error], [], False))

        def start_packaging(should_save: bool):
            if should_save:
                omni.kit.window.file.save(on_save_done=lambda s, e: ensure_future(package(s, e)))
            else:
                ensure_future(package(True, ""))

        @omni.usd.handle_exception
        async def validate_pending_edits():
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
                    ok_handler=partial(start_packaging, True),
                    middle_handler=partial(start_packaging, False),
                )
            else:
                start_packaging(False)

        output_url = _OmniUrl(self._package_output_widget.output_path)
        if not silent and output_url.exists and list(output_url.iterdir()):
            _TrexMessageDialog(
                message="The output directory is not empty.\n\n"
                "Would you like to delete the directory content or cancel the packaging process?",
                ok_handler=partial(ensure_future, validate_pending_edits()),
                ok_label="Delete",
            )
        else:
            ensure_future(validate_pending_edits())

    def _on_packaging_progress(self, current: int, total: int, status: str):
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
        self, errors: List[str], failed_assets: List[Tuple[str, str, str]], was_cancelled: bool
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
            message = (
                "The mod packaging process was cancelled." if was_cancelled else "The mod was successfully packaged."
            )
            title = "Mod Packaging Cancelled" if was_cancelled else "Mod Packaging Successful"
            _TrexMessageDialog(message, title, disable_cancel_button=True)

    @omni.usd.handle_exception
    async def _retry_packaging(self, ignored_errors: List[Tuple[str, str, str]]):
        # Wait 1 frame to make sure the dialogs are centered
        await omni.kit.app.get_app().next_update_async()

        self._on_package_pressed(silent=True, ignored_errors=ignored_errors)

    def __on_info_hovered(self, icon_widget, tooltip, hovered):
        self._tooltip_window = None
        if hovered:
            if self.__info_hovered_task:
                self.__info_hovered_task.cancel()
            self.__exit_task = False
            self.__info_hovered_task = ensure_future(self.__deferred_on_info_hovered(icon_widget, tooltip))
        else:
            self.__exit_task = True
            if self.__info_hovered_task:
                self.__info_hovered_task.cancel()

    @omni.usd.handle_exception
    async def __deferred_on_info_hovered(self, icon_widget, tooltip):
        if self.__exit_task:
            return
        flags = ui.WINDOW_FLAGS_POPUP
        flags |= ui.WINDOW_FLAGS_NO_TITLE_BAR
        flags |= ui.WINDOW_FLAGS_NO_DOCKING
        flags |= ui.WINDOW_FLAGS_NO_BACKGROUND
        flags |= ui.WINDOW_FLAGS_NO_RESIZE
        flags |= ui.WINDOW_FLAGS_NO_COLLAPSE
        flags |= ui.WINDOW_FLAGS_NO_CLOSE
        flags |= ui.WINDOW_FLAGS_NO_SCROLLBAR
        self._tooltip_window = ui.Window(
            "Context Info",
            width=600,
            height=100,
            visible=True,
            flags=flags,
            position_x=icon_widget.screen_position_x + icon_widget.computed_width,
            position_y=icon_widget.screen_position_y,
        )
        with self._tooltip_window.frame:
            with ui.ZStack():
                ui.Rectangle(name="PropertiesPaneSectionWindowBackground")
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(8))
                    with ui.VStack():
                        ui.Spacer(height=ui.Pixel(8))
                        label = ui.Label(tooltip, height=0, width=0, identifier="context_tooltip")
                        ui.Spacer(height=ui.Pixel(8))
                    ui.Spacer(width=ui.Pixel(8))

        await omni.kit.app.get_app().next_update_async()

        self._tooltip_window.width = label.computed_width + 24
        self._tooltip_window.height = label.computed_height + 24

        size = omni.appwindow.get_default_app_window().get_size()

        if self._tooltip_window.width > size[0] - self._tooltip_window.position_x - 8:
            self._tooltip_window.position_x = size[0] - self._tooltip_window.width - 8
            # Override bottom of the screen, shift above icon
            if self._tooltip_window.height > size[1] - self._tooltip_window.position_y - 8:
                self._tooltip_window.position_y = self._tooltip_window.position_y - 72
            # Otherwise shift under the icon
            else:
                self._tooltip_window.position_y = self._tooltip_window.position_y + 16

    def destroy(self):
        _reset_default_attrs(self)

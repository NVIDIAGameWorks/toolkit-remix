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
from pathlib import Path
from typing import Callable, List, Optional

from lightspeed.common import constants as _constants
from lightspeed.trex.capture.core.shared import Setup as _CaptureCoreSetup
from lightspeed.trex.capture_tree.model import CaptureTreeDelegate as _CaptureTreeDelegate
from lightspeed.trex.capture_tree.model import CaptureTreeItem as _CaptureTreeItem
from lightspeed.trex.capture_tree.model import CaptureTreeModel as _CaptureTreeModel
from lightspeed.trex.project_wizard.core import ProjectWizardKeys as _ProjectWizardKeys
from lightspeed.trex.project_wizard.core import ProjectWizardSchema as _ProjectWizardSchema
from lightspeed.trex.project_wizard.file_picker.widget import FilePickerWidget as _FilePickerWidget
from omni import client, kit, ui, usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import async_wrap as _async_wrap
from omni.flux.wizard.widget import WizardPage as _WizardPage


class SetupPage(_WizardPage):
    LABEL_WIDTH = 140
    TREE_HEIGHT = 100

    def __init__(
        self,
        context_name: str = "",
        previous_page: Optional[_WizardPage] = None,
        next_page: Optional[_WizardPage] = None,
    ):
        super().__init__(
            previous_page=previous_page, next_page=next_page, next_text="Select Mods", done_text="Create", blocked=True
        )

        default_attr = self._default_attr
        default_attr.update(
            {
                "_context_name": None,
                "_capture_core": None,
                "_capture_model": None,
                "_capture_delegate": None,
                "_open_or_create": None,
                "_project_path_valid": None,
                "_remix_path_valid": None,
                "_capture_selected": None,
                "_project_path_picker": None,
                "_capture_overlay_widget": None,
                "_capture_frame": None,
                "_capture_background": None,
                "_capture_tree": None,
                "_sub_project_file_picker_opened": None,
                "_sub_project_file_picker_closed": None,
                "_sub_remix_file_picker_opened": None,
                "_sub_remix_file_picker_closed": None,
            }
        )

        self._context_name = context_name
        self._capture_core = _CaptureCoreSetup(self._context_name)

        self._capture_model = _CaptureTreeModel(context_name=self._context_name, show_progress=False)
        self._capture_delegate = _CaptureTreeDelegate(preview_on_hover=False)

        self._open_or_create = True

        self._project_path_valid = False
        self._remix_path_valid = False
        self._capture_selected = False

        self._project_path_picker = None
        self._capture_overlay_widget = None
        self._capture_frame = None
        self._capture_background = None
        self._capture_tree = None

        self._sub_project_file_picker_opened = None
        self._sub_project_file_picker_closed = None
        self._sub_remix_file_picker_opened = None
        self._sub_remix_file_picker_closed = None

        self.__on_file_picker_opened = _Event()
        self.__on_file_picker_closed = _Event()

    @property
    def open_or_create(self) -> bool:
        """
        Whether the setup is to open an existing project or create a new project
        """
        return self._open_or_create

    @open_or_create.setter
    def open_or_create(self, value: bool) -> None:
        """
        Whether the setup is to open an existing project or create a new project
        """
        self._open_or_create = value
        self._done_text = "Open" if self.open_or_create else "Create"

        self.payload = {_ProjectWizardKeys.EXISTING_PROJECT.value: value}

    def __validate_project_path(self, project_path: str):
        validation_error = None
        try:
            _ProjectWizardSchema.is_project_file_valid(
                Path(project_path or ""),
                {
                    _ProjectWizardKeys.EXISTING_PROJECT.value: self.open_or_create,
                    _ProjectWizardKeys.REMIX_DIRECTORY.value: self.payload.get(
                        _ProjectWizardKeys.REMIX_DIRECTORY.value, None
                    ),
                },
            )
        except ValueError as e:
            validation_error = str(e)

        self.__update_validity(project_path_valid=not bool(validation_error))

        return validation_error

    def __validate_remix_path(self, remix_path: str):
        validation_error = None
        try:
            _ProjectWizardSchema.is_remix_directory_valid(Path(remix_path or ""), {})
        except ValueError as e:
            validation_error = str(e)

        self.__update_validity(remix_path_valid=not bool(validation_error))

        return validation_error

    def __update_validity(
        self, project_path_valid: bool = None, remix_path_valid: bool = None, capture_selected: bool = None
    ):
        if project_path_valid is not None:
            self._project_path_valid = project_path_valid
        if remix_path_valid is not None:
            self._remix_path_valid = remix_path_valid
        if capture_selected is not None:
            self._capture_selected = capture_selected

        # Only block capture selected when creating a project
        self.blocked = (
            not self._project_path_valid
            or not self._remix_path_valid
            or (not self._capture_selected and not self._open_or_create)
        )

    def __update_payload_project(self, project_path: Optional[str]):
        if not project_path:
            return
        self.payload = {
            _ProjectWizardKeys.EXISTING_PROJECT.value: self.open_or_create,
            _ProjectWizardKeys.PROJECT_FILE.value: Path(project_path),
        }

    def __update_payload_remix(self, remix_path: str):
        if remix_path:
            self.payload = {
                _ProjectWizardKeys.REMIX_DIRECTORY.value: Path(remix_path),
            }
            # Validate the project again to make sure the project doesn't already exist
            self._project_path_picker.set_validation_error(
                self.__validate_project_path(self.payload.get(_ProjectWizardKeys.PROJECT_FILE.value, None))
            )
        self.__enable_capture_picker(bool(remix_path))

    def __update_payload_capture(self, selection: List[_CaptureTreeItem]):
        if not selection:
            return
        self.payload = {
            _ProjectWizardKeys.CAPTURE_FILE.value: Path(selection[0].path),
        }
        self.__update_validity(capture_selected=bool(self.payload.get(_ProjectWizardKeys.CAPTURE_FILE.value, False)))

    def __enable_capture_picker(self, enable: bool):
        if self.open_or_create:
            return

        if self._capture_background:
            self._capture_background.visible = False

        if self._capture_frame:
            self._capture_frame.clear()
            with self._capture_frame:
                ui.Label(
                    (
                        "Loading available captures..."
                        if enable
                        else f'Select a valid "{_constants.REMIX_FOLDER}" directory to view available captures.'
                    ),
                    alignment=ui.Alignment.LEFT_TOP,
                )

        if enable:
            ensure_future(self.__fetch_capture_files_wrapped(self.__update_capture_picker_ui))

        if self._capture_overlay_widget:
            self._capture_overlay_widget.visible = not enable

    @usd.handle_exception
    async def __fetch_capture_files_wrapped(self, callback):
        wrapped_fn = _async_wrap(self.__fetch_capture_files)
        captures = await wrapped_fn()

        callback(captures)

    def __fetch_capture_files(self):
        captures = []
        captures_dir = (
            Path(self.payload.get(_ProjectWizardKeys.REMIX_DIRECTORY.value, "")) / _constants.REMIX_CAPTURE_FOLDER
        )

        result, entries = client.list(str(captures_dir))
        if result == client.Result.OK:
            for entry in entries:
                if Path(entry.relative_path).suffix not in _constants.USD_EXTENSIONS:
                    continue

                capture_path = captures_dir / entry.relative_path
                if not self._capture_core.is_capture_file(str(capture_path)):
                    continue

                captures.append(str(capture_path))

        return captures

    def __update_capture_picker_ui(self, capture_files: List[str]):
        if not self._capture_frame:
            return

        self._capture_frame.clear()

        if not capture_files:
            with self._capture_frame:
                with ui.VStack():
                    ui.Label("No capture available.", name="WizardDescription", height=0)
                    ui.Label("Create a capture in the runtime before creating a project.", height=0)
            return

        if self._capture_background:
            self._capture_background.visible = True

        self._capture_model.refresh([(path, self._capture_core.get_capture_image(path)) for path in capture_files])

        with self._capture_frame:
            self._capture_tree = ui.TreeView(
                self._capture_model,
                delegate=self._capture_delegate,
                root_visible=False,
                header_visible=False,
                columns_resizable=False,
                selection_changed_fn=self.__update_payload_capture,
                identifier="CaptureTree",
            )

        ensure_future(self.__select_current_capture_deferred())

    async def __select_current_capture_deferred(self):
        await kit.app.get_app().next_update_async()

        current_capture = self.payload.get(_ProjectWizardKeys.CAPTURE_FILE.value, None)
        if current_capture:
            filtered_items = [
                i for i in self._capture_model.get_item_children(None) if str(i.path) == str(current_capture)
            ]
            self._capture_tree.selection = filtered_items

    def create_ui(self):
        with ui.VStack():
            ui.Spacer(height=ui.Pixel(16), width=0)

            if self.open_or_create:
                ui.Label(
                    "The selected project was not setup correctly for this environment.",
                    name="WizardDescription",
                    alignment=ui.Alignment.CENTER,
                )
                ui.Spacer(height=ui.Pixel(8), width=0)

            ui.Label(
                (
                    "Choose your existing project's location."
                    if self.open_or_create
                    else "Choose a location where your project will be saved."
                ),
                name="WizardDescription",
                alignment=ui.Alignment.CENTER,
            )

            ui.Label(
                f'Choose the game\'s "{_constants.REMIX_FOLDER}" directory.',
                name="WizardDescription",
                alignment=ui.Alignment.CENTER,
            )

            if not self.open_or_create:
                ui.Label(
                    "Choose a capture from the list if applicable.",
                    name="WizardDescription",
                    alignment=ui.Alignment.CENTER,
                )

            ui.Spacer(height=ui.Pixel(24), width=0)
            ui.Rectangle(height=ui.Pixel(1), name="WizardSeparator")
            ui.Spacer(height=ui.Pixel(16), width=0)

            with ui.HStack():
                ui.Label(
                    "Project File Location",
                    name="WizardDescription",
                    alignment=ui.Alignment.RIGHT_CENTER,
                    width=self.LABEL_WIDTH,
                )
                ui.Spacer(width=ui.Pixel(8), height=0)

                save_label = "Select a project file location"
                self._project_path_picker = _FilePickerWidget(
                    save_label,
                    False,
                    self.__validate_project_path,
                    self.__update_payload_project,
                    current_path=self.payload.get(_ProjectWizardKeys.PROJECT_FILE.value, None),
                    apply_button_label=(
                        "Open" if self.payload.get(_ProjectWizardKeys.EXISTING_PROJECT.value, False) else "Save As"
                    ),
                    placeholder_label=save_label,
                )
                self._sub_project_file_picker_opened = self._project_path_picker.subscribe_file_picker_opened(
                    self._on_file_picker_opened
                )
                self._sub_project_file_picker_closed = self._project_path_picker.subscribe_file_picker_closed(
                    self._on_file_picker_closed
                )

            ui.Spacer(height=ui.Pixel(8), width=0)

            with ui.HStack():
                ui.Label(
                    "Remix Directory",
                    name="WizardDescription",
                    alignment=ui.Alignment.RIGHT_CENTER,
                    width=self.LABEL_WIDTH,
                )
                ui.Spacer(width=ui.Pixel(8), height=0)

                remix_label = f'Select the game\'s "{_constants.REMIX_FOLDER}" directory'
                remix_file_picker = _FilePickerWidget(
                    remix_label,
                    True,
                    self.__validate_remix_path,
                    self.__update_payload_remix,
                    current_path=self.payload.get(_ProjectWizardKeys.REMIX_DIRECTORY.value, None),
                    apply_button_label="Select",
                    placeholder_label=remix_label,
                )
                self._sub_remix_file_picker_opened = remix_file_picker.subscribe_file_picker_opened(
                    self._on_file_picker_opened
                )
                self._sub_remix_file_picker_closed = remix_file_picker.subscribe_file_picker_closed(
                    self._on_file_picker_closed
                )

            if not self.open_or_create:
                ui.Spacer(height=ui.Pixel(16), width=0)
                ui.Rectangle(height=ui.Pixel(1), name="WizardSeparator")
                ui.Spacer(height=ui.Pixel(24), width=0)

                with ui.ZStack():
                    with ui.HStack():
                        ui.Label(
                            "Capture",
                            name="WizardDescription",
                            alignment=ui.Alignment.RIGHT_TOP,
                            width=self.LABEL_WIDTH,
                        )
                        ui.Spacer(width=ui.Pixel(8), height=0)

                        with ui.ZStack():
                            self._capture_background = ui.Rectangle(name="WizardTreeBackground")
                            self._capture_frame = ui.ScrollingFrame(
                                name="PropertiesPaneSection",
                                height=ui.Pixel(self.TREE_HEIGHT),
                            )
                            with self._capture_frame:
                                pass
                    with ui.Frame(separate_window=True):  # Keep the Z order
                        self._capture_overlay_widget = ui.Rectangle(name="DisabledOverlay")

        self.__validate_project_path(self.payload.get(_ProjectWizardKeys.PROJECT_FILE.value, None))
        self.__validate_remix_path(self.payload.get(_ProjectWizardKeys.REMIX_DIRECTORY.value, None))
        self.__enable_capture_picker(bool(self.payload.get(_ProjectWizardKeys.REMIX_DIRECTORY.value, None)))

    def _on_file_picker_opened(self):
        """
        Trigger the __on_file_picker_opened event
        """
        self.__on_file_picker_opened()

    def subscribe_file_picker_opened(self, function: Callable[[], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the file picker is opened.
        """
        return _EventSubscription(self.__on_file_picker_opened, function)

    def _on_file_picker_closed(self):
        """
        Trigger the __on_file_picker_closed event
        """
        self.__on_file_picker_closed()

    def subscribe_file_picker_closed(self, function: Callable[[], None]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Called when the file picker is closed.
        """
        return _EventSubscription(self.__on_file_picker_closed, function)

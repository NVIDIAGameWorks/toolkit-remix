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
from pathlib import Path
from typing import List, Optional

from lightspeed.common import constants as _constants
from lightspeed.trex.project_wizard.core import ProjectWizardKeys as _ProjectWizardKeys
from lightspeed.trex.replacement.core.shared import Setup as _AssetReplacementCore
from omni import client, ui, usd
from omni.flux.utils.common import async_wrap as _async_wrap
from omni.flux.wizard.widget import WizardPage as _WizardPage

from .selection_tree.delegate import ModSelectionDelegate as _ModSelectionDelegate
from .selection_tree.model import ModSelectionModel as _ModSelectionModel


class ExistingModsPage(_WizardPage):
    TREE_HEIGHT = 184

    def __init__(self, context_name: str = "", previous_page: Optional[_WizardPage] = None):
        super().__init__(previous_page=previous_page, done_text="Create", blocked=True)

        default_attr = self._default_attr
        default_attr.update(
            {
                "_set_mod_file": None,
                "_available_mods_frame": None,
                "_available_tree": None,
                "_selected_mods_frame": None,
                "_selected_tree": None,
                "_replacement_core": None,
                "_tree_model_available": None,
                "_tree_model_selected": None,
                "_tree_delegate": None,
                "_available_item_dropped_sub": None,
                "_selected_item_dropped_sub": None,
            }
        )

        self._set_mod_file = False

        self._available_mods_frame = None
        self._available_tree = None
        self._selected_mods_frame = None
        self._selected_tree = None

        self._replacement_core = _AssetReplacementCore(context_name)

        self._tree_model_available = _ModSelectionModel()
        self._tree_model_selected = _ModSelectionModel()
        self._tree_delegate = _ModSelectionDelegate()

        self._available_item_dropped_sub = self._tree_model_available.subscribe_item_dropped(
            partial(self.__on_item_dropped, True)
        )
        self._selected_item_dropped_sub = self._tree_model_selected.subscribe_item_dropped(
            partial(self.__on_item_dropped, False)
        )

    @property
    def set_mod_file(self) -> bool:
        return self._set_mod_file

    @set_mod_file.setter
    def set_mod_file(self, value: bool) -> None:
        self._set_mod_file = value

    def __on_item_dropped(self, is_available: bool, path: str):
        if is_available:
            self._tree_model_selected.remove_item(path)
        else:
            self._tree_model_available.remove_item(path)
        self.__update_payload()

    @usd.handle_exception
    async def __fetch_existing_mods_wrapped(self, callback):
        wrapped_fn = _async_wrap(self.__fetch_existing_mods)
        existing_mods = await wrapped_fn()

        callback(existing_mods)

    def __fetch_existing_mods(self):
        mod_dirs = []
        existing_mods = []

        remix_directory = self.payload.get(_ProjectWizardKeys.REMIX_DIRECTORY.value, None)
        if not remix_directory:
            return existing_mods

        mods_directory = remix_directory / _constants.REMIX_MODS_FOLDER
        if not mods_directory:
            return existing_mods

        result, entries = client.list(str(mods_directory))
        if result == client.Result.OK:
            for entry in entries:
                mod_dirs.append(Path(mods_directory) / entry.relative_path)

        for mod_dir in mod_dirs:
            result, entries = client.list(str(mod_dir))
            if result == client.Result.OK:
                for entry in entries:
                    if Path(entry.relative_path).suffix not in _constants.USD_EXTENSIONS:
                        continue

                    mod_path = mod_dir / entry.relative_path
                    if not self._replacement_core.is_mod_file(str(mod_path)):
                        continue

                    existing_mods.append(mod_path)

        return existing_mods

    def __update_existing_mods_ui(self, existing_mods: List[Path]):
        selected_mods = self.payload.get(_ProjectWizardKeys.EXISTING_MODS.value, [])
        self._tree_model_available.refresh([p for p in existing_mods if p not in selected_mods])

        if self._available_mods_frame:
            self._available_mods_frame.clear()
            with self._available_mods_frame:
                self._available_tree = ui.TreeView(
                    self._tree_model_available,
                    delegate=self._tree_delegate,
                    drop_between_items=True,
                    root_visible=False,
                    header_visible=False,
                    columns_resizable=False,
                    identifier="AvailableModsTree",
                )

        if self._selected_mods_frame:
            self._selected_mods_frame.clear()
            with self._selected_mods_frame:
                self._selected_tree = ui.TreeView(
                    self._tree_model_selected,
                    delegate=self._tree_delegate,
                    drop_between_items=True,
                    root_visible=False,
                    header_visible=False,
                    columns_resizable=False,
                    identifier="SelectedModsTree",
                )

    def __update_payload(self):
        selected_mods = [i.path for i in self._tree_model_selected.get_item_children(None)]

        self.blocked = not selected_mods

        self.payload = {
            _ProjectWizardKeys.EXISTING_MODS.value: selected_mods,
            _ProjectWizardKeys.MOD_FILE.value: selected_mods[0] if selected_mods and self.set_mod_file else None,
        }

    def create_ui(self):
        with ui.VStack(height=0):
            ui.Spacer(height=ui.Pixel(16), width=0)

            ui.Label(
                "Add and order mods in the project by dragging and dropping them to the right-pane.",
                name="WizardDescription",
                alignment=ui.Alignment.CENTER,
            )
            ui.Label(
                "Mods placed higher in the list will have precedence over mods placed lower in the list.",
                name="WizardDescription",
                alignment=ui.Alignment.CENTER,
            )

            ui.Spacer(height=ui.Pixel(24), width=0)
            ui.Rectangle(height=ui.Pixel(1), name="WizardSeparator")
            ui.Spacer(height=ui.Pixel(16), width=0)

            with ui.HStack():
                with ui.VStack():
                    ui.Label("Available Mods", name="WizardDescription", alignment=ui.Alignment.CENTER, height=0)
                    ui.Spacer(height=ui.Pixel(16), width=0)
                    with ui.ZStack():
                        ui.Rectangle(name="WizardTreeBackground")
                        self._available_mods_frame = ui.ScrollingFrame(
                            name="PropertiesPaneSection",
                            height=ui.Pixel(self.TREE_HEIGHT),
                        )
                        with self._available_mods_frame:
                            ui.Label("Loading mods...", alignment=ui.Alignment.CENTER)
                ui.Spacer(width=ui.Pixel(16), height=0)
                with ui.VStack():
                    ui.Label("Selected Mods", name="WizardDescription", alignment=ui.Alignment.CENTER, height=0)
                    ui.Spacer(height=ui.Pixel(16), width=0)
                    with ui.ZStack():
                        ui.Rectangle(name="WizardTreeBackground")
                        self._selected_mods_frame = ui.ScrollingFrame(
                            name="PropertiesPaneSection",
                            height=ui.Pixel(self.TREE_HEIGHT),
                        )
                        with self._selected_mods_frame:
                            ui.Label("Loading mods...", alignment=ui.Alignment.CENTER)

        ensure_future(self.__fetch_existing_mods_wrapped(self.__update_existing_mods_ui))

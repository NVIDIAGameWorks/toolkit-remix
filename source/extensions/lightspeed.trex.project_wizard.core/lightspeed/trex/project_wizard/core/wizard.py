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
import stat
from shutil import copytree
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Union

import carb
import carb.settings
import omni.usd
from lightspeed.common import constants as _constants
from lightspeed.layer_manager.core import LayerManagerCore as _LayerManager
from lightspeed.layer_manager.core import LayerType as _LayerType
from lightspeed.trex.capture.core.shared import Setup as _CaptureCore
from lightspeed.trex.replacement.core.shared import Setup as _ReplacementCore
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common.symlink import create_folder_symlinks as _create_folder_symlinks
from omni.kit.usd.layers import LayerUtils as _LayerUtils

from .items import ProjectWizardSchema as _ProjectWizardSchema

if TYPE_CHECKING:
    from functools import partial


SETTING_JUNCTION_NAME = "/exts/lightspeed.trex.project_wizard.core/force_use_junction"


class ProjectWizardCore:
    CONTEXT_NAME = "ProjectWizard"

    def __init__(self):
        """
        Project Wizard core that creates project scaffolding according to a given schema.
        """
        self.__on_run_finished = _Event()
        self.__on_run_progress = _Event()
        self.__on_log_info = _Event()
        self.__on_log_error = _Event()

    def subscribe_run_finished(self, callback: Union["partial", Callable[[bool, Optional[str]], Any]]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_run_finished, callback)

    def subscribe_run_progress(self, callback: Callable[[float], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_run_progress, callback)

    def subscribe_log_info(self, callback: Callable[[str], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_log_info, callback)

    def subscribe_log_error(self, callback: Callable[[str], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_log_error, callback)

    def setup_project(self, schema: Dict, dry_run: bool = False):
        r"""
        Run the project setup using the given schema.

        Args:
            schema: the schema to use for the project creation. Please see the documentation.
            dry_run: whether a dry run or a "real" run should be performed.

        Examples:
            >>> ProjectWizardCore(
            >>>    {
            >>>         "existing_project": False,
            >>>         "project_path": Path("R:\Remix\projects\MyProject\my_project.usda")
            >>>         "remix_directory": Path("R:\Remix\rtx-remix"),
            >>>         "mod_file": Path("R:\Remix\rtx-remix\mods\ExistingMod1\existing_mod_1.usda"),
            >>>         "existing_mods": [
            >>>             Path("R:\Remix\rtx-remix\mods\ExistingMod1\existing_mod_1.usda")
            >>>         ],
            >>>         "capture_file": Path("R:\Remix\rtx-remix\captures\capture_1.usda"),
            >>>    }
            >>>)
        """
        return asyncio.ensure_future(self.setup_project_async(schema, dry_run))

    @omni.usd.handle_exception
    async def setup_project_async(self, schema: Dict, dry_run: bool = False):
        """
        Asynchronous implementation of setup_project
        """
        await self.setup_project_async_with_exceptions(schema, dry_run)

    async def setup_project_async_with_exceptions(self, schema: Dict, dry_run: bool = False):
        """
        Asynchronous implementation of setup_project, but async without error handling.  This is meant for testing.
        """
        try:
            self._on_run_progress(0)
            self._log_info("Starting project setup")

            context, stage = await self._setup_usd_stage()
            self._on_run_progress(10)

            self._log_info("Setup core and validated schema")
            layer_manager = _LayerManager(self.CONTEXT_NAME)
            capture_core = _CaptureCore(self.CONTEXT_NAME)
            replacement_core = _ReplacementCore(self.CONTEXT_NAME)
            model = _ProjectWizardSchema(**schema)
            self._on_run_progress(20)

            project_directory = model.project_file.parent
            deps_directory = project_directory / _constants.REMIX_DEPENDENCIES_FOLDER
            mods_directory = deps_directory / _constants.REMIX_MODS_FOLDER
            captures_directory = deps_directory / _constants.REMIX_CAPTURE_FOLDER

            if not model.existing_project:
                mods_error = self._create_mods_dir(model.remix_directory, dry_run)

                # If for some reason the user has a file here, tell them
                if mods_error:
                    self._log_error(mods_error)
                    self._on_run_finished(False, error=mods_error)
                    return

            # Item validation should check that the symlinks are already valid if the remix_directory is None
            symlink_error = await self._create_symlinks(
                model, project_directory, deps_directory, model.remix_directory, dry_run
            )
            if symlink_error:
                self._log_error(symlink_error)
                self._on_run_finished(False, error=symlink_error)
                return
            self._on_run_progress(30)

            if model.existing_project:
                self._log_info(f"Project is ready: {model.project_file}")
                self._on_run_progress(100)
                self._on_run_finished(True)
                return

            stage = await self._create_project_layer(model.project_file, layer_manager, context, stage, dry_run)
            self._on_run_progress(40)

            if not dry_run and not stage:
                error_message = f"Could not open stage for the project file ({model.project_file})."
                self._log_error(error_message)
                self._on_run_finished(False, error=error_message)
                return

            await self._insert_capture_layer(capture_core, captures_directory, model.capture_file, dry_run)
            self._on_run_progress(50)

            await self._insert_existing_mods(
                replacement_core, model.existing_mods, model.mod_file, mods_directory, dry_run
            )
            self._on_run_progress(60)

            if model.mod_file:
                mod_file = await self._setup_existing_mod_project(
                    replacement_core, model.mod_file, project_directory, dry_run
                )
            else:
                mod_file = await self._setup_new_mod_project(replacement_core, project_directory, dry_run)
            self._on_run_progress(70)

            await self._save_authoring_layer(mod_file, stage, dry_run)
            self._on_run_progress(80)

            await self._save_project_layer(layer_manager, dry_run)
            self._on_run_progress(90)

            self._destroy_context()

            self._log_info(f"Project is ready: {model.project_file}")
            self._on_run_progress(100)
            self._on_run_finished(True)
        except Exception as e:  # noqa
            error_message = f"An unknown error occurred: {e}"
            self._log_error(error_message)
            self._on_run_finished(False, error=error_message)

    def _create_mods_dir(self, remix_directory, dry_run):
        # Mod dir validation should check if mods dir exists, if not create
        rtx_remix_mods_directory = remix_directory / _constants.REMIX_MODS_FOLDER
        if not rtx_remix_mods_directory.exists():
            if dry_run:
                self._log_info(f"Creating directory at '{rtx_remix_mods_directory}'")
            else:
                rtx_remix_mods_directory.mkdir()

        # If for some reason the user has a file here, tell them
        if not dry_run and not rtx_remix_mods_directory.is_dir():
            return f"Please delete the file named {_constants.REMIX_MODS_FOLDER}, under {_constants.REMIX_FOLDER}."

        return None

    def _on_run_finished(self, result, error=None):
        self.__on_run_finished(result, error)

    def _on_run_progress(self, progress):
        self.__on_run_progress(progress)

    def _log_info(self, message):
        carb.log_info(message)
        self.__on_log_info(message)

    def _log_error(self, message):
        carb.log_error(message)
        self.__on_log_error(message)

    def _destroy_context(self):
        if omni.usd.get_context(self.CONTEXT_NAME):
            omni.usd.destroy_context(self.CONTEXT_NAME)

    async def _setup_usd_stage(self):
        self._log_info("Setting up USD context and stage")

        if not omni.usd.get_context(self.CONTEXT_NAME):
            omni.usd.create_context(self.CONTEXT_NAME)

        context = omni.usd.get_context(self.CONTEXT_NAME)

        await context.new_stage_async()
        stage = context.get_stage()

        return context, stage

    def __symlink_need_get_model(self, model: _ProjectWizardSchema = None, schema: Dict = None):
        if model is None and schema is None:
            raise ValueError("Please specify a model or a schema")
        if schema is not None:
            model = _ProjectWizardSchema(**schema)
        return model

    def need_deps_directory_symlink(self, model: _ProjectWizardSchema = None, schema: Dict = None):
        model = self.__symlink_need_get_model(model=model, schema=schema)
        project_directory = model.project_file.parent
        deps_directory = project_directory / _constants.REMIX_DEPENDENCIES_FOLDER
        return not deps_directory.exists()

    def need_project_directory_symlink(self, model: _ProjectWizardSchema = None, schema: Dict = None):
        model = self.__symlink_need_get_model(model=model, schema=schema)
        remix_directory = model.remix_directory
        if not remix_directory:
            return False
        remix_mods_directory = remix_directory / _constants.REMIX_MODS_FOLDER
        remix_project_directory = remix_mods_directory / model.project_file.parent.stem
        return not remix_project_directory.exists()

    async def _create_symlinks(
        self, model, project_directory, deps_directory, remix_directory, dry_run, create_junction: bool = False
    ):
        if not deps_directory:
            return "Unable to find the path to the project dependencies"

        # Item validation should check that the symlinks are already valid if the remix_directory is None
        if not remix_directory:
            return None

        isettings = carb.settings.get_settings()
        if isettings.get(SETTING_JUNCTION_NAME):
            create_junction = True

        remix_mods_directory = remix_directory / _constants.REMIX_MODS_FOLDER
        remix_project_directory = remix_mods_directory / project_directory.stem

        if not remix_mods_directory.exists():
            if not dry_run:
                remix_mods_directory.mkdir(parents=True)
            else:
                self._log_info(f"Creating parent directory '{remix_mods_directory}'")

        symlink_directories = []

        if self.need_deps_directory_symlink(model=model):
            if not dry_run:
                symlink_directories.append((deps_directory, remix_directory))
            else:
                self._log_info(f"Symlink from '{remix_directory}' to '{deps_directory}'")

        # If the project doesn't already exists in the rtx-remix dir
        if self.need_project_directory_symlink(model=model):
            if not dry_run:
                symlink_directories.append((remix_project_directory, project_directory))
            else:
                self._log_info(f"Symlink from '{project_directory}' to '{remix_project_directory}'")
        elif remix_project_directory != project_directory:
            # Don't allow creating a new project with the same name as an existing project.
            # If OPENING a project from the rtx-remix dir it will have the same path.
            if symlink_directories:
                _create_folder_symlinks(symlink_directories, create_junction=create_junction)
            return (
                f"A project with the same name already exists in the '{_constants.REMIX_FOLDER}' directory: "
                f"'{remix_project_directory}'"
            )

        if symlink_directories:
            _create_folder_symlinks(symlink_directories, create_junction=create_junction)

        return None

    async def _create_project_layer(self, project_file, layer_manager, context, stage, dry_run):
        self._log_info(f"Create project file: {project_file}")

        if dry_run:
            return stage

        layer_manager.create_new_sublayer(_LayerType.workfile, str(project_file), do_undo=False)
        await context.open_stage_async(str(project_file))

        return context.get_stage()

    async def _insert_capture_layer(self, capture_core, deps_captures_directory, capture_file, dry_run):
        deps_capture_file = deps_captures_directory / capture_file.name
        self._log_info(f"Add Sub-Layer to Project: {deps_capture_file}")

        if not dry_run:
            capture_core.import_capture_layer(str(deps_capture_file))

    async def _insert_existing_mods(self, replacement_core, existing_mods, mod_file, mods_directory, dry_run):
        if not existing_mods:
            return

        # Reverse the order since replacement layers will be inserted at index 0
        for mod in reversed(existing_mods):
            if mod == mod_file:
                continue

            mod_path = mods_directory / mod.parent.stem / mod.name
            self._log_info(f"Add Sub-Layer to Project: {mod_path}")

            if not dry_run:
                replacement_core.import_replacement_layer(
                    str(mod_path),
                    use_existing_layer=True,
                    set_edit_target=False,
                    replace_existing=False,
                    sublayer_position=0,
                )

    async def _setup_existing_mod_project(self, replacement_core, mod_file, project_directory, dry_run):
        self._log_info(f"Copy content of '{mod_file.parent}' to '{project_directory}'")

        project_mod_file = project_directory / mod_file.name

        if not dry_run:
            copytree(str(mod_file.parent), str(project_directory), dirs_exist_ok=True)
            project_mod_file.chmod(stat.S_IREAD | stat.S_IWRITE)
            replacement_core.import_replacement_layer(
                str(project_mod_file),
                use_existing_layer=True,
                set_edit_target=True,
                replace_existing=False,
                sublayer_position=0,
            )

        return project_mod_file

    async def _setup_new_mod_project(self, replacement_core, project_directory, dry_run):
        mod_file = project_directory / _constants.REMIX_MOD_FILE
        self._log_info(f"Create replacement layer: {mod_file}")

        if not dry_run:
            replacement_core.import_replacement_layer(
                str(mod_file),
                use_existing_layer=False,
                set_edit_target=True,
                replace_existing=False,
                sublayer_position=0,
            )

        return mod_file

    async def _save_authoring_layer(self, mod_file, stage, dry_run):
        self._log_info(f"Save Active Edit Target to Project: {mod_file}")

        if dry_run or not stage:
            return

        _LayerUtils.save_authoring_layer_to_custom_data(stage)

    async def _save_project_layer(self, layer_manager, dry_run):
        self._log_info("Save the project file content")

        if dry_run:
            return

        layer_manager.save_layer(_LayerType.workfile)

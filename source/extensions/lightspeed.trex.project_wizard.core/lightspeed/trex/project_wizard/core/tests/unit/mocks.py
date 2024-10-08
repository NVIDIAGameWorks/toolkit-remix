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
import subprocess
import sys
from pathlib import Path
from typing import List, Optional
from unittest.mock import Mock, patch

import carb
import omni.usd
from lightspeed.trex.project_wizard.core import ProjectWizardCore
from omni.kit.usd.layers import LayerUtils


class ProjectWizardSchemaMock:
    def __init__(
        self,
        existing_project: bool,
        project_file: Path,
        remix_directory: Optional[Path] = None,
        existing_mods: Optional[List[Path]] = None,
        mod_file: Optional[Path] = None,
        capture_file: Optional[Path] = None,
    ):
        self.existing_project = existing_project
        self.project_file = project_file
        self.remix_directory = remix_directory
        self.existing_mods = existing_mods
        self.mod_file = mod_file
        self.capture_file = capture_file


class WizardMockContext:
    def __init__(
        self,
        schema_mock: ProjectWizardSchemaMock = None,
        mock_wizard_methods: bool = False,
        mock_wizard_event_methods: bool = True,
    ):
        self.__schema_mock = schema_mock
        self.__mock_wizard_methods = mock_wizard_methods
        self.__mock_wizard_event_methods = mock_wizard_event_methods

    def __enter__(self):
        # Define patches
        if self.__mock_wizard_methods:
            self._setup_usd_mock = patch.object(ProjectWizardCore, "_setup_usd_stage")
            self._create_mods_dir = patch.object(ProjectWizardCore, "_create_mods_dir")
            self._create_symlinks_mock = patch.object(ProjectWizardCore, "_create_symlinks")
            self._create_project_mock = patch.object(ProjectWizardCore, "_create_project_layer")
            self._setup_existing_mod_mock = patch.object(ProjectWizardCore, "_setup_existing_mod_project")
            self._setup_new_mod_mock = patch.object(ProjectWizardCore, "_setup_new_mod_project")
            self._insert_existing_mods_mock = patch.object(ProjectWizardCore, "_insert_existing_mods")
            self._insert_capture_layer_mock = patch.object(ProjectWizardCore, "_insert_capture_layer")
            self._save_authoring_layer_mock = patch.object(ProjectWizardCore, "_save_authoring_layer")
            self._save_project_layer_mock = patch.object(ProjectWizardCore, "_save_project_layer")
        if self.__mock_wizard_event_methods:
            self._progress_mock = patch.object(ProjectWizardCore, "_on_run_progress")
            self._finished_mock = patch.object(ProjectWizardCore, "_on_run_finished")
        self._schema_mock = patch("lightspeed.trex.project_wizard.core.wizard._ProjectWizardSchema")
        self._layer_manager_mock = patch("lightspeed.trex.project_wizard.core.wizard._LayerManager")
        self._capture_core_mock = patch("lightspeed.trex.project_wizard.core.wizard._CaptureCore")
        self._replacement_core_mock = patch("lightspeed.trex.project_wizard.core.wizard._ReplacementCore")
        self._log_error_mock = patch.object(carb, "log_error")
        self._save_custom_data_mock = patch.object(LayerUtils, "save_authoring_layer_to_custom_data")
        self._copy_tree_mock = patch("lightspeed.trex.project_wizard.core.wizard.copytree")
        self._check_call_mock = patch.object(subprocess, "check_call")
        self._path_exists_mock = patch.object(Path, "exists")
        self._path_chmod_mock = patch.object(Path, "chmod")
        self._create_context_mock = patch.object(omni.usd, "create_context")
        self._get_context_mock = patch.object(omni.usd, "get_context")

        # Start the patches
        if self.__mock_wizard_methods:
            self.setup_usd_mock = self._setup_usd_mock.start()
            self.create_mods_dir = self._create_mods_dir.start()
            self.create_symlinks_mock = self._create_symlinks_mock.start()
            self.create_project_mock = self._create_project_mock.start()
            self.setup_existing_mod_mock = self._setup_existing_mod_mock.start()
            self.setup_new_mod_mock = self._setup_new_mod_mock.start()
            self.insert_existing_mods_mock = self._insert_existing_mods_mock.start()
            self.insert_capture_layer_mock = self._insert_capture_layer_mock.start()
            self.save_authoring_layer_mock = self._save_authoring_layer_mock.start()
            self.save_project_layer_mock = self._save_project_layer_mock.start()
        if self.__mock_wizard_event_methods:
            self.progress_mock = self._progress_mock.start()
            self.finished_mock = self._finished_mock.start()
        self.schema_mock = self._schema_mock.start()
        self.layer_manager_mock = self._layer_manager_mock.start()
        self.capture_core_mock = self._capture_core_mock.start()
        self.replacement_core_mock = self._replacement_core_mock.start()
        self.log_error_mock = self._log_error_mock.start()
        self.save_custom_data_mock = self._save_custom_data_mock.start()
        self.copy_tree_mock = self._copy_tree_mock.start()
        self.check_call_mock = self._check_call_mock.start()
        self.path_exists_mock = self._path_exists_mock.start()
        self.path_chmod_mock = self._path_chmod_mock.start()
        self.create_context_mock = self._create_context_mock.start()
        self.get_context_mock = self._get_context_mock.start()

        # Setup mocks
        if self.__mock_wizard_methods:
            self.create_mods_dir.return_value = None

            if sys.version_info.minor > 7:
                generic_wizard_future = Mock()
            else:
                generic_wizard_future = asyncio.Future()
                generic_wizard_future.set_result(Mock())
            self.create_project_mock.return_value = generic_wizard_future
            self.insert_existing_mods_mock.return_value = generic_wizard_future
            self.insert_capture_layer_mock.return_value = generic_wizard_future
            self.save_authoring_layer_mock.return_value = generic_wizard_future
            self.save_project_layer_mock.return_value = generic_wizard_future

            if sys.version_info.minor > 7:
                self.create_symlinks_mock.return_value = None
            else:
                symlink_error_future = asyncio.Future()
                symlink_error_future.set_result(None)
                self.create_symlinks_mock.return_value = symlink_error_future

            if sys.version_info.minor > 7:
                self.setup_usd_mock.return_value = (Mock(), Mock())
            else:
                setup_usd_future = asyncio.Future()
                setup_usd_future.set_result((Mock(), Mock()))
                self.setup_usd_mock.return_value = setup_usd_future

            if sys.version_info.minor > 7:
                setup_mod_future = Mock()
            else:
                setup_mod_future = asyncio.Future()
                setup_mod_future.set_result(Mock())
            self.setup_existing_mod_mock.return_value = setup_mod_future
            self.setup_new_mod_mock.return_value = setup_mod_future

        self.schema_mock.return_value = self.__schema_mock

        omni_client_future = asyncio.Future()
        omni_client_future.set_result((True, ""))
        context_mock = Mock()
        context_mock.new_stage_async.return_value = omni_client_future
        context_mock.open_stage_async.return_value = omni_client_future
        context_mock.close_stage_async.return_value = omni_client_future
        self.get_context_mock.return_value = context_mock

        # Return access to the class members
        return self

    def __exit__(self, *args):
        # Stop patches
        if self.__mock_wizard_methods:
            self._setup_usd_mock.stop()
            self._create_mods_dir.stop()
            self._create_symlinks_mock.stop()
            self._create_project_mock.stop()
            self._setup_existing_mod_mock.stop()
            self._setup_new_mod_mock.stop()
            self._insert_existing_mods_mock.stop()
            self._insert_capture_layer_mock.stop()
            self._save_authoring_layer_mock.stop()
            self._save_project_layer_mock.stop()
        if self.__mock_wizard_event_methods:
            self._progress_mock.stop()
            self._finished_mock.stop()
        self._schema_mock.stop()
        self._layer_manager_mock.stop()
        self._capture_core_mock.stop()
        self._replacement_core_mock.stop()
        self._save_custom_data_mock.stop()
        self._copy_tree_mock.stop()
        self._check_call_mock.stop()
        self._path_exists_mock.stop()
        self._path_chmod_mock.stop()
        self._create_context_mock.stop()
        self._get_context_mock.stop()

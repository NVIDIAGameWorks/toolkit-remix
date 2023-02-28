"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import asyncio
import subprocess
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
        self._core_mock = patch("lightspeed.trex.project_wizard.core.wizard._LayerManager")
        self._log_error_mock = patch.object(carb, "log_error")
        self._save_custom_data_mock = patch.object(LayerUtils, "save_authoring_layer_to_custom_data")
        self._copy_tree_mock = patch("lightspeed.trex.project_wizard.core.wizard.copy_tree")
        self._check_call_mock = patch.object(subprocess, "check_call")
        self._path_exists_mock = patch.object(Path, "exists")
        self._path_chmod_mock = patch.object(Path, "chmod")
        self._create_context_mock = patch.object(omni.usd, "create_context")
        self._get_context_mock = patch.object(omni.usd, "get_context")

        # Start the patches
        if self.__mock_wizard_methods:
            self.setup_usd_mock = self._setup_usd_mock.start()
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
        self.core_mock = self._core_mock.start()
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
            generic_wizard_future = asyncio.Future()
            generic_wizard_future.set_result(None)
            self.create_symlinks_mock.return_value = generic_wizard_future
            self.insert_existing_mods_mock.return_value = generic_wizard_future
            self.insert_capture_layer_mock.return_value = generic_wizard_future
            self.save_authoring_layer_mock.return_value = generic_wizard_future
            self.save_project_layer_mock.return_value = generic_wizard_future

            tuple_wizard_future = asyncio.Future()
            tuple_wizard_future.set_result((Mock(), Mock()))
            self.setup_usd_mock.return_value = tuple_wizard_future
            self.create_project_mock.return_value = tuple_wizard_future

            mod_wizard_future = asyncio.Future()
            mod_wizard_future.set_result(Mock())
            self.setup_existing_mod_mock.return_value = mod_wizard_future
            self.setup_new_mod_mock.return_value = mod_wizard_future

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
        self._core_mock.stop()
        self._save_custom_data_mock.stop()
        self._copy_tree_mock.stop()
        self._check_call_mock.stop()
        self._path_exists_mock.stop()
        self._path_chmod_mock.stop()
        self._create_context_mock.stop()
        self._get_context_mock.stop()

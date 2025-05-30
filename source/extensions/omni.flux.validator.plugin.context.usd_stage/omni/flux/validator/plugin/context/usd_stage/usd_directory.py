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

import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Optional, Tuple

import carb.tokens
import omni.client
import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.validator.factory import FIXES_APPLIED as _FIXES_APPLIED
from omni.flux.validator.factory import InOutDataFlow as _InOutDataFlow
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from omni.flux.validator.factory import utils as _validator_factory_utils
from pydantic import Field, model_validator

from .base.context_base_usd import ContextBaseUSD as _ContextBaseUSD


class USDDirectory(_ContextBaseUSD):
    class Data(_ContextBaseUSD.Data):
        directory: str = Field(...)
        recursive: bool = Field(default=True)
        ignore_paths: list[str] | None = Field(default=None)
        save_all_layers_on_exit: bool = Field(default=False)
        close_stage_on_exit: bool = Field(default=False)
        close_dependency_between_round: bool = Field(default=True)
        skip_validated_files: bool = Field(default=False)
        file_validated_fixes: set[str] | None = Field(default=None)
        cooked_files: list[str] | None = Field(default=None)

        _compatible_data_flow_names = ["InOutData"]
        data_flows: Optional[List[_InOutDataFlow]] = Field(default=None)

        @model_validator(mode="after")
        @classmethod
        def file_validated_fixes_set(cls, instance_model: "USDDirectory.Data") -> "USDDirectory.Data":
            if instance_model.skip_validated_files and not instance_model.file_validated_fixes:
                raise ValueError("When `skip_validated_files` is True, `file_validated_fixes` must be set")
            return instance_model

    name = "USDDirectory"
    display_name = "USD Directory"
    tooltip = "This plugin will iterate and open all USD stages in the given path"
    data_type = Data

    @omni.usd.handle_exception
    async def _check(self, schema_data: Data, parent_context: _SetupDataTypeVar) -> Tuple[bool, str]:
        """
        Function that will be called to execute the data.

        Args:
            schema_data: the USD file path to check
            parent_context: context data from the parent context

        Returns: True if the check passed, False if not
        """
        directory_path = omni.client.normalize_url((carb.tokens.get_tokens_interface().resolve(schema_data.directory)))
        directory_url = _OmniUrl(directory_path)

        if not directory_url.is_directory:
            return False, f"Can't find the directory {directory_path}"

        if schema_data.skip_validated_files:
            input_files = await self.__glob_usd_files(
                schema_data.directory,
                recursive=schema_data.recursive,
                ignore_paths=schema_data.ignore_paths,
            )
            files_to_validate = 0
            for input_file in input_files:
                if not schema_data.file_validated_fixes.intersection(
                    _path_utils.read_metadata(input_file, _FIXES_APPLIED) or []
                ):
                    files_to_validate += 1
            if files_to_validate < 1:
                return False, "All the files within the directory were already validated."

        return True, f"Directory {directory_path} ok to read"

    async def _setup(
        self,
        schema_data: Data,
        run_callback: Callable[[_SetupDataTypeVar], Awaitable[None]],
        parent_context: _SetupDataTypeVar,
    ) -> Tuple[bool, str, _SetupDataTypeVar]:
        """
        Function that will be executed to set the data. Here we will open the file path and give the stage

        Args:
            schema_data: the data that we should set. Same data than check()
            run_callback: the validation that will be run in the context of this setup
            parent_context: context data from the parent context

        Returns: True if ok + message + data that need to be passed into another plugin
        """
        directory_path = omni.client.normalize_url((carb.tokens.get_tokens_interface().resolve(schema_data.directory)))
        context = await self._set_current_context(schema_data, parent_context)
        if not context:
            return False, f"The context {schema_data.computed_context} doesn't exist!", None

        usd_file_paths = (
            schema_data.cooked_files  # noqa PLW0212
            if schema_data.cooked_files  # noqa PLW0212
            else await self.__glob_usd_files(
                directory_path, recursive=schema_data.recursive, ignore_paths=schema_data.ignore_paths
            )
        )

        progress = 0
        progress_delta = 1 / len(usd_file_paths)

        files_to_validate = 0
        for i, file_path in enumerate(usd_file_paths):
            if schema_data.skip_validated_files and schema_data.file_validated_fixes.intersection(
                _path_utils.read_metadata(file_path, _FIXES_APPLIED) or []
            ):
                # File was already validated
                continue

            files_to_validate += 1

            _validator_factory_utils.push_input_data(schema_data, [str(file_path)])

            if schema_data.save_all_layers_on_exit:
                _validator_factory_utils.push_output_data(schema_data, [str(file_path)])

            result, error = await context.open_stage_async(file_path)
            if not result:
                return False, f"Can't open the file {file_path: {error}}", None
            progress += progress_delta / 2

            self.on_progress(progress, f"Opened {Path(file_path).name}", True)

            await run_callback(schema_data.computed_context)

            if schema_data.save_all_layers_on_exit:
                result, error, _saved_layers = await context.save_stage_async()
                if not result:
                    return False, f"Can't save the file {file_path: {error}}", None

            if schema_data.close_dependency_between_round and i != len(usd_file_paths) - 1:
                await self._close_stage(schema_data.computed_context)

            progress += progress_delta / 2
            self.on_progress(progress, f"Processed {Path(file_path).name}", True)

        if files_to_validate < 1:
            return False, "All the files within the directory were already validated.", None

        return True, directory_path, usd_file_paths

    async def _on_exit(self, schema_data: Data, parent_context: _SetupDataTypeVar) -> Tuple[bool, str]:
        """
        Function that will be called to after the check of the data. For example, save the input USD stage

        Args:
            schema_data: the data that should be checked
            parent_context: context data from the parent context

        Returns:
            bool: True if the on exit passed, False if not.
            str: the message you want to show, like "Succeeded to exit this context"
        """
        if schema_data.close_stage_on_exit:
            await self._close_stage(schema_data.computed_context)
        return True, "Exit ok"

    @omni.usd.handle_exception
    async def _mass_cook_template(self, schema_data_template: Data) -> Tuple[bool, Optional[str], List[Data]]:
        """
        Take a template as an input and the (previous) result, and edit the result for mass processing.
        Here, for each file input, we generate a list of schema

        Args:
            schema_data_template: the data of the plugin from the schema

        Returns:
            A tuple of the shape `(TemplateCookingSuccess, ErrorMessage, CookingData)`
        """
        # for mass ingestion, from the template, we want to generate multiple schema from the template by input file
        result = []

        # Validate the context inputs are valid
        success, message = await self._check(schema_data_template, None)
        if not success:
            return False, message, result

        input_files = await self.__glob_usd_files(
            schema_data_template.directory,
            recursive=schema_data_template.recursive,
            ignore_paths=schema_data_template.ignore_paths,
        )

        for input_file in input_files:
            if schema_data_template.skip_validated_files and schema_data_template.file_validated_fixes.intersection(
                _path_utils.read_metadata(input_file, _FIXES_APPLIED) or []
            ):
                continue

            schema = self.Data(**schema_data_template.model_dump(serialize_as_any=True))
            schema.cooked_files = [input_file]  # noqa PLW0212
            schema.display_name_mass_template = str(_OmniUrl(input_file).stem)
            schema.display_name_mass_template_tooltip = input_file
            schema.uuid = str(uuid.uuid4())
            result.append(schema)

        return True, None, result

    @omni.usd.handle_exception
    async def _mass_build_ui(self, schema_data: Data) -> Any:
        """
        Build the mass UI of a plugin. A mass UI is a UI that will expose some UI for mass processing. Mass processing
        will call multiple validation core. So this UI exposes controllers that will be passed to each schema.

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        pass

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        with ui.VStack():
            # context
            with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                with ui.HStack(width=ui.Percent(40)):
                    ui.Spacer()
                    ui.Label("Context", name="PropertiesWidgetLabel")
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(4))
                    _context_field = ui.StringField(
                        height=ui.Pixel(18), style_type_name_override="Field", read_only=True
                    )
                    _context_field.model.set_value(
                        schema_data.context_name
                        if schema_data.context_name is not None
                        else (schema_data.computed_context or "None")
                    )
            # file path
            ui.Spacer(height=ui.Pixel(8))
            with ui.HStack(height=ui.Pixel(24), spacing=ui.Pixel(8)):
                with ui.HStack(width=ui.Percent(40)):
                    ui.Spacer()
                    ui.Label("File path", name="PropertiesWidgetLabel")
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(4))
                    _file_field = ui.StringField(height=ui.Pixel(18), style_type_name_override="Field")
                    file_path = carb.tokens.get_tokens_interface().resolve(schema_data.directory)
                    file_path = omni.client.normalize_url(file_path)
                    _file_field.model.set_value(file_path)

    async def __glob_usd_files(self, directory_path: str, recursive: bool = False, ignore_paths: list[str] = None):
        directory_path = _OmniUrl(directory_path).path
        file_paths = []

        if ignore_paths is not None:
            for ignore_path in ignore_paths:
                if ignore_path in directory_path:
                    return file_paths

        result, entries = await omni.client.list_async(directory_path)
        if result != omni.client.Result.OK:
            return False, f"Can't list the files within {directory_path}", None

        for entry in entries:
            file_url = _OmniUrl(directory_path) / entry.relative_path

            if file_url.is_file and file_url.suffix in {".usd", ".usda", ".usdb", ".usdc"}:
                file_paths.append(str(file_url))

            if recursive and file_url.is_directory:
                file_paths.extend(
                    await self.__glob_usd_files(str(file_url), recursive=recursive, ignore_paths=ignore_paths)
                )

        return file_paths

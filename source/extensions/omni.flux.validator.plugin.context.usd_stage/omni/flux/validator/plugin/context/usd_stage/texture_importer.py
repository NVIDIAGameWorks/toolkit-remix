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

import shutil
import uuid
from functools import partial
from typing import Any, Awaitable, Callable, List, Optional, Tuple

import carb
import omni.client
import omni.kit.app
import omni.kit.commands
import omni.kit.undo
import omni.ui as ui
import omni.usd
from omni.flux.asset_importer.core import get_texture_sets as _get_texture_sets
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.asset_importer.core.data_models import TextureTypes as _TextureTypes
from omni.flux.asset_importer.widget.texture_import_list import TextureImportItem as _TextureImportItem
from omni.flux.asset_importer.widget.texture_import_list import TextureImportListModel as _TextureImportListModel
from omni.flux.asset_importer.widget.texture_import_list import TextureImportListWidget as _TextureImportListWidget
from omni.flux.asset_importer.widget.texture_import_list.utils import (
    create_prims_and_link_assets as _create_prims_and_link_assets,
)
from omni.flux.info_icon.widget import InfoIconWidget as _InfoIconWidget
from omni.flux.utils.common.api import send_request as _send_request
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.common.path_utils import get_invalid_extensions as _get_invalid_extensions
from omni.flux.utils.widget.file_pickers import open_file_picker as _open_file_picker
from omni.flux.validator.factory import InOutDataFlow as _InOutDataFlow
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from omni.flux.validator.factory import utils as _validator_factory_utils
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager
from pydantic import validator

from .base.context_base_usd import ContextBaseUSD as _ContextBaseUSD


class TextureImporter(_ContextBaseUSD):
    DEFAULT_UI_WIDTH_PIXEL = 115
    DEFAULT_UI_HEIGHT_PIXEL = 24
    DEFAULT_UI_SPACING_PIXEL = 8

    class Data(_ContextBaseUSD.Data):
        allow_empty_input_files_list: Optional[bool] = False  # Leave before input_files, required in validation
        input_files: List[Tuple[_OmniUrl, _TextureTypes]]
        error_on_texture_types: Optional[List[_TextureTypes]] = None  # if we set texture with this type, it will crash
        create_output_directory_if_missing: bool = True
        output_directory: _OmniUrl
        default_output_endpoint: Optional[str] = None  # An API endpoint to hit up to get the default output directory

        _compatible_data_flow_names = ["InOutData"]
        data_flows: Optional[List[_InOutDataFlow]] = None  # override base argument with the good typing

        @validator("input_files", allow_reuse=True)
        def at_least_one(cls, v, values):  # noqa N805
            if len(v) < 1 and not values.get("allow_empty_input_files_list", False):
                raise ValueError("There should at least be 1 item")
            return v

        @validator("input_files", each_item=True, allow_reuse=True)
        def is_valid(cls, v):  # noqa N805
            result, message = _TextureImportItem.is_valid(v[0])
            if not result:
                raise ValueError(message)
            return v

        @validator("output_directory", allow_reuse=True)
        def can_have_children(cls, v, values):  # noqa N805
            if str(v).strip() == ".":
                # empty path
                return v
            path = carb.tokens.get_tokens_interface().resolve(str(v))
            if path.strip() == ".":
                # token hasn't been set
                return v

            # If we allow to create the output, assume the path is valid and fail during setup
            if values.get("create_output_directory_if_missing"):
                return v

            result, entry = omni.client.stat(path)
            if result != omni.client.Result.OK:
                raise ValueError("The output directory is not valid")
            if not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                raise ValueError("The output directory cannot have children")
            return v

        @validator("output_directory", allow_reuse=True)
        def output_dir_unequal_input_dirs(cls, v, values):  # noqa N805
            for input_file, _ in values.get("input_files", []):
                # check if output_directory is same as input_directory
                if v.path == input_file.parent_url:
                    raise ValueError(f'Output directory "{v}" cannot be the same as any input file directory.')
            return v

        class Config(_ContextBaseUSD.Data.Config):
            validate_assignment = True

    name = "TextureImporter"
    display_name = "Texture Importer"
    tooltip = (
        "This plugin will import a list of textures, assign them to USD materials using the OmniPBR shader, "
        "and process the various textures sequentially."
    )
    data_type = Data

    def __init__(self):
        super().__init__()
        self._output_field = None
        self._output_field_validate_sub = None
        self._output_field_update_sub = None
        self._file_list_field_item_changed_sub = None
        self._file_list_field_type_changed_sub = None
        self._file_list_field = None

    @omni.usd.handle_exception
    async def _check(self, schema_data: Data, parent_context: _SetupDataTypeVar) -> Tuple[bool, str]:
        """
        Function that will be called to execute the data.

        Args:
            schema_data: the USD file path to check, output directory of imported assets
            parent_context: context data from the parent context

        Returns: True if the check passed, False if not
        """
        if len(schema_data.input_files) < 1:
            return False, "ERROR: No input file paths were given."

        if schema_data.error_on_texture_types:
            not_allowed = set()
            for _, texture_type in schema_data.input_files:
                if texture_type in schema_data.error_on_texture_types:
                    not_allowed.add(str(texture_type))
            if not_allowed:
                return False, f"Texture type {','.join(list(not_allowed))} is not allowed"

        stripped_output = str(schema_data.output_directory).strip()
        if not stripped_output or stripped_output == ".":
            return False, "ERROR: An output directory must be set."

        return True, "The selected files are valid."

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

        Returns: True if ok + message + list of paths of the imported files
        """
        imported_files = []
        output_dir = _OmniUrl(carb.tokens.get_tokens_interface().resolve(str(schema_data.output_directory)))

        # Create the output directory if allowed
        if schema_data.create_output_directory_if_missing:
            try:
                await omni.client.create_folder_async(str(output_dir))
            except Exception as e:  # noqa PLW0718
                return False, str(e), None

        # Copy every input file in the output directory
        for input_file in schema_data.input_files:
            input_file_path, input_file_type = input_file
            input_path = carb.tokens.get_tokens_interface().resolve(str(input_file_path))
            input_path = omni.client.normalize_url(input_path)

            _validator_factory_utils.push_input_data(schema_data, [str(input_path)])

            output_path = carb.tokens.get_tokens_interface().resolve(str((output_dir / _OmniUrl(input_path).name)))
            output_path = omni.client.normalize_url(output_path)

            try:
                shutil.copyfile(str(input_path), str(output_path))
            except (shutil.SameFileError, OSError) as e:
                return False, str(e), None

            _validator_factory_utils.push_output_data(schema_data, [str(output_path)])

            # Make sure to retain what kind of texture we imported
            imported_files.append((output_path, _TextureTypes[input_file_type]))  # noqa

        context = await self._set_current_context(schema_data, parent_context)
        if not context:
            return False, f"The context '{schema_data.computed_context or 'None'}' doesn't exist!", None

        # Make sure the context has a clean, valid stage
        await context.new_stage_async()

        # Create prims for the textures and link the assets in the attributes
        await _create_prims_and_link_assets(schema_data.computed_context, imported_files)

        # Run the check plugins
        await run_callback(schema_data.computed_context)

        return True, "Textures were imported successfully", imported_files

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
        # for mass ingestion, from the template, we want to generate multiple schema from the template by PBR material
        result = []

        # Validate the context inputs are valid
        success, message = await self._check(schema_data_template, None)
        if not success:
            return False, message, []

        all_paths = {str(texture_url): texture_type for texture_url, texture_type in schema_data_template.input_files}
        texture_sets = _get_texture_sets(list(all_paths.keys()))
        for mat_prefix, texture_types in texture_sets.items():
            schema = self.Data(**schema_data_template.dict())
            schema.input_files = [(path, all_paths[str(_OmniUrl(path))]) for _, path in texture_types]
            schema.display_name_mass_template = str(mat_prefix)
            schema.display_name_mass_template_tooltip = "\n".join([str(_OmniUrl(path)) for _, path in texture_types])
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
        # this plugin will promote the regular UI into the mass UI.
        # meaning we don't need to show the UI into the regular validation UI
        # we use a custom kwargs (force_build_ui) for that
        await self._build_ui(schema_data, force_build_ui=True)

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data, force_build_ui: bool = False) -> Any:
        """
        Build the UI for the plugin
        """
        if schema_data.expose_mass_ui and not force_build_ui:
            return

        def __filter_drop(paths: List[str]):
            return [
                path
                for path in paths
                if not _get_invalid_extensions(file_paths=[path], valid_extensions=_SUPPORTED_TEXTURE_EXTENSIONS)
            ]

        with ui.VStack():
            # context
            with ui.HStack(
                height=ui.Pixel(self.DEFAULT_UI_HEIGHT_PIXEL), spacing=ui.Pixel(self.DEFAULT_UI_SPACING_PIXEL)
            ):
                ui.Label(
                    "Context",
                    name="PropertiesWidgetLabel",
                    alignment=ui.Alignment.RIGHT_TOP,
                    width=ui.Pixel(self.DEFAULT_UI_WIDTH_PIXEL),
                )
                context_field = ui.StringField(
                    style_type_name_override="Field", enabled=False, identifier="context_field", read_only=True
                )
                ui.Spacer(width=ui.Pixel(self.DEFAULT_UI_SPACING_PIXEL), height=0)

            context_field.model.set_value(schema_data.context_name or schema_data.computed_context or "None")

            ui.Spacer(height=ui.Pixel(self.DEFAULT_UI_SPACING_PIXEL))

            # file input
            with ui.HStack(
                height=ui.Pixel(6 * self.DEFAULT_UI_HEIGHT_PIXEL), spacing=ui.Pixel(self.DEFAULT_UI_SPACING_PIXEL)
            ):
                ui.Label(
                    "Input File Paths",
                    name="PropertiesWidgetLabel",
                    alignment=ui.Alignment.RIGHT_TOP,
                    width=ui.Pixel(self.DEFAULT_UI_WIDTH_PIXEL),
                )
                self._file_list_field = _TextureImportListWidget(
                    allow_empty_input_files_list=schema_data.allow_empty_input_files_list,
                    enable_drop=True,
                    drop_filter_fn=__filter_drop,
                )
                _InfoIconWidget(
                    "The list of texture files to import.\n\n"
                    "The end of the filename determines the file type.\n\n"
                    "For example, 'T_Metal_01_Normal.png correlates to a 'Normal' texture type.\n\n"
                    "If this tool does not pick the correct texture type, use the dropdown to specify the given"
                    " texture file.\n\n"
                    "See filename examples by hovering the cursor over the dropdowns.\n\n"
                    "NOTE: At least one file is required."
                )

            self._file_list_field.model.refresh([(p, _TextureTypes[t]) for p, t in schema_data.input_files])  # noqa
            self._file_list_field_item_changed_sub = self._file_list_field.model.subscribe_item_changed_fn(
                partial(self.__update_file_list, schema_data, self._file_list_field.model)
            )
            self._file_list_field_type_changed_sub = self._file_list_field.model.subscribe_texture_type_changed(
                partial(self.__update_file_list, schema_data, self._file_list_field.model)
            )

            ui.Spacer(height=ui.Pixel(self.DEFAULT_UI_SPACING_PIXEL))

            # output directory
            with ui.HStack(
                height=ui.Pixel(self.DEFAULT_UI_HEIGHT_PIXEL), spacing=ui.Pixel(self.DEFAULT_UI_SPACING_PIXEL)
            ):
                ui.Label(
                    "Output Directory",
                    name="PropertiesWidgetLabel",
                    alignment=ui.Alignment.RIGHT_TOP,
                    width=ui.Pixel(self.DEFAULT_UI_WIDTH_PIXEL),
                )
                self._output_field = ui.StringField(
                    style_type_name_override="Field", identifier="output_directory_field"
                )
                ui.Image(
                    "",
                    name="OpenFolder",
                    identifier="output_directory_open_file_picker",
                    height=ui.Pixel(20),
                    width=ui.Pixel(20),
                    mouse_pressed_fn=partial(self.__open_dialog, schema_data, self._output_field.model),
                )
                _InfoIconWidget("The directory to import the converted input files to.")

            if schema_data.default_output_endpoint:
                try:
                    response = await _send_request("GET", schema_data.default_output_endpoint)
                    output_directory = response.get("asset_path")

                    schema_data.output_directory = _OmniUrl(output_directory)
                except RuntimeError:
                    pass

            self._output_field.model.set_value(
                carb.tokens.get_tokens_interface().resolve(str(schema_data.output_directory))
            )

            self._output_field_validate_sub = self._output_field.model.subscribe_value_changed_fn(
                partial(self.__validate_output_directory, schema_data)
            )
            self._output_field_update_sub = self._output_field.model.subscribe_end_edit_fn(
                partial(self.__update_output_directory, schema_data)
            )

            ui.Spacer(height=ui.Pixel(self.DEFAULT_UI_SPACING_PIXEL))

    def __open_dialog(self, schema_data: Data, model: ui.AbstractValueModel, _x, _y, b, _m):
        if b != 0:
            return
        default_dir = carb.tokens.get_tokens_interface().resolve(str(schema_data.output_directory))
        _open_file_picker(
            "Choose output directory",
            partial(self.__update_output_directory_from_string, schema_data, model),
            lambda *_: None,
            apply_button_label="Select",
            file_extension_options=[],
            select_directory=True,
            current_file=default_dir,
            validate_selection=partial(self.__validate_dialog_selection, schema_data, model),
            validation_failed_callback=partial(self.__show_validation_failed_dialog, schema_data, model),
        )

    def __show_validation_failed_dialog(
        self, schema_data: Data, model: ui.AbstractValueModel, dirname: str, filename: str
    ):
        try:
            schema_data.output_directory = _OmniUrl(dirname)
        except ValueError as e:
            PromptManager.post_simple_prompt(
                "An Error Occurred",
                str(e),
                ok_button_info=PromptButtonInfo("Okay", None),
                cancel_button_info=None,
                modal=True,
                no_title_bar=True,
            )

    def __validate_dialog_selection(self, schema_data: Data, model: ui.AbstractValueModel, dirname: str, filename: str):
        try:
            schema_data.output_directory = _OmniUrl(dirname)
            return True
        except ValueError:
            return False

    def __validate_output_directory(self, schema_data: Data, model: ui.AbstractValueModel):
        try:
            # trigger all checks for output_directory
            schema_data.output_directory = _OmniUrl(model.get_value_as_string())
            # Valid output directory
            self._output_field.style_type_name_override = "Field"
            self._output_field.tooltip = ""
        except ValueError as e:
            # Invalid output directory
            self._output_field.style_type_name_override = "FieldError"
            self._output_field.tooltip = str(e)

    def __update_output_directory(self, schema_data: Data, model: ui.AbstractValueModel):
        self.__update_output_directory_from_string(schema_data, model, model.get_value_as_string())

    def __update_output_directory_from_string(self, schema_data: Data, model: ui.AbstractValueModel, value: str):
        try:
            schema_data.output_directory = _OmniUrl(value)
            model.set_value(value)
        except ValueError:
            # Invalid output directory
            carb.log_warn("The output directory would be invalid if the action was applied. Undoing the action.")
            model.set_value(carb.tokens.get_tokens_interface().resolve(str(schema_data.output_directory)))

    @_ignore_function_decorator(attrs=["_ignore_update_file_list"])
    def __update_file_list(self, schema_data: Data, model: _TextureImportListModel, *_):
        item_paths = [(i.path, i.texture_type.name) for i in model.get_item_children(None)]
        previous_input_files = set(schema_data.input_files)
        try:
            schema_data.input_files = item_paths
        except ValueError:
            # if the size of the new list is inferior and the new list is a sub set of the previous one, it means
            # we removed an element. So we don't reset and remove the element
            if len(item_paths) < len(previous_input_files) and set(item_paths).issubset(previous_input_files):
                carb.log_verbose("Input items were not reset")
            else:
                # Invalid input files
                carb.log_warn("The file list would be invalid if the action was applied. Undoing the action.")
                model.refresh([(p, _TextureTypes[t]) for p, t in schema_data.input_files])
        # if all input files are correct, check the output directory versus new input files:
        try:
            schema_data.output_directory = schema_data.output_directory  # trigger Pydantic check
            self._output_field.style_type_name_override = "Field"
            self._output_field.tooltip = ""
        except ValueError as e:
            msg = str(e)
            carb.log_warn(msg)
            self._output_field.style_type_name_override = "FieldError"
            self._output_field.tooltip = msg

    def destroy(self):
        self._output_field_validate_sub = None
        self._output_field_update_sub = None
        self._file_list_field_item_changed_sub = None
        self._file_list_field_type_changed_sub = None
        self._file_list_field = None

        super().destroy()

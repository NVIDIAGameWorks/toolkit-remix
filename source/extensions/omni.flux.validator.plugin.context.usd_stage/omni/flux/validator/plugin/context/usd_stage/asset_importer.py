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

import os
import uuid
from asyncio import ensure_future
from functools import partial
from pathlib import Path
from typing import Any, Awaitable, Callable

import carb
import omni.client
import omni.kit.app
import omni.kit.asset_converter as _kit_asset_converter
import omni.ui as ui
import omni.usd
from omni.flux.asset_importer.core import AssetImporterModel as _AssetImporterModel
from omni.flux.asset_importer.core import ImporterCore as _ImporterCore
from omni.flux.asset_importer.core.data_models import (
    CASE_SENSITIVE_ASSET_EXTENSIONS as _CASE_SENSITIVE_ASSET_EXTENSIONS,
)
from omni.flux.asset_importer.core.data_models import SUPPORTED_ASSET_EXTENSIONS as _SUPPORTED_ASSET_EXTENSIONS
from omni.flux.asset_importer.core.data_models import UsdExtensions as _UsdExtensions
from omni.flux.asset_importer.widget.file_import_list import FileImportListModel as _FileImportListModel
from omni.flux.asset_importer.widget.file_import_list import FileImportListWidget as _FileImportListWidget
from omni.flux.info_icon.widget import InfoIconWidget as _InfoIconWidget
from omni.flux.utils.common.api import send_request as _send_request
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.widget.file_pickers import open_file_picker as _open_file_picker
from omni.flux.validator.factory import InOutDataFlow as _InOutDataFlow
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from omni.flux.validator.factory import utils as _validator_factory_utils
from omni.kit.viewport.utility import get_active_viewport
from omni.kit.widget.prompt import PromptButtonInfo, PromptManager
from pydantic import ConfigDict, Field, ValidationError, create_model, field_validator
from pydantic.functional_validators import SkipValidation
from pydantic_core.core_schema import ValidationInfo

from .base.context_base_usd import ContextBaseUSD as _ContextBaseUSD


def _get_converter_context():
    """
    Adapter for Pydantic V2 to V1 compatibility.

    Returns:
        dict: Processed converter context dictionary with modified boolean fields
    """
    converter_context_dict = _kit_asset_converter.AssetConverterContext().to_dict()
    for field_name, default_value in converter_context_dict.items():
        if isinstance(default_value, bool):
            # Wrap the boolean type with SkipValidation
            converter_context_dict[field_name] = (SkipValidation[bool], default_value)
    return converter_context_dict


class AssetImporter(_ContextBaseUSD):
    DEFAULT_UI_WIDTH_PIXEL = 120
    DEFAULT_UI_HEIGHT_PIXEL = 24
    DEFAULT_UI_SPACING_PIXEL = 8

    class DataBase(_ContextBaseUSD.Data):
        allow_empty_input_files_list: bool | None = Field(default=False)
        input_files: list[_OmniUrl] = Field(...)
        create_output_directory_if_missing: bool = Field(default=True)
        output_directory: _OmniUrl = Field(...)
        output_usd_extension: _UsdExtensions | None = Field(default=None)
        full_path_keep: bool = Field(
            default=False,
            description=(
                "Keep the full path like c:/source/path2/asset.usd will be c:/output/path2/asset.usd if full_path_root "
                "is c:/source/ and full_path_keep is True"
            ),
        )
        full_path_root: _OmniUrl | None = Field(default=None)
        close_stage_on_exit: bool = Field(default=False)
        default_output_endpoint: str | None = Field(
            default=None, description="An API endpoint to hit up to get the default output directory"
        )

        data_flows: list[_InOutDataFlow] | None = Field(default=None)
        output_files: dict[str, str] | None = Field(
            default=None, exclude=True, description="This is tmp we don't keep it in the schema"
        )

        model_config = ConfigDict(validate_assignment=True, extra="forbid")

        _compatible_data_flow_names = ["InOutData"]

        @field_validator("input_files", mode="before")
        @classmethod
        def at_least_one(cls, v: list[_OmniUrl], info: ValidationInfo) -> list[_OmniUrl]:
            if len(v) < 1 and not info.data.get("allow_empty_input_files_list", False):
                raise ValueError("There should at least be 1 item in input_files")
            return v

        @field_validator("input_files", mode="before")
        @classmethod
        def is_readable(cls, v: list[_OmniUrl]) -> list[_OmniUrl]:
            validated_items = []
            for item in v:
                path = carb.tokens.get_tokens_interface().resolve(str(item))
                result, entry = omni.client.stat(path)
                if result != omni.client.Result.OK:
                    raise ValueError(f"The input file is not valid: {item}")
                if not entry.flags & omni.client.ItemFlags.READABLE_FILE:
                    raise ValueError(f"The input file is not readable: {item}")
                validated_items.append(item)
            return validated_items

        @field_validator("output_directory", mode="before")
        @classmethod
        def can_have_children(cls, v: _OmniUrl, info: ValidationInfo) -> _OmniUrl:
            if str(v).strip() == ".":
                # empty path
                return v

            resolved_path = carb.tokens.get_tokens_interface().resolve(str(v))
            if resolved_path.strip() == ".":
                # token hasn't been set
                return v

            # If we allow to create the output, assume the path is valid and fail during setup
            if info.data.get("create_output_directory_if_missing"):
                return v

            result, entry = omni.client.stat(resolved_path)
            if result != omni.client.Result.OK:
                raise ValueError(f"The output directory is not valid: {resolved_path}")
            if not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                raise ValueError(f"The output directory cannot have children: {resolved_path}")
            return v

        @field_validator("output_directory", mode="before")
        @classmethod
        def output_dir_unequal_input_dirs(cls, v: _OmniUrl, info: ValidationInfo) -> _OmniUrl:
            url = _OmniUrl(v)
            for input_file in info.data.get("input_files", []):
                if url.path == input_file.parent_url:
                    raise ValueError(f'Output directory "{url}" cannot be the same as any input file directory.')
            return url

    Data = create_model("Data", __base__=DataBase, **_get_converter_context())

    name = "AssetImporter"
    display_name = "Asset Importer"
    tooltip = "This plugin will import a list of files and process them sequentially"
    data_type = Data

    def __init__(self):
        super().__init__()
        self._output_field = None
        self._output_field_validate_sub = None
        self._output_field_update_sub = None
        self._extension_field_sub = None
        self._mass_content_tree_widget = None
        self._sub_mass_content_tree_widget_item_changed = None
        self._file_list_field = None

        self._extensions = [_UsdExtensions.USD, _UsdExtensions.USDA, _UsdExtensions.USDC]

    @omni.usd.handle_exception
    async def _check(self, schema_data: Data, parent_context: _SetupDataTypeVar) -> tuple[bool, str]:
        """
        Function that will be called to execute the data.

        Args:
            schema_data: the USD file path to check, output directory of imported assets
            parent_context: context data from the parent context

        Returns: True if the check passed, False if not
        """
        is_valid = True
        error_message = "ERROR:\n"

        if len(schema_data.input_files) < 1:
            return False, "ERROR: No input file paths were given."

        output_dir = carb.tokens.get_tokens_interface().resolve(str(schema_data.output_directory))
        output_path = str(_OmniUrl(output_dir))

        stripped_output = output_dir.strip()
        if not stripped_output or stripped_output == ".":
            return False, "ERROR: An output directory must be set."

        for input_file in schema_data.input_files:
            # No need to re-implement all the checks. The Asset-Importer model can validate the values.
            try:
                if schema_data.full_path_keep and str(input_file).startswith(str(schema_data.full_path_root)):
                    # will work with URL/Omniverse/etc etc
                    output_path = os.path.dirname(
                        str(
                            _OmniUrl(output_dir)
                            / os.path.relpath(str(_OmniUrl(input_file)), str(_OmniUrl(schema_data.full_path_root)))
                        )
                    )
                    result, entry = omni.client.stat(output_path)
                    if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                        result = await omni.client.create_folder_async(str(_OmniUrl(output_path)))
                        if result != omni.client.Result.OK:
                            error_message += f"- {str(_OmniUrl(output_path))} doesn't exist\n"
                            is_valid = False
                            continue
                new_schema_data = {
                    "input_path": carb.tokens.get_tokens_interface().resolve(str(input_file)),
                    "output_path": str(_OmniUrl(output_path)),
                    "output_usd_extension": (
                        schema_data.output_usd_extension.value if schema_data.output_usd_extension else None
                    ),
                }

                for key in _kit_asset_converter.AssetConverterContext().to_dict():
                    new_schema_data[key] = getattr(schema_data, key)

                # Create the output directory if allowed
                if schema_data.create_output_directory_if_missing:
                    try:
                        await omni.client.create_folder_async(str(output_dir))
                    except Exception as e:  # noqa PLW0718
                        return False, str(e)

                _ = _AssetImporterModel(data=[new_schema_data])
            except (ValidationError, ValueError) as e:
                error_message += f"- {str(e)}\n"
                is_valid = False

        return is_valid, "The selected files are valid." if is_valid else error_message

    async def _setup(
        self,
        schema_data: Data,
        run_callback: Callable[[_SetupDataTypeVar], Awaitable[None]],
        parent_context: _SetupDataTypeVar,
    ) -> tuple[bool, str, _SetupDataTypeVar]:
        """
        Function that will be executed to set the data. Here we will open the file path and give the stage

        Args:
            schema_data: the data that we should set. Same data than check()
            run_callback: the validation that will be run in the context of this setup
            parent_context: context data from the parent context

        Returns: True if ok + message + list of paths of the imported files
        """
        final_data = []
        output_dir = _OmniUrl(carb.tokens.get_tokens_interface().resolve(str(schema_data.output_directory)))

        progress = 0
        self.on_progress(progress, "Start", True)
        to_add = 1 / len(schema_data.input_files)

        for i_input_file, input_file in enumerate(schema_data.input_files):
            progress += to_add / 2
            self.on_progress(progress, f"Progressing...{i_input_file + 1}/{len(schema_data.input_files)}", True)
            core = _ImporterCore()
            input_path = _OmniUrl(carb.tokens.get_tokens_interface().resolve(str(input_file)))

            output_path = str(_OmniUrl(output_dir))
            if schema_data.full_path_keep and str(input_file).startswith(str(schema_data.full_path_root)):
                # will work with URL/Omniverse/etc etc
                output_path = os.path.dirname(
                    str(
                        _OmniUrl(output_dir)
                        / os.path.relpath(str(_OmniUrl(input_file)), str(_OmniUrl(schema_data.full_path_root)))
                    )
                )

            _validator_factory_utils.push_input_data(schema_data, [str(input_path)])

            await core.import_batch(
                {
                    "data": [
                        {
                            "input_path": str(input_path),
                            "output_usd_extension": (
                                schema_data.output_usd_extension.value if schema_data.output_usd_extension else None
                            ),
                        }
                    ]
                },
                default_output_folder=str(_OmniUrl(output_path)),
            )

            extension = (
                schema_data.output_usd_extension.value
                if schema_data.output_usd_extension
                else self._extensions[0].value
            )
            result_data = (_OmniUrl(output_path) / input_path.name).with_suffix(f".{extension}")

            file_path = carb.tokens.get_tokens_interface().resolve(str(result_data))
            file_path = omni.client.normalize_url(file_path)

            # we update the tmp value of the schema of this plugin. This attribute is private in purpose
            if schema_data.output_files is None:
                schema_data.output_files = {}
            schema_data.output_files[str(input_path)] = str(file_path)  # noqa

            _validator_factory_utils.push_output_data(schema_data, [str(file_path)])

            context = await self._set_current_context(schema_data, parent_context)
            if not context:
                return False, f"The context '{schema_data.computed_context or 'None'}' doesn't exist!", None
            result, error = await context.open_stage_async(file_path)
            if not result:
                return False, error, None

            await run_callback(schema_data.computed_context)

            # Make sure the file is valid before appending to the final_data
            final_data.append(result_data)
            progress += to_add / 2
            self.on_progress(progress, f"Opened {Path(file_path).name}", True)

        return True, "Files were imported successfully", final_data

    async def _on_exit(self, schema_data: Data, parent_context: _SetupDataTypeVar) -> tuple[bool, str]:
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
    async def _mass_cook_template(self, schema_data_template: Data) -> tuple[bool, str | None, list[Data]]:
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
            return False, message, []

        for file_url in schema_data_template.input_files:
            schema = self.Data(**schema_data_template.model_dump(serialize_as_any=True))
            str_file = str(file_url)
            schema.input_files = [str_file]
            # because of OM-105296, we can create multiple contexts, or it will be very slow
            # For now, we keep processing on the current context
            # When the user would want to see the stage we will open a USD file
            # schema_data_template["context_name"] = f"{schema_data_template.context_name}_{str(uuid.uuid4()).replace(
            # '-', '')
            # }"
            schema.display_name_mass_template = str(file_url.stem)
            schema.display_name_mass_template_tooltip = str_file
            schema.uuid = str(uuid.uuid4())
            result.append(schema)
        return True, None, result

    def _mass_build_queue_action_ui(
        self, schema_data: Data, default_actions: list[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> None:
        """
        Default exposed action for Mass validation. The UI will be built into the delegate of the mass queue.
        For example, you can add a button to open the asset into a USD viewport
        """

        def __open_output_file():
            viewport_api = get_active_viewport(usd_context_name=schema_data.computed_context)
            if viewport_api is not None:
                carb.log_error("Can't open the stage, no viewport")
                return
            # for mass ingestion, we only has 1 file
            # we grab the tmp value of the schema of this plugin. This attribute is private in purpose
            file_path = schema_data.output_files[str(schema_data.input_files[0])]  # noqa
            context = omni.usd.get_context(schema_data.computed_context)
            context.open_stage(file_path)
            callback("show_in_viewport")

        # for mass, we only have one input.
        with ui.VStack(width=ui.Pixel(28), height=ui.Pixel(28)):
            ui.Spacer(height=ui.Pixel(2))
            with ui.ZStack():
                ui.Rectangle(name="BackgroundWithWhiteBorder")
                with ui.HStack():
                    ui.Spacer(width=ui.Pixel(2))
                    ui.Image(
                        "",
                        name="ShowInViewport",
                        tooltip="Show in viewport",
                        mouse_pressed_fn=lambda x, y, b, m: __open_output_file(),
                        width=ui.Pixel(24),
                        height=ui.Pixel(24),
                    )
                    ui.Spacer(width=ui.Pixel(2))
            ui.Spacer(height=ui.Pixel(2))

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

        def __filter_drop(paths: list[str]):
            case_sensitive = [
                path
                for path in paths
                if _OmniUrl(path).suffix.lower() in _CASE_SENSITIVE_ASSET_EXTENSIONS
                and _OmniUrl(path).suffix not in _CASE_SENSITIVE_ASSET_EXTENSIONS
            ]
            return [
                path
                for path in paths
                if _OmniUrl(path).suffix.lower() in _SUPPORTED_ASSET_EXTENSIONS and path not in case_sensitive
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
                ui.Spacer(width=ui.Pixel(16), height=0)

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
                self._file_list_field = _FileImportListWidget(
                    enable_drop=True,
                    drop_filter_fn=__filter_drop,
                    allow_empty_input_files_list=schema_data.allow_empty_input_files_list,
                )
                _InfoIconWidget(
                    "The list of files to import as USD files.\n\n"
                    "NOTE: There must be at least 1 file in the list for it to be valid."
                )

            self._file_list_field.model.refresh(schema_data.input_files)
            self._file_list_field_sub = self._file_list_field.model.subscribe_item_changed_fn(
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

            await self._update_default_output_directory(schema_data)

            self._output_field_validate_sub = self._output_field.model.subscribe_value_changed_fn(
                partial(self.__validate_output_directory, schema_data)
            )
            self._output_field_update_sub = self._output_field.model.subscribe_end_edit_fn(
                partial(self.__update_output_directory, schema_data)
            )

            ui.Spacer(height=ui.Pixel(self.DEFAULT_UI_SPACING_PIXEL))

            # file extension
            with ui.HStack(
                height=ui.Pixel(self.DEFAULT_UI_HEIGHT_PIXEL), spacing=ui.Pixel(self.DEFAULT_UI_SPACING_PIXEL)
            ):
                ui.Label(
                    "Output Extension",
                    name="PropertiesWidgetLabel",
                    alignment=ui.Alignment.RIGHT_TOP,
                    width=ui.Pixel(self.DEFAULT_UI_WIDTH_PIXEL),
                )

                try:
                    selected_extension = self._extensions.index(schema_data.output_usd_extension)
                except ValueError:
                    selected_extension = 0

                extension_field = ui.ComboBox(
                    selected_extension, *[e.value for e in self._extensions], identifier="extension_comboxbox"
                )
                _InfoIconWidget("The USD file extension to use for the converted input files.")

            self._extension_field_sub = extension_field.model.subscribe_item_changed_fn(
                partial(self.__update_usd_extension, schema_data)
            )

    @omni.usd.handle_exception
    async def _update_default_output_directory(self, schema_data):
        if schema_data.default_output_endpoint:
            try:
                response = await _send_request("GET", schema_data.default_output_endpoint)
                schema_data.output_directory = _OmniUrl(response.get("directory_path"))
            except RuntimeError:
                pass

        if self._output_field:
            self._output_field.model.set_value(
                carb.tokens.get_tokens_interface().resolve(str(schema_data.output_directory))
            )

    def __open_dialog(self, schema_data: Data, model: ui.AbstractValueModel, _x, _y, b, _m):
        if b != 0:
            return
        default_dir = carb.tokens.get_tokens_interface().resolve(str(schema_data.output_directory))
        _open_file_picker(
            "Choose output directory",
            partial(self.__update_output_directory_from_dialog, schema_data, model),
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
            schema_data.output_directory = _OmniUrl(model.get_value_as_string())
            # Valid output directory
            self._output_field.style_type_name_override = "Field"
            self._output_field.tooltip = ""
        except ValueError as e:
            # Invalid output directory
            self._output_field.style_type_name_override = "FieldError"
            self._output_field.tooltip = str(e)

    def __update_output_directory(self, schema_data: Data, model: ui.AbstractValueModel):
        try:
            schema_data.output_directory = _OmniUrl(model.get_value_as_string())
        except ValueError:
            # Invalid output directory
            carb.log_warn("The output directory would be invalid if the action was applied. Undoing the action.")
            model.set_value(carb.tokens.get_tokens_interface().resolve(str(schema_data.output_directory)))

    def __update_output_directory_from_dialog(self, schema_data: Data, model: ui.AbstractValueModel, value: str):
        try:
            schema_data.output_directory = _OmniUrl(value)
            model.set_value(value)
        except ValueError:
            # Invalid output directory
            carb.log_warn("The output directory would be invalid if the action was applied. Undoing the action.")
            model.set_value(carb.tokens.get_tokens_interface().resolve(str(schema_data.output_directory)))

    def __update_usd_extension(self, schema_data: Data, model: ui.AbstractItemModel, _):
        # No validation required for combo-boxes
        selected_index = model.get_item_value_model().get_value_as_int()
        schema_data.output_usd_extension = self._extensions[selected_index]

    @_ignore_function_decorator(attrs=["_ignore_update_file_list"])
    def __update_file_list(self, schema_data: Data, model: _FileImportListModel, *_):
        item_paths = [i.path for i in model.get_item_children(None)]
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
                model.refresh(schema_data.input_files)
        # if all input files are correct, check the output directory versus new input files:
        try:
            schema_data.output_directory = schema_data.output_directory  # trigger Pydantic check
            self._output_field.style_type_name_override = "Field"
            self._output_field.tooltip = ""
        except ValueError:
            msg = "The selected output directory is located at the same path as one or more input file."
            carb.log_warn(msg)
            self._output_field.style_type_name_override = "FieldError"
            self._output_field.tooltip = msg

    def show(self, value: bool, schema_data: Data):
        if not value:
            return
        ensure_future(self._update_default_output_directory(schema_data))

    def destroy(self):
        self._output_field_validate_sub = None
        self._output_field_update_sub = None
        self._extension_field_sub = None
        self._sub_mass_content_tree_widget_item_changed = None
        self._file_list_field = None

        super().destroy()

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
import json
import weakref
from pathlib import Path
from typing import Any, Callable, List, Optional, Union

import carb
import carb.tokens
import omni.client
import omni.kit.asset_converter as _kit_asset_converter
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit.usd.collect import Collector
from pydantic import BaseModel, Field, create_model, field_validator
from pydantic.functional_validators import SkipValidation

from .data_models.enums import UsdExtensions as _UsdExtensions


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


class AssetItemImporterModelBase(BaseModel):
    input_path: str = Field()
    output_path: Optional[Union[str, Path]] = Field(default=None)
    output_usd_extension: Optional[_UsdExtensions] = Field(default=None)

    @field_validator("input_path", mode="before")
    @classmethod
    def input_path_exist(cls, v):
        """Check if the input path exist"""
        v = carb.tokens.get_tokens_interface().resolve(v)
        result, entry = omni.client.stat(v)
        if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.READABLE_FILE:
            raise ValueError(f"import_batch was passed an invalid input_path. {v} doesn't exist!")
        return v

    @field_validator("output_path", mode="before")
    @classmethod
    def output_folder_valid(cls, v):
        """Check if the input path exist"""
        if v is not None:
            v = carb.tokens.get_tokens_interface().resolve(v)
            output_folder = OmniUrl(v).parent_url
            result, entry = omni.client.stat(output_folder)
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                raise ValueError(f"import_batch was passed an invalid output_folder. {v} doesn't exist!")
        return v


AssetItemImporterModel = create_model(
    "AssetItemImporterModel", __base__=AssetItemImporterModelBase, **_get_converter_context()
)


class AssetImporterModel(BaseModel):
    data: List[AssetItemImporterModel]

    @field_validator("data", mode="before")
    @classmethod
    def at_least_one(cls, v):
        """Check if there is at least 1 asset"""
        if not v:
            raise ValueError("import_batch's config should have at least 1 asset")
        return v


class ImporterCore:
    def __init__(self):
        """
        Importer that can convert batches of mesh files (i.e. fbx, obj, etc) to usd files.
        """
        self.__on_batch_finished = _Event()
        self.__on_batch_progress = _Event()

    def import_batch(self, batch_config: Union[str, Path, dict], default_output_folder: Union[str, Path] = None):
        """
        Function to convert batches of mesh files to usd.

        Note:
            .. code-block:: js
                :caption: The config should conform to this format

                {
                    "data": {
                        "input_path": "filename.fbx",       // the filename to be imported
                        "output_path": "./output/file.usd", // the path to save the generated .usd file to.
                        "output_usd_extension": "usd"       // the extension to use for the USD file.
                                                            // Only used if using 'default_output_folder'
                        // any properties from omni.kit.asset_converter's AssetConverterContext object can be set here.
                    }
                }


        Args:
            batch_config: can be a json file path or a dictionary.
            default_output_folder: the folder to place outputs in.  Overridden by "output_path" in batch_config.

        """
        return asyncio.ensure_future(self.import_batch_async(batch_config, default_output_folder))

    @omni.usd.handle_exception
    async def import_batch_async(
        self, batch_config: Union[str, Path, dict], default_output_folder: Union[str, Path] = None
    ):
        """
        As import_batch, but async.
        """
        return await self.import_batch_async_with_error(batch_config, default_output_folder)

    async def import_batch_async_with_error(
        self, batch_config: Union[str, Path, dict], default_output_folder: Union[str, Path] = None
    ):
        """
        As import_batch, but async without error handling.  This is meant for testing.
        """
        if default_output_folder is not None:
            default_output_folder = omni.client.normalize_url(str(default_output_folder))
            result, entry = omni.client.stat(default_output_folder)
            if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
                carb.log_error(
                    f"import_batch was passed an invalid default_output_folder. {default_output_folder} doesn't exist!"
                )
                return False

        if isinstance(batch_config, (Path, str)):
            # batch_config is a json filename, need to load it
            try:
                batch_config = carb.tokens.get_tokens_interface().resolve(str(batch_config))
                json_path = omni.client.normalize_url(batch_config)
                result, entry = omni.client.stat(json_path)
                if result != omni.client.Result.OK or not entry.flags & omni.client.ItemFlags.READABLE_FILE:
                    carb.log_error(f"Config file passed to import_batch could not be opened. path: {batch_config}")
                    return False
                batch_config = _path_utils.read_json_file(json_path)
            except (OSError, json.JSONDecodeError):
                carb.log_error(f"Config file passed to import_batch failed json parsing. path: {batch_config}")
                return False
        model = AssetImporterModel(**batch_config)

        converter_manager = _kit_asset_converter.get_instance()
        tasks = []
        collections = []
        all_success = True
        output_path = None

        for config in model.data:
            input_url = OmniUrl(carb.tokens.get_tokens_interface().resolve(config.input_path))
            if config.output_path:
                output_path = OmniUrl(carb.tokens.get_tokens_interface().resolve(config.output_path))
            if config.output_path is not None:
                output_folder = OmniUrl(carb.tokens.get_tokens_interface().resolve(config.output_path)).parent_url
            elif default_output_folder is not None:
                output_folder = default_output_folder
            else:
                output_folder = input_url.parent_url

            desired_suffix = f".{config.output_usd_extension.value}" if config.output_usd_extension else ".usd"
            if input_url.suffix.lower() in {".usd", ".usda", ".usdb", ".usdc"}:
                # Importing a USD file, need to use collector
                rename_task = None
                if config.output_path is not None:
                    collect_out_path = omni.client.normalize_url(str(OmniUrl(output_folder) / input_url.name))
                    desired_out_path = omni.client.normalize_url(str(output_path))
                    if collect_out_path != desired_out_path:
                        rename_task = (collect_out_path, desired_out_path)
                elif desired_suffix.lower() != input_url.suffix.lower():
                    out_path = str(OmniUrl(output_folder) / input_url.name)
                    rename_task = (out_path, str(Path(out_path).with_suffix(desired_suffix)))

                collector = Collector(config.input_path, output_folder, False, True, False)
                collections.append((collector, rename_task))

                output_path = str(OmniUrl(output_folder) / input_url.stem) + desired_suffix
            else:
                # Not a USD file, need to use asset converter.
                if config.output_path is not None:
                    output_path = omni.client.normalize_url(str(output_path))
                elif default_output_folder is not None:
                    output_path = OmniUrl(default_output_folder) / input_url.name
                    output_path = str(output_path.with_suffix(desired_suffix))
                else:
                    output_path = str(input_url.with_suffix(desired_suffix))

                context = self._context_from_model(config)
                tasks.append(converter_manager.create_converter_task(config.input_path, output_path, None, context))

        # If an asset with that name in output_folder already exists, delete it
        dest_asset_path = Path(str(output_path))
        if dest_asset_path.exists():
            carb.log_warn(f"The asset at, {dest_asset_path}, already exists! Overwriting the asset...")
            dest_asset_path.unlink()

        if (len(tasks) + len(collections)) == 0:
            self._on_batch_finished(all_success)
            return all_success

        to_add = 100 / (len(tasks) + len(collections))
        progress = 0
        self._on_batch_progress(progress)
        for task in tasks:
            if not await task.wait_until_finished():
                all_success = False
            progress += to_add
            self._on_batch_progress(progress)

        rename_context = None
        for collection, rename_task in collections:
            collector_weakref = weakref.ref(collection)

            def progress_callback(step, total):
                if total != 0:
                    self._on_batch_progress(progress + to_add * step / total)  # noqa B023

            def on_finish():
                collector_weakref().destroy()  # noqa

            await collection.collect(progress_callback, on_finish)

            if rename_task:
                if rename_context is None:
                    rename_context = omni.usd.create_context("asset_importer_renamer")

                if not rename_context.open_stage(rename_task[0]) or not rename_context.save_as_stage(rename_task[1]):
                    all_success = False
                    carb.log_error(f"Failed to rename imported USD from {rename_task[0]} to {rename_task[1]}")

                rename_context.close_stage()
                omni.client.delete(rename_task[0])

            progress += to_add
            self._on_batch_progress(progress)

        if rename_context is not None:
            rename_context = None
            omni.usd.destroy_context("asset_importer_renamer")

        self._on_batch_progress(100)
        self._on_batch_finished(all_success)

        return all_success

    def _context_from_model(self, model: AssetItemImporterModel):
        context = _kit_asset_converter.AssetConverterContext()
        for key in context.to_dict():
            value = getattr(model, key, None)
            if value is not None:
                setattr(context, key, value)
        return context

    def _on_batch_progress(self, progress):
        carb.log_info(f"Progress: {progress}%")
        self.__on_batch_progress(progress)

    def _on_batch_finished(self, result):
        self.__on_batch_finished(result)

    def subscribe_batch_finished(self, callback: Callable[[bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_batch_finished, callback)

    def subscribe_batch_progress(self, callback: Callable[[float], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_batch_progress, callback)

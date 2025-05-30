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
import os
from pathlib import Path
from typing import Callable

import carb
import omni.client
import omni.usd
from lightspeed.common import constants
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.validator.factory import BASE_HASH_KEY, VALIDATION_PASSED
from omni.kit.usd.collect import Collector


def copy_usd_asset(context: omni.usd.UsdContext, asset_path: str, callback_func: Callable):
    """
    Copy the usd asset to a generated destination path within the project hierarchy with its metadata

    Args:
        context: current context of the application
        asset_path: current path where the asset is located
        callback_func: function to add the asset reference within the Remix after finishing the copy operation

    Returns:
        The full path of the newly copied USD file within the /(root)/assets/ingested folder
    """
    is_valid_usd_file(asset_path)

    # init collector to copy the asset to the appropriate project subdirectory
    asset_replacements_core = _AssetReplacementsCore(context.get_name())
    asset_path_response_model = asset_replacements_core.get_default_output_directory_with_data_model()
    dest_path = asset_path_response_model.directory_path
    collector = Collector(usd_path=asset_path, collect_dir=dest_path)

    def set_ref():
        callback_func(str(_OmniUrl(dest_path) / _OmniUrl(asset_path).name))
        _copy_metadata(asset_path, dest_path)

    # collect external asset, perform appropriate callback to add the ref to stage, and copy metadata
    asyncio.ensure_future(collector.collect(progress_callback=None, finish_callback=set_ref))


def copy_non_usd_asset(context: omni.usd.UsdContext, asset_path: str, callback_func: Callable):
    """
    Copy the non-usd asset to a generated destination path within the project hierarchy with its metadata

    Args:
        context: current context of the application
        asset_path: current path where the asset is located
        callback_func: changes the asset reference to the newly copied asset

    Returns:
        None
    """
    try:
        # obtain the destination directory path
        asset_replacements_core = _AssetReplacementsCore(context.get_name())
        asset_path_response_model = asset_replacements_core.get_default_output_directory_with_data_model()
        dest_dir_path = asset_path_response_model.directory_path

        dest_dir_path_url = _OmniUrl(_OmniUrl(dest_dir_path).path)
        asset_path_basename = _OmniUrl(asset_path).name
        dest_path_url = str(dest_dir_path_url / asset_path_basename)

        # copy the non-usd asset and it's metadata file
        omni.client.copy(asset_path, dest_path_url, omni.client.CopyBehavior.OVERWRITE)
        _copy_metadata(asset_path, dest_dir_path)

        # re-reference the newly copied asset
        callback_func(_AssetReplacementsCore.switch_ref_abs_to_rel_path(context.get_stage(), dest_path_url))

    except FileNotFoundError:
        carb.log_error(f"Error moving the non-USD asset file: {asset_path}.")


def _copy_metadata(asset_path: str, dest_path: str):
    """
    Copy the metadata given the asset path of the ingested asset and the destination path for the copied metadata

    Args:
        asset_path: the original path of the ingested asset (not metadata path)
        dest_path: the destination path where the metadata will be copied to

    Returns:
        None
    """
    # Double-check that the metadata has actually been ingested/validated
    if not _path_utils.read_metadata(file_path=asset_path, key=VALIDATION_PASSED):
        carb.log_error(
            f"The metadata file at {asset_path}.meta indicates that the asset's validation was not passed. "
            f"This metadata file will not be copied into {dest_path}. Please make sure the asset was properly ingested "
            f"or re-ingest it."
        )
        return

    # Copy the metadata
    asset_path_basename = _OmniUrl(asset_path).name
    dest_path_url = _OmniUrl(_OmniUrl(dest_path).path)
    dest_metadata_path = str(dest_path_url / asset_path_basename) + ".meta"
    new_asset_path = f"{dest_path}/{asset_path_basename}"
    try:
        omni.client.copy(f"{asset_path}.meta", dest_metadata_path, omni.client.CopyBehavior.OVERWRITE)
    except OSError:
        carb.log_error(f"The metadata file could not be copied from {asset_path}.meta to {dest_path}.")

    # Update metadata if there is no hash or if the current hash does not match
    if not _path_utils.read_metadata(file_path=asset_path, key=BASE_HASH_KEY) or not _path_utils.hash_match_metadata(
        file_path=new_asset_path, key=BASE_HASH_KEY
    ):
        try:
            updated_hash = _path_utils.hash_file(file_path=new_asset_path)
            _path_utils.write_metadata(file_path=new_asset_path, key=BASE_HASH_KEY, value=updated_hash, append=False)
        except OSError:
            os.remove(dest_metadata_path)
            carb.log_error(
                f"The hash within the copied metadata file at, {new_asset_path}.meta, could not be updated. This new "
                f"metadata has been removed."
            )


def is_valid_usd_file(asset_path: str):
    # Make sure we have a valid USD path
    if not asset_path or not str(asset_path).strip() or Path(asset_path).suffix not in constants.USD_EXTENSIONS:
        raise ValueError(f"'{str(asset_path)}' is not a valid USD path")

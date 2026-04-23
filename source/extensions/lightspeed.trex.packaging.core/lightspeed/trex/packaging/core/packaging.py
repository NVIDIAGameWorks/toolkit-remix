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

from __future__ import annotations

import re
import uuid
from asyncio import ensure_future
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import carb
import omni.client
import omni.kit.app
import omni.usd
from lightspeed.common.constants import REMIX_CAPTURE_FOLDER as _REMIX_CAPTURE_FOLDER
from lightspeed.common.constants import REMIX_DEPENDENCIES_FOLDER as _REMIX_DEPENDENCIES_FOLDER
from lightspeed.common.constants import REMIX_MODS_FOLDER as _REMIX_MODS_FOLDER
from lightspeed.common.constants import REMIX_SUBUSD_RELATIVE_PATH as _REMIX_SUBUSD_RELATIVE_PATH
from lightspeed.layer_manager.core import LSS_LAYER_MOD_DEPENDENCIES as _LSS_LAYER_MOD_DEPENDENCIES
from lightspeed.layer_manager.core import LSS_LAYER_MOD_NAME as _LSS_LAYER_MOD_NAME
from lightspeed.layer_manager.core import LSS_LAYER_MOD_NOTES as _LSS_LAYER_MOD_NOTES
from lightspeed.layer_manager.core import LSS_LAYER_MOD_VERSION as _LSS_LAYER_MOD_VERSION
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.asset_importer.core.data_models import UsdExtensions as _UsdExtensions
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.material_converter.utils import MaterialConverterUtils as _MaterialConverterUtils
from omni.kit.usd.collect.omni_client_wrapper import OmniClientWrapper as _OmniClientWrapper
from omni.kit.usd.layers import LayerUtils as _LayerUtils
from pxr import Sdf, Usd, UsdUtils

from .enum import get_packaged_root_export_args as _get_packaged_root_export_args
from .enum import get_packaged_root_output_suffix as _get_packaged_root_output_suffix
from .enum import ModPackagingMode as _ModPackagingMode
from .items import ModPackagingSchema as _ModPackagingSchema

# Aligned with omni.flux.asset_importer.core.data_models.constants.SUPPORTED_TEXTURE_EXTENSIONS
_PACKAGING_TEXTURE_SUFFIXES = frozenset(suffix.lower() for suffix in (_SUPPORTED_TEXTURE_EXTENSIONS))


class PackagingCore:
    def __init__(self):
        self.default_attr = {
            "_cancel_token": None,
            "_current_count": None,
            "_total_count": None,
            "_temp_files": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._cancel_token = False
        self._current_count = 0
        self._total_count = 0
        self._status = "Initializing..."
        self._temp_files = {}

        self.__packaging_progress = _Event()
        self.__packaging_completed = _Event()

    def cancel(self):
        """
        Cancel the packaging process.
        """
        self._cancel_token = True

    @property
    def current_count(self) -> int:
        """
        Get the current packaged items count
        """
        return self._current_count

    @current_count.setter
    def current_count(self, val):
        self._current_count = min(val, self.total_count)
        self._packaging_progress()

    @property
    def total_count(self) -> int:
        """
        Get the current total items count
        """
        return self._total_count

    @total_count.setter
    def total_count(self, val):
        self._total_count = val
        self._packaging_progress()

    @property
    def status(self) -> str:
        """
        Get the current packaging status
        """
        return self._status

    def package(self, schema: dict):
        r"""
        Execute the project packaging process using the given schema.

        Args:
            schema: the schema to use for the project packaging. Please see the documentation.

        Examples:
            >>> core = PackagingCore()
            >>> core.package(
            >>>    {
            >>>         "context_name": "Packaging",
            >>>         "mod_layer_paths": [Path("R:\Remix\projects\MyProject\mod.usda")],
            >>>         "selected_layer_paths": [
            >>>             Path("R:\Remix\projects\MyProject\mod.usda"),
            >>>             Path("R:\Remix\projects\MyProject\sublayer.usda"),
            >>>         ],
            >>>         "output_directory": Path("R:\Remix\rtx-remix\captures\capture_1.usda"),
            >>>         "mod_name": "Packaged Mod Name",
            >>>         "mod_version": "1.0.0",
            >>>         "mod_details": "Optional Mod Details",
            >>>    }
            >>>)
        """
        return ensure_future(self.package_async(schema))

    @omni.usd.handle_exception
    async def package_async(self, schema: dict):
        """
        Asynchronous implementation of package
        """
        await self.package_async_with_exceptions(schema)

    async def package_async_with_exceptions(self, schema: dict):
        """
        Asynchronous implementation of package, but async without error handling.  This is meant for testing.
        """
        errors = []
        failed_assets = []
        try:
            model = _ModPackagingSchema(**schema)

            if model.mod_layer_paths[0] not in model.selected_layer_paths:
                carb.log_warn("The root-level mod layer was not selected. Nothing to package.")
                return

            stage = await self._initialize_usd_stage(model.context_name, str(model.mod_layer_paths[0]))
            if not stage:
                raise RuntimeError("No stage is available in the current context.")

            root_mod_layer = Sdf.Layer.FindOrOpen(str(model.mod_layer_paths[0]))
            if not root_mod_layer:
                raise RuntimeError(f"Unable to open the root mod layer at path: {model.mod_layer_paths[0]}")
            temp_root_mod_layer = Sdf.Layer.FindOrOpen(await self._make_temp_layer(root_mod_layer.identifier))

            # Remove all deselected sublayers
            self._packaging_new_stage("Filtering the selected layers...", 1)
            temp_layers = await self._filter_sublayers(
                model.context_name,
                None,
                temp_root_mod_layer,
                [_OmniUrl(p).path.lower() for p in model.selected_layer_paths],
            )
            self.current_count += 1

            packaging_root_layer = temp_root_mod_layer
            packaging_temp_layers = temp_layers

            # Get the updated external mods dependencies pointing to the installed external mods
            if model.packaging_mode == _ModPackagingMode.REDIRECT:
                mod_dependencies, redirected_dependencies = self._get_redirected_dependencies(
                    temp_root_mod_layer, [m for m in model.mod_layer_paths if m not in model.selected_layer_paths]
                )
            else:
                mod_dependencies = set()
                redirected_dependencies = set()

            if model.packaging_mode == _ModPackagingMode.FLATTEN:
                packaging_root_layer = await self._flatten_temp_root_layer(temp_root_mod_layer)
                if self._cancel_token:
                    return
                packaging_temp_layers = [packaging_root_layer.identifier]
                stage = await self._initialize_usd_stage(model.context_name, packaging_root_layer.identifier)
                if not stage:
                    raise RuntimeError("Unable to open the flattened temporary root stage.")

            # Don't use the omni collector because it's not flexible enough
            collect_errors, collected_failed_assets = await self._collect(
                stage,
                packaging_root_layer,
                packaging_temp_layers,
                model.output_directory,
                redirected_dependencies,
                model.ignored_errors,
                model.output_format,
            )
            errors.extend(collect_errors)
            failed_assets = collected_failed_assets

            if not failed_assets:
                exported_mod_layer = Sdf.Layer.FindOrOpen(
                    str(
                        _OmniUrl(model.output_directory)
                        / self._get_packaged_root_output_name(model.mod_layer_paths[0], model.output_format)
                    )
                )
                if exported_mod_layer:
                    errors.extend(self._update_layer_metadata(model, exported_mod_layer, mod_dependencies, True))
                else:
                    errors.append("Unable to find the exported mod file.")
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
        finally:
            # Cleanup the temp files
            await self._clean_temp_files()
            # Reset the cancel state
            self._packaging_completed(errors, failed_assets)

    @omni.usd.handle_exception
    async def _make_temp_layer(self, layer_path: str) -> str:
        layer_url = _OmniUrl(layer_path)
        temp_path = layer_url.with_name(
            _OmniUrl(layer_url.stem + f"_{uuid.uuid4()}").with_suffix(layer_url.suffix).path
        ).path

        await _OmniClientWrapper.copy(layer_path, temp_path, set_target_writable_if_read_only=True)

        self._temp_files[temp_path] = layer_url.name
        return temp_path

    @staticmethod
    def _get_packaged_root_output_name(root_layer_path: Path | str, output_format: _UsdExtensions | None) -> str:
        root_layer_url = _OmniUrl(root_layer_path)
        if output_format is not None:
            return Path(root_layer_url.name).with_suffix(_get_packaged_root_output_suffix(output_format)).name
        return root_layer_url.name

    @staticmethod
    def _export_packaged_layer(
        layer: Sdf.Layer,
        output_path: Path | str,
        output_format: _UsdExtensions | None,
        *,
        is_packaged_root: bool = False,
    ):
        if not is_packaged_root or output_format is None:
            layer.Export(str(output_path))
            return
        export_args = _get_packaged_root_export_args(output_format)
        if export_args:
            layer.Export(str(output_path), args=export_args)
            return
        layer.Export(str(output_path))

    @omni.usd.handle_exception
    async def _clean_temp_files(self):
        self._packaging_new_stage("Cleaning up temporary layers...", len(self._temp_files))

        for temp_file in self._temp_files:
            try:
                await _OmniClientWrapper.delete(str(temp_file))
            except Exception:  # noqa: BLE001
                carb.log_warn(f"Unable to cleanup temporary layer: {temp_file}")
            self.current_count += 1
        self._temp_files.clear()

    @omni.usd.handle_exception
    async def _flatten_temp_root_layer(self, temp_root_layer: Sdf.Layer) -> Sdf.Layer:
        if self._cancel_token:
            return temp_root_layer

        self._packaging_new_stage("Preparing packaged stage for flattening...", 4)

        stage = Usd.Stage.Open(temp_root_layer.identifier)
        if not stage:
            raise RuntimeError(f"Unable to open the temporary root mod layer at path: {temp_root_layer.identifier}")

        stage.Load()
        self.current_count += 1

        if self._cancel_token:
            return temp_root_layer

        self._packaging_update_status("Flattening packaged layers...")
        flattened_layer = stage.Flatten()
        self.current_count += 1

        flattened_custom_data = dict(flattened_layer.customLayerData)
        flattened_custom_data.update(temp_root_layer.customLayerData)
        flattened_layer.customLayerData = flattened_custom_data

        if self._cancel_token:
            return temp_root_layer

        self._packaging_update_status("Writing flattened package root...")
        flattened_temp_path = await self._make_temp_layer(temp_root_layer.identifier)
        original_root_path = self._get_original_path(temp_root_layer.identifier)
        if original_root_path:
            self._temp_files[_OmniUrl(flattened_temp_path).path] = _OmniUrl(original_root_path).name
        flattened_layer.Export(flattened_temp_path)
        self.current_count += 1

        if self._cancel_token:
            return temp_root_layer

        self._packaging_update_status("Finalizing flattened package root...")
        flattened_temp_layer = Sdf.Layer.FindOrOpen(flattened_temp_path)
        if not flattened_temp_layer:
            raise RuntimeError(f"Unable to open the flattened temporary root layer at path: {flattened_temp_path}")
        self.current_count += 1

        return flattened_temp_layer

    @omni.usd.handle_exception
    async def _initialize_usd_stage(self, context_name: str, root_mod_layer_path: str) -> Usd.Stage | None:
        del context_name
        return Usd.Stage.Open(root_mod_layer_path)

    @omni.usd.handle_exception
    async def _filter_sublayers(
        self,
        context_name: str,
        parent_layer: Sdf.Layer | None,
        temp_layer: Sdf.Layer,
        selected_layer_paths: list[str],
    ) -> list[str]:
        # The given layer is already a temp path
        temp_layers = [temp_layer.identifier]

        if self._cancel_token:
            return temp_layers

        self.current_count += 1

        original_path = self._get_original_path(temp_layer.identifier)

        # If the parent is not selected, all children will be filtered out too
        if original_path.lower() not in selected_layer_paths:
            if parent_layer:
                sublayer_position = _LayerUtils.get_sublayer_position_in_parent(parent_layer.identifier, original_path)
                # If position is -1, the item was not found, so we should not remove a random layer
                if sublayer_position >= 0:
                    parent_sublayers = list(parent_layer.subLayerPaths)
                    parent_sublayers.pop(sublayer_position)
                    parent_layer.subLayerPaths = parent_sublayers
                    parent_layer.Save()
            return temp_layers

        self.total_count += len(temp_layer.subLayerPaths)

        for sublayer_path in temp_layer.subLayerPaths:
            if self._cancel_token:
                return temp_layers
            temp_sublayer = Sdf.Layer.FindOrOpen(
                await self._make_temp_layer(temp_layer.ComputeAbsolutePath(sublayer_path))
            )
            if not temp_sublayer:
                self.current_count += 1
                continue
            temp_layers.extend(
                await self._filter_sublayers(context_name, temp_layer, temp_sublayer, selected_layer_paths)
            )

        return temp_layers

    @omni.usd.handle_exception
    async def _collect(
        self,
        stage: Usd.Stage,
        temp_root_layer: Sdf.Layer,
        existing_temp_layers: list[str],
        output_directory: Path | str,
        redirected_dependencies: set[str],
        ignored_errors: list[tuple[str, str, str]] | None,
        output_format: _UsdExtensions | None,
    ) -> tuple[list[str], list[tuple[str, str, str]]]:
        errors = []
        failed_assets = []
        if self._cancel_token:
            return errors, failed_assets

        all_layers, all_assets, unresolved_paths = UsdUtils.ComputeAllDependencies(temp_root_layer.identifier)

        stage_prims = list(stage.TraverseAll())
        self._packaging_new_stage("Resolving invalid references...", len(stage_prims))

        invalid_assets = self._collect_invalid_packaging_assets(stage_prims, unresolved_paths)

        invalid_assets.difference_update(ignored_errors or [])
        if invalid_assets:
            return errors, list(invalid_assets)

        self._packaging_new_stage("Creating temporary layers...", len(all_layers))

        temp_layers_map = {self._get_original_path(temp_layer): temp_layer for temp_layer in existing_temp_layers}
        temp_layers = []
        for layer in all_layers:
            if self._cancel_token:
                return errors, failed_assets

            self.current_count += 1

            # The root layer is already a temporary layer
            if layer.identifier == temp_root_layer.identifier:
                temp_layer_path = layer.identifier
            # For every other layer, make sure a temporary layer was not already created before creating one
            else:
                temp_layer_path = temp_layers_map.get(_OmniUrl(layer.identifier).path) or await self._make_temp_layer(
                    layer.identifier
                )
            temp_layer = Sdf.Layer.FindOrOpen(temp_layer_path)
            if not temp_layer:
                errors.append(f"Unable to open temporary file: {temp_layer_path}")
            else:
                temp_layers.append(temp_layer)

        if errors or self._cancel_token:
            return errors, failed_assets

        temp_layer_paths = {_OmniUrl(temp_layer.identifier).path: temp_layer for temp_layer in temp_layers}
        all_dependencies = [*temp_layer_paths.keys(), *all_assets]

        self._packaging_new_stage("Listing assets to collect...", len(all_dependencies))

        updated_dependencies = {}
        shader_subidentifiers = [url.name for url in _MaterialConverterUtils.get_material_library_shader_urls()]

        for dependency in all_dependencies:
            if self._cancel_token:
                return errors, failed_assets

            dependency_path = _OmniUrl(dependency).path
            original_dependency_path = self._get_original_path(dependency) or dependency_path

            # If the dependency is a known shader, we should not collect it or update the dependency
            if _OmniUrl(original_dependency_path).name in shader_subidentifiers:
                self.current_count += 1
                continue

            if original_dependency_path in redirected_dependencies:
                # If the dependency was redirected, we should not collect it but should update the dependency
                updated_dependencies[original_dependency_path] = self._redirect_to_existing_project
            else:
                # Make sure to redirect the dependency inside the output directory if it does not resolve there
                # The update method will also mark all assets for collection
                updated_dependencies[original_dependency_path] = partial(
                    self._redirect_inside_package_directory, dependency_path, output_directory
                )

            self.current_count += 1

        # Collected dependencies will be populated during ModifyAssetPaths.
        # Layers will be pre-populated in case they don't have dependencies.
        self._collected_dependencies = {
            _OmniUrl(temp_layer.identifier).path: f"./{_OmniUrl(temp_layer.identifier).name}"
            for temp_layer in temp_layers
            if self._get_original_path(temp_layer.identifier) not in redirected_dependencies
        }

        self._packaging_new_stage("Updating asset paths...", len(temp_layers))

        for temp_layer in temp_layers:
            if self._cancel_token:
                return errors, failed_assets
            self.current_count += 1
            UsdUtils.ModifyAssetPaths(temp_layer, partial(self._modify_asset_paths, temp_layer, updated_dependencies))

        # Wrap in a try for when Export fails to write the file
        try:
            if self._cancel_token:
                return errors, failed_assets

            # Make sure to create a clean packaging directory
            if _OmniUrl(output_directory).exists:
                await _OmniClientWrapper.delete(str(output_directory))

            self._packaging_new_stage("Collecting assets...", len(self._collected_dependencies))

            # Copy all collected assets to the output directory
            for temp_input_path, relative_output_path in self._collected_dependencies.items():
                if self._cancel_token:
                    return errors, failed_assets
                output_path = _OmniUrl(output_directory) / relative_output_path
                input_path = self._get_original_path(temp_input_path)
                is_packaged_root = temp_input_path == _OmniUrl(temp_root_layer.identifier).path
                if input_path:
                    output_name = (
                        self._get_packaged_root_output_name(input_path, output_format)
                        if is_packaged_root
                        else _OmniUrl(input_path).name
                    )
                    output_path = output_path.with_name(output_name)

                # Create all the missing folders in the tree
                cumulative_url = None
                for part in Path(output_path.parent_url).parts:
                    if not cumulative_url:
                        cumulative_url = _OmniUrl(part)
                    else:
                        cumulative_url /= part
                    if not str(cumulative_url).startswith(str(output_directory)) or cumulative_url.exists:
                        continue
                    await _OmniClientWrapper.create_folder(str(cumulative_url))

                # If the dependency is a layer, export it to the output directory to keep references changes applied
                input_layer = temp_layer_paths.get(temp_input_path)
                if input_layer:
                    self._export_packaged_layer(
                        input_layer, output_path, output_format, is_packaged_root=is_packaged_root
                    )
                # Otherwise simply copy the dependency to the output directory
                else:
                    await _OmniClientWrapper.copy(temp_input_path, str(output_path))

                self.current_count += 1
        # Make sure to bubble up failures
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

        # Clear assets marked for collection now that they were copied
        self._collected_dependencies.clear()

        return errors, failed_assets

    @staticmethod
    def _normalize_packaging_absolute_path(absolute_path: str) -> str:
        """Normalize dependency / disk paths for stable set comparisons (posix format)."""
        return Path(absolute_path).as_posix()

    def _collect_invalid_packaging_assets(
        self,
        stage_prims: list[Usd.Prim],
        unresolved_paths: list[str],
        *,
        include_missing_authored_textures: bool = True,
    ) -> set[tuple[str, str, str]]:
        """
        Scan stage prims once for packaging failures: missing authored textures (optional) and/or
        prim references and per-spec asset attributes matching ``unresolved_paths`` (when non-empty).
        """
        unresolved_set = (
            {self._normalize_packaging_absolute_path(p) for p in unresolved_paths} if unresolved_paths else None
        )
        result: set[tuple[str, str, str]] = set()

        for prim in stage_prims:
            if self._cancel_token:
                return result

            if unresolved_set:
                prim_stack = prim.GetPrimStack()
                for prim_spec in prim_stack:
                    for ref in prim_spec.referenceList.GetAddedOrExplicitItems():
                        resolved_path = self._normalize_packaging_absolute_path(
                            prim_spec.layer.ComputeAbsolutePath(ref.assetPath)
                        )
                        if resolved_path in unresolved_set:
                            result.add((prim_spec.layer.identifier, str(prim_spec.path), resolved_path))

            for prop in prim.GetAttributes():
                if not isinstance(prop.Get(), Sdf.AssetPath):
                    continue
                property_stack = prop.GetPropertyStack(Usd.TimeCode.Default())
                for prop_spec in property_stack:
                    prop_layer = prop_spec.layer
                    authored_value = prop_spec.default
                    if not isinstance(authored_value, Sdf.AssetPath) or not authored_value.path:
                        continue
                    abs_path = self._normalize_packaging_absolute_path(
                        prop_layer.ComputeAbsolutePath(authored_value.path)
                    )
                    if include_missing_authored_textures and self._is_missing_packaging_texture_path(abs_path):
                        result.add((prop_layer.identifier, str(prop.GetPath()), abs_path))
                    if unresolved_set and abs_path in unresolved_set:
                        result.add((prop_layer.identifier, str(prop.GetPath()), abs_path))

            self.current_count += 1

        return result

    def _is_missing_packaging_texture_path(self, absolute_path: str) -> bool:
        """True if ``absolute_path`` looks like a packaging texture and the file is not present."""
        absolute_url = _OmniUrl(absolute_path)
        if absolute_url.suffix.lower() not in _PACKAGING_TEXTURE_SUFFIXES:
            return False
        return not absolute_url.exists

    @omni.usd.handle_exception
    async def _get_unresolved_assets_prim_paths(
        self, stage: Usd.Stage, unresolved_paths: list[str]
    ) -> list[tuple[str, str, str]]:
        prims = list(stage.TraverseAll())
        return list(
            self._collect_invalid_packaging_assets(prims, unresolved_paths, include_missing_authored_textures=False)
        )

    def _get_original_path(self, temp_layer_path: str) -> str | None:
        original_name = self._temp_files.get(_OmniUrl(temp_layer_path).path)
        return _OmniUrl(temp_layer_path).with_name(original_name).path if original_name else None

    def _get_redirected_dependencies(
        self, temp_root_layer: Sdf.Layer, external_mod_paths: list[Path]
    ) -> tuple[set[str], set[str]]:
        mod_dependencies = set()
        redirected_dependencies = set()

        all_layers, all_assets, _ = UsdUtils.ComputeAllDependencies(temp_root_layer.identifier)
        all_dependencies = [*[layer.identifier for layer in all_layers], *all_assets]

        self._packaging_new_stage("Redirecting dependencies...", len(all_dependencies))

        # Update all the layer dependencies in this layer
        for dependency in all_dependencies:
            if self._cancel_token:
                return mod_dependencies, redirected_dependencies

            self.current_count += 1

            dependency_path = _OmniUrl(dependency).path

            # If dependency is in the capture directory, we should not redirect the dependency
            if (_OmniUrl(_REMIX_DEPENDENCIES_FOLDER) / _REMIX_CAPTURE_FOLDER).path in dependency_path:
                continue

            # Check if the dependency comes from a known mod
            external_mod = None
            for mod_path in external_mod_paths:
                if (_OmniUrl(_REMIX_MODS_FOLDER) / mod_path.parent.name).path in dependency_path:
                    external_mod = mod_path.as_posix()
                    break

            # If the dependency points to a known mod, redirect it to the installed mod and store the mod path
            if external_mod:
                mod_dependencies.add(external_mod)
                redirected_dependencies.add(dependency_path)

        return mod_dependencies, redirected_dependencies

    def _update_layer_metadata(
        self, model: _ModPackagingSchema, layer: Sdf.Layer, mod_dependencies: set[str], update_dependencies: bool
    ) -> list[str]:
        errors = []

        if self._cancel_token:
            return errors

        # Build a tree-shaken dict of mod dependencies with and their versions
        dependencies = {}
        if update_dependencies:
            for dependency in mod_dependencies:
                if self._cancel_token:
                    return errors

                dependency_layer = Sdf.Layer.OpenAsAnonymous(dependency, metadataOnly=True)
                if dependency_layer:
                    dependency_name = dependency_layer.customLayerData.get(_LSS_LAYER_MOD_NAME, None)
                    dependency_version = dependency_layer.customLayerData.get(_LSS_LAYER_MOD_VERSION, None)
                else:
                    dependency_name = None
                    dependency_version = None

                if not dependency_name or not dependency_version:
                    errors.append(
                        f'Invalid mod dependency was found: "{dependency}". Dependencies must to be packaged mods.'
                    )
                else:
                    dependencies[dependency_name] = dependency_version

        # Make sure to reload the root mod layer from its persistent state to discard packaging changes
        layer.Reload()

        # Update the mod metadata with the mod information
        mod_custom_data = layer.customLayerData
        mod_custom_data[_LSS_LAYER_MOD_NAME] = model.mod_name
        mod_custom_data[_LSS_LAYER_MOD_VERSION] = model.mod_version
        if model.mod_details:
            mod_custom_data[_LSS_LAYER_MOD_NOTES] = model.mod_details
        if update_dependencies:
            mod_custom_data[_LSS_LAYER_MOD_DEPENDENCIES] = dependencies
        layer.customLayerData = mod_custom_data

        # Save the mod metadata
        layer.Save()

        return errors

    def _redirect_to_existing_project(self, _: Sdf.Layer, relative_path: str) -> str:
        if self._cancel_token:
            return relative_path
        return relative_path.replace(f"{_REMIX_DEPENDENCIES_FOLDER}/", "../../")

    def _redirect_inside_package_directory(
        self, dependency_path: str, output_directory: Path | str, temp_layer: Sdf.Layer, relative_path: str
    ) -> str:
        if self._cancel_token:
            return relative_path

        fixed_relative_path = relative_path

        # Make sure absolute paths are converted to relative paths
        relative_path_is_absolute = Path(relative_path).is_absolute()
        if relative_path_is_absolute:
            fixed_relative_path = (_OmniUrl(_REMIX_SUBUSD_RELATIVE_PATH) / _OmniUrl(relative_path).name).path

        # If the parent was collected, make sure to add its relative path from the output directory to the child deps.
        # IMPORTANT NOTE: This assumes the parent was collected before the dependency which entirely depends on the
        # USD Utils implementation and there doesn't seem to be any guarantee that this will remain true.
        parent_relative_path = self._collected_dependencies.get(_OmniUrl(temp_layer.identifier).path, "")
        if parent_relative_path:
            parent_relative_path = _OmniUrl(parent_relative_path).parent_url

        output_path = self._simplify_relative_path(
            (_OmniUrl(output_directory) / parent_relative_path / fixed_relative_path).path
        )

        # If the resulting output path is outside the output directory, the relative path should be modified
        if not str(output_path).startswith(_OmniUrl(output_directory).path):
            fixed_relative_path = re.sub("^((?:./)*../)+", _REMIX_SUBUSD_RELATIVE_PATH, fixed_relative_path)

        # Normalize the path
        fixed_relative_path = _OmniUrl(fixed_relative_path).path

        # Make sure to keep the preceding "./" if it was there in the first place
        if not fixed_relative_path.startswith("./") and not fixed_relative_path.startswith("../"):
            fixed_relative_path = f"./{fixed_relative_path}"

        # Store the dependency's overall relative output path for collection and future dependencies paths
        self._collected_dependencies[dependency_path] = (_OmniUrl(parent_relative_path) / fixed_relative_path).path

        return fixed_relative_path

    def _modify_asset_paths(
        self, temp_layer: Sdf.Layer, dependency_updates: dict[str, Callable[[Sdf.Layer, str], str]], relative_path: str
    ) -> str:
        if self._cancel_token:
            return relative_path

        fixed_relative_path = relative_path

        # If the asset is on a different drive, the path will be absolute
        if Path(relative_path).is_absolute():
            absolute_url = _OmniUrl(relative_path)
        else:
            # Try to resolve the relative path in the current layer to find its absolute path
            absolute_url = _OmniUrl(_OmniUrl(temp_layer.identifier).parent_url) / relative_path
        absolute_path = self._simplify_relative_path(absolute_url.path)

        # If we found an existing resolved asset, and it should be updated, update the reference
        if absolute_url.exists and absolute_path in dependency_updates:
            fixed_relative_path = dependency_updates[absolute_path](temp_layer, relative_path)

        return fixed_relative_path

    def _simplify_relative_path(self, relative_path: str) -> str:
        """
        Remove `./`, as well as `../` and the parent directory from relative paths to simplify them.

        Args:
            relative_path: A POSIX path (/ separator) to simplify

        Returns:
            A simplified POSIX path.
        """
        simplified_path = relative_path

        # Remove `./`
        pattern_single = re.compile("(.*)[^.]\\.(/.*)")
        match_single = re.search(pattern_single, simplified_path)
        while match_single:
            simplified_path = f"{match_single.group(1)}{match_single.group(2)}"
            match_single = re.search(pattern_single, simplified_path)

        # Remove `../`
        pattern_double = re.compile("(.*)/(?!\\.\\.).+?/\\.\\.(/.*)")
        match_double = re.search(pattern_double, simplified_path)
        while match_double:
            simplified_path = f"{match_double.group(1)}{match_double.group(2)}"
            match_double = re.search(pattern_double, simplified_path)

        return simplified_path

    def _packaging_new_stage(self, status: str, total_count: int):
        self._status = status
        self._current_count = 0
        self._total_count = total_count
        self._packaging_progress()

    def _packaging_update_status(self, status: str):
        self._status = status
        self._packaging_progress()

    def _packaging_progress(self):
        """Call the event object that has the list of functions"""
        self.__packaging_progress(self.current_count, self.total_count, self.status)

    def subscribe_packaging_progress(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__packaging_progress, function)

    def _packaging_completed(self, errors: list[str], failed_assets: list[tuple[str, str, str]]):
        """Call the event object that has the list of functions"""
        for error in errors:
            carb.log_error(error)
        self.__packaging_completed(errors, failed_assets, self._cancel_token)
        self._cancel_token = False

    def subscribe_packaging_completed(self, function: Callable[[list[str], list[tuple[str, str, str]], bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__packaging_completed, function)

    def destroy(self):
        _reset_default_attrs(self)

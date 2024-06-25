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

import re
import uuid
from asyncio import ensure_future
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Set, Tuple, Union

import carb
import omni.client
import omni.kit.app
import omni.kit.commands
import omni.usd
from lightspeed.common.constants import REMIX_CAPTURE_FOLDER as _REMIX_CAPTURE_FOLDER
from lightspeed.common.constants import REMIX_DEPENDENCIES_FOLDER as _REMIX_DEPENDENCIES_FOLDER
from lightspeed.common.constants import REMIX_MODS_FOLDER as _REMIX_MODS_FOLDER
from lightspeed.common.constants import REMIX_SUBUSD_RELATIVE_PATH as _REMIX_SUBUSD_RELATIVE_PATH
from lightspeed.layer_manager.core import LSS_LAYER_MOD_DEPENDENCIES as _LSS_LAYER_MOD_DEPENDENCIES
from lightspeed.layer_manager.core import LSS_LAYER_MOD_NAME as _LSS_LAYER_MOD_NAME
from lightspeed.layer_manager.core import LSS_LAYER_MOD_NOTES as _LSS_LAYER_MOD_NOTES
from lightspeed.layer_manager.core import LSS_LAYER_MOD_VERSION as _LSS_LAYER_MOD_VERSION
from lightspeed.trex.packaging.core.items import ModPackagingSchema as _ModPackagingSchema
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.utils.material_converter.utils import MaterialConverterUtils as _MaterialConverterUtils
from omni.kit.usd.collect.omni_client_wrapper import OmniClientWrapper as _OmniClientWrapper
from omni.kit.usd.layers import LayerUtils as _LayerUtils
from pxr import Sdf, UsdUtils

if TYPE_CHECKING:
    from pxr import Usd


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
        self._status = "(0/7) Initializing"
        self._temp_files = {}

        self.__packaging_progress = _Event()
        self.__packaging_completed = _Event()

    def package(self, schema: Dict):
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
    async def package_async(self, schema: Dict):
        """
        Asynchronous implementation of package
        """
        await self.package_async_with_exceptions(schema)

    async def package_async_with_exceptions(self, schema: Dict):
        """
        Asynchronous implementation of package, but async without error handling.  This is meant for testing.
        """
        errors = []
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
            self._packaging_new_stage("(1/7) Filtering the selected layers...", 1)
            temp_layers = await self._filter_sublayers(
                model.context_name,
                None,
                temp_root_mod_layer,
                [_OmniUrl(p).path.lower() for p in model.selected_layer_paths],
            )
            self.current_count += 1

            # Get the updated external mods dependencies pointing to the installed external mods
            if model.redirect_external_dependencies:
                mod_dependencies, redirected_dependencies = self._get_redirected_dependencies(
                    temp_root_mod_layer, [m for m in model.mod_layer_paths if m not in model.selected_layer_paths]
                )
            # No dependencies will be redirected
            else:
                mod_dependencies = set()
                redirected_dependencies = set()

            # Don't use the omni collector because it's not flexible enough
            errors.extend(
                await self._collect(temp_root_mod_layer, temp_layers, model.output_directory, redirected_dependencies)
            )

            exported_mod_layer = Sdf.Layer.FindOrOpen(
                str(
                    _OmniUrl(model.output_directory)
                    / _OmniUrl(self._temp_files.get(_OmniUrl(temp_root_mod_layer.identifier).path)).name
                )
            )
            if exported_mod_layer:
                errors.extend(self._update_layer_metadata(model, exported_mod_layer, mod_dependencies, True))
                errors.extend(self._update_layer_metadata(model, root_mod_layer, mod_dependencies, False))
            else:
                errors.append("Unable to find the exported mod file.")
        except Exception as e:  # noqa PLW0718
            if not errors:
                errors = []
            errors.append(str(e))
        finally:
            # Cleanup the temp files
            await self._clean_temp_files()
            # Reset the cancel state
            self._packaging_completed(errors)

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
        Get the current total items count
        """
        return self._status

    @omni.usd.handle_exception
    async def _make_temp_layer(self, layer_path: str) -> str:
        layer_url = _OmniUrl(layer_path)
        temp_path = layer_url.with_name(
            _OmniUrl(layer_url.stem + f"_{uuid.uuid4()}").with_suffix(layer_url.suffix).path
        ).path

        await _OmniClientWrapper.copy(layer_path, temp_path, set_target_writable_if_read_only=True)

        self._temp_files[temp_path] = layer_url.name
        return temp_path

    def _get_original_path(self, temp_layer_path: str) -> Optional[str]:
        original_name = self._temp_files.get(_OmniUrl(temp_layer_path).path)
        return _OmniUrl(temp_layer_path).with_name(original_name).path if original_name else None

    @omni.usd.handle_exception
    async def _clean_temp_files(self):
        self._packaging_new_stage("(7/7) Cleaning up temporary layers...", len(self._temp_files))

        for temp_file in self._temp_files:
            try:
                await _OmniClientWrapper.delete(str(temp_file))
            except Exception:  # noqa PLW0718
                carb.log_warn(f"Unable to cleanup temporary layer: {temp_file}")
            self.current_count += 1
        self._temp_files.clear()

    @omni.usd.handle_exception
    async def _initialize_usd_stage(self, context_name: str, root_mod_layer_path: str) -> "Usd.Stage":
        # Make sure the context exists
        context = omni.usd.get_context(context_name)
        if not context:
            context = omni.usd.create_context(context_name)

        if not context:
            return None

        # Using `open_stage_async` causes a crash here
        context.open_stage(root_mod_layer_path)

        return context.get_stage()

    @omni.usd.handle_exception
    async def _filter_sublayers(
        self,
        context_name: str,
        parent_layer: Optional[Sdf.Layer],
        temp_layer: Sdf.Layer,
        selected_layer_paths: List[str],
    ) -> List[str]:
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
                    omni.kit.commands.execute(
                        "RemoveSublayerCommand",
                        layer_identifier=parent_layer.identifier,
                        sublayer_position=sublayer_position,
                        usd_context=context_name,
                    )
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

    def _get_redirected_dependencies(
        self, temp_root_layer: Sdf.Layer, external_mod_paths: List[Path]
    ) -> Tuple[Set[str], Set[str]]:
        mod_dependencies = set()
        redirected_dependencies = set()

        all_layers, all_assets, _ = UsdUtils.ComputeAllDependencies(temp_root_layer.identifier)
        all_dependencies = [*[layer.identifier for layer in all_layers], *all_assets]

        self._packaging_new_stage("(2/7) Redirecting dependencies...", len(all_dependencies))

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

    @omni.usd.handle_exception
    async def _collect(
        self,
        temp_root_layer: Sdf.Layer,
        existing_temp_layers: List[str],
        output_directory: Union[Path, str],
        redirected_dependencies: Set[str],
    ) -> List[str]:
        errors = []

        if self._cancel_token:
            return errors

        all_layers, all_assets, unresolved_paths = UsdUtils.ComputeAllDependencies(temp_root_layer.identifier)

        self._packaging_new_stage("(3/7) Creating temporary layers...", len(all_layers))

        temp_layers_map = {self._get_original_path(temp_layer): temp_layer for temp_layer in existing_temp_layers}
        temp_layers = []
        for layer in all_layers:
            if self._cancel_token:
                return errors

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

        for unresolved_path in unresolved_paths:
            errors.append(f"Unresolved asset found when collecting dependencies: {unresolved_path}")

        if errors or self._cancel_token:
            return errors

        temp_layer_paths = {_OmniUrl(temp_layer.identifier).path: temp_layer for temp_layer in temp_layers}
        all_dependencies = [*temp_layer_paths.keys(), *all_assets]

        self._packaging_new_stage("(4/7) Listing assets to collect...", len(all_dependencies))

        updated_dependencies = {}
        shader_subidentifiers = [url.name for url in _MaterialConverterUtils.get_material_library_shader_urls()]

        for dependency in all_dependencies:
            if self._cancel_token:
                return errors

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

        self._packaging_new_stage("(5/7) Updating asset paths...", len(temp_layers))

        for temp_layer in temp_layers:
            if self._cancel_token:
                return errors
            self.current_count += 1
            UsdUtils.ModifyAssetPaths(temp_layer, partial(self._modify_asset_paths, temp_layer, updated_dependencies))

        # Wrap in a try for when Export fails to write the file
        try:
            if self._cancel_token:
                return errors

            # Make sure to create a clean packaging directory
            if _OmniUrl(output_directory).exists:
                await _OmniClientWrapper.delete(str(output_directory))

            self._packaging_new_stage("(6/7) Collecting assets...", len(self._collected_dependencies))

            # Copy all collected assets to the output directory
            for temp_input_path, relative_output_path in self._collected_dependencies.items():
                if self._cancel_token:
                    return errors

                output_path = _OmniUrl(output_directory) / relative_output_path
                input_path = self._get_original_path(temp_input_path)
                if input_path:
                    output_path = output_path.with_name(_OmniUrl(input_path).name)

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
                    input_layer.Export(str(output_path))
                # Otherwise simply copy the dependency to the output directory
                else:
                    await _OmniClientWrapper.copy(temp_input_path, str(output_path))

                self.current_count += 1
        # Make sure to bubble up failures
        except Exception as e:  # noqa PLW0706
            errors.append(e)

        # Clear assets marked for collection now that they were copied
        self._collected_dependencies.clear()

        return errors

    def _update_layer_metadata(
        self, model: _ModPackagingSchema, layer: Sdf.Layer, mod_dependencies: Set[str], update_dependencies: bool
    ) -> List[str]:
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
        self, dependency_path: str, output_directory: Union[Path, str], temp_layer: Sdf.Layer, relative_path: str
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
        self, temp_layer: Sdf.Layer, dependency_updates: Dict[str, Callable[[Sdf.Layer, str], str]], relative_path: str
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

    def _packaging_progress(self):
        """Call the event object that has the list of functions"""
        self.__packaging_progress(self.current_count, self.total_count, self.status)

    def subscribe_packaging_progress(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__packaging_progress, function)

    def _packaging_completed(self, errors: List[str]):
        """Call the event object that has the list of functions"""
        for error in errors:
            carb.log_error(error)
        self.__packaging_completed(errors, self._cancel_token)
        self._cancel_token = False

    def subscribe_packaging_completed(self, function):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__packaging_completed, function)

    def destroy(self):
        _reset_default_attrs(self)

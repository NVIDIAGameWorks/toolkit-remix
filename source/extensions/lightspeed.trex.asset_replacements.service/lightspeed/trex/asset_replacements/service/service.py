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

from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementsCore
from lightspeed.trex.asset_replacements.core.shared.data_models import (
    AssetReplacementsValidators,
    AssetType,
    DefaultAssetDirectory,
    GetPrimsQueryModel,
    PrimPathsResponseModel,
    PrimTypes,
    SetSelectionPathParamModel,
)
from lightspeed.trex.asset_replacements.core.shared.data_models.models import (
    AppendReferenceRequestModel,
    DirectoryResponseModel,
    FilePathsResponseModel,
    GetAvailableAssetsQueryModel,
    GetTexturesQueryModel,
    PrimInstancesPathParamModel,
    PrimReferencePathParamModel,
    PrimTexturesPathParamModel,
    ReferenceResponseModel,
    ReplaceReferenceRequestModel,
    TexturesResponseModel,
)
from omni.flux.asset_importer.core.data_models import TextureTypeNames
from omni.flux.service.factory import ServiceBase


class AssetReplacementsService(ServiceBase):
    def __init__(self, context_name: str = ""):
        """
        A service class that provides access to asset replacement functionality in a RestAPI.

        Args:
            context_name: The USD context name
        """

        self.__context_name = context_name
        self.__asset_core = AssetReplacementsCore(context_name=context_name)

        super().__init__()

    @classmethod
    @property
    def prefix(cls) -> str:
        return "/assets"

    def register_endpoints(self):
        context_name = self.__context_name
        prim_path_description = "The prim path to the asset that will be inspected for {0}"

        @self.router.get(
            path="/default-directory/models/available",
            operation_id="get_available_model_assets",
            description=(
                "Get the list of available non-ingested model assets. "
                "This will use the default output directory for non-ingested model assets to list the available assets."
            ),
            response_model=FilePathsResponseModel,
        )
        async def get_available_model_assets() -> DirectoryResponseModel:
            try:
                return self.__asset_core.get_available_assets_with_data_model(directory=DefaultAssetDirectory.MODELS)
            except ValueError as e:
                ServiceBase.raise_error(404, e)

        @self.router.get(
            path="/default-directory/textures/available",
            operation_id="get_available_texture_assets",
            description=(
                "Get the list of available non-ingested texture assets. "
                "This will use the default output directory for non-ingested texture assets to list the available "
                "assets."
            ),
            response_model=FilePathsResponseModel,
        )
        # Keep this definition before "/{prim_path:path}/textures" or the router will not work
        async def get_available_texture_assets() -> DirectoryResponseModel:
            try:
                return self.__asset_core.get_available_assets_with_data_model(directory=DefaultAssetDirectory.TEXTURES)
            except ValueError as e:
                ServiceBase.raise_error(404, e)

        @self.router.get(
            path="/default-directory/available",
            operation_id="get_available_ingested_assets",
            description=(
                "Get the list of available ingested assets. "
                "This will use the default output directory for ingested assets to list the available assets."
            ),
            response_model=FilePathsResponseModel,
        )
        async def get_available_ingested_assets(
            asset_type: AssetType | None = ServiceBase.describe_query_param(  # noqa B008
                None, "A type of asset to filter the results by ('textures' or 'models')"
            ),
        ) -> DirectoryResponseModel:
            try:
                return self.__asset_core.get_available_assets_with_data_model(
                    directory=DefaultAssetDirectory.INGESTED,
                    query=GetAvailableAssetsQueryModel(asset_type=asset_type),
                )
            except ValueError as e:
                ServiceBase.raise_error(404, e)

        @self.router.get(
            path="/default-directory/models",
            operation_id="get_default_model_asset_directory",
            description="Get the default output directory for non-ingested model assets.",
            response_model=DirectoryResponseModel,
        )
        async def get_default_model_asset_directory() -> DirectoryResponseModel:
            try:
                return self.__asset_core.get_default_output_directory_with_data_model(
                    directory=DefaultAssetDirectory.MODELS
                )
            except ValueError as e:
                ServiceBase.raise_error(404, e)

        @self.router.get(
            path="/default-directory/textures",
            operation_id="get_default_texture_asset_directory",
            description="Get the default output directory for non-ingested texture assets.",
            response_model=DirectoryResponseModel,
        )
        # Keep this definition before "/{prim_path:path}/textures" or the router will not work
        async def get_default_texture_asset_directory() -> DirectoryResponseModel:
            try:
                return self.__asset_core.get_default_output_directory_with_data_model(
                    directory=DefaultAssetDirectory.TEXTURES
                )
            except ValueError as e:
                ServiceBase.raise_error(404, e)

        @self.router.get(
            path="/default-directory",
            operation_id="get_default_ingested_asset_directory",
            description="Get the default output directory for ingested assets.",
            response_model=DirectoryResponseModel,
        )
        async def get_default_ingested_asset_directory() -> DirectoryResponseModel:
            try:
                return self.__asset_core.get_default_output_directory_with_data_model(
                    directory=DefaultAssetDirectory.INGESTED
                )
            except ValueError as e:
                ServiceBase.raise_error(404, e)

        @self.router.get(
            path="/",
            operation_id="get_prim_paths",
            description="Get the the prim paths in the current stage.",
            response_model=PrimPathsResponseModel,
        )
        async def get_prim_paths(
            prim_hashes: set[str] | None = ServiceBase.describe_query_param(  # noqa B008
                None, "Filter prim paths to keep specific hashes"
            ),
            prim_types: set[PrimTypes] | None = ServiceBase.describe_query_param(  # noqa B008
                None, "Filter prim paths to keep specific types of prims"
            ),
            selection: bool = ServiceBase.describe_query_param(  # noqa B008
                False, "Select all prims (False) or the prims currently selected in the viewport (True)"
            ),
            filter_session_prims: bool = ServiceBase.describe_query_param(  # noqa B008
                False, "Filter out the prims that exist on the session layer or not"
            ),
            layer_identifier: str | None = ServiceBase.describe_query_param(  # noqa B008
                None,
                "Look for prims that exists or not on a given layer. "
                "Use the `exists` query parameter to set whether existing or non-existing prims should be "
                "returned.",
            ),
            exists: bool = ServiceBase.describe_query_param(  # noqa B008
                True,
                "Filter an prim if it exists or not on a given layer. Use in conjunction with `layer_identifier` "
                "to filter on a given layer, otherwise this parameter will be ignored.",
            ),
        ) -> PrimPathsResponseModel:
            try:
                return self.__asset_core.get_prim_paths_with_data_model(
                    GetPrimsQueryModel(
                        prim_hashes=prim_hashes,
                        prim_types=prim_types,
                        return_selection=selection,
                        filter_session_prims=filter_session_prims,
                        layer_identifier=layer_identifier,
                        exists=exists,
                        context_name=context_name,
                    )
                )
            except ValueError as e:
                ServiceBase.raise_error(422, e)

        @self.router.get(
            path="/{prim_path:path}/instances",
            operation_id="get_model_instances",
            description="Get a given model's instances. The prim must be a model.",
            response_model=PrimPathsResponseModel,
        )
        async def get_model_instances(
            prim_path: str = ServiceBase.validate_path_param(  # noqa B008
                PrimInstancesPathParamModel,
                description=prim_path_description.format("instances"),  # noqa B008
                context_name=context_name,
            ),
        ) -> PrimPathsResponseModel:
            return self.__asset_core.get_instances_with_data_model(prim_path)

        @self.router.get(
            path="/{prim_path:path}/textures",
            operation_id="get_material_textures",
            description="Get a given material's textures. The prim must be a material.",
            response_model=TexturesResponseModel,
        )
        async def get_material_textures(
            prim_path: str = ServiceBase.validate_path_param(  # noqa B008
                PrimTexturesPathParamModel,
                description=prim_path_description.format("textures"),  # noqa B008
                context_name=context_name,
            ),
            texture_types: set[TextureTypeNames] | None = ServiceBase.describe_query_param(  # noqa B008
                None, "The type of textures to look for in the given material."
            ),
        ) -> TexturesResponseModel:
            return self.__asset_core.get_textures_with_data_model(
                prim_path, GetTexturesQueryModel(texture_types=texture_types)
            )

        @self.router.get(
            path="/{prim_path:path}/file-paths",
            operation_id="get_prim_reference_file_paths",
            description="Get a given prim's reference file paths.",
            response_model=ReferenceResponseModel,
        )
        async def get_prim_reference_file_paths(
            prim_path: str = ServiceBase.validate_path_param(  # noqa B008
                PrimReferencePathParamModel,
                description=prim_path_description.format("file paths"),  # noqa B008
                context_name=context_name,
            ),
        ) -> ReferenceResponseModel:
            return self.__asset_core.get_reference_with_data_model(prim_path)

        @self.router.post(
            path="/{prim_path:path}/file-paths",
            operation_id="append_prim_reference_file_path",
            description="Append a new reference to a given prim.",
            response_model=ReferenceResponseModel,
        )
        async def append_prim_reference_file_path(
            body: ServiceBase.inject_hidden_fields(AppendReferenceRequestModel, context_name=context_name),
            prim_path: str = ServiceBase.validate_path_param(  # noqa B008
                PrimReferencePathParamModel,
                description="The prim path to append a reference to",
                context_name=context_name,
            ),
        ) -> ReferenceResponseModel:
            return self.__asset_core.append_reference_with_data_model(prim_path, body)

        @self.router.put(
            path="/{prim_path:path}/file-paths",
            operation_id="replace_prim_reference_file_path",
            description=(
                "Replace a prim's reference file path. "
                "If no existing file path is provided, the first reference will be replaced."
            ),
            response_model=ReferenceResponseModel,
        )
        async def replace_prim_reference_file_path(
            body: ServiceBase.inject_hidden_fields(ReplaceReferenceRequestModel, context_name=context_name),
            prim_path: str = ServiceBase.validate_path_param(  # noqa B008
                PrimReferencePathParamModel,
                description="The prim path for which to replace a reference",
                context_name=context_name,
            ),
        ) -> ReferenceResponseModel:
            # Extra validation is required in the endpoint since we need both the path param and the body
            try:
                if body.existing_asset_file_path or body.existing_asset_layer_id:
                    AssetReplacementsValidators.ref_exists_in_prim(
                        body.existing_asset_file_path,
                        body.existing_asset_layer_id,
                        prim_path.prim_path,
                        context_name,
                    )
                else:
                    AssetReplacementsValidators.has_at_least_one_ref(prim_path.prim_path, context_name)
            except ValueError as e:
                # Handle validation errors
                ServiceBase.raise_error(422, e)

            return self.__asset_core.replace_reference_with_data_model(prim_path, body)

        @self.router.put(
            path="/selection/{prim_paths:path}",
            operation_id="set_selection",
            description="Set the selection in the current stage.",
        )
        async def set_selection(
            prim_paths: str = ServiceBase.validate_path_param(  # noqa B008
                SetSelectionPathParamModel,
                description="Comma-separated list of prim paths to select",
                validate_list=True,
                context_name=context_name,
            ),
        ) -> str:
            return self.__asset_core.select_prim_paths_with_data_model(prim_paths) or "OK"

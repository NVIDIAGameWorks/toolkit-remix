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
    DefaultAssetDirectory,
    GetPrimsQueryModel,
    PrimsResponseModel,
    PrimTypes,
    SetSelectionPathParamModel,
)
from lightspeed.trex.asset_replacements.core.shared.data_models.models import (
    AppendReferenceRequestModel,
    AssetPathResponseModel,
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
        asset_path_description = "The asset path to the asset that will be inspected for {0}"

        @self.router.get(
            path="/default-directory/models",
            description="Get the default output directory for non-ingested model assets.",
            response_model=AssetPathResponseModel,
        )
        async def get_default_model_asset_path_directory() -> AssetPathResponseModel:
            try:
                return self.__asset_core.get_default_output_directory_with_data_model(
                    directory=DefaultAssetDirectory.MODELS
                )
            except ValueError as e:
                ServiceBase.raise_error(404, e)

        @self.router.get(
            path="/default-directory/textures",
            description="Get the default output directory for non-ingested texture assets.",
            response_model=AssetPathResponseModel,
        )
        # Keep this definition before "/{asset_path:path}/textures" or the router will not work
        async def get_default_texture_asset_path_directory() -> AssetPathResponseModel:
            try:
                return self.__asset_core.get_default_output_directory_with_data_model(
                    directory=DefaultAssetDirectory.TEXTURES
                )
            except ValueError as e:
                ServiceBase.raise_error(404, e)

        @self.router.get(
            path="/default-directory",
            description="Get the default output directory for ingested assets.",
            response_model=AssetPathResponseModel,
        )
        async def get_default_ingested_asset_path_directory() -> AssetPathResponseModel:
            try:
                return self.__asset_core.get_default_output_directory_with_data_model(
                    directory=DefaultAssetDirectory.INGESTED
                )
            except ValueError as e:
                ServiceBase.raise_error(404, e)

        @self.router.get(
            path="/",
            description="Get the the assets in the current stage.",
            response_model=PrimsResponseModel,
        )
        async def get_assets(
            asset_hashes: set[str] | None = ServiceBase.describe_query_param(  # noqa B008
                None, "Filter assets to keep specific hashes"
            ),
            asset_types: set[PrimTypes] | None = ServiceBase.describe_query_param(  # noqa B008
                None, "Filter assets to keep specific types of assets"
            ),
            selection: bool = ServiceBase.describe_query_param(  # noqa B008
                False, "Select all assets (False) or the stage selection (True)"
            ),
            filter_session_assets: bool = ServiceBase.describe_query_param(  # noqa B008
                False, "Filter out the assets that exist on the session layer or not"
            ),
            layer_identifier: str | None = ServiceBase.describe_query_param(  # noqa B008
                None,
                "Look for assets that exists or not on a given layer. "
                "Use the `exists` query parameter to set whether existing or non-existing assets should be "
                "returned.",
            ),
            exists: bool = ServiceBase.describe_query_param(  # noqa B008
                True,
                "Filter an asset if it exists or not on a given layer. Use in conjunction with `layer_identifier` "
                "to filter on a given layer, otherwise this parameter will be ignored.",
            ),
        ) -> PrimsResponseModel:
            try:
                return self.__asset_core.get_prim_paths_with_data_model(
                    GetPrimsQueryModel(
                        asset_hashes=asset_hashes,
                        asset_types=asset_types,
                        return_selection=selection,
                        filter_session_prims=filter_session_assets,
                        layer_identifier=layer_identifier,
                        exists=exists,
                        context_name=context_name,
                    )
                )
            except ValueError as e:
                ServiceBase.raise_error(422, e)

        @self.router.get(
            path="/{asset_path:path}/instances",
            description="Get a given model's instances. The asset must be a model.",
            response_model=PrimsResponseModel,
        )
        async def get_model_instances(
            asset_path: str = ServiceBase.validate_path_param(  # noqa B008
                PrimInstancesPathParamModel,
                description=asset_path_description.format("instances"),  # noqa B008
                context_name=context_name,
            ),
        ) -> PrimsResponseModel:
            return self.__asset_core.get_instances_with_data_model(asset_path)

        @self.router.get(
            path="/{asset_path:path}/textures",
            description="Get a given material's textures. The asset must be a material.",
            response_model=TexturesResponseModel,
        )
        async def get_material_textures(
            asset_path: str = ServiceBase.validate_path_param(  # noqa B008
                PrimTexturesPathParamModel,
                description=asset_path_description.format("textures"),  # noqa B008
                context_name=context_name,
            ),
            texture_types: set[TextureTypeNames] | None = ServiceBase.describe_query_param(  # noqa B008
                None, "The type of textures to look for in the given material."
            ),
        ) -> TexturesResponseModel:
            return self.__asset_core.get_textures_with_data_model(
                asset_path, GetTexturesQueryModel(texture_types=texture_types)
            )

        @self.router.get(
            path="/{asset_path:path}/file-paths",
            description="Get a given asset's file source paths.",
            response_model=ReferenceResponseModel,
        )
        async def get_asset_file_paths(
            asset_path: str = ServiceBase.validate_path_param(  # noqa B008
                PrimReferencePathParamModel,
                description=asset_path_description.format("file paths"),  # noqa B008
                context_name=context_name,
            ),
        ) -> ReferenceResponseModel:
            return self.__asset_core.get_reference_with_data_model(asset_path)

        @self.router.post(
            path="/{asset_path:path}/file-paths",
            description="Append a new asset file path.",
            response_model=ReferenceResponseModel,
        )
        async def append_asset_file_path(
            body: ServiceBase.inject_hidden_fields(AppendReferenceRequestModel, context_name=context_name),
            asset_path: str = ServiceBase.validate_path_param(  # noqa B008
                PrimReferencePathParamModel,
                description="The path to the asset to append a file path to",
                context_name=context_name,
            ),
        ) -> ReferenceResponseModel:
            return self.__asset_core.append_reference_with_data_model(asset_path, body)

        @self.router.put(
            path="/{asset_path:path}/file-paths",
            description=(
                "Replace an asset file path. "
                "If no existing file path is provided, the first file path will be replaced."
            ),
            response_model=ReferenceResponseModel,
        )
        async def replace_asset_file_path(
            body: ServiceBase.inject_hidden_fields(ReplaceReferenceRequestModel, context_name=context_name),
            asset_path: str = ServiceBase.validate_path_param(  # noqa B008
                PrimReferencePathParamModel,
                description="The path to the asset to replace a file path",
                context_name=context_name,
            ),
        ) -> ReferenceResponseModel:
            # Extra validation is required in the endpoint since we need both the path param and the body
            try:
                if body.existing_asset_file_path or body.existing_asset_layer_id:
                    AssetReplacementsValidators.ref_exists_in_prim(
                        body.existing_asset_file_path,
                        body.existing_asset_layer_id,
                        asset_path.asset_path,
                        context_name,
                    )
                else:
                    AssetReplacementsValidators.has_at_least_one_ref(asset_path.asset_path, context_name)
            except ValueError as e:
                # Handle validation errors
                ServiceBase.raise_error(422, e)

            return self.__asset_core.replace_reference_with_data_model(asset_path, body)

        @self.router.put(path="/selection/{asset_paths:path}", description="Set the selection in the current stage.")
        async def set_selection(
            asset_paths: str = ServiceBase.validate_path_param(  # noqa B008
                SetSelectionPathParamModel,
                description="Comma-separated list of asset paths to select",
                validate_list=True,
                context_name=context_name,
            )
        ) -> str:
            return self.__asset_core.select_prim_paths_with_data_model(asset_paths) or "OK"

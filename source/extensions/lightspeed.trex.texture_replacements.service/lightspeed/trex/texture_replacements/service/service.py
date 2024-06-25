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

from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore
from lightspeed.trex.texture_replacements.core.shared.data_models import (
    GetTexturesQueryModel,
    PrimsResponseModel,
    ReplaceTexturesRequestModel,
    TextureMaterialPathParamModel,
    TexturesResponseModel,
    TextureTypesResponseModel,
)
from omni.flux.asset_importer.core.data_models import TextureTypeNames
from omni.flux.service.factory import ServiceBase


class TextureReplacementsService(ServiceBase):
    def __init__(self, context_name: str = ""):
        """
        A service class that provides access to texture replacement functionality in a RestAPI.

        Args:
            context_name: The USD context name
        """

        self.__context_name = context_name
        self.__texture_core = TextureReplacementsCore(context_name=context_name)

        super().__init__()

    @classmethod
    @property
    def prefix(cls) -> str:
        return "/textures"

    def register_endpoints(self):
        context_name = self.__context_name

        @self.router.get(
            path="/",
            description="Get the texture properties and associated asset paths in the current stage.",
            response_model=TexturesResponseModel,
        )
        async def get_textures(
            asset_hashes: set[str] | None = ServiceBase.describe_query_param(  # noqa B008
                None, "Filter textures to keep textures from specific material hashes"
            ),
            texture_types: set[TextureTypeNames] | None = ServiceBase.describe_query_param(  # noqa B008
                None, "The types of textures to look for"
            ),
            selection: bool = ServiceBase.describe_query_param(  # noqa B008
                False, "Select all prims (False) or the stage selection (True)"
            ),
            filter_session_prims: bool = ServiceBase.describe_query_param(  # noqa B008
                False, "Filter out prims that exist on the session layer or not"
            ),
            layer_identifier: str | None = ServiceBase.describe_query_param(  # noqa B008
                None,
                "Look for textures that exist or not on a given layer. "
                "Use the `exists` query parameter to set whether existing or non-existing textures should be "
                "returned.",
            ),
            exists: bool = ServiceBase.describe_query_param(  # noqa B008
                True,
                "Filter an texture if it exists or not on a given layer. Use in conjunction with `layer_identifier` "
                "to filter on a given layer, otherwise this parameter will be ignored.",
            ),
        ) -> TexturesResponseModel:
            try:
                return self.__texture_core.get_texture_prims_assets_with_data_models(
                    GetTexturesQueryModel(
                        asset_hashes=asset_hashes,
                        texture_types=texture_types,
                        return_selection=selection,
                        filter_session_prims=filter_session_prims,
                        layer_identifier=layer_identifier,
                        exists=exists,
                        context_name=context_name,
                    )
                )
            except ValueError as e:
                ServiceBase.raise_error(422, e)

        @self.router.put(
            path="/",
            description="Override the given textures on the current edit target in the current stage.",
        )
        async def override_textures(
            body: ServiceBase.inject_hidden_fields(ReplaceTexturesRequestModel, context_name=context_name)
        ) -> str:
            return self.__texture_core.replace_texture_with_data_models(body) or "OK"

        @self.router.get(
            path="/types",
            description="Get a list of the available texture types.",
            response_model=TextureTypesResponseModel,
        )
        async def get_texture_types() -> TextureTypesResponseModel:
            return TextureTypesResponseModel(texture_types=[item.value for item in TextureTypeNames])

        @self.router.get(
            path="/{texture_asset_path:path}/material",
            description="Get the parent material for a given texture asset path.",
            response_model=PrimsResponseModel,
        )
        async def get_texture_material(
            texture_asset_path: str = ServiceBase.validate_path_param(  # noqa B008
                TextureMaterialPathParamModel,
                description="The asset path of a given texture",
                context_name=context_name,
            )
        ) -> PrimsResponseModel:
            try:
                return self.__texture_core.get_texture_material_with_data_models(texture_asset_path)
            except ValueError as e:
                ServiceBase.raise_error(404, e)

        @self.router.get(
            path="/{texture_asset_path:path}/material/inputs",
            description="Get the parent material inputs for a given texture asset path.",
            response_model=PrimsResponseModel,
        )
        async def get_texture_material_inputs(
            texture_asset_path: str = ServiceBase.validate_path_param(  # noqa B008
                TextureMaterialPathParamModel,
                description="The asset path of a given texture",
                context_name=context_name,
            ),
            texture_type: TextureTypeNames | str = ServiceBase.describe_query_param(  # noqa B008
                None, "Get the expected input for a given texture type or based on an ingested texture's file name."
            ),
        ) -> PrimsResponseModel:
            try:
                if texture_type is not None:
                    return await self.__texture_core.get_texture_expected_material_inputs_with_data_models(
                        texture_asset_path, texture_type=texture_type
                    )
                return await self.__texture_core.get_texture_material_inputs_with_data_models(texture_asset_path)
            except ValueError as e:
                ServiceBase.raise_error(404, e)

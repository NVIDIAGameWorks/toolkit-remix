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

from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from lightspeed.layer_manager.core.data_models import (
    CreateLayerRequestModel,
    DeleteLayerPathParamModel,
    DeleteLayerRequestModel,
    GetLayerPathParamModel,
    GetLayersQueryModel,
    LayerResponseModel,
    LayerStackResponseModel,
    LayerTypeResponseModel,
    LockLayerPathParamModel,
    LockLayerRequestModel,
    MoveLayerPathParamModel,
    MoveLayerRequestModel,
    MuteLayerPathParamModel,
    MuteLayerRequestModel,
    SaveLayerPathParamModel,
    SetEditTargetPathParamModel,
)
from omni.flux.service.factory import ServiceBase
from pydantic import constr


class LayerManagerService(ServiceBase):
    def __init__(self, context_name: str = ""):
        """
        A service class that provides access to layer management functionality in a RestAPI.

        Args:
            context_name: The USD context name
        """

        self.__context_name = context_name
        self.__layer_core = LayerManagerCore(context_name=context_name)

        super().__init__()

    @classmethod
    @property
    def prefix(cls) -> str:
        return "/layers"

    def register_endpoints(self):
        context_name = self.__context_name
        layer_types_pattern = f"{'|'.join([layer_type.name for layer_type in LayerType])}|None"

        @self.router.get(
            path="/",
            description="Get the layer tree in the current stage.",
            response_model=LayerStackResponseModel,
        )
        async def get_layers(
            # Use regex to validate the enum values since None is also a valid type
            layer_types: set[constr(regex=layer_types_pattern)] = ServiceBase.describe_query_param(  # noqa B008,F722
                None, "The type of layer to get. Filtering by layer type will ignore layer children."
            ),
            layer_count: int = ServiceBase.describe_query_param(  # noqa B008
                -1,
                "The number of layers to get per `layer_type`. "
                "If `layer_type` is not set this parameter will have no effect. "
                "Use -1 to get all the layers.",
            ),
        ) -> LayerStackResponseModel:
            return self.__layer_core.get_layer_stack_with_data_models(
                GetLayersQueryModel(layer_types=self.__get_layer_types(layer_types), layer_count=layer_count)
            )

        @self.router.get(
            path="/{layer_id:path}/sublayers",
            description="Get the immediate sublayers of the given layer.",
            response_model=LayerStackResponseModel,
        )
        async def get_sublayers(
            layer_id: str = ServiceBase.validate_path_param(  # noqa B008
                GetLayerPathParamModel,
                description="Layer identifier for the layer to get the sublayers from",
                context_name=context_name,
            ),
            layer_types: set[constr(regex=layer_types_pattern)] = ServiceBase.describe_query_param(  # noqa B008,F722
                None, "The type of layer to get."
            ),
        ) -> LayerStackResponseModel:
            try:
                return self.__layer_core.get_sublayers_with_data_models(
                    layer_id,
                    GetLayersQueryModel(layer_types=self.__get_layer_types(layer_types)),
                )
            except ValueError as e:
                ServiceBase.raise_error(422, e)

        @self.router.post(path="/", description="Create a layer in the current stage.")
        async def create_layer(
            body: ServiceBase.inject_hidden_fields(CreateLayerRequestModel, context_name=context_name)
        ) -> str:
            return self.__layer_core.create_layer_with_data_model(body) or "OK"

        @self.router.delete(
            path="/{layer_id:path}",
            description="Remove a layer from the current stage.",
        )
        async def remove_layer(
            body: ServiceBase.inject_hidden_fields(DeleteLayerRequestModel, context_name=context_name),
            layer_id: str = ServiceBase.validate_path_param(  # noqa B008
                DeleteLayerPathParamModel,
                description="Layer identifier for the layer to remove",
                context_name=context_name,
            ),
        ) -> str:
            return self.__layer_core.remove_layer_with_data_model(layer_id, body) or "OK"

        @self.router.put(
            path="/{layer_id:path}/move",
            description="Move a layer in the current stage.",
        )
        async def move_layer(
            body: ServiceBase.inject_hidden_fields(MoveLayerRequestModel, context_name=context_name),
            layer_id: str = ServiceBase.validate_path_param(  # noqa B008
                MoveLayerPathParamModel, description="Layer identifier for the layer to move", context_name=context_name
            ),
        ) -> str:
            return self.__layer_core.move_layer_with_data_model(layer_id, body) or "OK"

        @self.router.put(
            path="/{layer_id:path}/lock",
            description="Lock or unlock a layer in the current stage.",
        )
        async def lock_layer(
            body: ServiceBase.inject_hidden_fields(LockLayerRequestModel, context_name=context_name),
            layer_id: str = ServiceBase.validate_path_param(  # noqa B008
                LockLayerPathParamModel,
                description="Layer identifier for the layer to lock/unlock",
                context_name=context_name,
            ),
        ) -> str:
            return self.__layer_core.lock_layer_with_data_model(layer_id, body) or "OK"

        @self.router.put(
            path="/{layer_id:path}/mute",
            description="Mute or unmute a layer in the current stage.",
        )
        async def mute_layer(
            body: ServiceBase.inject_hidden_fields(MuteLayerRequestModel, context_name=context_name),
            layer_id: str = ServiceBase.validate_path_param(  # noqa B008
                MuteLayerPathParamModel,
                description="Layer identifier for the layer to lock/unlock",
                context_name=context_name,
            ),
        ) -> str:
            return self.__layer_core.mute_layer_with_data_model(layer_id, body) or "OK"

        @self.router.post(
            path="/{layer_id:path}/save",
            description="Save a layer in the current stage.",
        )
        async def save_layer(
            layer_id: str = ServiceBase.validate_path_param(  # noqa B008
                SaveLayerPathParamModel, description="Layer identifier for the layer to save", context_name=context_name
            )
        ) -> str:
            return self.__layer_core.save_layer_with_data_model(layer_id) or "OK"

        @self.router.get(
            path="/target",
            description="Get the active edit target in the current stage.",
            response_model=LayerResponseModel,
        )
        async def get_edit_target() -> LayerResponseModel:
            return self.__layer_core.get_edit_target_with_data_model()

        @self.router.put(
            path="/target/{layer_id:path}",
            description="Set the active edit target in the current stage.",
        )
        async def set_edit_target(
            layer_id: str = ServiceBase.validate_path_param(  # noqa B008
                SetEditTargetPathParamModel,
                description="Layer identifier for the layer to set as edit target",
                context_name=context_name,
            )
        ) -> str:
            return self.__layer_core.set_edit_target_with_data_model(layer_id) or "OK"

        @self.router.get(
            path="/types",
            description="Get the available layer types.",
            response_model=LayerTypeResponseModel,
        )
        async def get_layer_types() -> LayerTypeResponseModel:
            return LayerTypeResponseModel(layer_types=[layer_type.name for layer_type in LayerType])

    def __get_layer_types(self, layer_types: set[str]):
        return {layer_type if layer_type != "None" else None for layer_type in layer_types} if layer_types else None

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

__all__ = ["MassValidatorService"]

import traceback
from json import dumps, loads

import carb
import omni.kit.app
from omni.flux.service.factory import ServiceBase
from omni.flux.utils.common import path_utils
from omni.flux.validator.manager.core import ValidationSchema, validation_schema_json_encoder
from omni.flux.validator.mass.core import ManagerMassCore
from omni.flux.validator.mass.core.data_models import Executors, MassValidationResponseModel
from omni.flux.validator.mass.queue.core import get_mass_validation_queue_instance
from omni.flux.validator.mass.queue.core.data_models import UpdateSchemaRequestModel
from pydantic import ValidationError, create_model


class MassValidatorService(ServiceBase):
    def __init__(
        self,
        schema_models: list[dict[str, str]],
        standalone: bool = False,
    ):
        """
        A service class that provides access to mass validation functionality in a RestAPI.

        Args:
            schema_models: list of dictionaries containing schema definitions in the form:
                           [{"path": "FILE_PATH", "name": "SCHEMA_NAME"}].
            standalone: flag to indicate whether the service is running standalone or not.
        """

        self._mass_queue_core = get_mass_validation_queue_instance()
        self._schema_models = schema_models
        self._standalone = standalone

        self._update_subscriptions = {}

        super().__init__()

    @classmethod
    @property
    def prefix(cls) -> str:
        return "/mass-validator"

    def register_endpoints(self):
        @self.router.put(
            path="/schema",
            operation_id="update_ingestion_schema",
            description=(
                "Update the mass validation schema. "
                "Can be used to update the validation progress from an external process."
            ),
        )
        async def update_schema(
            body: dict,
            queue_id: str = ServiceBase.describe_query_param(None, "ID to describe which queue should be updated"),
        ) -> str:
            return (
                self._mass_queue_core.update_schema(
                    UpdateSchemaRequestModel(validation_schema=ValidationSchema(**body), queue_id=queue_id)
                )
                or "OK"
            )

        def build_queue_endpoint(_schema_model):
            """
            Dynamically build endpoints for the various schemas provided in the init
            """
            schema_path = carb.tokens.get_tokens_interface().resolve(_schema_model["path"])
            data = path_utils.read_json_file(schema_path)

            # Build a model class for FastAPI typing
            dynamic_model = create_model(
                f"Add{_schema_model['name'].capitalize()}ItemToQueue",
                executor=(Executors, 1),
                **{key: (type(value), value) for key, value in data.items()},
            )

            # Build the schema to pass to the ManagerMassCore
            schema = ValidationSchema(**data)

            @self.router.post(
                path=f"/queue/{_schema_model['name'].lower()}",
                operation_id=f"ingest_{_schema_model['name'].lower()}_asset",
                description="Add an item to the mass validation queue.",
                response_model=MassValidationResponseModel,
            )
            async def add_item_to_queue(body: dynamic_model) -> MassValidationResponseModel:
                # Update the dict non-destructively to only update the values set in the body
                updated_dict = self.__update_dict_recursively(
                    schema.model_dump(serialize_as_any=True), body.model_dump(serialize_as_any=True)
                )

                mass_core = None
                try:
                    mass_core = ManagerMassCore(schema_dicts=[updated_dict], standalone=self._standalone)
                except (ValueError, ValidationError) as e:
                    # An error occurred while building the schema model
                    ServiceBase.raise_error(422, e)

                items = mass_core.schema_model.get_item_children(None)

                tasks = {}
                for item in items:
                    if not all(item.model.is_ready_to_run().values()):
                        ServiceBase.raise_error(
                            422, "One or more input is invalid. Remove of fix the inputs before continuing."
                        )

                    cooked_templates = None
                    try:
                        cooked_templates = await item.cook_template()
                    except (ValueError, ValidationError) as e:
                        carb.log_error(traceback.format_exc())
                        ServiceBase.raise_error(422, e)

                    results = await mass_core.create_tasks(
                        body.executor,
                        cooked_templates,
                        standalone=self._standalone,
                    )

                    # Accumulate the Future variables
                    for model, task in results:
                        tasks[task] = model.model

                        # Subscribe to the schema update event and update the associated result
                        self._update_subscriptions[task] = self._mass_queue_core.subscribe_on_update_item(
                            lambda updated_schema, queue_id, t=task: tasks.update({t: updated_schema})
                        )

                # Executors can be asyncio or concurrent libraries
                tasks_in_progress = list(tasks.keys())
                while bool(tasks_in_progress):
                    await omni.kit.app.get_app().next_update_async()
                    completed_tasks = []
                    for task in tasks_in_progress:
                        if not task.done():
                            continue
                        completed_tasks.append(task)
                    for task in completed_tasks:
                        # Remove the task subscription when the task completes
                        self._update_subscriptions.pop(task)
                        tasks_in_progress.remove(task)

                if not all(v.validation_passed for v in tasks.values()):
                    ServiceBase.raise_error(
                        500, "The validation did not complete successfully. See the logs for more information."
                    )

                # Serialize to JSON using the custom encoder and convert back to a dict after
                completed_schemas_dicts = [
                    loads(dumps(v.model_dump(serialize_as_any=True), default=validation_schema_json_encoder))
                    for v in tasks.values()
                ]
                return MassValidationResponseModel(completed_schemas=completed_schemas_dicts)

            return add_item_to_queue

        for schema_model in self._schema_models:
            build_queue_endpoint(schema_model)

    def __update_dict_recursively(self, dictionary: dict, updates: dict):
        """
        Recursively update a dictionary.

        Args:
            dictionary: The dictionary to be updated.
            updates: The dictionary containing updates.

        Returns:
            The dictionary with the updates applied.
        """
        for key, value in updates.items():
            if isinstance(value, dict) and key in dictionary:
                dictionary[key] = self.__update_dict_recursively(dictionary.get(key, {}), value)
            else:
                dictionary[key] = value
        return dictionary

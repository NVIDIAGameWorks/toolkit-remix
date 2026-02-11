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
from typing import Any
from collections.abc import Callable

import carb.settings
import omni.kit.app
import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.validator.manager.core import ManagerCore as _ManagerCore

from .data_models import Executors
from .executors import CurrentProcessExecutor, ExternalProcessExecutor
from .schema_tree import model as _schema_model

SCHEMA_PATH_SETTING = "/exts/omni.flux.validator.mass.widget/schemas"  # list of paths of schema separated by a coma


class ManagerMassCore:
    def __init__(self, schema_paths: list[str] = None, schema_dicts: list[dict] = None, standalone: bool = False):
        """
        Validation mass manager that will execute the validation.

        Args:
            standalone: if this is running in pure CLI standalone mode

        """
        self.__standalone = standalone
        self.__executors = [CurrentProcessExecutor(), ExternalProcessExecutor()]

        if schema_paths is None:
            schema_paths = []

        if schema_dicts is None:
            schema_dicts = []

        default_schemas = carb.settings.get_settings().get(SCHEMA_PATH_SETTING)
        if not schema_paths and default_schemas and not schema_dicts:
            schema_paths = carb.tokens.get_tokens_interface().resolve(default_schemas)
            schema_paths = [schema_path for schema_path in schema_paths.split(",") if schema_path]

        self.__schema_datas = [_path_utils.read_json_file(schema_path) for schema_path in schema_paths]
        self.__schema_datas.extend(schema_dicts)

        self.__schema_model = _schema_model.Model()
        self.add_schemas(self.__schema_datas)

        self.__on_core_added = _Event()
        self.__on_run_finished = _Event()

    def _on_run_finished(self, validation_core, i_progress, size_progress, result, message: str | None = None):
        self.__on_run_finished(validation_core, i_progress, size_progress, result, message=message)

    def subscribe_run_finished(self, callback: Callable[[_ManagerCore, int, int, bool, str | None], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_run_finished, callback)

    def _on_core_added(self, core: _ManagerCore):
        self.__on_core_added(core)

    def subscribe_core_added(self, callback: Callable[[_ManagerCore], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_core_added, callback)

    @property
    def schema_model(self) -> _schema_model.Model:
        """Return the model that contain all the added validation schema"""
        return self.__schema_model

    def add_schemas(self, schemas: list[dict[Any, Any]]):
        """
        Add schema as an item to run

        Args:
            schemas: the schema dictionary
        """
        self.__schema_model.add_schemas(schemas)

    @omni.usd.handle_exception
    async def create_tasks_with_exception(
        self,
        executor: Executors,
        data: list[dict[Any, Any]],
        print_result: bool = False,
        silent: bool = False,
    ) -> list[tuple[_ManagerCore, asyncio.Future]]:
        """
        Run the validation using the current schema

        Args:
            executor: the executor to use
            data: list of schemas to run
            print_result: print the result or not into stdout
            silent: silent the stdout
        """
        return await self.create_tasks(executor, data, print_result=print_result, silent=silent)

    async def create_tasks(
        self,
        executor: Executors,
        data: list[dict[Any, Any]],
        custom_executors: tuple[CurrentProcessExecutor, ExternalProcessExecutor] = None,
        print_result: bool = False,
        silent: bool = False,
        timeout: int | None = None,
        standalone: bool | None = False,
        queue_id: str | None = None,
    ) -> list[tuple[_ManagerCore, asyncio.Future]]:
        """
        Run the validation using the current schema

        Args:
            executor: the executor used to select an actual executor with int index
            data: list of schemas to run
            custom_executors: optional override executors
            print_result: print the result or not into stdout
            silent: silent the stdout
            timeout: the maximum time a task should take
            standalone: does the process run in a standalone mode or not (like a CLI)
            queue_id: the queue ID to use. Needed if you have multiple widgets that shows different queues

        Returns:
            The created core validation manager + the corresponding task
        """
        result = []
        size = len(data)
        for schema in data:
            core = _ManagerCore(schema)
            actual_executor = custom_executors[int(executor)] if custom_executors else self.__executors[int(executor)]
            task = actual_executor.submit(
                core,
                print_result=print_result,
                silent=silent,
                timeout=timeout,
                standalone=standalone,
                queue_id=queue_id,
            )

            result.append((core, task))
            self._on_core_added(core)

        if self.__standalone:
            counter = 0
            while bool(result):
                await omni.kit.app.get_app().next_update_async()
                to_delete = []
                for result_data in result:
                    core, task = result_data
                    if not task.done():
                        continue
                    to_delete.append(result_data)
                    result_validation, message_validation = task.result()
                    self._on_run_finished(core, counter, size, result_validation, message_validation)
                    counter += 1
                for to_d in to_delete:
                    result.remove(to_d)

        return result

    def destroy(self):
        pass

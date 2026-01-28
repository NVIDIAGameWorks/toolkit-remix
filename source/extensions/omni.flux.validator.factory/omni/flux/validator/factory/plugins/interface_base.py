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

__all__ = ["IBase", "IBaseSchema"]

import abc
from enum import Enum
from typing import Any, Callable

from omni.flux.factory.base import PluginBase
from omni.flux.validator.factory import DataFlow as _DataFlow
from pydantic import BaseModel
from pydantic_core.core_schema import ValidationInfo


class IBase(PluginBase, abc.ABC):
    @property
    @abc.abstractmethod
    def tooltip(self) -> str:
        pass

    @property
    @abc.abstractmethod
    def data_type(self) -> type[BaseModel]:
        pass

    @property
    @abc.abstractmethod
    def display_name(self) -> str | None:
        pass

    class Data(BaseModel, abc.ABC):
        @property
        @abc.abstractmethod
        def data_flow_compatible_name(self) -> list[str] | None:
            pass

        @classmethod
        @abc.abstractmethod
        def sanitize_uuid(cls, v: str | None) -> str | None:
            pass

        @classmethod
        @abc.abstractmethod
        def _fire_progress_callback(
            cls, v: tuple[float, str, bool] | None, info: ValidationInfo
        ) -> tuple[float, str, bool] | None:
            pass

        @classmethod
        @abc.abstractmethod
        def _fire_global_progress_value_callback(cls, v: float | None, info: ValidationInfo) -> float | None:
            pass

    @abc.abstractmethod
    def set_parent_schema(self, schema: "IBaseSchema"):
        """
        Set the schema

        Args:
            schema: the schema to set
        """
        pass

    @abc.abstractmethod
    def _on_validator_run(self, items: list["IBase"], run_mode: Enum, catch_exception: bool = True):
        """
        Run the validator

        Args:
            items: if the run mode is "only selected", or "self to end", this is the item(s) to run from
            run_mode: the mode to use to run the validator
            catch_exception: catch async exception or not
        """
        pass

    @abc.abstractmethod
    def _on_validator_enable(self, value: bool):
        """
        Enable or disable the validation

        Args:
            value: True if enabled, else False
        """
        pass

    @abc.abstractmethod
    def _on_validation_is_ready_to_run(self, value: bool):
        """
        Enable or disable the validation

        Args:
            value: True if enabled, else False
        """
        pass

    @abc.abstractmethod
    def subscribe_validator_run(self, callback: Callable[[list["IBase"], Enum, bool | None], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Subscription that will let the plugin re-run a validation by itself.
        """
        pass

    @abc.abstractmethod
    def subscribe_enable_validation(self, callback: Callable[[bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Subscription that will let the plugin re-run a validation by itself.
        """
        pass

    @abc.abstractmethod
    def subscribe_on_validation_is_ready_to_run(self, callback: Callable[[int, bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Subscription that will let the plugin re-run a validation by itself.
        """
        pass

    @abc.abstractmethod
    def subscribe_build_ui(self, callback: Callable[[Any], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        pass

    @abc.abstractmethod
    def subscribe_mass_build_ui(self, callback: Callable[[Any], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        pass

    @abc.abstractmethod
    def subscribe_mass_build_queue_action_ui(self, callback: Callable[[Any], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        pass

    @abc.abstractmethod
    def on_mass_cook_template(self, success: bool, message: str, data: Any):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        pass

    @abc.abstractmethod
    def subscribe_mass_cook_template(self, callback: Callable[[tuple[bool, str | None, Any]], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        pass

    @abc.abstractmethod
    def get_progress(self) -> tuple[float, str, bool]:
        pass

    @abc.abstractmethod
    def on_progress(self, progress: float, message: str, result: bool):
        """
        Set the progression of the plugin. Setting the attribute will fire self.__on_progress
        """
        pass

    @abc.abstractmethod
    def subscribe_progress(self, callback: Callable[[float, str, bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.

        Args:
            callback: function that should be called during the progress.
                float: the progress between 0.0 and 1.0
                str: the message of the progress
                bool: the result of the plugin. At 1.0, it can be True or False.
        """
        pass

    @abc.abstractmethod
    def subscribe_global_progress(self, callback: Callable[[float], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.

        Args:
            callback: function that should be called during the progress.
                float: the progress between 0.0 and 1.0
                str: the message of the progress
                bool: the result of the plugin. At 1.0, it can be True or False.
        """
        pass

    @abc.abstractmethod
    def get_global_progress(self) -> float:
        """The value of the global progression of the validation"""
        pass

    @abc.abstractmethod
    def set_global_progress(self, value: float):
        """The value of the global progression of the validation"""
        pass

    @abc.abstractmethod
    async def on_crash(self, schema_data: Any, data: Any) -> None:
        """
        Function that will be called when a plugin crash

        Args:
            schema_data: the data of the plugin from the schema
            data: any random data we want to pass
        """
        pass

    @abc.abstractmethod
    async def _on_crash(self, schema_data: Any, data: Any) -> None:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data of the plugin from the schema
            data: any random data we want to pass
        """
        pass

    @abc.abstractmethod
    async def build_ui(self, schema_data: Any) -> Any:
        """
        Build the UI of a plugin

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        pass

    @abc.abstractmethod
    async def _build_ui(self, schema_data: Any) -> Any:
        """
        Build the UI of a plugin

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        pass

    @abc.abstractmethod
    async def mass_build_ui(self, schema_data: Any) -> Any:
        """
        Build the mass UI of a plugin. This function should not be overridden. Please implement your code using
        _mass_build_ui()

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        pass

    @abc.abstractmethod
    async def _mass_build_ui(self, schema_data: Any) -> Any:
        """
        Build the mass UI of a plugin. A mass UI is a UI that will expose some UI for mass processing. Mass processing
        will call multiple validation core. So this UI exposes controllers that will be passed to each schema.

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        pass

    @abc.abstractmethod
    def mass_build_queue_action_ui(
        self, schema_data: Any, default_actions: list[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> Any:
        """
        Default exposed action for Mass validation. The UI will be built into the delegate of the mass queue.
        Please implement your code using _mass_build_queue_action_ui()
        """
        pass

    @abc.abstractmethod
    def _mass_build_queue_action_ui(
        self, schema_data: Any, default_actions: list[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> Any:
        """
        Default exposed action for Mass validation. The UI will be built into the delegate of the mass queue.
        For example, you can add a button to open the asset into a USD viewport
        """
        pass

    @abc.abstractmethod
    async def mass_cook_template(self, schema_data_template: Any) -> tuple[bool, str | None, list[Data]]:
        """
        Take a template as an input and the (previous) result, and edit the result for mass processing.
        For example, receive 1 template that has a context plugin with a list of files, and generate multiple schema
        from the template, with 1 input file for each template.
        Please implement your code using _mass_cook_template()

        Args:
            schema_data_template: the data of the plugin from the schema

        Returns:
            A tuple of the shape `(TemplateCookingSuccess, ErrorMessage, CookingData)`
        """
        pass

    @abc.abstractmethod
    async def _mass_cook_template(self, schema_data_template: Any) -> tuple[bool, str | None, Any]:
        """
        Take a template as an input and the (previous) result, and edit the result for mass processing.
        For example, receive 1 template that has a context plugin with a list of files, and generate multiple schema
        from the template, with 1 input file for each template.

        Args:
            schema_data_template: the data of the plugin from the schema

        Returns:
            A tuple of the shape `(TemplateCookingSuccess, ErrorMessage, CookingData)`
        """
        pass

    @abc.abstractmethod
    def _get_schema_data_flows(self, schema_data: Data, schema: BaseModel) -> list[_DataFlow]:
        """Get the various data flows defined in the schema"""
        pass

    @abc.abstractmethod
    def show(self, value: bool, schema_data: Any):
        """
        Called whenever the plugin is show or hidden in the UI.
        """
        pass


class IBaseSchema(BaseModel, abc.ABC):
    @property
    @abc.abstractmethod
    def instance(self) -> Any:
        pass

    @classmethod
    @abc.abstractmethod
    def is_registered(cls, v: str) -> str:
        pass

    @abc.abstractmethod
    def destroy(self):
        pass

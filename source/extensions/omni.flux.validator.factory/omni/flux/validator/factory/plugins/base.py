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

import abc
from enum import Enum as _Enum
from typing import TYPE_CHECKING, Any, Callable, Iterable, List, Optional, Tuple, Type

import omni.usd
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from pydantic import BaseModel, Extra, Field, PrivateAttr, validator

from ..data_flow.base_data_flow import DataFlow
from ..extension import get_instance as _get_factory_instance

if TYPE_CHECKING:
    from omni.flux.validator.factory import DataFlow as _DataFlow


class ValidatorRunMode(_Enum):
    BASE_ALL = "base_all"  # re-run all plugins
    BASE_SELF_TO_END = "base_self_to_end"  # re-run from itself to the end
    BASE_ONLY_SELECTED = "base_only_selected"  # re-run only the passed list of plugins


class Base:

    name: str = NotImplementedError("Please implement a name")
    tooltip: str = NotImplementedError("Please implement a tooltip")
    data_type: Type[BaseModel] = NotImplementedError("Please implement a data model")
    display_name: Optional[str] = None

    class Data(BaseModel):
        on_progress_callback: Optional[Callable[[float, str, bool], None]] = Field(default=None, exclude=True)
        on_global_progress_callback: Optional[Callable[[float], None]] = Field(default=None, exclude=True)

        # Write data that plugins can use downstream for example.
        # Useful to do a post process at the end of the validation
        _compatible_data_flow_names: Optional[List[str]] = None  # names of data flows compatible for the plugin
        data_flows: Optional[List[DataFlow]] = None
        channel: str = "Default"
        expose_mass_ui: bool = False  # set this to true if a mass ui is implemented
        expose_mass_queue_action_ui: bool = (
            False  # set this to true if you want to show the UI from `_mass_build_queue_action_ui()`
        )
        cook_mass_template: bool = (
            False  # set this to true if you want the mass validator to use the plugin to cook the template
        )
        display_name_mass_template: str = None  # name to show when we process a cooked template from mass processing
        display_name_mass_template_tooltip: str = (
            None  # tooltip to show when we process a cooked template from mass processing
        )
        uuid: Optional[str] = None  # unique identifier to track a schema
        progress: Optional[Tuple[float, str, bool]] = (0.0, "Initializing", True)  # progression value of the plugin
        global_progress_value: Optional[float] = 0.0  # progression value of the plugin

        @property
        def data_flow_compatible_name(self):
            return self._compatible_data_flow_names

        @validator("uuid", allow_reuse=True)
        def sanitize_uuid(cls, v):  # noqa N805
            if v is not None:
                v = v.replace("-", "")
            return v

        @validator("progress", allow_reuse=True)
        def _fire_progress_callback(cls, v, values):  # noqa N805
            callback = values.get("on_progress_callback")
            if callback:
                callback(*v)
            return v

        @validator("global_progress_value", allow_reuse=True)
        def _fire_global_progress_value_callback(cls, v, values):  # noqa N805
            callback = values.get("on_global_progress_callback")
            if callback:
                callback(v)
            return v

        class Config:
            extra = Extra.forbid
            underscore_attrs_are_private = True
            validate_assignment = True

    def __init__(self):
        self._schema: Optional[BaseSchema] = None

        self.__on_build_ui = _Event()
        self.__on_mass_build_ui = _Event()
        self.__on_mass_build_queue_action_ui = _Event()
        self.__on_mass_cook_template = _Event()
        self.__on_progress = _Event()
        self.__on_global_progress = _Event()
        self.__on_validator_run = _Event()
        self.__on_enable_validation = _Event()
        self.__on_validation_is_ready_to_run = _Event()

    def _set_schema_attribute(self, attr: str, value: Any):
        """Call the event object that has the list of functions"""
        setattr(self._schema, attr, value)

    def _get_schema_attribute(self, attr: str) -> Any:
        """Call the event object that has the list of functions"""
        return getattr(self._schema, attr)

    @abc.abstractmethod
    def _callback_to_set(self) -> None:
        """
        Implementation of the callback to set up the event when data are changed
        Warnings: super() should be called before
        """
        self._schema.data.on_progress_callback = self.__on_progress
        self._schema.data.on_global_progress_callback = self.__on_global_progress

    def set_parent_schema(self, schema: BaseSchema):
        """
        Set the schema

        Args:
            schema: the schema to set
        """
        self._schema: BaseSchema = schema
        self._callback_to_set()

    def _on_validator_run(self, items: List["Base"], run_mode: ValidatorRunMode, catch_exception: bool = True):
        """
        Run the validator

        Args:
            items: if the run mode is "only selected", or "self to end", this is the item(s) to run from
            run_mode: the mode to use to run the validator
            catch_exception: catch async exception or not
        """
        self.__on_validator_run(items, run_mode, catch_exception)

    def _on_validator_enable(self, value: bool):
        """
        Enable or disable the validation

        Args:
            value: True if enabled, else False
        """
        self.__on_enable_validation(value)

    def _on_validation_is_ready_to_run(self, value: bool):
        """
        Enable or disable the validation

        Args:
            value: True if enabled, else False
        """
        self.__on_validation_is_ready_to_run(id(self), value)

    def subscribe_validator_run(self, callback: Callable[[List["Base"], ValidatorRunMode, Optional[bool]], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Subscription that will let the plugin re-run a validation by itself.
        """
        return _EventSubscription(self.__on_validator_run, callback)

    def subscribe_enable_validation(self, callback: Callable[[bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Subscription that will let the plugin re-run a validation by itself.
        """
        return _EventSubscription(self.__on_enable_validation, callback)

    def subscribe_on_validation_is_ready_to_run(self, callback: Callable[[int, bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        Subscription that will let the plugin re-run a validation by itself.
        """
        return _EventSubscription(self.__on_validation_is_ready_to_run, callback)

    def subscribe_build_ui(self, callback: Callable[[Any], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_build_ui, callback)

    def subscribe_mass_build_ui(self, callback: Callable[[Any], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_mass_build_ui, callback)

    def subscribe_mass_build_queue_action_ui(self, callback: Callable[[Any], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_mass_build_queue_action_ui, callback)

    def on_mass_cook_template(self, success, message, data):
        self.__on_mass_cook_template(success, message, data)

    def subscribe_mass_cook_template(self, callback: Callable[[Tuple[bool, Optional[str], Any]], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_mass_cook_template, callback)

    def get_progress(self) -> Tuple[float, str, bool]:
        return self._schema.data.progress

    def on_progress(self, progress: float, message: str, result: bool):
        """
        Set the progression of the plugin. Setting the attribute will fire self.__on_progress
        """
        self._schema.data.progress = (progress, message, result)

    def subscribe_progress(self, callback: Callable[[float, str, bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.

        Args:
            callback: function that should be called during the progress.
                float: the progress between 0.0 and 1.0
                str: the message of the progress
                bool: the result of the plugin. At 1.0, it can be True or False.
        """
        return _EventSubscription(self.__on_progress, callback)

    def subscribe_global_progress(self, callback: Callable[[float], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.

        Args:
            callback: function that should be called during the progress.
                float: the progress between 0.0 and 1.0
                str: the message of the progress
                bool: the result of the plugin. At 1.0, it can be True or False.
        """
        return _EventSubscription(self.__on_global_progress, callback)

    def get_global_progress(self) -> float:
        """The value of the global progression of the validation"""
        return self._schema.data.global_progress_value

    def set_global_progress(self, value: float):
        """The value of the global progression of the validation"""
        self._schema.data.global_progress_value = value

    @omni.usd.handle_exception
    async def on_crash(self, schema_data: Any, data: Any) -> None:
        """
        Function that will be called when a plugin crash

        Args:
            schema_data: the data of the plugin from the schema
            data: any random data we want to pass
        """
        await self._on_crash(schema_data, data)

    @omni.usd.handle_exception
    @abc.abstractmethod
    async def _on_crash(self, schema_data: Any, data: Any) -> None:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data of the plugin from the schema
            data: any random data we want to pass
        """
        pass

    @omni.usd.handle_exception
    async def build_ui(self, schema_data: Any) -> Any:
        """
        Build the UI of a plugin

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        result = await self._build_ui(schema_data)
        self.__on_build_ui(result)
        return result

    @omni.usd.handle_exception
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

    @omni.usd.handle_exception
    async def mass_build_ui(self, schema_data: Any) -> Any:
        """
        Build the mass UI of a plugin. This function should not be overridden. Please implement your code using
        _mass_build_ui()

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        result = await self._mass_build_ui(schema_data)
        self.__on_mass_build_ui(result)
        return result

    @omni.usd.handle_exception
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

    def mass_build_queue_action_ui(
        self, schema_data: Any, default_actions: List[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> Any:
        """
        Default exposed action for Mass validation. The UI will be built into the delegate of the mass queue.
        Please implement your code using _mass_build_queue_action_ui()
        """
        result = self._mass_build_queue_action_ui(schema_data, default_actions, callback)  # noqa PLE1111
        self.__on_mass_build_queue_action_ui(result)
        return result

    def _mass_build_queue_action_ui(
        self, schema_data: Any, default_actions: List[Callable[[], Any]], callback: Callable[[str], Any]
    ) -> Any:
        """
        Default exposed action for Mass validation. The UI will be built into the delegate of the mass queue.
        For example, you can add a button to open the asset into a USD viewport
        """
        pass

    @omni.usd.handle_exception
    async def mass_cook_template(self, schema_data_template: Any) -> Tuple[bool, Optional[str], List[Data]]:
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
        success, message, data = await self._mass_cook_template(schema_data_template)
        self.on_mass_cook_template(success, message, data)
        return success, message, data

    @omni.usd.handle_exception
    async def _mass_cook_template(self, schema_data_template: Any) -> Tuple[bool, Optional[str], Any]:
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

    def _get_schema_data_flows(self, schema_data: Data, schema: BaseModel) -> list["_DataFlow"]:
        all_data_flows = []
        schema_dict = schema.dict()
        for attr in schema_dict.keys():
            next_plugin = getattr(schema, attr)
            next_plugins = []
            if isinstance(next_plugin, BaseSchema):
                next_plugins = [next_plugin]
            elif isinstance(next_plugin, Iterable):
                next_plugins = [plugin for plugin in next_plugin if isinstance(plugin, BaseSchema)]

            for plugin in next_plugins:
                data_flows: list["_DataFlow"] | None = plugin.data.data_flows
                if data_flows:
                    for data_flow in data_flows:
                        if data_flow.channel != schema_data.channel:
                            continue
                        all_data_flows.append(data_flow)
                all_data_flows.extend(self._get_schema_data_flows(schema_data, plugin))
        return all_data_flows

    def destroy(self):
        self._schema = None
        self.__on_build_ui = None
        self.__on_progress = None
        self.__on_validator_run = None


class BaseSchema(BaseModel):
    name: str
    enabled: bool = True
    data: Base.Data
    _instance: Any = PrivateAttr()  # instance before data because data need the instance

    def __init__(self, **data):
        if "name" not in data:
            raise KeyError(f"The key 'name' is missing from the plugin {type(self)}")
        plugin = _get_factory_instance().get_plugins_from_name(data["name"])
        if not plugin:
            raise ValueError(
                f"Plugin {data['name']} was not registered! Please enable the extension that has the plugin"
            )  # noqa
        self._instance = plugin()
        # transform the dict data into a model data
        try:
            data["data"] = self._instance.data_type(**data["data"])
        except KeyError:
            raise ValueError(f"'data' key is missing for the plugin {data['name']}")  # noqa
        BaseSchema._check_data_flow(data)
        # check the data flow compatibility
        super().__init__(**data)
        self._instance.set_parent_schema(self)

    @staticmethod
    def _check_data_flow(data):
        data_flow_compatible_names = data["data"].data_flow_compatible_name
        for data_flow in data["data"].data_flows or []:
            if data_flow.name not in data_flow_compatible_names:
                raise ValueError(
                    f"'{data_flow.name}' DataFlow is not compatible with the plugin {data['name']}. Compatible data "
                    f"flows are {data_flow_compatible_names}"
                )  # noqa

    @property
    def instance(self):
        return self._instance

    @validator("name")
    def is_registered(cls, v):  # noqa
        result = _get_factory_instance().is_plugin_registered(v)
        if not result:
            raise ValueError(f"Plugin {v} is not registered")
        return v

    def destroy(self):
        self._instance.destroy()
        self._instance = None

    class Config:
        extra = Extra.forbid

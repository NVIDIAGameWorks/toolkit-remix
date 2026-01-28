# noqa PLC0302
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
import functools
import io
import pathlib
import pprint
import sys
from collections.abc import Iterable
from contextlib import asynccontextmanager, contextmanager, redirect_stderr, redirect_stdout
from enum import Enum as _Enum
from json import JSONEncoder
from typing import Any, Awaitable, Callable

import carb
import carb.settings
import omni.kit.app
import omni.usd
import requests
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common.decorators import ignore_function_decorator as _ignore_function_decorator
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from omni.flux.validator.factory import Base as _BaseInstancePlugin
from omni.flux.validator.factory import BaseSchema as _BaseSchema
from omni.flux.validator.factory import BaseValidatorRunMode as _BaseValidatorRunMode
from omni.flux.validator.factory import CheckSchema as _CheckSchema
from omni.flux.validator.factory import ContextSchema as _ContextSchema
from omni.flux.validator.factory import ResultorSchema as _ResultorSchema
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from omni.flux.validator.factory import get_instance as _get_factory_instance
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core.core_schema import ValidationInfo

EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_HOST = "/exts/omni.services.transport.server.http/host"
EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_PORT = "/exts/omni.services.transport.server.http/port"
EXTS_MASS_VALIDATOR_SERVICE_PREFIX = "/exts/omni.flux.validator.mass.service/service/prefix"


@contextmanager
def disable_exception_traceback():
    """
    All traceback information is suppressed and only the exception type and value are printed
    """
    default_value = getattr(sys, "tracebacklimit", 1000)  # `1000` is a Python's default value
    sys.tracebacklimit = 0
    try:
        yield
    finally:
        sys.tracebacklimit = default_value  # revert changes


class ValidationSchema(BaseModel):
    on_progress_callback: Callable[[float, bool], None] | None = Field(default=None, exclude=True)
    on_finished_callback: Callable[[bool, str, bool], None] | None = Field(default=None, exclude=True)

    name: str
    uuid: str | None = Field(default=None)
    data: dict[Any, Any] | None = Field(default=None)
    progress: float = Field(default=0.0)
    send_request: bool = Field(default=False)
    context_plugin: _ContextSchema = Field(...)
    check_plugins: list[_CheckSchema] = Field(...)
    resultor_plugins: list[_ResultorSchema] | None = Field(default=None)
    validation_passed: bool = Field(default=False)
    finished: tuple[bool, str] = Field(default=(False, "Nothing"))  # validation finished or not

    model_config = ConfigDict(validate_assignment=True)

    @field_validator("uuid", mode="before")
    @classmethod
    def sanitize_uuid(cls, v: str | None) -> str | None:
        if v is not None:
            v = str(v).replace("-", "")
        return v

    @field_validator("progress", mode="before")
    @classmethod
    def _fire_progress_callback(cls, v: float, info: ValidationInfo) -> float:
        callback = info.data.get("on_progress_callback")
        if callback:
            callback(v, False, True)
        return v

    @field_validator("finished", mode="before")
    @classmethod
    def _fire_finished_callback(cls, v: tuple[bool, str], info: ValidationInfo):
        callback = info.data.get("on_finished_callback")
        if callback:
            callback(*v, set_schema_value=False, force_not_send_request=True)
        return v

    @field_validator("check_plugins", mode="before")
    @classmethod
    def at_least_one(cls, v: list[_CheckSchema]) -> list[_CheckSchema]:
        if not v:
            raise ValueError("We should have at least 1 check plugin")
        return v

    def update(self, data: dict) -> "ValidationSchema":
        """This function updates the attributes of a `ValidationSchema` instance with new values provided in a
        dictionary. The update is performed recursively for nested models and lists within the model."""

        # Validate only at the top level
        validated_data = self.model_validate(data).model_dump(serialize_as_any=True)

        # Create an update function that works with the validated data
        def _update(model: BaseModel, updated_values: dict):
            for field_name, value in updated_values.items():
                if not hasattr(model, field_name):
                    continue

                current_value = getattr(model, field_name)

                # Handle nested BaseModels
                if isinstance(current_value, BaseModel):
                    if isinstance(value, dict):
                        _update(current_value, value)
                        continue
                    if current_value != value:
                        setattr(model, field_name, value)
                    continue

                # Handle lists (potentially containing models)
                if isinstance(current_value, list):
                    if not isinstance(value, list):
                        setattr(model, field_name, value)
                        continue
                    # Only update existing items, don't add new ones
                    for i, item in enumerate(current_value):
                        if i >= len(value):
                            continue
                        next_value = value[i]
                        if isinstance(item, BaseModel) and isinstance(next_value, dict):
                            _update(item, next_value)
                            continue
                        if item != next_value:
                            current_value[i] = next_value
                    continue

                # Handle dictionaries
                if isinstance(current_value, dict):
                    if not isinstance(value, dict):
                        setattr(model, field_name, value)
                        continue
                    for key in current_value:
                        if key not in value:
                            continue
                        if current_value[key] != value[key]:
                            current_value[key] = value[key]
                    continue

                # Simple values
                if current_value != value:
                    setattr(model, field_name, value)

        # Update the model with the validated data
        _update(self, validated_data)

        return self


def validation_schema_json_encoder(obj):
    if isinstance(obj, (_OmniUrl, pathlib.PurePath)):
        return str(obj)
    if isinstance(obj, _Enum):
        return obj.value

    return JSONEncoder().default(obj)


class ManagerCore:
    def __init__(self, schema: dict):
        """
        Validation manager that will execute the validation.

        Args:
            schema: the schema to use for the validation. Please see the documentation.

        Examples:
            >>> ManagerCore(
            >>>    {
            >>>        "context_plugin": {"name": "CurrentStage", "data": {"context_name": ""}},
            >>>        "check_plugins": [
            >>>            {
            >>>                 "name": "PrintPrims",
            >>>                 "selector_plugins": [{"name": "AllPrims", "data": {}}],
            >>>                 "resultor_plugins": [{"name": "MyResultor", "data": {}}],
            >>>                 "data": {}
            >>>             }
            >>>        ],
            >>>        "resultor_plugins": [{"name": "ToJson", "data": {"json_path": "C:/result.json"}}],
            >>>    }
            >>>)
        """
        self._last_run_task = None
        self.__force_ignore_exception = False
        self.__factory_instance = _get_factory_instance()  # noqa
        self.__no_check_failed = True

        self.__run_started = False
        self.__run_finished = None

        self.__settings = carb.settings.get_settings()

        self.__on_run_started = _Event()
        self.__on_run_finished = _Event()
        self.__on_run_paused = _Event()
        self.__on_run_stopped = _Event()
        self.__on_run_progress = _Event()
        self.__print_result = False
        self.__silent = False
        self.__current_queue_id = None
        self.__enable = True
        self.__is_ready_to_run = {}
        self.__pause_validation = False
        self.__stop_validation = False
        self.__progress = 0.0

        self.__model = ValidationSchema(**self._recursive_model_dump(schema))
        self.__model.on_progress_callback = self._on_run_progress
        self.__model.on_finished_callback = self._on_run_finished

        self.__model_original = None
        self.__subs_validator_run_by_plugin = {}
        self.__subs_validator_enable_by_plugin = {}
        self.__subs_validator_is_ready_to_run_by_plugin = {}
        self.__init_sub_validator_run_by_plugin()

    def is_paused(self):
        return self.__pause_validation

    def is_stopped(self):
        return self.__stop_validation

    def _recursive_model_dump(self, schema: Any) -> dict:
        """
        Recursively convert any Pydantic models in the data to dictionaries

        Pydantic V2 doesn't deepcopy the data when validating the model so sub-models will be mutated without this.
        """
        if isinstance(schema, BaseModel):
            return schema.model_dump(serialize_as_any=True)
        if isinstance(schema, dict):
            return {k: self._recursive_model_dump(v) for k, v in schema.items()}
        if isinstance(schema, Iterable) and not isinstance(schema, (str, dict)):
            return type(schema)(self._recursive_model_dump(item) for item in schema)
        return schema

    def mass_build_queue_action_ui(self, default_actions: list[Callable[[], Any]], callback: Callable[[str], Any]):
        """
        Default exposed action for Mass validation. The UI will be built into the delegate of the mass queue.
        """

        def nester_mass_build_queue_action_ui_for_plugins(model):
            to_dict = model.model_dump(serialize_as_any=True)
            for attr in to_dict:
                next_plugin = getattr(model, attr)
                next_plugins = []
                if isinstance(next_plugin, _BaseSchema):
                    next_plugins = [next_plugin]
                elif isinstance(next_plugin, Iterable):
                    next_plugins = [nexp for nexp in next_plugin if isinstance(nexp, _BaseSchema)]

                for plugin in next_plugins:
                    if plugin.data.expose_mass_queue_action_ui:
                        plugin.instance.mass_build_queue_action_ui(plugin.data, default_actions, callback)
                    nester_mass_build_queue_action_ui_for_plugins(plugin)

        nester_mass_build_queue_action_ui_for_plugins(self.__model)

    def __init_sub_validator_run_by_plugin(self):
        def nester_init_sub_validator_run_by_plugin(model):
            to_dict = model.model_dump(serialize_as_any=True)
            for attr in to_dict:
                next_plugin = getattr(model, attr)
                next_plugins = []
                if isinstance(next_plugin, _BaseSchema):
                    next_plugins = [next_plugin]
                elif isinstance(next_plugin, Iterable):
                    next_plugins = [nexp for nexp in next_plugin if isinstance(nexp, _BaseSchema)]

                for plugin in next_plugins:
                    self.__subs_validator_run_by_plugin[id(plugin.instance)] = plugin.instance.subscribe_validator_run(
                        self.__on_validator_run_by_plugin
                    )
                    self.__subs_validator_enable_by_plugin[id(plugin.instance)] = (
                        plugin.instance.subscribe_enable_validation(self.enable)
                    )
                    self.__subs_validator_is_ready_to_run_by_plugin[id(plugin.instance)] = (
                        plugin.instance.subscribe_on_validation_is_ready_to_run(self.set_ready_to_run)
                    )
                    nester_init_sub_validator_run_by_plugin(plugin)

        nester_init_sub_validator_run_by_plugin(self.__model)

    def enable(self, enable: bool):
        """
        Enable the validator or not

        Args:
            enable: True is enabled, else False
        """
        self.__enable = enable

    def is_enabled(self):
        """Tell if the validator is enabled or not"""
        return self.__enable

    def set_ready_to_run(self, plugin_id: int, enable: bool):
        """
        Is the validator read to be run or not

        Args:
            plugin_id: the id of the plugin
            enable: True is enabled, else False
        """
        self.__is_ready_to_run[plugin_id] = enable

    def is_ready_to_run(self) -> dict[int, bool]:
        """Tell if the validator is enabled or not"""
        return self.__is_ready_to_run

    def __on_validator_run_by_plugin(
        self, items: list[_BaseInstancePlugin], run_mode: _BaseValidatorRunMode, catch_exception: bool = True
    ):
        self.run(run_mode=run_mode, instance_plugins=items, catch_exception=catch_exception)

    @property
    def model(self) -> ValidationSchema:
        """Return the current model of the schema"""
        return self.__model

    def update_model(self, model: ValidationSchema):
        """Return the current model of the schema"""
        self.__model.update(model.model_dump(serialize_as_any=True))

    @_ignore_function_decorator(attrs=["_ignore_on_run_progress"])
    def _on_run_progress(self, progress, set_schema_value=True, force_not_send_request: bool = False):
        carb.log_info(f"Progress: {progress}%")

        def nester_on_run_progress(model):
            to_dict = model.model_dump(serialize_as_any=True)
            for attr in to_dict:
                next_plugin = getattr(model, attr)
                next_plugins = []
                if isinstance(next_plugin, _BaseSchema):
                    next_plugins = [next_plugin]
                elif isinstance(next_plugin, Iterable):
                    next_plugins = [nexp for nexp in next_plugin if isinstance(nexp, _BaseSchema)]

                for plugin in next_plugins:
                    plugin.instance.set_global_progress(progress)
                    nester_on_run_progress(plugin)

        nester_on_run_progress(self.__model)

        self.__progress = progress
        self.__on_run_progress(progress)

        if set_schema_value:
            self.__model.progress = progress

        if not force_not_send_request and self.__model.send_request:
            self._send_update_request()

    def _send_update_request(self):
        """This method handles the POST request to update a schema. It sends an HTTP post request with JSON data of
        current model instance, and expects status code 200 if everything is okay."""
        host = self.__settings.get(EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_HOST)
        port = self.__settings.get(EXTS_OMNI_SERVICES_TRANSPORT_SERVER_HTTP_PORT)
        prefix = self.__settings.get(EXTS_MASS_VALIDATOR_SERVICE_PREFIX)

        url = f"http://{host}:{port}{prefix}/mass-validator/schema"  # use IP. localhost is very slow
        if self.__current_queue_id:
            url += f"?queue_id={self.__current_queue_id}"  # Set the query param if we have a queue ID

        r = None
        try:
            # Sending a schema update request should be quick. Set a short timeout.
            r = requests.put(url, data=self.model.model_dump_json(serialize_as_any=True), timeout=5)
            r.raise_for_status()
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            raise ValueError(r.text) from e

    def get_progress(self):
        return self.__progress

    @_ignore_function_decorator(attrs=["_ignore_on_run_finished"])
    def _on_run_finished(
        self, result, message: str | None = None, set_schema_value: bool = True, force_not_send_request: bool = False
    ):
        if self.__print_result:
            pprint.pprint("=" * 50)
            pprint.pprint(self.__model.model_dump(serialize_as_any=True))
        if set_schema_value:
            self.__model.finished = (result, message)
        self.__run_finished = result
        self.__on_run_finished(result, message=message)

        if not force_not_send_request and self.__model.send_request:
            self._send_update_request()

    def is_run_finished(self):
        return self.__run_finished

    def subscribe_run_finished(self, callback: Callable[[bool, str | None], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_run_finished, callback)

    def is_run_started(self):
        return self.__run_started

    def _on_run_started(self):
        self.__run_started = True
        self.__on_run_started()

    def subscribe_run_started(self, callback: Callable[[], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_run_started, callback)

    def subscribe_run_paused(self, callback: Callable[[bool], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_run_paused, callback)

    def subscribe_run_stopped(self, callback: Callable[[], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_run_stopped, callback)

    def subscribe_run_progress(self, callback: Callable[[float], Any]):
        """
        Return the object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_run_progress, callback)

    async def __run_selector(self, check_plugin_model: _CheckSchema, context_data: _SetupDataTypeVar):
        # first, run the select plugins
        selector_data = None
        selector_ran = 0
        for select_plugin_model in check_plugin_model.selector_plugins:
            if not select_plugin_model.enabled:
                continue
            selector_ran += 1
            result_select = await select_plugin_model.instance.select(
                select_plugin_model.data, context_data, selector_data
            )
            if result_select is None:
                error_message = (
                    f"Selector {check_plugin_model.name} returned invalid value. It may have crashed. "
                    f"Please check the first error."
                )
                await select_plugin_model.instance.on_crash(select_plugin_model.data, context_data)
                self._on_run_finished(False, message=error_message)
                raise ValueError(error_message)
            result, message, selector_data = result_select
            if not result:
                await select_plugin_model.instance.on_crash(select_plugin_model.data, context_data)
                self._on_run_finished(False, message=message)
                raise ValueError(message)
        if not selector_ran:
            error_message = f"A selector plugin should be enabled for the check plugin {check_plugin_model.name}"
            self._on_run_finished(False, message=error_message)
            raise ValueError(error_message)
        return selector_data

    async def __run_resultor(
        self, plugin_model: _CheckSchema | ValidationSchema, progress_check: int, progress_check_add: int
    ):
        if plugin_model.resultor_plugins:
            size_plugins = len(plugin_model.resultor_plugins)
            progress_check_add = (progress_check_add / size_plugins) / 2  # divide by 2 because we start at 50
            for resultor_plugin in plugin_model.resultor_plugins:  # noqa PLE1133
                progress_check += progress_check_add
                self._on_run_progress(progress_check)
                if not resultor_plugin.enabled:
                    continue
                result_resultor = await resultor_plugin.instance.result(resultor_plugin.data, self.__model)
                if result_resultor is None:
                    error_message = (
                        f"Resultor {resultor_plugin.name} returned invalid value. It may have crashed. "
                        f"Please check the first error."
                    )
                    await resultor_plugin.instance.on_crash(resultor_plugin.data, None)
                    self._on_run_finished(False, message=error_message)
                    raise ValueError(error_message)
                result, message = result_resultor
                if not result:
                    await resultor_plugin.instance.on_crash(resultor_plugin.data, None)
                    self._on_run_finished(False, message=message)
                    raise ValueError(message)
                if self.__stop_validation:
                    self.__do_stop_validation()

    async def __run_check(self, check_plugin_model: _CheckSchema, context_data: _SetupDataTypeVar):
        selector_data = await self.__run_selector(check_plugin_model, context_data)
        # second, create and run the check plugins
        result_check_check = await check_plugin_model.instance.check(
            check_plugin_model.data, context_data, selector_data
        )
        if result_check_check is None:
            error_message = (
                f"Check {check_plugin_model.name} returned invalid value. It may have crashed. "
                f"Please check the first error."
            )
            await check_plugin_model.instance.on_crash(check_plugin_model.data, context_data)
            self._on_run_finished(False, message=error_message)
            raise ValueError(error_message)
        if self.__stop_validation:
            self.__do_stop_validation()
        result, _message, _data = result_check_check
        if not result:  # if the check return False, we have to run the auto fix
            # we re-run the selectors
            selector_data = await self.__run_selector(check_plugin_model, context_data)
            result_check_check = await check_plugin_model.instance.fix(
                check_plugin_model.data, context_data, selector_data
            )
            if result_check_check is None:
                error_message = (
                    f"Fix {check_plugin_model.name} returned invalid value. It may have crashed. "
                    f"Please check the first error."
                )
                await check_plugin_model.instance.on_crash(check_plugin_model.data, context_data)
                self._on_run_finished(False, message=error_message)
                raise ValueError(error_message)
            if self.__stop_validation:
                self.__do_stop_validation()
            result, message, _data = result_check_check
            if not result and check_plugin_model.stop_if_fix_failed:
                error_message = (
                    f"Plugin {check_plugin_model.name} failed with message:\n {message} stopped validation\n"
                )
                await check_plugin_model.instance.on_crash(check_plugin_model.data, context_data)
                self._on_run_finished(False, message=error_message)
                with disable_exception_traceback():
                    raise ValueError(error_message)
            elif not result and check_plugin_model.pause_if_fix_failed:
                carb.log_warn(f"Pause validation from plugin {check_plugin_model.name}")
                self.pause()
                while self.__pause_validation:
                    if self.__stop_validation:
                        break
                    await omni.kit.app.get_app().next_update_async()
                if self.__stop_validation:
                    self.__do_stop_validation()
                result = await self.__run_check(check_plugin_model, context_data)
                if not result:
                    error_message = (
                        f"Plugin {check_plugin_model.name} failed with message:\n {message} stopped validation\n"
                    )
                    await check_plugin_model.instance.on_crash(check_plugin_model.data, context_data)
                    self._on_run_finished(False, message=error_message)
                    with disable_exception_traceback():
                        raise ValueError(error_message)
            if not result:
                self.__no_check_failed = False
        if self.__stop_validation:
            self.__do_stop_validation()
        return True

    def __do_stop_validation(self):
        if self.__stop_validation:
            error_message = "Stopped validation"
            self._on_run_finished(False, message=error_message)
            self.__on_run_stopped()
            with disable_exception_traceback():
                raise ValueError(error_message)

    async def __run_check_groups(self, context_data: _SetupDataTypeVar):
        """
        Run all check(s) + resultor(s) inside the global context
        """
        # run the check plugins
        if not self.__model.check_plugins:
            error_message = "No check plugin(s) enabled to run."
            self._on_run_finished(False, message=error_message)
            raise ValueError(error_message)

        progress_check = 50  # because the context starts a 50
        size_plugins = len(self.__model.check_plugins) + 1

        progress_check_add = (100 / size_plugins) / 2  # divide by 2 because we start at 50
        checked_ran = 0
        for check_plugin_model in self.__model.check_plugins:
            progress_check += progress_check_add
            self._on_run_progress(progress_check)
            if not check_plugin_model.enabled:
                continue
            checked_ran += 1
            await self.__run_context(
                check_plugin_model.context_plugin, functools.partial(self.__run_check, check_plugin_model), context_data
            )
            await self.__run_resultor(check_plugin_model, progress_check, progress_check_add)

        self.__model.validation_passed = True

        # run the resultors
        await self.__run_resultor(self.__model, progress_check, progress_check_add)

        progress_check = 100
        self._on_run_progress(progress_check)

        if not checked_ran:
            error_message = "No check plugin(s) enabled to run."
            self._on_run_finished(False, message=error_message)
            raise ValueError(error_message)

        self._on_run_finished(self.__no_check_failed, message="Check done")

    async def __run_context(
        self,
        context_plugin,
        run_callback: Callable[[_SetupDataTypeVar], Awaitable[None]],
        parent_context: _SetupDataTypeVar,
    ):
        # create and run the context instance plugin
        if not context_plugin.enabled:
            error_message = "A context plugin should be enabled"
            self._on_run_finished(False, message=error_message)
            raise ValueError(error_message)
        if self.__stop_validation:
            self.__do_stop_validation()

        result_context_check = await context_plugin.instance.check(context_plugin.data, parent_context)
        if result_context_check is None:
            error_message = (
                f"Context {context_plugin.name} returned invalid value on check. It may have crashed. "
                f"Please check the first error."
            )
            await context_plugin.instance.on_crash(context_plugin.data, parent_context)
            self._on_run_finished(False, message=error_message)
            raise ValueError(error_message)
        if self.__stop_validation:
            self.__do_stop_validation()
        result, message = result_context_check
        if result:
            result_context_setup = await context_plugin.instance.setup(
                context_plugin.data, run_callback, parent_context
            )
            if result_context_setup is None:
                error_message = (
                    f"Context {context_plugin.name} returned invalid value. on setup It may have crashed. "
                    f"Please check the first error."
                )
                await context_plugin.instance.on_crash(context_plugin.data, parent_context)
                self._on_run_finished(False, message=error_message)
                raise ValueError(error_message)
            if self.__stop_validation:
                self.__do_stop_validation()
            result, message, _context_data = result_context_setup
            if not result:
                error_message = f"{context_plugin.name}: {message}"
                await context_plugin.instance.on_crash(context_plugin.data, parent_context)
                self._on_run_finished(False, message=error_message)
                raise ValueError(error_message)
            result_context_exit = await context_plugin.instance.on_exit(context_plugin.data, parent_context)
            if result_context_exit is None:
                error_message = (
                    f"Context {context_plugin.name} returned invalid value on exit. It may have crashed. "
                    f"Please check the first error."
                )
                await context_plugin.instance.on_crash(context_plugin.data, parent_context)
                self._on_run_finished(False, message=error_message)
                raise ValueError(error_message)
            if self.__stop_validation:
                self.__do_stop_validation()
            result, message = result_context_exit
            if not result:
                error_message = f"{context_plugin.name}: {message}"
                await context_plugin.instance.on_crash(context_plugin.data, parent_context)
                self._on_run_finished(False, message=error_message)
                raise ValueError(error_message)
        else:
            error_message = f"{context_plugin.name}: {message}"
            await context_plugin.instance.on_crash(context_plugin.data, parent_context)
            self._on_run_finished(False, message=error_message)
            raise ValueError(error_message)

    def pause(self):
        """Pause the validator"""
        carb.log_warn("Pause validation")
        self.__pause_validation = True
        self.__on_run_paused(True)

    def resume(self):
        """Resume the validator (if paused)"""
        carb.log_warn("Resume validation")
        self.__pause_validation = False
        self.__on_run_paused(False)

    def stop(self):
        """Stop the validator"""
        self.__stop_validation = True
        self.__pause_validation = False
        self.__on_run_paused(False)

    def set_force_ignore_exception(self, value):
        """Ignore async exception or not"""
        self.__force_ignore_exception = value

    def run(
        self,
        catch_exception: bool = True,
        print_result: bool = False,
        silent: bool = False,
        run_mode: _BaseValidatorRunMode = _BaseValidatorRunMode.BASE_ALL,
        instance_plugins: list[_BaseInstancePlugin] | None = None,
        queue_id: str | None = None,
    ):
        """
        Run the validation using the current schema

        Args:
            catch_exception: ignore async exception or not
            print_result: print the result or not into stdout
            silent: silent the stdout
            run_mode: the mode to use to run the validator
            instance_plugins: plugins used by the mode to run
            queue_id: the queue ID to use. Needed if you have multiple widgets that shows different queues
        """
        self.__print_result = print_result
        self.__silent = silent
        if self.__force_ignore_exception:
            catch_exception = False
        if catch_exception:
            self._last_run_task = asyncio.ensure_future(
                self.deferred_run_with_exception(
                    print_result=print_result,
                    silent=silent,
                    run_mode=run_mode,
                    instance_plugins=instance_plugins,
                    queue_id=queue_id,
                )
            )
        else:
            self._last_run_task = asyncio.ensure_future(
                self.deferred_run(
                    print_result=print_result,
                    silent=silent,
                    run_mode=run_mode,
                    instance_plugins=instance_plugins,
                    queue_id=queue_id,
                )
            )

    @omni.usd.handle_exception
    async def deferred_run_with_exception(
        self,
        print_result: bool = False,
        silent: bool = False,
        run_mode: _BaseValidatorRunMode = _BaseValidatorRunMode.BASE_ALL,
        instance_plugins: list[_BaseInstancePlugin] | None = None,
        queue_id: str | None = None,
    ):
        """
        Run the validation using the current schema

        Args:
            print_result: print the result or not into stdout
            silent: silent the stdout
            run_mode: the mode to use to run the validator
            instance_plugins: plugins used by the mode to run
            queue_id: the queue ID to use. Needed if you have multiple widgets that shows different queues
        """
        self.__print_result = print_result
        self.__silent = silent
        await self.deferred_run(
            print_result=print_result,
            silent=silent,
            run_mode=run_mode,
            instance_plugins=instance_plugins,
            queue_id=queue_id,
        )

    def __set_mode_base_all(self):
        def _nester_set_mode_base_all(model, original_model):
            to_dict = model.model_dump(serialize_as_any=True)
            for attr in to_dict:
                next_plugin = getattr(model, attr)
                next_original_plugin = getattr(original_model, attr)
                next_plugins = []
                next_original_plugins = []
                if isinstance(next_plugin, _BaseSchema):
                    next_plugins = [next_plugin]
                    next_original_plugins = [next_original_plugin]
                elif isinstance(next_plugin, Iterable):
                    next_plugins = [nexp for nexp in next_plugin if isinstance(nexp, _BaseSchema)]
                    next_original_plugins = [nexp for nexp in next_original_plugin if isinstance(nexp, _BaseSchema)]

                for plugin, original_plugin in zip(next_plugins, next_original_plugins):
                    plugin.enabled = all([True, original_plugin.enabled])
                    _nester_set_mode_base_all(plugin, original_plugin)

        _nester_set_mode_base_all(self.__model, self.__model_original)

    def __set_mode_base_only_selected(self, instance_plugins: list[_BaseInstancePlugin] | None = None):
        if not instance_plugins:
            instance_plugins = []

        # context should always be enabled by default
        self.__model.context_plugin.enabled = all([True, self.__model_original.context_plugin.enabled])
        for check_plugin_model, check_plugin_original_model in zip(
            self.__model.check_plugins, self.__model_original.check_plugins
        ):
            # if any of the check group is True, we re-run the whole check group (sub context + selector(s) + check)
            found_selfs = (
                [check_plugin_model.instance in instance_plugins]
                + [
                    select_plugin_model.instance in instance_plugins
                    for select_plugin_model in check_plugin_model.selector_plugins
                ]
                + [
                    resultor_plugin_model.instance in instance_plugins
                    for resultor_plugin_model in check_plugin_model.resultor_plugins or []
                ]
            )
            found_selfs.append(check_plugin_model.context_plugin.instance in instance_plugins)

            check_plugin_model.enabled = all([any(found_selfs), check_plugin_original_model.enabled])
            check_plugin_model.context_plugin.enabled = all(
                [any(found_selfs), check_plugin_original_model.context_plugin.enabled]
            )
            for select_plugin_model, select_plugin_original_model in zip(
                check_plugin_model.selector_plugins, check_plugin_original_model.selector_plugins
            ):
                select_plugin_model.enabled = all([any(found_selfs), select_plugin_original_model.enabled])
            if check_plugin_model.resultor_plugins:
                for resultor_plugin_model, resultor_plugin_original_model in zip(
                    check_plugin_model.resultor_plugins, check_plugin_original_model.resultor_plugins
                ):
                    resultor_plugin_model.enabled = all([any(found_selfs), resultor_plugin_original_model.enabled])
        if self.__model.resultor_plugins:
            for resultor_plugin, resultor_original_plugin in zip(
                self.__model.resultor_plugins, self.__model_original.resultor_plugins
            ):  # noqa
                resultor_plugin.enabled = all(
                    [resultor_plugin.instance in instance_plugins, resultor_original_plugin.enabled]
                )

    def __set_mode_base_self_to_end(self, instance_plugins: list[_BaseInstancePlugin] | None = None):
        if not instance_plugins:
            instance_plugins = []
        # context should always be enabled by default
        found_self = False
        self.__model.context_plugin.enabled = all([True, self.__model_original.context_plugin.enabled])
        for check_plugin_model, check_plugin_original_model in zip(
            self.__model.check_plugins, self.__model_original.check_plugins
        ):
            # if any of the check group is True, we re-run the whole check group (sub context + selector(s) + check)
            found_selfs = (
                [check_plugin_model.instance in instance_plugins]
                + [
                    select_plugin_model.instance in instance_plugins
                    for select_plugin_model in check_plugin_model.selector_plugins
                ]
                + [
                    resultor_plugin_model.instance in instance_plugins
                    for resultor_plugin_model in check_plugin_model.resultor_plugins or []
                ]
            )
            found_selfs.append(check_plugin_model.context_plugin.instance in instance_plugins)
            if not found_self:
                found_self = all([any(found_selfs), check_plugin_original_model.enabled])
            check_plugin_model.enabled = found_self
            if not found_self:
                found_self = all([any(found_selfs), check_plugin_original_model.context_plugin.enabled])
            check_plugin_model.context_plugin.enabled = found_self
            for select_plugin_model, select_plugin_original_model in zip(
                check_plugin_model.selector_plugins, check_plugin_original_model.selector_plugins
            ):
                if not found_self:
                    found_self = all([any(found_selfs), select_plugin_original_model.enabled])
                select_plugin_model.enabled = found_self
            if check_plugin_model.resultor_plugins:
                for resultor_plugin_model, resultor_plugin_original_model in zip(
                    check_plugin_model.resultor_plugins, check_plugin_original_model.resultor_plugins
                ):
                    if not found_self:
                        found_self = all([any(found_selfs), resultor_plugin_original_model.enabled])
                    resultor_plugin_model.enabled = found_self
        if self.__model.resultor_plugins:
            for resultor_plugin, resultor_original_plugin in zip(
                self.__model.resultor_plugins, self.__model_original.resultor_plugins
            ):  # noqa
                if not found_self:
                    found_self = all([resultor_plugin.instance in instance_plugins, resultor_original_plugin.enabled])
                resultor_plugin.enabled = found_self

    async def deferred_set_mode(
        self,
        run_mode: _BaseValidatorRunMode = _BaseValidatorRunMode.BASE_ALL,
        instance_plugins: list[_BaseInstancePlugin] | None = None,
    ):
        """
        Run the validation using the current schema

        Args:
            run_mode: the mode to run. We can ask the validator to run everything (by default), or just one plugin...
            instance_plugins: instance plugin where the call come from
        """
        if run_mode == _BaseValidatorRunMode.BASE_ALL:
            self.__set_mode_base_all()
        elif run_mode == _BaseValidatorRunMode.BASE_ONLY_SELECTED:
            self.__set_mode_base_only_selected(instance_plugins)
        elif run_mode == _BaseValidatorRunMode.BASE_SELF_TO_END:
            self.__set_mode_base_self_to_end(instance_plugins)

    @asynccontextmanager
    async def disable_some_plugins(
        self,
        run_mode: _BaseValidatorRunMode = _BaseValidatorRunMode.BASE_ALL,
        instance_plugins: list[_BaseInstancePlugin] | None = None,
    ):
        """
        Context manager that will disable some plugins usin a run mode

        Args:
            run_mode: the mode to use to run the validator
            instance_plugins: plugins used by the mode to run
        """
        carb.log_info("Temporarily disable some plugins: start")
        saved_model = ValidationSchema.parse_obj(self.__model.model_dump(serialize_as_any=True))
        await self.deferred_set_mode(run_mode, instance_plugins=instance_plugins)
        yield

        def _nester_disable_some_plugins(model, original_model):
            to_dict = model.model_dump(serialize_as_any=True)
            for attr in to_dict:
                next_plugin = getattr(model, attr)
                next_original_plugin = getattr(original_model, attr)
                next_plugins = []
                next_original_plugins = []
                if isinstance(next_plugin, _BaseSchema):
                    next_plugins = [next_plugin]
                    next_original_plugins = [next_original_plugin]
                elif isinstance(next_plugin, Iterable):
                    next_plugins = [nexp for nexp in next_plugin if isinstance(nexp, _BaseSchema)]
                    next_original_plugins = [nexp for nexp in next_original_plugin if isinstance(nexp, _BaseSchema)]

                for plugin, original_plugin in zip(next_plugins, next_original_plugins):
                    plugin.enabled = original_plugin.enabled
                    _nester_disable_some_plugins(plugin, original_plugin)

        _nester_disable_some_plugins(self.__model, saved_model)

        carb.log_info("Temporarily disable some plugins: end")

    async def deferred_run(
        self,
        print_result: bool = False,
        silent: bool = False,
        run_mode: _BaseValidatorRunMode = _BaseValidatorRunMode.BASE_ALL,
        instance_plugins: list[_BaseInstancePlugin] | None = None,
        queue_id: str | None = None,
    ):
        """
        Run the validation using the current schema

        Args:
            print_result: print the result or not into stdout
            silent: silent the stdout
            run_mode: the mode to use to run the validator
            instance_plugins: plugins used by the mode to run
            queue_id: the queue ID to use. Needed if you have multiple widgets that shows different queues
        """
        if not self.__enable:
            carb.log_warn("Validator is disabled!")
            return
        # start
        # stop previous validation if they are in a resume stat
        self.__stop_validation = True
        await omni.kit.app.get_app().next_update_async()

        self._on_run_started()
        self.__current_queue_id = queue_id
        self.__stop_validation = False
        self.__pause_validation = False
        self.__no_check_failed = True
        self.__print_result = print_result
        self.__silent = silent

        # reset progress for all plugins
        def nester_reset_progress(model):
            to_dict = model.model_dump(serialize_as_any=True)
            for attr in to_dict:
                next_plugin = getattr(model, attr)
                next_plugins = []
                if isinstance(next_plugin, _BaseSchema):
                    next_plugins = [next_plugin]
                elif isinstance(next_plugin, Iterable):
                    next_plugins = [nexp for nexp in next_plugin if isinstance(nexp, _BaseSchema)]

                for plugin in next_plugins:
                    plugin.instance.on_progress(0.0, "", True)
                    plugin.instance.set_global_progress(0)
                    nester_reset_progress(plugin)

        nester_reset_progress(self.__model)

        self.__model.validation_passed = False
        self._on_run_progress(0.0)

        async def go():
            self.__model_original = ValidationSchema.parse_obj(self.__model.model_dump(serialize_as_any=True))
            async with self.disable_some_plugins(run_mode, instance_plugins=instance_plugins):
                self._on_run_progress(50)
                await self.__run_context(self.__model.context_plugin, self.__run_check_groups, None)

        if self.__silent:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                await go()
        else:
            await go()

    def destroy(self):
        self.__subs_validator_run_by_plugin = None

        def nester_destroy(model):
            to_dict = model.model_dump(serialize_as_any=True)
            for attr in to_dict:
                next_plugin = getattr(model, attr)
                next_plugins = []
                if isinstance(next_plugin, _BaseSchema):
                    next_plugins = [next_plugin]
                elif isinstance(next_plugin, Iterable):
                    next_plugins = [nexp for nexp in next_plugin if isinstance(nexp, _BaseSchema)]

                for plugin in next_plugins:
                    plugin.instance.destroy()
                    nester_destroy(plugin)

        nester_destroy(self.__model)

        if self._last_run_task:
            self._last_run_task.cancel()
        self.__model = None

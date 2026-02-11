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

import abc
from typing import Any, ClassVar

from fast_version import VersionedAPIRouter
from fastapi import Depends, Path, Query
from omni.flux.factory.base import PluginBase
from omni.flux.service.shared import BaseServiceModel
from omni.services.core import exceptions
from omni.services.core.routers import ServiceAPIRouter
from pydantic import Field, ValidationError, create_model
from pydantic.json_schema import SkipJsonSchema


class APIRouter(VersionedAPIRouter, ServiceAPIRouter):
    pass


class ServiceBase(PluginBase, abc.ABC):
    """
    A base class used to define a Service.

    All endpoints must be defined within the implementation of the `register_endpoints` function.
    """

    def __init__(self, *args, **kwargs):
        self._router = APIRouter()

        self.register_endpoints()

    def __init_subclass__(cls, *args, **kwargs):
        super().__init_subclass__(*args, **kwargs)
        cls.name = cls.__name__

    name: ClassVar[str] = Field(
        description="The Service Name must be unique. It is used in the Service Factory to fetch specific services"
    )
    prefix: ClassVar[str] = Field(
        default="/",
        description=(
            "The Service Prefix is prepended to all routes defined in the service. It must start with a '/' character"
        ),
    )

    @property
    def router(self) -> APIRouter:
        """
        The router inherits from VersionedAPIRouter from fast_version and from ServiceAPIRouter from
        omni.services.core.routers.

        The VersionedAPIRouter base class will have priority over the ServiceAPIRouter class when the same attribute
        is defined in both base classes.

        Both of these routers are based on the FastAPI Router.

        Returns:
            The router
        """
        return self._router

    @staticmethod
    def inject_hidden_fields(base_model: type[BaseServiceModel], **kwargs) -> type[BaseServiceModel]:
        """
        Inject hidden fields (non-visible in OpenAPI) in the given model

        Args:
            base_model: The base model to inject the fields in
            kwargs: Keyword arguments in the format field_name=value that will be injected as hidden fields

        Returns:
            The model with all the injected fields
        """
        # Create hidden field from the kwargs using SkipJsonSchema to hide from OpenAPI and exclude=True to hide from
        # serialization
        fields = {key: (SkipJsonSchema[type(val)], Field(default=val)) for key, val in kwargs.items()}

        # Inject the hidden fields in the model
        return create_model(base_model.__name__, __base__=base_model, **fields)

    @staticmethod
    def validate_path_param(
        base_model: type[BaseServiceModel], description: str | None = None, validate_list: bool = False, **kwargs
    ):
        """
        Get a path parameter validation dependency that will check the validity of a value using a Pydantic model.

        Args:
            base_model: The Pydantic model to use to validate the given value
            description: A description for the path parameter to display in the OpenAPI docs
            validate_list: Whether to validate the value as a comma-separated list of as a single item
            kwargs: Key-word arguments to be passed down to the Pydantic model for validation

        Returns:
            The FastAPI path parameter dependency
        """

        # Use the first field name for validation.
        field_name = next(iter(base_model.model_fields))

        async def dependency(value: str = Path(..., alias=field_name, description=description)):
            try:
                # If the input is a list, split it using a "," separator
                if validate_list:
                    validation_value = value.split(",")
                else:
                    validation_value = value
                # Dynamically create an instance of the model and validate the input
                # Pass the kwargs as context to the model_validate method
                model = base_model.model_validate({field_name: validation_value}, context=kwargs)
                # Return the model rather than the input string
                return model
            except (ValueError, ValidationError) as e:
                # Handle validation errors
                ServiceBase.raise_error(422, e)

        return Depends(dependency)

    @staticmethod
    def describe_query_param(default_value: Any, description: str):
        """
        Get a query parameter field with a description.

        Returns:
            a FastAPI query parameter field
        """
        return Query(default_value, description=description)

    @staticmethod
    def raise_error(status_code: int, details: Exception | str):
        """
        Raise an HTTP error with given status code and detail message or based on an exception

        Args:
            status_code: The desired HTTP status code
            details: The detail message or exception to build the error from

        Raises:
            exceptions.KitServicesBaseException: The HTTP error
        """
        if isinstance(details, Exception):
            raise exceptions.KitServicesBaseException(status_code=status_code, detail=str(details)) from details

        raise exceptions.KitServicesBaseException(status_code=status_code, detail=str(details))

    @abc.abstractmethod
    def register_endpoints(self):
        """
        Endpoints should be registered in this function as to not include `self` as a required query parameter.

        This also allows the endpoints to have access to any of the class instance's properties.
        """
        raise NotImplementedError(
            "The method `register_endpoints` must be implemented to describe the service's endpoints."
        )

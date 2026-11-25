"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import re
from collections.abc import Callable, Coroutine
from copy import copy
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.datastructures import DefaultPlaceholder
from fastapi.openapi.utils import get_openapi
from fastapi.routing import (
    APIRoute,
    APIRouter,
    RouteContext,
    _get_scope_effective_route_context,
    _iter_routes_with_context,
)
from fastapi.types import DecoratedCallable
from starlette.datastructures import Headers
from starlette.responses import JSONResponse, Response
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

_Version = tuple[int, int]
_VERSION_FORMAT = re.compile(r"([0-9]+)\.([0-9]+)")
_REQUEST_VERSION = "flux.request_version"
_LATEST_VERSION = "flux.latest_version"
_VERSION_ERROR = "flux.version_error"
_VENDOR_MEDIA_TYPE = "flux.vendor_media_type"
_JSON_MEDIA_TYPE = "application/json"


def _version_label(version: _Version) -> str:
    return f"{version[0]}.{version[1]}"


def _media_type(vendor: str, version: _Version) -> str:
    return f"{vendor}; version={_version_label(version)}"


class VersionedAPIRoute(APIRoute):
    """Select a version after the path and method match."""

    @property
    def version(self) -> _Version:
        """Return the endpoint version or the default of 1.0."""
        return vars(self.endpoint).get("version", (1, 0))

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        """Keep FastAPI's path and method matches before selecting a version."""
        match, child_scope = super().matches(scope)
        if match != Match.FULL:
            return match, child_scope

        requested = scope.get(_REQUEST_VERSION)
        # FastAPI keeps the full path in the context for each router inclusion.
        context = _get_scope_effective_route_context(scope)
        path = context.path_format if context is not None and context.original_route is self else self.path_format
        # Scan the live app routes in O(n) per match. Add an index if the scan becomes slow.
        versions = {
            route.version
            for route, included in _iter_routes_with_context(scope["app"].routes)
            if isinstance(route, VersionedAPIRoute)
            and (route if included is None else included).path_format == path
            and route.methods == self.methods
        }
        latest = max(versions)
        if requested in versions:
            if requested != self.version:
                return Match.NONE, {}
        elif self.version != latest:
            return Match.NONE, {}
        elif requested is not None:
            available = ", ".join(_version_label(version) for version in sorted(versions))
            child_scope[_VERSION_ERROR] = (
                f"Version {_version_label(requested)} is not available for this endpoint. Available versions: {available}"
            )
        child_scope[_LATEST_VERSION] = latest
        return match, child_scope

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Return HTTP 406 when the endpoint has no matching version."""
        if detail := scope.get(_VERSION_ERROR):
            await JSONResponse({"detail": detail}, status_code=406)(scope, receive, send)
        else:
            await super().handle(scope, receive, send)

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Set the vendor media type on JSON responses and mark responses from an older version as deprecated."""
        handler = super().get_route_handler()

        async def versioned_handler(request: Request) -> Response:
            response = await handler(request)
            if self.version != request.scope.get(_LATEST_VERSION, self.version):
                # RFC 9745 wants a deprecation date. Add a date to `set_api_version` when a sunset policy exists.
                response.headers["deprecation"] = "true"
            vendor = request.scope.get(_VENDOR_MEDIA_TYPE)
            if vendor and response.headers.get("content-type") == _JSON_MEDIA_TYPE:
                response.headers["content-type"] = _media_type(vendor, self.version)
            return response

        return versioned_handler


class VersionedAPIRouter(APIRouter):
    """Register versioned routes with the standard FastAPI decorators."""

    def api_route(self, path: str, **kwargs: Any) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """Build a decorator that registers a versioned route."""

        def decorator(endpoint: DecoratedCallable) -> DecoratedCallable:
            self.add_api_route(path, endpoint, route_class_override=VersionedAPIRoute, **kwargs)
            return endpoint

        return decorator

    @staticmethod
    def set_api_version(version: _Version) -> Callable[[DecoratedCallable], DecoratedCallable]:
        """Set the endpoint version before the router registers the route."""

        def decorator(endpoint: DecoratedCallable) -> DecoratedCallable:
            vars(endpoint)["version"] = version
            return endpoint

        return decorator


class VersioningMiddleware:
    """Read the API version from the vendor media type in Accept."""

    def __init__(self, app: ASGIApp, vendor_media_type: str) -> None:
        self.app = app
        self.vendor_media_type = vendor_media_type

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            scope[_VENDOR_MEDIA_TYPE] = self.vendor_media_type
            try:
                scope[_REQUEST_VERSION] = _parse_accept(Headers(scope=scope).get("accept", ""), self.vendor_media_type)
            except ValueError as error:
                await JSONResponse({"detail": str(error)}, status_code=400)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _parse_accept(header: str, vendor: str) -> _Version | None:
    """Return no version unless the header specifies a vendor parameter."""
    media_type, separator, parameter = header.partition(";")
    if not separator or media_type.strip().lower() != vendor.lower():
        return None

    name, equals, value = parameter.partition("=")
    if not equals or name.strip().lower() != "version":
        raise ValueError("No version in Accept header")
    match = _VERSION_FORMAT.fullmatch(value.strip())
    error = "Version should be in <major>.<minor> format"
    if match is None:
        raise ValueError(error)
    try:
        return int(match[1]), int(match[2])
    except ValueError as exc:
        raise ValueError(error) from exc


def _versioned_openapi(app: FastAPI, vendor: str) -> dict[str, Any]:
    routes = []
    versioned_paths = {}
    for original, context in _iter_routes_with_context(app.routes):
        if not isinstance(original, VersionedAPIRoute):
            routes.append(RouteContext(original, context))
            continue

        # Use a unique path key so FastAPI generates a schema for every version.
        route = copy(original if context is None else context)
        key = f"versioned-route:{len(versioned_paths)}"
        media_type = _media_type(vendor, original.version)
        versioned_paths[key] = (route.path_format, original.version, media_type)
        route.path_format = key
        response_class = route.response_class
        if isinstance(response_class, DefaultPlaceholder):
            response_class = response_class.value
        if response_class.media_type == _JSON_MEDIA_TYPE:
            route.response_class = cast(
                "type[Response]", type("VersionedJSONResponse", (response_class,), {"media_type": media_type})
            )
        routes.append(route if context is None else RouteContext(original, route))

    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        summary=app.summary,
        description=app.description,
        terms_of_service=app.terms_of_service,
        contact=app.contact,
        license_info=app.license_info,
        routes=routes,
        webhooks=app.webhooks.routes,
        tags=app.openapi_tags,
        servers=app.servers,
        separate_input_output_schemas=app.separate_input_output_schemas,
        external_docs=app.openapi_external_docs,
    )
    paths = {}
    operations = {}
    for key, methods in schema["paths"].items():
        if key not in versioned_paths:
            paths.setdefault(key, {}).update(methods)
            continue
        path, version, media_type = versioned_paths[key]
        paths.setdefault(path, {})
        for method, operation in methods.items():
            if body := operation.get("requestBody"):
                content = body.get("content", {})
                if _JSON_MEDIA_TYPE in content:
                    body["content"] = {media_type: content.pop(_JSON_MEDIA_TYPE), **content}
            operations.setdefault((path, method), []).append((version, operation))

    for (path, method), versions in operations.items():
        versions.sort(key=lambda item: item[0], reverse=True)
        latest = versions[0][1]
        paths[path][method] = latest
        for _, older in versions[1:]:
            if "requestBody" in latest and "requestBody" in older:
                _append_content(latest["requestBody"], older["requestBody"])
            for status, response in older["responses"].items():
                if status in latest["responses"]:
                    _append_content(latest["responses"][status], response)
                else:
                    latest["responses"][status] = response
        if len(versions) > 1:
            deprecated = ", ".join(_version_label(version) for version, _ in versions[1:])
            note = f"**Deprecated versions:** {deprecated}. Their responses have the `Deprecation: true` header."
            latest["description"] = f"{latest['description']}\n\n{note}" if latest.get("description") else note

    schema["paths"] = paths
    return schema


def _append_content(latest: dict[str, Any], older: dict[str, Any]) -> None:
    if content := older.get("content"):
        target = latest.setdefault("content", {})
        for media_type, entry in content.items():
            target.setdefault(media_type, entry)


def init_versioning(app: FastAPI, vendor_media_type: str) -> None:
    """
    Install version selection and the versioned OpenAPI schema on this app.

    The middleware is added only on the first call, because Starlette refuses new middleware after the app starts.
    The flag is kept on `app.state`, not on the middleware class, because a reload of this extension makes a new class.
    Each call installs the OpenAPI generator again, so it uses the route classes of the current module.
    """
    if not hasattr(app.state, "flux_vendor_media_type"):
        app.add_middleware(VersioningMiddleware, vendor_media_type=vendor_media_type)
        app.state.flux_vendor_media_type = vendor_media_type
    vendor = app.state.flux_vendor_media_type
    app.openapi_schema = None

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = _versioned_openapi(app, vendor)
        return app.openapi_schema

    app.openapi = openapi

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

import importlib.util
import warnings

import fastmcp
from fastapi import FastAPI
from fastapi.testclient import TestClient
from omni.flux.service.factory import init_versioning, versioning
from omni.flux.service.factory.services.base import APIRouter
from omni.kit.test import AsyncTestCase
from pydantic import BaseModel

_VENDOR = "application/flux.service+json"
_V1 = f"{_VENDOR}; version=1.0"
_V2 = f"{_VENDOR}; version=2.0"
_V3 = f"{_VENDOR}; version=3.0"


class _LegacyBody(BaseModel):
    legacy: str


class _CurrentBody(BaseModel):
    current: int


class TestVersioning(AsyncTestCase):
    def setUp(self) -> None:
        self._app = FastAPI()
        router = APIRouter()

        @router.get("/x", operation_id="get_x_v1", summary="Read X version 1")
        async def get_x_v1() -> dict[str, str]:
            return {"version": "1.0"}

        @router.get("/y")
        async def get_y() -> dict[str, str]:
            return {"version": "1.0"}

        @router.get("/x", operation_id="get_x_v2", summary="Read X version 2")
        @router.set_api_version((2, 0))
        async def get_x_v2() -> dict[str, str]:
            return {"version": "2.0"}

        @router.post("/y", operation_id="post_y")
        async def post_y_v1(body: _LegacyBody) -> _LegacyBody:
            return body

        @router.post("/y", operation_id="post_y")
        @router.set_api_version((2, 0))
        async def post_y_v2(body: _CurrentBody) -> _CurrentBody:
            return body

        # Version 2.0 moves the path parameter into the body.
        @router.put("/z/{name}", operation_id="put_z")
        async def put_z_v1(name: str) -> dict[str, str]:
            return {"name": name}

        @router.put("/z", operation_id="put_z")
        @router.set_api_version((2, 0))
        async def put_z_v2(body: _CurrentBody) -> _CurrentBody:
            return body

        # One version on two paths, for example from a copied operation ID.
        @router.get("/w/a", operation_id="get_w")
        async def get_w_a() -> dict[str, str]:
            return {"path": "a"}

        @router.get("/w/b", operation_id="get_w")
        async def get_w_b() -> dict[str, str]:
            return {"path": "b"}

        self._app.include_router(router)
        init_versioning(self._app, _VENDOR)
        self._client = TestClient(self._app)
        self._client.headers.pop("accept", None)
        self.addCleanup(self._client.close)

    async def test_get_without_version_uses_latest_for_endpoint(self) -> None:
        for path, headers, version, media_type in (
            ("/x", {}, "2.0", _V2),
            ("/x", {"Accept": "*/*"}, "2.0", _V2),
            ("/x", {"Accept": "application/json"}, "2.0", _V2),
            ("/x", {"Accept": _VENDOR}, "2.0", _V2),
            ("/y", {}, "1.0", _V1),
        ):
            with self.subTest(path=path, headers=headers):
                # Act
                response = self._client.get(path, headers=headers)

                # Assert
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"version": version})
                self.assertEqual(response.headers["content-type"], media_type)
                self.assertNotIn("deprecation", response.headers)

    async def test_get_with_available_version_uses_that_version(self) -> None:
        # Act
        response = self._client.get("/x", headers={"Accept": _V1})

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"version": "1.0"})
        self.assertEqual(response.headers["content-type"], _V1)
        self.assertEqual(response.headers["deprecation"], "true")

    async def test_get_with_unavailable_version_lists_available_versions(self) -> None:
        # Act
        response = self._client.get("/x", headers={"Accept": _V3})

        # Assert
        self.assertEqual(response.status_code, 406)
        self.assertEqual(
            response.json(),
            {"detail": "Version 3.0 is not available for this endpoint. Available versions: 1.0, 2.0"},
        )

    async def test_get_with_malformed_vendor_header_returns_bad_request(self) -> None:
        for header, detail in (
            (f"{_VENDOR}; version=invalid", "Version should be in <major>.<minor> format"),
            (f"{_VENDOR}; invalid=1.0", "No version in Accept header"),
        ):
            with self.subTest(header=header):
                # Act
                response = self._client.get("/x", headers={"Accept": header})

                # Assert
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"detail": detail})

    async def test_request_without_path_or_method_match_keeps_routing_error(self) -> None:
        for method, path, status in (("GET", "/missing", 404), ("DELETE", "/x", 405)):
            with self.subTest(method=method, path=path):
                # Act
                response = self._client.request(method, path, headers={"Accept": _V3})

                # Assert
                self.assertEqual(response.status_code, status)

    async def test_post_uses_accept_instead_of_content_type_to_select_version(self) -> None:
        # Act
        response = self._client.post("/y", headers={"Content-Type": _V1}, json={"current": 2})

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"current": 2})
        self.assertEqual(response.headers["content-type"], _V2)

    async def test_openapi_uses_latest_operation_and_orders_versioned_content(self) -> None:
        # Act
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            schema = self._app.openapi()

        # Assert
        self.assertEqual([str(warning.message) for warning in caught], [])
        self.assertEqual(list(schema["paths"]), ["/x", "/y", "/z/{name}", "/z", "/w/a", "/w/b"])
        operation = schema["paths"]["/x"]["get"]
        self.assertEqual(operation["operationId"], "get_x_v2")
        self.assertEqual(operation["summary"], "Read X version 2")
        self.assertIn("**Deprecated versions:** 1.0.", operation["description"])
        self.assertEqual(list(operation["responses"]["200"]["content"]), [_V2, _V1])
        body_content = schema["paths"]["/y"]["post"]["requestBody"]["content"]
        self.assertEqual(list(body_content), [_V2, _V1])
        for media_type, field in ((_V2, "current"), (_V1, "legacy")):
            model = body_content[media_type]["schema"]["$ref"].rsplit("/", 1)[-1]
            self.assertEqual(list(schema["components"]["schemas"][model]["properties"]), [field])

    async def test_version_on_another_path_selects_by_path_and_deprecates_the_older_path(self) -> None:
        for method_path, headers, json, status, body, media_type in (
            ("/z/a", {}, None, 200, {"name": "a"}, _V1),
            ("/z", {}, {"current": 2}, 200, {"current": 2}, _V2),
            ("/z/a", {"Accept": _V2}, None, 406, {"detail": "Version 2.0 of this endpoint uses the path /z"}, None),
            (
                "/z",
                {"Accept": _V1},
                None,
                406,
                {"detail": "Version 1.0 of this endpoint uses the path /z/{name}"},
                None,
            ),
        ):
            with self.subTest(path=method_path, headers=headers):
                # Act
                response = self._client.put(method_path, headers=headers, json=json)

                # Assert
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json(), body)
                if media_type:
                    self.assertEqual(response.headers["content-type"], media_type)
                    self.assertEqual(response.headers.get("deprecation"), "true" if media_type == _V1 else None)

        schema = self._app.openapi()
        latest = schema["paths"]["/z"]["put"]
        older = schema["paths"]["/z/{name}"]["put"]
        self.assertEqual(latest["operationId"], "put_z")
        self.assertIn("**Deprecated versions:** 1.0 (`PUT /z/{name}`).", latest["description"])
        self.assertEqual(older["operationId"], "put_z_v1_0")
        self.assertTrue(older["deprecated"])
        self.assertIn("**Deprecated:** version 2.0 of this endpoint uses `PUT /z`.", older["description"])

    async def test_same_version_on_two_paths_answers_on_each_path(self) -> None:
        for path in ("a", "b"):
            with self.subTest(path=path):
                # Act
                response = self._client.get(f"/w/{path}", headers={"Accept": _V1})

                # Assert
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"path": path})
                self.assertNotIn("deprecation", response.headers)

        schema = self._app.openapi()
        for path in ("/w/a", "/w/b"):
            self.assertNotIn("deprecated", schema["paths"][path]["get"])

    async def test_version_on_another_path_stays_under_its_router_prefix(self) -> None:
        # Arrange
        app = FastAPI()
        router = APIRouter()

        @router.put("/z/{name}", operation_id="put_z")
        async def put_z_v1(name: str) -> dict[str, str]:
            return {"name": name}

        @router.put("/z", operation_id="put_z")
        @router.set_api_version((2, 0))
        async def put_z_v2(body: _CurrentBody) -> _CurrentBody:
            return body

        for prefix in ("/a", "/b"):
            app.include_router(router, prefix=prefix)
        init_versioning(app, _VENDOR)
        client = TestClient(app)
        client.headers.pop("accept", None)
        self.addCleanup(client.close)
        schema = app.openapi()

        for prefix in ("/a", "/b"):
            with self.subTest(prefix=prefix):
                # Act
                older = client.put(f"{prefix}/z/n")
                moved = client.put(f"{prefix}/z/n", headers={"Accept": _V2})

                # Assert
                self.assertEqual(older.json(), {"name": "n"})
                self.assertEqual(older.headers["deprecation"], "true")
                self.assertEqual(moved.status_code, 406)
                self.assertEqual(moved.json(), {"detail": f"Version 2.0 of this endpoint uses the path {prefix}/z"})
                latest = schema["paths"][f"{prefix}/z"]["put"]
                self.assertEqual(latest["operationId"], "put_z")
                self.assertNotIn("deprecated", latest)
                self.assertIn(
                    f"**Deprecated versions:** 1.0 (`PUT {prefix}/z/{{name}}`). Their responses", latest["description"]
                )
                self.assertEqual(schema["paths"][f"{prefix}/z/{{name}}"]["put"]["operationId"], "put_z_v1_0")

    async def test_version_for_one_method_leaves_other_methods_on_older_version(self) -> None:
        # Arrange
        app = FastAPI()
        router = APIRouter()

        @router.api_route("/m", methods=["GET", "POST"], operation_id="read_or_write_m")
        async def m_v1() -> dict[str, str]:
            return {"version": "1.0"}

        @router.get("/m", operation_id="read_m")
        @router.set_api_version((2, 0))
        async def get_m_v2() -> dict[str, str]:
            return {"version": "2.0"}

        app.include_router(router)
        init_versioning(app, _VENDOR)
        client = TestClient(app)
        client.headers.pop("accept", None)
        self.addCleanup(client.close)

        for method, headers, version in (
            ("GET", {}, "2.0"),
            ("GET", {"Accept": _V2}, "2.0"),
            ("GET", {"Accept": _V1}, "1.0"),
            ("POST", {}, "1.0"),
        ):
            with self.subTest(method=method, headers=headers):
                # Act
                response = client.request(method, "/m", headers=headers)

                # Assert
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"version": version})
                deprecated = "true" if method == "GET" and version == "1.0" else None
                self.assertEqual(response.headers.get("deprecation"), deprecated)

        # FastAPI gives each method of one route the same operation ID and warns about it.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            operations = app.openapi()["paths"]["/m"]
        self.assertEqual(operations["get"]["operationId"], "read_m")
        self.assertIn("**Deprecated versions:** 1.0.", operations["get"]["description"])
        self.assertEqual(operations["post"]["operationId"], "read_or_write_m")
        self.assertNotIn("deprecated", operations["post"])

    async def test_mcp_tool_uses_latest_schema_and_route(self) -> None:
        # Arrange
        mcp = fastmcp.FastMCP.from_fastapi(self._app)

        # Act
        async with fastmcp.Client(mcp) as client:
            tool = next(tool for tool in await client.list_tools() if tool.name == "post_y")
            result = await client.call_tool("post_y", {"current": 2})

        # Assert
        self.assertEqual(list(tool.input_schema["properties"]), ["current"])
        self.assertEqual(result.structured_content, {"current": 2})

    async def test_init_versioning_after_extension_reload_keeps_started_app(self) -> None:
        # Arrange
        self.assertEqual(self._client.get("/x").status_code, 200)
        spec = importlib.util.spec_from_file_location("reloaded_versioning", versioning.__file__)
        reloaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reloaded)

        # Act
        reloaded.init_versioning(self._app, _VENDOR)
        response = self._client.get("/x", headers={"Accept": _V1})

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"version": "1.0"})
        self.assertEqual(len(self._app.user_middleware), 1)

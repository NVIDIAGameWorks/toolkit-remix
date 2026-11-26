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
from fastapi import FastAPI, Response
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
        async def get_x_v1(response: Response) -> dict[str, str]:
            response.headers["Vary"] = "Origin, Accept-Encoding"
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

        # Version 2.0 uses a different path and a new request model.
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
            ("/x", {"Accept": f"{_VENDOR}; q=1, {_V1}; q=0.5"}, "2.0", _V2),
            ("/x", {"Accept": f"{_V1}; q=0"}, "2.0", _V2),
            ("/y", {}, "1.0", _V1),
        ):
            with self.subTest(path=path, headers=headers):
                # Act
                response = self._client.get(path, headers=headers)

                # Assert
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"version": version})
                self.assertEqual(response.headers["content-type"], media_type)
                self.assertEqual(response.headers["vary"], "Accept")
                self.assertNotIn("deprecation", response.headers)

    async def test_get_with_available_version_uses_that_version(self) -> None:
        for header in (
            _V1,
            f"application/json;q=0.1, {_V1}",
            f"{_V1}, */*;q=0.1",
            f"{_V2}; q=0.1, {_VENDOR.upper()}; q=1; VERSION=1.0",
            f"{_V1}; q=0.8, {_V2}; q=0.1",
            f"{_V2}; q=0, {_V1}; q=0.1",
            f'{_VENDOR}; profile="a;b,c"; version="1.0"; q=1, {_V2}; q=0.1',
        ):
            with self.subTest(header=header):
                # Act
                response = self._client.get("/x", headers={"Accept": header})

                # Assert
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"version": "1.0"})
                self.assertEqual(response.headers["content-type"], _V1)
                self.assertEqual(response.headers["deprecation"], "true")
                self.assertEqual(response.headers["vary"], "Origin, Accept-Encoding, Accept")

    async def test_get_with_unavailable_version_lists_available_versions(self) -> None:
        # Act
        response = self._client.get("/x", headers={"Accept": _V3})

        # Assert
        self.assertEqual(response.status_code, 406)
        self.assertEqual(response.headers["vary"], "Accept")
        self.assertEqual(
            response.json(),
            {"detail": "Version 3.0 is not available for this endpoint. Available versions: 1.0, 2.0"},
        )

    async def test_get_with_malformed_vendor_header_returns_bad_request(self) -> None:
        for header in (f"{_VENDOR}; version=invalid", f"{_V2}; q=0.1, {_VENDOR}; q=1; version=invalid"):
            with self.subTest(header=header):
                # Act
                response = self._client.get("/x", headers={"Accept": header})

                # Assert
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"detail": "Version should be in <major>.<minor> format"})

    async def test_request_without_path_or_method_match_keeps_routing_error(self) -> None:
        for method, path, status in (("GET", "/missing", 404), ("DELETE", "/x", 405)):
            with self.subTest(method=method, path=path):
                # Act
                response = self._client.request(method, path, headers={"Accept": _V3})

                # Assert
                self.assertEqual(response.status_code, status)

    async def test_post_uses_accept_instead_of_content_type_to_select_version(self) -> None:
        for headers, body, media_type, deprecation in (
            ({"Content-Type": _V1}, {"current": 2}, _V2, None),
            ({"Accept": _V1, "Content-Type": _V2}, {"legacy": "old"}, _V1, "true"),
        ):
            with self.subTest(headers=headers):
                # Act
                response = self._client.post("/y", headers=headers, json=body)

                # Assert
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), body)
                self.assertEqual(response.headers["content-type"], media_type)
                self.assertEqual(response.headers.get("deprecation"), deprecation)

    async def test_openapi_uses_latest_operation_and_orders_versioned_content(self) -> None:
        # Act
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warnings.filterwarnings("ignore", message="Duplicate Operation ID")
            schema = self._app.openapi()

        # Assert
        self.assertEqual([str(warning.message) for warning in caught], [])
        self.assertCountEqual(schema["paths"], ["/x", "/y", "/z/{name}", "/z", "/w/a", "/w/b"])
        operation = schema["paths"]["/x"]["get"]
        self.assertEqual(operation["operationId"], "get_x_v2")
        self.assertEqual(operation["summary"], "Read X version 2")
        self.assertNotIn("**Deprecated versions:**", operation.get("description", ""))
        self.assertEqual(list(operation["responses"]["200"]["content"]), [_V2, _V1])
        operation = schema["paths"]["/y"]["post"]
        for content in (operation["requestBody"]["content"], operation["responses"]["200"]["content"]):
            self.assertEqual(list(content), [_V2, _V1])
            for media_type, field in ((_V2, "current"), (_V1, "legacy")):
                model = content[media_type]["schema"]["$ref"].rsplit("/", 1)[-1]
                self.assertEqual(list(schema["components"]["schemas"][model]["properties"]), [field])

    async def test_openapi_keeps_older_request_body_optional_when_latest_has_none(self) -> None:
        # Arrange
        router = APIRouter()

        @router.post("/body")
        async def post_body_v1(body: _LegacyBody) -> _LegacyBody:
            return body

        @router.post("/body")
        @router.set_api_version((2, 0))
        async def post_body_v2() -> dict[str, int]:
            return {"current": 2}

        self._app.include_router(router)

        # Act
        schema = self._app.openapi()

        # Assert
        body = schema["paths"]["/body"]["post"]["requestBody"]
        self.assertIs(body["required"], False)
        self.assertEqual(list(body["content"]), [_V1])

    async def test_openapi_uses_hidden_first_route_to_group_visible_versions(self) -> None:
        # Arrange
        router = APIRouter()

        @router.get("/old", operation_id="read_item", include_in_schema=False)
        @router.set_api_version((0, 9))
        async def get_hidden_item() -> dict[str, str]:
            return {"version": "0.9"}

        @router.get("/old", operation_id="read_legacy_item")
        async def get_old_item() -> dict[str, str]:
            return {"version": "1.0"}

        @router.get("/new", operation_id="read_item")
        @router.set_api_version((2, 0))
        async def get_new_item() -> dict[str, str]:
            return {"version": "2.0"}

        self._app.include_router(router, prefix="/catalog")

        # Act
        schema = self._app.openapi()

        # Assert
        operation = schema["paths"]["/catalog/old"]["get"]
        self.assertTrue(operation["deprecated"])
        self.assertEqual(operation["operationId"], "read_legacy_item_v1_0")
        self.assertEqual(list(operation["responses"]["200"]["content"]), [_V1])

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
        self.assertNotIn("**Deprecated versions:**", latest.get("description", ""))
        self.assertEqual(older["operationId"], "put_z_v1_0")
        self.assertTrue(older["deprecated"])
        self.assertIn("**Deprecated:** version 2.0 of this endpoint uses `PUT /z`.", older["description"])

    async def test_requested_version_path_wins_over_earlier_path_template(self) -> None:
        # Arrange
        router = APIRouter()

        @router.get("/items/{name}", operation_id="read_item")
        async def get_named_item(name: str) -> dict[str, str]:
            return {"name": name}

        @router.get("/items/current", operation_id="read_item")
        @router.set_api_version((2, 0))
        async def get_current_item() -> dict[str, str]:
            return {"current": "item"}

        self._app.include_router(router)

        # Act
        response = self._client.get("/items/current", headers={"Accept": _V2})

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"current": "item"})
        self.assertEqual(response.headers["content-type"], _V2)

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
                self.assertNotIn("**Deprecated versions:**", latest.get("description", ""))
                self.assertEqual(schema["paths"][f"{prefix}/z/{{name}}"]["put"]["operationId"], "put_z_v1_0")

    async def test_version_for_one_method_leaves_other_methods_on_older_version(self) -> None:
        """GET moves to v2, POST stays on v1, and OpenAPI shows the same split."""
        # Arrange
        app = FastAPI()
        router = APIRouter()

        @router.get("/m", operation_id="read_m")
        @router.set_api_version((2, 0))
        async def get_m_v2() -> dict[str, str]:
            return {"version": "2.0"}

        @router.api_route("/m", methods=["GET", "POST"], operation_id="read_or_write_m")
        async def m_v1() -> dict[str, str]:
            return {"version": "1.0"}

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
            warnings.filterwarnings("ignore", message="Duplicate Operation ID")
            operations = app.openapi()["paths"]["/m"]
        self.assertEqual(operations["get"]["operationId"], "read_m")
        self.assertEqual(list(operations["get"]["responses"]["200"]["content"]), [_V2, _V1])
        self.assertEqual(operations["post"]["operationId"], "read_or_write_m")
        self.assertNotIn("deprecated", operations["post"])
        self.assertEqual(list(operations["post"]["responses"]["200"]["content"]), [_V1])

    async def test_add_api_route_keeps_bound_method_version_at_registration(self) -> None:
        # Arrange
        class Endpoint:
            async def get_version(self) -> dict[str, str]:
                return {"version": "2.0"}

        router = APIRouter()
        endpoint = Endpoint().get_version
        router.set_api_version((2, 0))(endpoint)
        router.add_api_route("/direct", endpoint, methods=["GET"])
        router.set_api_version((3, 0))(endpoint)
        self._app.include_router(router)

        # Act
        response = self._client.get("/direct", headers={"Accept": _V2})

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], _V2)

    async def test_set_api_version_rejects_invalid_versions(self) -> None:
        for invalid_version in ([1, 0], (1,), (1, 0, 0), (1, -1), (1, 0.0), (True, 0)):
            # Act and assert
            with self.subTest(version=invalid_version), self.assertRaises(ValueError):
                APIRouter.set_api_version(invalid_version)

    async def test_mcp_tool_uses_latest_schema_and_route(self) -> None:
        # Arrange
        mcp = fastmcp.FastMCP.from_fastapi(self._app)

        # Act
        async with fastmcp.Client(mcp) as client:
            tool = next(tool for tool in await client.list_tools() if tool.name == "post_y")
            result = await client.call_tool("post_y", {"current": 2})

        # Assert
        self.assertEqual(list(tool.input_schema["properties"]), ["current"])
        self.assertNotIn("**Deprecated versions:**", tool.description or "")
        self.assertEqual(result.structured_content, {"current": 2})

    async def test_init_versioning_after_extension_reload_keeps_started_app(self) -> None:
        # Arrange
        primed = self._app.openapi()["paths"]["/y"]["get"]
        self.assertEqual(list(primed["responses"]["200"]["content"]), [_V1])
        self.assertEqual(self._client.get("/y").status_code, 200)
        spec = importlib.util.spec_from_file_location("reloaded_versioning", versioning.__file__)
        reloaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reloaded)

        # Act
        reloaded.init_versioning(self._app, "application/other+json")
        router = reloaded.VersionedAPIRouter()

        @router.get("/y", operation_id="get_y_v2")
        @router.set_api_version((2, 0))
        async def get_y_v2() -> dict[str, str]:
            return {"version": "2.0"}

        self._app.include_router(router)
        operation = self._app.openapi()["paths"]["/y"]["get"]
        latest = self._client.get("/y", headers={"Accept": _V2})
        older = self._client.get("/y", headers={"Accept": _V1})

        # Assert
        self.assertEqual(operation["operationId"], "get_y_v2")
        self.assertEqual(list(operation["responses"]["200"]["content"]), [_V2, _V1])
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json(), {"version": "2.0"})
        self.assertEqual(latest.headers["content-type"], _V2)
        self.assertEqual(older.status_code, 200)
        self.assertEqual(older.json(), {"version": "1.0"})
        self.assertEqual(older.headers["content-type"], _V1)
        self.assertEqual(older.headers["deprecation"], "true")
        self.assertEqual(len(self._app.user_middleware), 1)

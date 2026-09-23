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

# The real Kit app, the real mounted routers, the real fastmcp conversion. The unit suite checks the
# route maps against synthetic paths; only this file catches one that is internally valid but wrong
# about the app it points at.

import json
from copy import deepcopy

import fastmcp
import omni.kit.test
from fastmcp.exceptions import ClientError
from lightspeed.trex.mcp.core.mcp import _CURATED_ROUTE_MAPS, _compact_tool_descriptions
from omni.services.core import main

# Prefixes a capability serves. A new one is expected and fine; what the tests below assert is that
# the manifest matches the spec, not that this tuple is complete.
_CAPABILITY_PREFIXES = ("/stagecraft/", "/ingestcraft/")

# fastmcp names a tool after the route's operationId, and `mount` prepends the namespace.
_TOOL_NAMESPACE = "remix_"

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "options", "head", "trace"})


def _operation_ids(spec: dict, *, under_capability: bool) -> set[str]:
    """Every operationId the live app declares, split by whether it belongs to a capability."""
    found = set()
    for path, path_item in spec["paths"].items():
        if path.startswith(_CAPABILITY_PREFIXES) is not under_capability:
            continue
        for method, operation in path_item.items():
            if method.lower() in _HTTP_METHODS and "operationId" in operation:
                found.add(operation["operationId"])
    return found


class TestMCPManifest(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        # from_fastapi walks the app's OpenAPI spec, so this is the conversion MCPCore runs at
        # startup, against the routers this test app actually mounted.
        self.spec = main.get_app().openapi()
        self.mcp = fastmcp.FastMCP("test")
        rest_api_mcp = fastmcp.FastMCP.from_fastapi(main.get_app(), route_maps=_CURATED_ROUTE_MAPS)
        self.original_manifest = {
            name: tool.to_mcp_tool().model_dump(mode="json") for name, tool in (await rest_api_mcp.get_tools()).items()
        }
        self.original_spec = deepcopy(self.spec)
        await _compact_tool_descriptions(rest_api_mcp, self.spec)
        self.mcp.mount("remix", rest_api_mcp)

    async def tearDown(self):
        self.mcp = None
        self.spec = None
        self.original_manifest = None
        self.original_spec = None

    async def __tool_operation_ids(self) -> set[str]:
        tools = await self.mcp.get_tools()
        return {name.removeprefix(_TOOL_NAMESPACE) for name in tools}

    async def test_manifest_matches_the_capability_operations_in_the_spec(self):
        # Both directions, derived from the running app: a dropped operation and a leaked one
        # are the same assertion, and neither can be papered over by updating a fixture.
        # Arrange
        expected = _operation_ids(self.spec, under_capability=True)

        # Act
        served = await self.__tool_operation_ids()

        # Assert
        self.assertTrue(expected, "the test app mounted no capability routes to check against")
        self.assertEqual(served, expected)

    async def test_compact_manifest_preserves_tools_and_schemas_with_less_description_text(self):
        """Measure description savings against the real app's unmodified FastMCP manifest."""
        # Compare the advertised tools after the same cleanup and mount used at startup.
        manifest = {
            name.removeprefix(_TOOL_NAMESPACE): tool.to_mcp_tool(name=name.removeprefix(_TOOL_NAMESPACE)).model_dump(
                mode="json"
            )
            for name, tool in (await self.mcp.get_tools()).items()
        }
        before_chars = len(json.dumps(self.original_manifest, sort_keys=True))
        after_chars = len(json.dumps(manifest, sort_keys=True))
        print(f"MCP manifest JSON: {before_chars} -> {after_chars} characters ({before_chars - after_chars} saved)")
        self.assertLess(after_chars, before_chars)
        self.assertEqual(set(manifest), set(self.original_manifest))
        for name, tool in manifest.items():
            original = self.original_manifest[name]
            self.assertLessEqual(len(tool["description"]), len(original["description"]))
            self.assertEqual(
                {key: value for key, value in tool.items() if key != "description"},
                {key: value for key, value in original.items() if key != "description"},
            )
        self.assertEqual(self.spec, self.original_spec)

    async def test_update_ingestion_schema_manifest_exposes_request_fields(self):
        """Advertise required JSON fields and progress without unresolved schema references."""
        async with fastmcp.Client(self.mcp) as client:
            tools = {tool.name: tool for tool in await client.list_tools()}
        schema = tools["remix_update_ingestion_schema"].inputSchema
        self.assertEqual(set(schema["required"]), {"name", "context_plugin", "check_plugins"})
        self.assertIn("progress", schema["properties"])
        self.assertIn("queue_id", schema["properties"])
        self.assertNotIn("#/", json.dumps(schema))

    async def test_update_ingestion_schema_without_body_rejects_call(self):
        """Reject a missing body at the MCP boundary."""
        async with fastmcp.Client(self.mcp) as client:
            with self.assertRaisesRegex(ClientError, "required property"):
                await client.call_tool("remix_update_ingestion_schema", {"queue_id": "mcp-body-regression"})

    async def test_no_operation_outside_a_capability_reaches_the_manifest(self):
        # Same guarantee as above, stated so the failure names the leak. These are the transport's
        # health, readiness and asyncapi endpoints: useless to a model, and their arrival is silent.
        # Arrange
        outside = _operation_ids(self.spec, under_capability=False)

        # Act
        served = await self.__tool_operation_ids()

        # Assert
        self.assertEqual(served & outside, set())

    async def test_read_operations_are_tools_rather_than_resources(self):
        # fastmcp appends its own defaults after ours, and those classify a bare GET as a RESOURCE.
        # A deny-list missing the trailing TOOL catch-all passes every route-map unit test while
        # quietly serving the read half of the API as something a model cannot call.
        # Arrange
        reads = {
            operation["operationId"]
            for path, path_item in self.spec["paths"].items()
            if path.startswith(_CAPABILITY_PREFIXES)
            for method, operation in path_item.items()
            if method.lower() == "get" and "operationId" in operation
        }

        # Act
        served = await self.__tool_operation_ids()

        # Assert
        self.assertTrue(reads, "the test app mounted no GET routes to check against")
        self.assertEqual(reads - served, set(), "GET operations missing from the tool manifest")

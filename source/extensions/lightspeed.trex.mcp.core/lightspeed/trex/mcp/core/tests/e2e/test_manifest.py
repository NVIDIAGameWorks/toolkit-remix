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
import re
from copy import deepcopy

import fastmcp
import omni.kit.test
from fastmcp.exceptions import ToolError
from lightspeed.trex.mcp.core.mcp import _CURATED_ROUTE_MAPS, _describe_tool
from omni.flux.utils.tests.context_managers import open_test_project
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
        self.original_spec = deepcopy(self.spec)
        plain = fastmcp.FastMCP.from_fastapi(main.get_app(), route_maps=_CURATED_ROUTE_MAPS)
        self.original_manifest = {
            tool.name: tool.to_mcp_tool().model_dump(mode="json") for tool in await plain.list_tools()
        }
        rest_api_mcp = fastmcp.FastMCP.from_fastapi(
            main.get_app(), route_maps=_CURATED_ROUTE_MAPS, mcp_component_fn=_describe_tool
        )
        self.mcp = fastmcp.FastMCP("test")
        self.mcp.mount(rest_api_mcp, namespace="remix")

    async def tearDown(self):
        self.mcp = None
        self.spec = None
        self.original_manifest = None
        self.original_spec = None

    async def __tool_operation_ids(self) -> set[str]:
        return {tool.name.removeprefix(_TOOL_NAMESPACE) for tool in await self.mcp.list_tools()}

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

    async def test_described_manifest_changes_only_descriptions(self):
        """Keep every tool and schema fastmcp builds from the real app; only extend the descriptions."""
        manifest = {
            name: tool.to_mcp_tool(name=name).model_dump(mode="json")
            for tool in await self.mcp.list_tools()
            for name in (tool.name.removeprefix(_TOOL_NAMESPACE),)
        }
        before_chars = len(json.dumps(self.original_manifest, sort_keys=True))
        after_chars = len(json.dumps(manifest, sort_keys=True))
        print(f"MCP manifest JSON: {before_chars} -> {after_chars} characters ({after_chars - before_chars} added)")
        self.assertEqual(set(manifest), set(self.original_manifest))
        for name, tool in manifest.items():
            original = self.original_manifest[name]
            self.assertTrue(tool["description"].startswith(original["description"]), name)
            self.assertEqual(
                {key: value for key, value in tool.items() if key != "description"},
                {key: value for key, value in original.items() if key != "description"},
            )
        self.assertEqual(self.spec, self.original_spec)

    async def test_update_ingestion_schema_manifest_exposes_request_fields(self):
        """Advertise required JSON fields and progress without unresolved schema references."""
        async with fastmcp.Client(self.mcp) as client:
            tools = {tool.name: tool for tool in await client.list_tools()}
        schema = tools["remix_update_ingestion_schema"].input_schema
        self.assertEqual(set(schema["required"]), {"name", "context_plugin", "check_plugins"})
        self.assertIn("progress", schema["properties"])
        self.assertIn("queue_id", schema["properties"])
        self.assertNotIn("#/", json.dumps(schema))

    async def test_every_tool_schema_resolves_its_own_refs(self):
        """Keep every `$ref` inside the tool schema that uses it (GitHub rtx-remix#1097)."""
        # llama.cpp rejects the whole tool list over one unresolvable ref, and the MCP client fails any call to a
        # tool whose output schema has one.
        async with fastmcp.Client(self.mcp) as client:
            tools = await client.list_tools()
        dangling = {
            f"{tool.name}: {ref}"
            for tool in tools
            for schema in (tool.input_schema, tool.output_schema or {})
            for ref in re.findall(r'"\$ref": "([^"]*)"', json.dumps(schema))
            if ref.removeprefix("#/$defs/") not in schema.get("$defs", {})
        }
        self.assertEqual(dangling, set())

    async def test_get_layers_ignores_unknown_arguments_and_matches_the_output_schema(self):
        """Return a real layer stack through a client that checks results against `outputSchema`."""
        # The MCP client fails the call when the result does not match the output schema or the schema has a
        # `$ref` it cannot resolve. Only a non-empty stack reaches the layer schema. The unknown argument must be
        # dropped quietly: a warning goes to stderr, which Kit reports as `[Error]` and fails this run over.
        # Arrange
        async with open_test_project("usd/project_example/combined.usda", ext_name="lightspeed.trex.app.resources"):
            # Act
            async with fastmcp.Client(self.mcp) as client:
                result = await client.call_tool("remix_get_layers", {"unknown_argument": True})

        # Assert
        self.assertTrue(result.structured_content["layers"])

    async def test_update_ingestion_schema_without_body_rejects_call(self):
        """Reject a missing body and report the service's validation failure to the client."""
        async with fastmcp.Client(self.mcp) as client:
            with self.assertRaisesRegex(ToolError, "422"):
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
        # A model cannot call a resource, so every capability GET must be served as a tool.
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

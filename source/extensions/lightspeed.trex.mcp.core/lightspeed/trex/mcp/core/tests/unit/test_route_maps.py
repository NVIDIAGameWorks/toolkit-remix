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

__all__ = ("TestCuratedRouteMaps",)

from types import SimpleNamespace

import fastmcp.server.openapi as fastmcp_openapi
import omni.kit.test

from lightspeed.trex.mcp.core.mcp import _CURATED_ROUTE_MAPS


class TestCuratedRouteMaps(omni.kit.test.AsyncTestCase):
    # What is left here is what a booted app cannot show: paths no extension in this build
    # serves. The positive cases moved to tests/e2e/test_manifest.py, which asserts against the
    # real manifest instead of synthetic routes.
    """Verify the curated route_maps filter the MCP tool surface correctly.

    Uses fastmcp's private `_determine_route_type` helper to test the effective classification
    end to end. If that helper disappears in a future fastmcp release these tests fail fast.
    """

    def __classify(self, method: str, path: str):
        route = SimpleNamespace(method=method, path=path)
        return fastmcp_openapi._determine_route_type(route, _CURATED_ROUTE_MAPS)

    async def test_unregistered_route_prefixes_become_tools(self):
        # The point of the deny-list: a new prefix reaches the manifest with no edit here. GET is
        # the case that matters — fastmcp's defaults send it to RESOURCE, so this also pins that
        # the TOOL catch-all is still doing its job.
        cases = [
            ("GET", "/agentic/lights"),
            ("POST", "/agentic/lights"),
            ("DELETE", "/agentic/lights/some/prim/path"),
            ("GET", "/some-future-surface/thing"),
        ]
        for method, path in cases:
            with self.subTest(title=f"{method} {path}"):
                # Arrange / Act
                route_type = self.__classify(method, path)

                # Assert
                self.assertEqual(route_type, fastmcp_openapi.RouteType.TOOL)

    async def test_root_level_ui_automation_routes_are_ignored(self):
        # These belonged to an automation extension that no longer ships. Pinned so a regression
        # that re-introduces them cannot leak UI-driving endpoints into the tool manifest.
        cases = [
            ("GET", "/find_element/"),
            ("GET", "/find_elements/"),
            ("GET", "/widget_properties/"),
            ("GET", "/windows/"),
            ("GET", "/window_dimensions/"),
            ("GET", "/automation_sample_status/"),
            ("POST", "/click/"),
            ("POST", "/send_keys/"),
            ("POST", "/drag_and_drop/"),
            ("POST", "/scroll_frame/"),
            ("POST", "/click_at/"),
            ("POST", "/set_color_widget/"),
            ("POST", "/toggle_checkbox/"),
            ("POST", "/set_widget_value/"),
        ]
        for method, path in cases:
            with self.subTest(title=f"{method} {path}"):
                # Arrange / Act
                route_type = self.__classify(method, path)

                # Assert
                self.assertEqual(route_type, fastmcp_openapi.RouteType.IGNORE)

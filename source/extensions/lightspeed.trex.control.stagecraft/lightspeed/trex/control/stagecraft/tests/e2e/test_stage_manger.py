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

import tempfile
from enum import Enum
from pathlib import Path
from unittest.mock import patch

import omni.kit.app
import omni.usd as usd
from lightspeed.common.constants import LayoutFiles as _LayoutFiles
from lightspeed.common.constants import WindowNames as _WindowNames
from lightspeed.trex.properties_pane.widget import AssetReplacementsPane as _AssetReplacementsPane
from lightspeed.trex.utils.widget.quicklayout import load_layout
from omni.flux.utils.widget.resources import get_quicklayout_config as _get_quicklayout_config
from omni.flux.utils.widget.resources import get_test_data as _get_test_data
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from omni.kit.test_suite.helpers import open_stage


class TestPages(Enum):
    HOME_PAGE = "HomePage"
    WORKSPACE_PAGE = "WorkspacePage"


class TestStageManagerPropertiesInteraction(AsyncTestCase):
    async def setUp(self):
        # get a test usd path in a temporary dir to make sure anything saved is cleaned up
        self._temp_dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self._temp_path = (Path(self._temp_dir.name) / "test.usda").as_posix()

        # open something so that context can be set as dirty
        await open_stage(_get_test_data("usd/project_example/combined.usda"))

    # After running each test
    async def tearDown(self):
        self._temp_dir = None

    async def test_material_properties_update_stage_manager_should_not_refresh(self):
        usd_context = usd.get_context()
        usd_context.get_selection().set_selected_prim_paths(["/RootNode/meshes/mesh_0AB745B8BEE1F16B/mesh"], False)

        # Open up the workspace, so we can test the stage manager
        load_layout(_get_quicklayout_config(_LayoutFiles.WORKSPACE_PAGE))
        await ui_test.human_delay(10)

        layers_panel = ui_test.find(f"{_WindowNames.PROPERTIES}//Frame/**/Label[*].text=='LAYERS'")
        self.assertIsNotNone(layers_panel)
        await layers_panel.click()
        await ui_test.human_delay()

        property_branches = ui_test.find_all(
            f"{_WindowNames.PROPERTIES}//Frame/**/Image[*].identifier=='property_branch'"
        )
        await property_branches[0].click()
        await ui_test.human_delay(10)

        widget_refs = omni.kit.ui_test.find_all(f"{_WindowNames.PROPERTIES}//Frame/**/FloatDrag[*]")
        widget_ref = widget_refs[0]

        with patch.object(_AssetReplacementsPane, "refresh") as mock:
            drag_vector = widget_ref.center
            drag_vector.x = drag_vector.x - 400
            await omni.kit.ui_test.human_delay(30)
            await omni.kit.ui_test.emulate_mouse_drag_and_drop(widget_ref.center, drag_vector)
            await omni.kit.ui_test.wait_n_updates(2)

            self.assertEqual(0, mock.call_count)

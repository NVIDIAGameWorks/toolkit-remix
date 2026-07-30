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

import tempfile
from pathlib import Path

import carb.settings
import omni.usd
from lightspeed.trex.contexts.setup import Contexts as _Contexts
from omni.kit.test import AsyncTestCase
from omni.kit.viewport.menubar.lighting.actions import _set_lighting_mode

_LIGHTING_EXTENSION_ID = "omni.kit.viewport.menubar.lighting"
_LIGHT_RIG_PRIM_PATH = "/OmniKit_Viewport_LightRig"
_RIGS_SETTING = f"/exts/{_LIGHTING_EXTENSION_ID}/rigs"


class TestLightingRigSwap(AsyncTestCase):
    async def setUp(self):
        self._settings = carb.settings.get_settings()
        self._original_rigs = self._settings.get(_RIGS_SETTING)
        self._usd_context = omni.usd.get_context(_Contexts.STAGE_CRAFT.value)
        await self._usd_context.new_stage_async()

    async def tearDown(self):
        self._settings.set(_RIGS_SETTING, self._original_rigs)
        await self._usd_context.close_stage_async()

    async def test_set_lighting_mode_rig_invalid_usd_file_raises_without_authoring_reference(self):
        # Arrange
        stage = self._usd_context.get_stage()
        self.assertIsNotNone(stage)
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_rig_path = Path(temp_dir) / "invalid_rig.usda"
            invalid_rig_path.write_text("not a valid usd file", encoding="utf-8")
            self._settings.set(_RIGS_SETTING, temp_dir)

            # Act
            with self.assertRaisesRegex(RuntimeError, "Invalid light rig USD file"):
                _set_lighting_mode("Invalid Rig", usd_context=self._usd_context)

            # Assert
            light_rig_prim = stage.GetPrimAtPath(_LIGHT_RIG_PRIM_PATH)
            if light_rig_prim.IsValid():
                self.assertNotIn(str(invalid_rig_path), str(light_rig_prim.GetMetadata("references")))
